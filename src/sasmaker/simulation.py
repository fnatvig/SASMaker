# sasmaker/simulation.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Literal, Tuple
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
                # if col.startswith("vm_") or col.startswith("va_"):
                if col.startswith("vm_"):
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

def sample_ieds() -> SamplerFn:
    """All CT primary currents (kA) as flat scalars."""
    def _fn(s: "Substation") -> Dict[str, Any]:
        out: Dict[str, Any] = {}

        for name, ied in s.ieds.items():
            val = ied.ptrc.trip
            out[f"ied:{name}:protection_tripped"] = val

        for name, ct in s.cts.items():

            # CTs
            vals = ct.read_primary_current()
            vals_pwr = ct.read_power_flow()
            out[f"ct:{name}:Ia_ka"] = vals["Ia"]
            out[f"ct:{name}:Ib_ka"] = vals["Ib"]
            out[f"ct:{name}:Ic_ka"] = vals["Ic"]
            out[f"ct:{name}:Pa_mw"] = vals_pwr["Pa"]
            out[f"ct:{name}:Pb_mw"] = vals_pwr["Pb"]
            out[f"ct:{name}:Pc_mw"] = vals_pwr["Pc"]
            out[f"ct:{name}:Qa_mvar"] = vals_pwr["Qa"]
            out[f"ct:{name}:Qb_mvar"] = vals_pwr["Qb"]
            out[f"ct:{name}:Qc_mvar"] = vals_pwr["Qc"]

            # Bus
            nm = ct.get_bus_name()
            bid = s.busbars[nm].idx
            vn_kv = s.busbars[nm].vn_kv
            row = s.net.res_bus_3ph.loc[bid]
            ph_id = 0
            for col in row.index:
                # if col.startswith("vm_") or col.startswith("va_"):
                ph = ["a","b","c"]
                if col.startswith("vm_"):
                    out[f"bus:{ct.get_bus_name()}:vm_{ph[ph_id]}_kv"] = float(row[col])*vn_kv
                    ph_id+=1
            
            # CBs
        for nm, cb in s.cbs.items():
            out[f"cb:{nm}:closed"] = bool(cb.closed)


        for name, vt in s.vts.items():

            # VTs
            vals = vt.read_voltage()
            vn_kv = s.busbars[vt.get_bus_name()].vn_kv
            out[f"vt:{vt.get_bus_name()}:vm_a_kv"] = float(vals["Va"])*vn_kv
            out[f"vt:{vt.get_bus_name()}:vm_b_kv"] = float(vals["Vb"])*vn_kv
            out[f"vt:{vt.get_bus_name()}:vm_c_kv"] = (vals["Vc"])*vn_kv
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

