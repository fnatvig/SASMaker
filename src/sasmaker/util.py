# sasmaker/util.py
import os
import atexit
import signal
import shutil
import sys
import subprocess
import time
import pandas as pd
import numpy as np
from pathlib import Path



BUS_REF_COLS = {"bus", "from_bus", "to_bus", "hv_bus", "lv_bus"}


def _fix_ref_cols(df, name):
    if df is None or df.empty:
        return
    # cast any bus reference columns to int64 (no floats allowed)
    for c in set(df.columns) & BUS_REF_COLS:
        if df[c].dtype != "int64":
            df[c] = pd.to_numeric(df[c], errors="raise").astype("int64")
        if df[c].isna().any():
            raise ValueError(f"NaN in {name}.{c}")
    # element references (e.g., switch.element) must be int64 too
    if "element" in df.columns and df["element"].dtype != "int64":
        df["element"] = pd.to_numeric(df["element"], errors="raise").astype("int64")
    # in_service must be bool
    if "in_service" in df.columns and df["in_service"].dtype != bool:
        df["in_service"] = df["in_service"].astype(bool)

def sanitize_net_3ph(net):
    # bus index int64, in_service bool
    if not net.bus.empty:
        if net.bus.index.dtype != "int64":
            net.bus.index = pd.to_numeric(net.bus.index, errors="raise").astype("int64")
        if "in_service" in net.bus and net.bus["in_service"].dtype != bool:
            net.bus["in_service"] = net.bus["in_service"].astype(bool)

    # scan common 3-phase tables
    for name in ("line_3ph","line","ext_grid_3ph","ext_grid",
                 "load_3ph","load","shunt_3ph","shunt",
                 "trafo_3ph","trafo","switch","impedance"):
        df = getattr(net, name, None)
        if df is not None:
            _fix_ref_cols(df, name)

