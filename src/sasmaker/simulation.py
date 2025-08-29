# sasmaker/simulation.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Optional
import pandas as pd

# Types
EventFn   = Callable[["Substation"], None]
SamplerFn = Callable[["Substation"], Dict[str, Any]]

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

    

    def at(self, t: float, fn: EventFn, label: str = "") -> None:
        """Schedule an event at exact time t (before solve)."""
        self.events.append(TimedEvent(float(t), fn, label))
        self.events.sort(key=lambda e: e.t)

    def add_sampler(self, sampler: SamplerFn) -> None:
        """Register a sampler that returns a dict of scalar values."""
        self.samplers.append(sampler)

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

            # 2) apply load variation if enabled
            if self.vary_loads:
                for ld in s.loads.values():
                    ld.profile(ld.base_p, ld.base_q, t)   # or ld.vary(...) if using jitter
                    # you'd need to store base_p/base_q in Load when you construct it
                    
            # apply all events scheduled for this step
            for ev in ev_idx.get(key, []):
                ev.fn(s)


            # solve network
            s.run_powerflow()

            # tick all IEDs (may operate CBs, etc.)
            for ied in s.ieds.values():
                ied.tick()

            # sample outputs
            rec: Dict[str, Any] = {"t": t}
            for smp in self.samplers:
                rec.update(smp(s))
            rows.append(rec)

            t = round(t + self.dt, 9)

            # if an IED opened something this step, that affects next step's solve

        return pd.DataFrame(rows)

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

# --- Handy event helpers -------------------------------------------------

def evt_open_cb(cb_name: str) -> EventFn:
    return lambda s: s.cbs[cb_name].open()

def evt_close_cb(cb_name: str) -> EventFn:
    return lambda s: s.cbs[cb_name].close()

def evt_set_load(load_name: str, p_mw: float, q_mvar: float) -> EventFn:
    def _fn(s: "Substation"):
        s.loads[load_name].set_power(p_mw, q_mvar)
    return _fn
