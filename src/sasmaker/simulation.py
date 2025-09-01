# sasmaker/simulation.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Optional
import pandas as pd

from .util import replace_nan_with_zero
# Types
EventFn   = Callable[["Substation"], None]
SamplerFn = Callable[["Substation"], Dict[str, Any]]
StepHook = Callable[["Substation", float], None]

# --- Events --------------------------------------------------------------

@dataclass(order=True)
class TimedEvent:
    t: float
    fn: EventFn
    label: str = ""

# --- Simulation ----------------------------------------------------------

@dataclass
class Simulation:
    """
    Minimal discrete-time simulation:
      - apply events at t_k
      - run powerflow
      - tick all IEDs (protection/controls)
      - sample outputs into one row per step
    """
    name: str
    t_end: float
    dt: float = 0.1
    events: List[TimedEvent] = field(default_factory=list)
    samplers: List[SamplerFn] = field(default_factory=list)
    vary_loads: bool = False
    step_hooks: list[StepHook] = field(default_factory=list)

    

    def at(self, t: float, fn: EventFn, label: str = "") -> None:
        """Schedule an event at exact time t (before solve)."""
        self.events.append(TimedEvent(float(t), fn, label))
        self.events.sort(key=lambda e: e.t)

    def add_sampler(self, sampler: SamplerFn) -> None:
        """Register a sampler that returns a dict of scalar values."""
        self.samplers.append(sampler)
    
    def add_step_hook(self, hook: StepHook) -> None:
        self.step_hooks.append(hook)

    def run(self, s: "Substation") -> pd.DataFrame:
        # index events by time for O(1) lookup
        ev_idx: Dict[float, List[TimedEvent]] = {}
        for ev in self.events:
            key = round(ev.t, 9)
            ev_idx.setdefault(key, []).append(ev)

        rows: List[Dict[str, Any]] = []
        t = 0.0
        while t <= self.t_end + 1e-12:
            key = round(t, 9)

            # 1) apply load variation if enabled
            if self.vary_loads:
                for ld in s.loads.values():
                    ld.profile(ld.base_p, ld.base_q, t)   # or ld.vary(...) if using jitter
                    # you'd need to store base_p/base_q in Load when you construct it

            # 1.5) per-step hooks (e.g., persistent injections)
            for hook in self.step_hooks:
                hook(s, t)

            # 2) apply all events scheduled for this step
            for ev in ev_idx.get(key, []):
                ev.fn(s)


            # 3) solve network
            s.run_powerflow()

            # 4) tick all IEDs (may operate CBs, etc.)
            for ied in s.ieds.values():
                ied.tick()

            # 5) sample outputs
            rec: Dict[str, Any] = {"t": t}
            for smp in self.samplers:
                rec.update(smp(s))
            rows.append(rec)

            t = round(t + self.dt, 9)

            # if an IED opened something this step, that affects next step's solve

        return replace_nan_with_zero(pd.DataFrame(rows))

# --- Ready-made samplers -------------------------------------------------

def sample_cts() -> SamplerFn:
    """All CT primary currents (kA) as flat scalars."""
    def _fn(s: "Substation") -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name, ct in s.cts.items():
            vals = ct.read_primary_current()
            out[f"ct:{name}:Ia_ka"] = vals["Ia"]
            out[f"ct:{name}:Ib_ka"] = vals["Ib"]
            out[f"ct:{name}:Ic_ka"] = vals["Ic"]
        return out
    return _fn

def sample_lines(line_names: List[str]) -> SamplerFn:
    """Per-phase from/to currents for selected lines (uses res_line_3ph)."""
    def _fn(s: "Substation") -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if not hasattr(s.net, "res_line_3ph"):
            return out
        for nm in line_names:
            lid = s.lines[nm].idx
            row = s.net.res_line_3ph.loc[lid]
            for col in row.index:
                if col.startswith("i_"):  # i_a_from_ka, i_b_to_ka, etc.
                    out[f"line:{nm}:{col}"] = float(row[col])
        return out
    return _fn

def sample_buses(bus_names: List[str]) -> SamplerFn:
    """Per-phase voltages for selected buses (uses res_bus_3ph)."""
    def _fn(s: "Substation") -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if not hasattr(s.net, "res_bus_3ph"):
            return out
        for nm in bus_names:
            bid = s.busbars[nm].idx
            row = s.net.res_bus_3ph.loc[bid]
            for col in row.index:
                if col.startswith("vm_") or col.startswith("va_"):
                    out[f"bus:{nm}:{col}"] = float(row[col])
        return out
    return _fn