def trigger_busbar_protection(sim: "Simulation",
                              ied_name: str,
                              busbar_name: str,
                              t0: float) -> None:
    """
    IED-centric busbar protection with one-step communication delay.

    We snap t0 to the simulation grid so that:
      - main event runs at step k
      - peer event runs at step k+1
    """

    # Snap t0 to the nearest simulation step index
    step0 = round(t0 / sim.dt)
    t_main = round(step0 * sim.dt, 9)
    t_peers = round((step0 + 1) * sim.dt, 9)

    def _trip_main_ied(s: "Substation"):
        if ied_name not in s.ieds:
            raise KeyError(f"IED {ied_name!r} not found in substation.")
        main_ied = s.ieds[ied_name]
        if getattr(main_ied, "bb", None) != busbar_name:
            raise ValueError(
                f"IED {ied_name!r} is on busbar {main_ied.bb!r}, "
                f"not {busbar_name!r}"
            )
        if getattr(main_ied, "ptrc", None) is not None:
            main_ied.ptrc.set_trip(True)

    def _trip_peer_ieds(s: "Substation"):
        for nm, ied in s.ieds.items():
            if getattr(ied, "bb", None) != busbar_name:
                continue
            if getattr(ied, "ptrc", None) is not None:
                ied.ptrc.set_trip(True)
            if getattr(ied, "xcbr", None) is not None:
                ied.xcbr.open()

    sim.at(t_main, _trip_main_ied,
           label=f"BBAR_main[{busbar_name}] via {ied_name}")
    sim.at(t_peers, _trip_peer_ieds,
           label=f"BBAR_peers[{busbar_name}] via {ied_name}")

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
    """
    def on(s: "Substation"):
        for ld in _loads_on_buses(s, bus_names):
            # remember original once
            if not hasattr(ld, "_oc_prev"):
                # try to read current setpoints from pp table using ld.idx
                row = s.net.asymmetric_load.loc[ld.idx]
                p0 = float(row["p_a_mw"] + row["p_b_mw"] + row["p_c_mw"])
                q0 = float(row["q_a_mvar"] + row["q_b_mvar"] + row["q_c_mvar"])
                ld._oc_prev = (p0, q0)
            # scale *current* setpoints
            p_prev, q_prev = ld._oc_prev
            p_new = p_prev * float(factor)
            q_new = q_prev * float(factor)
            # distribute equally per phase
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
    Works even if vary_loads=True (profiles overwrite each step)
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

def inject_overcurrent_on_tx_side(sim: "Simulation", *,
                                  t0: float, duration: float,
                                  tx_name: str,
                                  side: Literal["hv","lv"] = "lv",
                                  factor: float = 2.0,
                                  debug: bool = True):
    """
    Scale loads connected to the HV/LV bus of transformer `tx_name` in [t0, t0+duration).
    If that side has no loads, attach a temporary 3φ load on the *opposite* side bus to
    force power across the transformer. Restores everything afterward.
    """
    import pandapower as pp

    # ---------------- helpers ----------------
    def _tx_indices_and_buses(s: "Substation") -> Tuple[int, int, int, str, str]:
        # Resolve transformer index and its hv/lv bus indices + names
        tx_obj = None
        for attr in ("transformers", "txs", "trafos"):
            d = getattr(s, attr, None)
            if isinstance(d, dict) and tx_name in d:
                tx_obj = d[tx_name]; break
        if tx_obj is not None and hasattr(tx_obj, "idx"):
            tx_idx = int(tx_obj.idx)
        else:
            hits = s.net.trafo.index[s.net.trafo["name"] == tx_name]
            if len(hits) == 0:
                raise ValueError(f"Transformer named {tx_name!r} not found.")
            if len(hits) > 1:
                raise ValueError(f"Multiple transformers named {tx_name!r}; use unique names.")
            tx_idx = int(hits[0])

        row = s.net.trafo.loc[tx_idx]
        hv = int(row["hv_bus"]); lv = int(row["lv_bus"])
        hvn = str(s.net.bus.at[hv, "name"]); lvn = str(s.net.bus.at[lv, "name"])
        return tx_idx, hv, lv, hvn, lvn

    def _rows_on_bus(s: "Substation", bidx: int):
        al = getattr(s.net, "asymmetric_load", None)
        if al is None or len(al) == 0:
            return []
        return list(al.index[al["bus"] == int(bidx)])

    def _snapshot_wrapper_loads_on(s: "Substation", bidx: int):
        saved = {}
        for ld in getattr(s, "loads", {}).values():
            if getattr(ld, "bus_idx", None) == int(bidx):
                r = s.net.asymmetric_load.loc[ld.idx]
                p0 = float(r["p_a_mw"] + r["p_b_mw"] + r["p_c_mw"])
                q0 = float(r["q_a_mvar"] + r["q_b_mvar"] + r["q_c_mvar"])
                saved[int(ld.idx)] = (p0, q0)
        return saved

    def _delta_p_from_res(s: "Substation", tx_idx: int) -> float:
        # Try using res_trafo at activation step; fallback to 1 MW if absent
        res = getattr(s.net, "res_trafo", None)
        if res is None or tx_idx not in getattr(res, "index", []):
            return max(factor - 1.0, 0.0) * 1.0
        try:
            p_side = float(res.at[tx_idx, "p_hv_mw"] if side == "hv" else res.at[tx_idx, "p_lv_mw"])
            return max(factor - 1.0, 0.0) * max(abs(p_side), 1e-3)
        except Exception:
            return max(factor - 1.0, 0.0) * 1.0

    # ---------------- state ----------------
    state = {
        "armed": False,
        "tx_idx": None,
        "bus_target": None, "bus_other": None,
        "name_target": "", "name_other": "",
        "saved": {},                 # wrapper loads on target side
        "temp_aload_idx": None,      # idx of created temp load (if any)
        "temp_side": None,           # "target" or "other"
    }

    # ---------------- hook ----------------
    def _hook(s: "Substation", t: float):
        t1 = t0 + max(duration, 0.0)
        active = (t >= t0 - 1e-12) and (t < t1 - 1e-12)

        # Resolve once
        if state["tx_idx"] is None:
            tx_idx, hv, lv, hvn, lvn = _tx_indices_and_buses(s)
            state["tx_idx"] = tx_idx
            if side == "hv":
                state["bus_target"], state["bus_other"] = hv, lv
                state["name_target"], state["name_other"] = hvn, lvn
            else:
                state["bus_target"], state["bus_other"] = lv, hv
                state["name_target"], state["name_other"] = lvn, hvn
            if debug:
                print(f"[TX-OCC] target=TX:{tx_name} side={side} "
                      f"target_bus={state['bus_target']} ({state['name_target']}), "
                      f"other_bus={state['bus_other']} ({state['name_other']}), "
                      f"factor={factor}, window=[{t0},{t1})")

        if debug:
            print(f"[TX-OCC] t={t:.6f} active={active}")

        if active:
            if not state["armed"]:
                # 1) Try to scale wrapper loads on the *target* bus
                state["saved"] = _snapshot_wrapper_loads_on(s, state["bus_target"])
                n_wrap = len(state["saved"])
                # 2) Detect whether there are ANY asym loads on that bus at all
                has_any = len(_rows_on_bus(s, state["bus_target"])) > 0
                if debug:
                    print(f"[TX-OCC] target_bus has wrapper_matched={n_wrap}, any_asym={has_any}")

                # 3) If no loads exist on the *target* side, create a temp load on the *other* side
                if not has_any and state["temp_aload_idx"] is None:
                    dp = _delta_p_from_res(s, state["tx_idx"])
                    if dp > 0.0:
                        idx = pp.create_asymmetric_load(
                            s.net, bus=int(state["bus_other"]),
                            p_a_mw=dp/3.0, p_b_mw=dp/3.0, p_c_mw=dp/3.0,
                            q_a_mvar=0.0,  q_b_mvar=0.0,  q_c_mvar=0.0,
                            name=f"__occ_tx_{tx_name}_{side}_otherbus"
                        )
                        try:
                            state["temp_aload_idx"] = int(idx)
                        except Exception:
                            state["temp_aload_idx"] = None
                        state["temp_side"] = "other"
                        if debug:
                            print(f"[TX-OCC] created temp load idx={state['temp_aload_idx']} "
                                  f"on OTHER side bus={state['bus_other']} ({state['name_other']}) "
                                  f"ΔP≈{dp:.6f} MW")

            # Reapply scaling each step for wrapper loads on target side
            if state["saved"]:
                for idx, (p0, q0) in state["saved"].items():
                    p = p0 * float(factor); q = q0 * float(factor)
                    s.net.asymmetric_load.at[idx, "p_a_mw"]   = p / 3.0
                    s.net.asymmetric_load.at[idx, "p_b_mw"]   = p / 3.0
                    s.net.asymmetric_load.at[idx, "p_c_mw"]   = p / 3.0
                    s.net.asymmetric_load.at[idx, "q_a_mvar"] = q / 3.0
                    s.net.asymmetric_load.at[idx, "q_b_mvar"] = q / 3.0
                    s.net.asymmetric_load.at[idx, "q_c_mvar"] = q / 3.0
                if debug:
                    Psum = sum(p for p,_ in state["saved"].values()); Qsum = sum(q for _,q in state["saved"].values())
                    print(f"[TX-OCC] scaled target-side wrapper loads: n={len(state['saved'])} "
                          f"baseP={Psum:.6f} baseQ={Qsum:.6f}")

            state["armed"] = True

        elif state["armed"]:
            # Restore wrapper loads on target side
            if state["saved"]:
                for idx, (p0, q0) in state["saved"].items():
                    s.net.asymmetric_load.at[idx, "p_a_mw"]   = p0 / 3.0
                    s.net.asymmetric_load.at[idx, "p_b_mw"]   = p0 / 3.0
                    s.net.asymmetric_load.at[idx, "p_c_mw"]   = p0 / 3.0
                    s.net.asymmetric_load.at[idx, "q_a_mvar"] = q0 / 3.0
                    s.net.asymmetric_load.at[idx, "q_b_mvar"] = q0 / 3.0
                    s.net.asymmetric_load.at[idx, "q_c_mvar"] = q0 / 3.0
                if debug:
                    print(f"[TX-OCC] restored {len(state['saved'])} target-side wrapper loads")
                state["saved"].clear()

            # Remove temp load if one was created
            if state["temp_aload_idx"] is not None:
                if state["temp_aload_idx"] in getattr(s.net, "asymmetric_load", getattr(sim, "EMPTY", [])):
                    pp.drop_elements(s.net, "asymmetric_load", [state["temp_aload_idx"]])
                if debug:
                    print(f"[TX-OCC] removed temp load idx={state['temp_aload_idx']} (side={state['temp_side']})")
                state["temp_aload_idx"] = None
                state["temp_side"] = None

            if debug:
                print("[TX-OCC] window ended")
            state["armed"] = False

    sim.add_step_hook(_hook)