def replace_nan_with_zero(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of df where all NaN/inf values are replaced with 0.0.
    """
    clean = df.copy()
    clean = clean.replace([pd.NA, float("nan"), float("inf"), -float("inf")], 0.0)
    clean = clean.fillna(0.0)
    return clean

def generate_values_df(df, ied):
    col_headers = [
        "Circuit breaker Open/Close Status",
        "Disconnector Open/Close Status",
        "Protection system healthy (Trip circuit healthy)",
        "Control level - Local or remote",
        "Protection tripped",
        "Circuit breaker mechanical failure",
        "Auxiliary power failure",
        "Intertrip command send",
        "Intertrip command receive",
        "Current Line 'L1'",
        "Current Line 'L2'",
        "Current Line 'L3'",
        "Voltage Phase 'L1-N'",
        "Voltage Phase 'L2-N'",
        "Voltage Phase 'L3-N'",
        "Active Power",
        "Reactive power",
        "Frequency",
        "Power Factor",
    ]

    df_new = pd.DataFrame(index=df.index)

    # --- Helper: stable PF (hold last valid) ---
    def hold_last_valid(series: pd.Series, valid_mask: pd.Series, default=0.0):
        out = series.copy()
        out[~valid_mask] = np.nan
        out = out.ffill().fillna(default)
        return out

    # --- If the IED has no CT, assume it still publishes voltages + freq ---
    if ied.ct is None:
        voltage_a = df[f"vt:{ied.bb}:vm_a_kv"] * 1000 / np.sqrt(3)
        voltage_b = df[f"vt:{ied.bb}:vm_b_kv"] * 1000 / np.sqrt(3)
        voltage_c = df[f"vt:{ied.bb}:vm_c_kv"] * 1000 / np.sqrt(3)

        # Fill ALL columns to avoid shape surprises (choose sane defaults)
        df_new[col_headers[0]] = 1
        df_new[col_headers[1]] = 1
        df_new[col_headers[2]] = 1
        df_new[col_headers[3]] = "FALSE"
        df_new[col_headers[4]] = "FALSE"
        df_new[col_headers[5]] = "FALSE"
        df_new[col_headers[6]] = "FALSE"
        df_new[col_headers[7]] = "FALSE"
        df_new[col_headers[8]] = "FALSE"
        df_new[col_headers[9]]  = voltage_a.astype("int32")
        df_new[col_headers[10]] = voltage_b.astype("int32")
        df_new[col_headers[11]] = voltage_c.astype("int32")
        df_new[col_headers[12]] = voltage_a.astype("int32")
        df_new[col_headers[13]] = voltage_b.astype("int32")
        df_new[col_headers[14]] = voltage_c.astype("int32")
        df_new[col_headers[15]] = 0
        df_new[col_headers[16]] = 0
        df_new[col_headers[17]] = 50.0
        df_new[col_headers[18]] = 0.0
        return df_new

    # --- Normal IED with CT/CB ---
    ied_trip = df[f"ied:{ied.name}:protection_tripped"].astype(bool)
    cb_closed = df[f"cb:{ied.cb}:closed"].astype(bool)

    # currents (kA -> A)
    current_a = (df[f"ct:{ied.ct}:Ia_ka"] * 1000).astype("int32")
    current_b = (df[f"ct:{ied.ct}:Ib_ka"] * 1000).astype("int32")
    current_c = (df[f"ct:{ied.ct}:Ic_ka"] * 1000).astype("int32")

    # voltages (kV -> V phase-to-neutral)
    voltage_a = (df[f"bus:{ied.bb}:vm_a_kv"] * 1000 / np.sqrt(3)).astype("int32")
    voltage_b = (df[f"bus:{ied.bb}:vm_b_kv"] * 1000 / np.sqrt(3)).astype("int32")
    voltage_c = (df[f"bus:{ied.bb}:vm_c_kv"] * 1000 / np.sqrt(3)).astype("int32")

    # power (MW/MVAr -> W/var)
    Pa = df[f"ct:{ied.ct}:Pa_mw"]
    Pb = df[f"ct:{ied.ct}:Pb_mw"]
    Pc = df[f"ct:{ied.ct}:Pc_mw"]
    Qa = df[f"ct:{ied.ct}:Qa_mvar"]
    Qb = df[f"ct:{ied.ct}:Qb_mvar"]
    Qc = df[f"ct:{ied.ct}:Qc_mvar"]

    P = (Pa + Pb + Pc) * 1_000_000
    Q = (Qa + Qb + Qc) * 1_000_000
    S = np.hypot(P, Q)

    # PF: magnitude-based; hold last valid when S ~ 0 (post-trip)
    pf_raw = (P.abs() / S).replace([np.inf, -np.inf], np.nan)
    valid = S > 1e-6
    pf = hold_last_valid(pf_raw, valid_mask=valid, default=0.0).clip(0.0, 1.0)
    pf = np.round(pf, 2)

    # --- Fill columns (keep your TRUE/FALSE style where you used it) ---
    df_new[col_headers[0]] = cb_closed.astype("int32")               # 1=closed 0=open
    df_new[col_headers[1]] = 1
    df_new[col_headers[2]] = 1
    df_new[col_headers[3]] = "FALSE"
    df_new[col_headers[4]] = ["TRUE" if x else "FALSE" for x in ied_trip]
    df_new[col_headers[5]] = "FALSE"
    df_new[col_headers[6]] = "FALSE"
    df_new[col_headers[7]] = "FALSE"
    df_new[col_headers[8]] = "FALSE"

    df_new[col_headers[9]]  = current_a
    df_new[col_headers[10]] = current_b
    df_new[col_headers[11]] = current_c

    df_new[col_headers[12]] = voltage_a
    df_new[col_headers[13]] = voltage_b
    df_new[col_headers[14]] = voltage_c

    df_new[col_headers[15]] = P.astype("int32")     # keep sign; change to abs(...) if you insist
    df_new[col_headers[16]] = Q.astype("int32")

    df_new[col_headers[17]] = 50.0                  # FIX: never 0
    df_new[col_headers[18]] = list(pf)

    return df_new

def generate_values_df_old(df, ied):
    col_headers = ["Circuit breaker Open/Close Status", 
            "Disconnector Open/Close Status", 
            # "Earth switch Open/Close Status", 
            "Protection system healthy (Trip circuit healthy)", 
            "Control level - Local or remote", 
            "Protection tripped", 
            "Circuit breaker mechanical failure", 
            "Auxiliary power failure", 
            "Intertrip command send", 
            "Intertrip command receive", 
            "Current Line 'L1'", 
            "Current Line 'L2'", 
            "Current Line 'L3'", 
            "Voltage Phase 'L1-N'", 
            "Voltage Phase 'L2-N'", 
            "Voltage Phase 'L3-N'", 
            "Active Power", 
            "Reactive power", 
            "Frequency", 
            "Power Factor"]
    
    if ied.ct == None:
        voltage_a = df[f"vt:{ied.bb}:vm_a_kv"]*1000/np.sqrt(3)
        voltage_b = df[f"vt:{ied.bb}:vm_b_kv"]*1000/np.sqrt(3)
        voltage_c = df[f"vt:{ied.bb}:vm_c_kv"]*1000/np.sqrt(3)

        df_new = pd.DataFrame()
        df_new[col_headers[6]] = len(df)*["FALSE"]
        df_new[col_headers[9]] = list(voltage_a.astype('int32'))
        df_new[col_headers[10]] = list(voltage_b.astype('int32'))
        df_new[col_headers[11]] = list(voltage_c.astype('int32'))
        df_new[col_headers[17]] = len(df)*[50.0] 
        return df_new
    else:
        ied_trip = df[f"ied:{ied.name}:protection_tripped"].astype('int32')
        cb_status = df[f"cb:{ied.cb}:closed"].astype('int32')
        cb_tripped = list(cb_status.eq(0))

        current_a = df[f"ct:{ied.ct}:Ia_ka"]*1000 
        current_b = df[f"ct:{ied.ct}:Ib_ka"]*1000
        current_c = df[f"ct:{ied.ct}:Ic_ka"]*1000
        
        voltage_a = df[f"bus:{ied.bb}:vm_a_kv"]*1000/np.sqrt(3)
        voltage_b = df[f"bus:{ied.bb}:vm_b_kv"]*1000/np.sqrt(3)
        voltage_c = df[f"bus:{ied.bb}:vm_c_kv"]*1000/np.sqrt(3)

        P = (df[f"ct:{ied.ct}:Pa_mw"] + df[f"ct:{ied.ct}:Pb_mw"] + df[f"ct:{ied.ct}:Pa_mw"])*1000000
        Q = (df[f"ct:{ied.ct}:Qa_mvar"] + df[f"ct:{ied.ct}:Qb_mvar"] + df[f"ct:{ied.ct}:Qa_mvar"])*1000000
        S = np.hypot(P, Q)

        pf = (P.abs() / S).fillna(0.0)
        df_new = pd.DataFrame()

        df_new[col_headers[0]] = list(cb_status)
        df_new[col_headers[1]] = len(df)*[1]

        df_new[col_headers[2]] = len(df)*[1]
        df_new[col_headers[3]] = len(df)*["FALSE"]

        df_new[col_headers[4]] = ["TRUE" if i else "FALSE" for i in ied_trip]

        df_new[col_headers[5]] = len(df)*[1]
        df_new[col_headers[6]] = len(df)*["FALSE"]

        df_new[col_headers[7]] = ["TRUE" if i else "FALSE" for i in cb_tripped]
        df_new[col_headers[8]] = len(df)*["FALSE"]
        
        # currents
        df_new[col_headers[9]] = list(current_a.astype('int32'))
        df_new[col_headers[10]] = list(current_b.astype('int32'))
        df_new[col_headers[11]] = list(current_c.astype('int32'))

        # voltages
        df_new[col_headers[12]] = list(voltage_a.astype('int32'))
        df_new[col_headers[13]] = list(voltage_b.astype('int32'))
        df_new[col_headers[14]] = list(voltage_c.astype('int32'))

        # powers
        df_new[col_headers[15]] = list(abs(P.astype('int32')))
        df_new[col_headers[16]] = list(abs(Q.astype('int32')))
        
        # frequency
        df_new[col_headers[17]] = [50.0 if i!=0 else 0 for i in list(P.astype('int32'))] 

        # power factor
        df_new[col_headers[18]] = list(np.round(pf, decimals=2))

        return df_new

def _cleanup_interfaces(numIEDs: int):
    helper = "/usr/local/libexec/sasmaker-network"
    if Path(helper).is_file():
        subprocess.run(
            ["sudo", "-n", helper, "cleanup", str(numIEDs)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

def _signal_handler(sig, frame, numIEDs):
    _cleanup_interfaces(numIEDs)
    sys.exit(0)

def create_interfaces(ieds):
    print("SASMaker v1.0")
    print("Interfaces Setup")
    helper = Path("/usr/local/libexec/sasmaker-network")
    if not helper.is_file():
        raise RuntimeError(
            "SASMaker networking is not installed. Run "
            "'sudo ./scripts/install_workshop_networking.sh' from the repository root."
        )

    try:
        subprocess.run(
            ["sudo", "-n", str(helper), "create", str(len(ieds))],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown error").strip()
        raise RuntimeError(f"Could not create SASMaker interfaces: {detail}") from exc

    for index, ied in enumerate(ieds, start=1):
        mac = f"A2:2E:D6:80:A8:{(index * 11) & 0xFF:02X}"
        print(f"Created veth1.{index} for {ied.name} ({mac})")

def spawn_script(cwd=None, python=None, py_paths=None, args=None):
    script = "toolchain.py"
    python = python or sys.executable
    argv = [python, script]

    if args:
        argv.extend(args)

    env = os.environ.copy()
    if py_paths:
        env["PYTHONPATH"] = os.pathsep.join(py_paths)

    p = subprocess.Popen(argv, cwd=cwd, env=env)
    print(f"Spawned {script} (pid={p.pid}) from {cwd or os.getcwd()} with args {args or []}")
    return p


def _stop_process(process, timeout=5):
    """Stop a subprocess and give it a chance to finalize its output."""
    if process is None or process.poll() is not None:
        return

    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def capture_to_pcap(
    ieds,
    duration,
    output,
    toolchain_directory="toolchain",
    interface="veth1",
    startup_timeout=5,
):
    """Run the existing GOOSE publishers and capture their traffic to a PCAP.

    The per-IED ``value.csv`` files must already exist in ``toolchain_directory``.
    This function owns the virtual interfaces for the duration of the run and
    removes them before returning, including when publishing or capture fails.
    """
    ieds = list(ieds)
    if not ieds:
        raise ValueError("At least one IED is required")
    if duration <= 0:
        raise ValueError("duration must be greater than zero")

    dumpcap = shutil.which("dumpcap")
    if dumpcap is None:
        raise RuntimeError(
            "dumpcap was not found. Install Wireshark/dumpcap before exporting PCAP files."
        )

    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Output file already exists: {output}")

    toolchain_directory = Path(toolchain_directory).resolve()
    if not (toolchain_directory / "toolchain.py").is_file():
        raise FileNotFoundError(
            f"toolchain.py was not found in {toolchain_directory}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    capture_process = None
    publisher_process = None
    try:
        create_interfaces(ieds)

        capture_process = subprocess.Popen(
            [dumpcap, "-q", "-F", "pcap", "-i", interface, "-w", str(output)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )

        deadline = time.monotonic() + startup_timeout
        while not output.exists() and capture_process.poll() is None:
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out while starting packet capture")
            time.sleep(0.05)

        if capture_process.poll() is not None:
            error = capture_process.stderr.read().strip()
            raise RuntimeError(f"dumpcap could not start: {error or 'unknown error'}")

        publisher_arguments = [ied.name for ied in ieds] + [str(duration)]
        publisher_process = spawn_script(
            cwd=toolchain_directory,
            py_paths=[str(toolchain_directory)],
            args=publisher_arguments,
        )
        try:
            return_code = publisher_process.wait(timeout=duration + startup_timeout + 5)
        except subprocess.TimeoutExpired as exc:
            _stop_process(publisher_process)
            raise RuntimeError("GOOSE publishers did not finish in time") from exc

        if return_code != 0:
            raise RuntimeError(f"GOOSE publishers exited with status {return_code}")

        if capture_process.poll() is not None:
            error = capture_process.stderr.read().strip()
            raise RuntimeError(
                f"dumpcap stopped before publishing completed: {error or 'unknown error'}"
            )
    finally:
        _stop_process(capture_process)
        _cleanup_interfaces(len(ieds))

    if not output.is_file() or output.stat().st_size <= 24:
        raise RuntimeError(f"No packet data was written to {output}")

    return output