def sample_cbs() -> SamplerFn:
    def _fn(s: "Substation") -> Dict[str, Any]:
        out = {}
        for nm, cb in s.cbs.items():
            out[f"cb:{nm}:closed"] = bool(cb.closed)
        return out
    return _fn

# --- Handy event helpers -------------------------------------------------

def evt_open_cb(cb_name: str) -> EventFn:
    return lambda s: s.cbs[cb_name].open()

def evt_close_cb(cb_name: str) -> EventFn:
    return lambda s: s.cbs[cb_name].close()

def evt_set_load(load_name: str, p_mw: float, q_mvar: float) -> EventFn:
    def _fn(s: "Substation"):
        s.loads[load_name].set_power(p_mw, q_mvar)
    return _fn


# --- Overcurrent injection by scaling downstream loads -------------------

def _busname_to_idx_map(substation) -> dict:
    net = substation.net
    return {str(net.bus.at[i, "name"]): int(i) for i in net.bus.index}

def _loads_on_buses(substation, bus_names):
    name2idx = _busname_to_idx_map(substation)
    targets = {name2idx[n] for n in bus_names if n in name2idx}
    for ld in substation.loads.values():
        if getattr(ld, "bus_idx", None) in targets:
            yield ld

def inject_overcurrent_on_buses(sim: "Simulation", *,
                                t0: float, duration: float,
                                bus_names: list[str], factor: float = 2.0):
    """
    Exogenous 'overcurrent' by scaling all loads connected to given buses:
    P,Q := factor * P,Q during [t0, t0+duration].

    - No changes to Load class required.
    - We store/restore per-load original (P,Q) using a private attribute.
    """
    def on(s: "Substation"):
        for ld in _loads_on_buses(s, bus_names):
            # remember original once
            if not hasattr(ld, "_oc_prev"):
                # try to read current setpoints from pp table using ld.idx
                # Works for asymmetric_loads we created; adjust if you use another element.
                row = s.net.asymmetric_load.loc[ld.idx]
                p0 = float(row["p_a_mw"] + row["p_b_mw"] + row["p_c_mw"])
                q0 = float(row["q_a_mvar"] + row["q_b_mvar"] + row["q_c_mvar"])
                ld._oc_prev = (p0, q0)
            # scale *current* setpoints
            p_prev, q_prev = ld._oc_prev
            p_new = p_prev * float(factor)
            q_new = q_prev * float(factor)
            # distribute equally per phase (your minimal load used equal-per-phase)
            s.net.asymmetric_load.at[ld.idx, "p_a_mw"] = p_new / 3.0
            s.net.asymmetric_load.at[ld.idx, "p_b_mw"] = p_new / 3.0
            s.net.asymmetric_load.at[ld.idx, "p_c_mw"] = p_new / 3.0
            s.net.asymmetric_load.at[ld.idx, "q_a_mvar"] = q_new / 3.0
            s.net.asymmetric_load.at[ld.idx, "q_b_mvar"] = q_new / 3.0
            s.net.asymmetric_load.at[ld.idx, "q_c_mvar"] = q_new / 3.0

    def off(s: "Substation"):
        for ld in _loads_on_buses(s, bus_names):
            if hasattr(ld, "_oc_prev"):
                p0, q0 = ld._oc_prev
                # restore
                s.net.asymmetric_load.at[ld.idx, "p_a_mw"] = p0 / 3.0
                s.net.asymmetric_load.at[ld.idx, "p_b_mw"] = p0 / 3.0
                s.net.asymmetric_load.at[ld.idx, "p_c_mw"] = p0 / 3.0
                s.net.asymmetric_load.at[ld.idx, "q_a_mvar"] = q0 / 3.0
                s.net.asymmetric_load.at[ld.idx, "q_b_mvar"] = q0 / 3.0
                s.net.asymmetric_load.at[ld.idx, "q_c_mvar"] = q0 / 3.0
                delattr(ld, "_oc_prev")

    sim.at(t0, on,  label=f"OC_on[{','.join(bus_names)}]x{factor}")
    sim.at(t0 + max(duration, 0.0), off, label=f"OC_off[{','.join(bus_names)}]")

