# sasmaker/util.py
import pandas as pd
import numpy as np

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

    # scan common 3φ tables
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
    col_headers = ["Circuit breaker Open/Close Status", 
            "Disconnector Open/Close Status", 
            "Earth switch Open/Close Status", 
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
    df_new[col_headers[2]] = len(df)*[0]
    df_new[col_headers[3]] = len(df)*[1]
    df_new[col_headers[4]] = len(df)*[False]
    df_new[col_headers[5]] = cb_tripped
    df_new[col_headers[6]] = len(df)*[1]
    df_new[col_headers[7]] = len(df)*[False]
    df_new[col_headers[8]] = cb_tripped
    df_new[col_headers[9]] = len(df)*[False]
    
    # currents
    df_new[col_headers[10]] = list(current_a.astype('int32'))
    df_new[col_headers[11]] = list(current_b.astype('int32'))
    df_new[col_headers[12]] = list(current_c.astype('int32'))

    # voltages
    df_new[col_headers[13]] = list(voltage_a.astype('int32'))
    df_new[col_headers[14]] = list(voltage_b.astype('int32'))
    df_new[col_headers[15]] = list(voltage_c.astype('int32'))

    # powers
    df_new[col_headers[16]] = list(P.astype('int32'))
    df_new[col_headers[17]] = list(Q.astype('int32'))
    
    # frequency
    df_new[col_headers[18]] = [50.0 if i!=0 else 0 for i in list(P.astype('int32'))] 

    # power factor
    df_new[col_headers[19]] = list(np.round(pf, decimals=2))

    
    return df_new