def inject_overcurrent_on_line_to_bus(sim: "Simulation", *,
                                      t0: float, duration: float,
                                      line_name: str, factor: float = 2.0):
    """
    Persistently scale loads on the 'to_bus' of the given line during [t0, t0+duration).
    Works even if vary_loads=True (profiles overwrite each step); we reapply after profiles.
    """

    def _to_bus_idx_and_name(s: "Substation") -> tuple[int, str]:
        ln = s.lines[line_name]
        tbl = s.net.line_3ph if hasattr(s.net, "line_3ph") else s.net.line
        to_idx = int(tbl.at[ln.idx, "to_bus"])
        return to_idx, str(s.net.bus.at[to_idx, "name"])

    # Keep a small cache of original totals to restore if vary_loads=False
    state = {"armed": False, "bus_idx": None, "saved": {}}

    def _hook(s: "Substation", t: float):
        t1 = t0 + max(duration, 0.0)
        # lazy-resolve target bus once
        if state["bus_idx"] is None:
            state["bus_idx"], _ = _to_bus_idx_and_name(s)

        active = (t >= t0 - 1e-12) and (t < t1 - 1e-12)

        if active:
            # Apply scaling after profile each step.
            for ld in s.loads.values():
                if getattr(ld, "bus_idx", None) != state["bus_idx"]:
                    continue
                # save original only once (for restore when vary_loads=False)
                if not state["armed"]:
                    row = s.net.asymmetric_load.loc[ld.idx]
                    p0 = float(row["p_a_mw"] + row["p_b_mw"] + row["p_c_mw"])
                    q0 = float(row["q_a_mvar"] + row["q_b_mvar"] + row["q_c_mvar"])
                    state["saved"][ld.idx] = (p0, q0)
                # read current (post-profile) setpoints, then overwrite with scaled base if we saved it,
                # else just multiply current values (safe when vary_loads=True)
                if ld.idx in state["saved"]:
                    p0, q0 = state["saved"][ld.idx]
                    p = p0 * float(factor)
                    q = q0 * float(factor)
                    s.net.asymmetric_load.at[ld.idx, "p_a_mw"] = p / 3.0
                    s.net.asymmetric_load.at[ld.idx, "p_b_mw"] = p / 3.0
                    s.net.asymmetric_load.at[ld.idx, "p_c_mw"] = p / 3.0
                    s.net.asymmetric_load.at[ld.idx, "q_a_mvar"] = q / 3.0
                    s.net.asymmetric_load.at[ld.idx, "q_b_mvar"] = q / 3.0
                    s.net.asymmetric_load.at[ld.idx, "q_c_mvar"] = q / 3.0
                else:
                    # fallback: multiply current values
                    row = s.net.asymmetric_load.loc[ld.idx]
                    for col in ("p_a_mw","p_b_mw","p_c_mw"):
                        s.net.asymmetric_load.at[ld.idx, col] = float(row[col]) * float(factor)
                    for col in ("q_a_mvar","q_b_mvar","q_c_mvar"):
                        s.net.asymmetric_load.at[ld.idx, col] = float(row[col]) * float(factor)

            state["armed"] = True

        elif state["armed"]:
            # Window ended → restore from saved (if we have it), else do nothing.
            for ld in s.loads.values():
                if getattr(ld, "bus_idx", None) != state["bus_idx"]:
                    continue
                if ld.idx in state["saved"]:
                    p0, q0 = state["saved"][ld.idx]
                    s.net.asymmetric_load.at[ld.idx, "p_a_mw"] = p0 / 3.0
                    s.net.asymmetric_load.at[ld.idx, "p_b_mw"] = p0 / 3.0
                    s.net.asymmetric_load.at[ld.idx, "p_c_mw"] = p0 / 3.0
                    s.net.asymmetric_load.at[ld.idx, "q_a_mvar"] = q0 / 3.0
                    s.net.asymmetric_load.at[ld.idx, "q_b_mvar"] = q0 / 3.0
                    s.net.asymmetric_load.at[ld.idx, "q_c_mvar"] = q0 / 3.0
            state["armed"] = False
            state["saved"].clear()

    sim.add_step_hook(_hook)
