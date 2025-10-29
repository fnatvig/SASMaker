import pandapower as pp
from typing import Literal

from .busbar import Busbar
from .line import Line
from .buslink import BusLink
from .load import Load
from .remotess import RemoteSS
from .ct import CT
from .vt import VT
from .cb import CB
from .ied import IED
from .tx import TX
from .util import sanitize_net_3ph

def _dump_nan_refs(net):
    import pandas as pd
    tables = ("ext_grid_3ph","ext_grid","line_3ph","line","load_3ph","load",
            "switch","trafo_3ph","trafo","impedance","shunt_3ph","shunt")
    ref_cols = {"bus","from_bus","to_bus","hv_bus","lv_bus","element"}

    for t in tables:
        df = getattr(net, t, None)
        if df is None or df.empty:
            continue
        cols = [c for c in df.columns if c in ref_cols]
        if not cols:
            continue
        bad = pd.DataFrame({c: df[c].isna() for c in cols})
        mask = bad.any(axis=1)
        if mask.any():
            print(f"\n[NaN refs] table={t} rows={list(df.index[mask])}")
            print(df.loc[mask, cols].to_string())
            # helpful context if available
            name_cols = [c for c in ("name","element_type") if c in df.columns]
            if name_cols:
                print(df.loc[mask, name_cols].to_string())

class Substation:
    """Owns the pandapower net + created objects."""
    def __init__(self, name: str):
        self.name = name
        self.net = pp.create_empty_network()
        self.busbars: dict[str, Busbar] = {}
        self.lines: dict[str, Line] = {}
        self.buslinks: dict[str, BusLink] = {}  
        self.ext_grids: dict[str, int] = {}
        self.loads: dict[str, Load] = {}
        self.cts: dict[str, CT] = {}
        self.vts: dict[str, VT] = {}
        self.cbs: dict[str, CB] = {}
        self.ieds: dict[str, IED] = {}
        self.txs: dict[str, TX] = {}
        self.three_phase = True


    # ----- creation helpers -----
    def add_busbar(self,
                name: str,
                vn_kv: float,
                x: float = 0.0,
                y: float = 0.0,
                draw_length: float | None = None,
                draw_thickness: float | None = None,
                draw_slots: int | None = None,
                ext_grid: bool = False,
                draw_label: bool = True):
        bb = Busbar(name, self.net, vn_kv, x, y,
                    draw_length=draw_length,
                    draw_thickness=draw_thickness,
                    draw_slots=draw_slots, ext_grid=ext_grid,
                    draw_label = draw_label)
        self.busbars[name] = bb
        return bb

    def add_line(self, name: str, from_busbar: Busbar, to_busbar: Busbar,
                length_km: float, *, std_type: str | None = None, 
                c_nf_per_km: float = 8.0, c0_nf_per_km: float = 5.0) -> Line:
        """
        Add a line between two busbars.
        Uses reasonable 3φ defaults if std_type is not given.
        """
        if std_type is not None:
            ln = Line(name=name, net=self.net,
                    from_bus_idx=from_busbar.idx, to_bus_idx=to_busbar.idx,
                    length_km=length_km, std_type=std_type)
        else:
            ln = Line(
                name=name, net=self.net,
                from_bus_idx=from_busbar.idx, to_bus_idx=to_busbar.idx,
                length_km=length_km,
                r_ohm_per_km=0.12, x_ohm_per_km=0.38, c_nf_per_km=c_nf_per_km, max_i_ka=1.0,
                r0_ohm_per_km=0.36, x0_ohm_per_km=1.14, c0_nf_per_km=c0_nf_per_km
            )
        self.lines[name] = ln
        return ln
    
    def add_ext_grid_with_th(self, name, at_busbar, vm_pu=1.0, va_degree=0.0,
                            i_limit=350, x_r=10, vn_kv=66.0):
        # compute Thevenin impedance magnitude
        import math
        z_abs = vn_kv * 1e3 / (math.sqrt(3) * i_limit)
        R = z_abs / math.sqrt(1 + x_r**2)
        X = R * x_r

        # create buses
        b_grid = at_busbar.idx
        b_int = pp.create_bus(self.net, vn_kv=vn_kv, name=f"{name}_INT")

        # slack source
        pp.create_ext_grid(
            self.net, at_busbar.idx,
            vm_pu=1.02, va_degree=0.0, name=name, in_service=True,
            s_sc_max_mva=300.0, s_sc_min_mva=300.0,   # ~350 A at 66 kV
            rx_max=0.1, rx_min=0.1,                 # R/X = 0.1  (X/R ~ 10)
            r0x0_max=0.4, x0x_max=1.0               # keep your zero-seq guesses if needed
        )

        # replace the impedance with a short 3φ line having the same R/X
        length_km = 0.001
        pp.create_line_from_parameters(
            self.net, from_bus=b_grid, to_bus=b_int, length_km=length_km,
            r_ohm_per_km=R/length_km, x_ohm_per_km=X/length_km, c_nf_per_km=0.0,
            r0_ohm_per_km=R/length_km, x0_ohm_per_km=X/length_km, c0_nf_per_km=0.0,
            max_i_ka=10.0, name="UPSTREAM_Zth_line"
        )

        return b_int
    
    def add_ext_grid(self, name: str, at_busbar: Busbar,
                 vm_pu: float = 1.0, va_degree: float = 0.0,
                 in_service: bool = True, s_sc_max_mva: float = 50000,
                 s_sc_min_mva: float = 10000) -> int:
        """Create an external grid with sane defaults for 3φ studies."""
        eg_idx = pp.create_ext_grid(
            self.net, at_busbar.idx,
            vm_pu=vm_pu, va_degree=va_degree, in_service=in_service, name=name,
            s_sc_max_mva=s_sc_max_mva, s_sc_min_mva=s_sc_min_mva,
            rx_max=0.1, rx_min=0.1,
            r0x0_max=0.4, x0x_max=1.0
        )
        self.ext_grids[name] = eg_idx
        return eg_idx
    
    def add_load(self, name: str, busbar, p_mw: float, q_mvar: float, draw_label: bool = True):
        ld = Load(name, self.net, busbar.idx, p_mw, q_mvar, draw_label=draw_label)
        self.loads[name] = ld
        return ld
    
    def add_remote_ss(self, name: str, busbar, p_mw: float, q_mvar: float,
                        draw_label: bool = True, **remote_kwargs):
        """
        Create a 'load-like' remote substation equivalent at a 66 kV bus.
        remote_kwargs: vm_pu, s_sc_mva, xr, tie_len_km, r0_factor, x0_factor,
                    c_nf_per_km, c0_nf_per_km
        """
        ld = RemoteSS(name, self.net, busbar.idx, p_mw, q_mvar,
                            draw_label=draw_label, **remote_kwargs)
        # store it right alongside normal loads so plotting works unchanged
        self.loads[name] = ld
        return ld
    
    def add_transformer_auto(self, name, hv_bus, lv_bus, *, sn_mva=25.0, in_service=True,
                            register_if_missing=True, defaults=None):
        tx = TX(name).attach_auto(self.net, hv_bus=hv_bus, lv_bus=lv_bus,
                                sn_mva=sn_mva, in_service=in_service,
                                register_if_missing=register_if_missing,
                                defaults=defaults)
        self.txs[name] = tx
        return tx

    def add_ct_tx(self, name: str, tx, *, side: str):
        """
        Add a CT on a transformer endpoint.
        Args:
            name: CT name
            tx: TX wrapper (with .idx) or pp.trafo index (int)
            side: 'hv' or 'lv'
        """
        from .ct import CT  # keep local to avoid circulars
        tidx = int(getattr(tx, "idx", tx))
        ct = CT(name).attach_tx(self.net, tidx, side)
        self.cts[name] = ct
        return ct
    
    def add_cb_tx(self, name: str, tx, *, side: str, closed: bool = True):
        """
        Add a CB on a transformer endpoint (pp.switch et='t').
        Args:
            name: CB name
            tx: TX wrapper (with .idx) or pp.trafo index (int)
            side: 'hv' or 'lv'
            closed: initial state
        """
        from .cb import CB
        tidx = int(getattr(tx, "idx", tx))
        cb = CB(name)
        cb.attach_tx(self.net, tidx, side, closed=closed)
        self.cbs[name] = cb
        return cb

    def add_ct(self, name: str, line, side: str) -> CT:
        """
        Create a CT on a given Line endpoint.
        Usage: s.add_ct("CT1", line_obj, side="from")
        """
        ct = CT(name)
        ct.attach_line(self.net, line_id=line.idx, side=side)
        self.cts[name] = ct
        return ct
    
    def add_vt(self, name: str, line, side: str, ied=None, link_buses=None) -> VT:
        """
        Create a VT on a given line endpoint and bind it to an IED.
        Optionally fan-out to additional buses for the UFIED-style drawing.
        Example:
            s.add_vt("VT-UFIED", cb200_line, "to", ied="UFIED",
                    link_buses=[bus_lv1, bus_lv2])
        """
        vt = VT(name).attach_line(self.net, line_id=line.idx, side=side,
                                ied=ied, link_buses=link_buses)
        ied.bb = vt.get_bus_name()
        self.vts[name] = vt
        return vt
    
    def add_cb(self, name: str, line, side: str, *, closed: bool = True) -> CB:
        cb = CB(name)
        cb.attach_line(self.net, line_id=line.idx, side=side, closed=closed)
        self.cbs[name] = cb
        return cb
    
    def add_ied(self, name: str, *, ct=None, cb=None) -> IED:
        ied = IED(name, ct=ct, cb=cb)

        self.ieds[name] = ied
        return ied
    
    def add_buslink(self, name: str, bus_a, bus_b, *, closed: bool = True) -> BusLink:
        """
        Create and register a bus-bus link (pp.switch et='b').
        Returns the BusLink wrapper so it can be passed to add_cb_buslink(...).
        """
        a = int(getattr(bus_a, "idx", bus_a))
        b = int(getattr(bus_b, "idx", bus_b))
        bl = BusLink(name, self.net, a, b, closed=closed)
        self.buslinks[name] = bl          # your plotter already iterates self.buslinks
        return bl
    
    def add_cb_buslink(self, name: str, buslink: BusLink | int, *, closed: bool | None = None) -> CB:
        """
        Wrap an existing bus-bus switch (et='b') with a CB so it appears in plotting
        and can be controlled by an IED. 'buslink' can be the BusLink object or its
        pp.switch index.
        """
        cb = CB(name).attach_buslink(self.net, buslink, closed=closed)
        self.cbs[name] = cb               # <-- critical: put it in cbs so plotting draws it
        return cb
    
    def add_ct_buslink(self, name: str, buslink: BusLink | int, *, side: Literal["from", "to"]) -> CT:
        """
        Add a CT on a bus coupler implemented as a *short 3-φ line*.

        Accepts:
        - the BusLink object (preferred), or
        - a raw line index (int) if you know it.

        NOTE: legacy switch-backed buslinks (pp.switch et='b') are NOT supported for CTs.
        """
        # Resolve the underlying line index
        if hasattr(buslink, "line_idx"):                   # new line-backed BusLink
            line_idx = int(buslink.line_idx)
        elif isinstance(buslink, int) and buslink in self.net.line.index:  # a raw line index
            line_idx = int(buslink)
        else:
            raise NotImplementedError(
                "add_ct_buslink requires a line-backed BusLink (with .line_idx) "
                "or a valid net.line index. Switch-backed bus-bus links (et='b') "
                "have no currents; convert the coupler to a short 3-φ line."
            )
        if side not in ("from", "to"):
            raise ValueError("side must be 'from' or 'to'")

        # Create & attach CT
        ct = CT(name)
        ct.attach_line(self.net, line_idx, side)
        self.cts[name] = ct  # ensure plotting & sampling pick it up
        return ct
    
    def run_simulation(self, sim: "Simulation"):
        from .simulation import Simulation  # local import to avoid cycles
        assert isinstance(sim, Simulation)
        return sim.run(self)


        # ----- power flow + helpers (3φ by default) -----
    def run_powerflow(self, **pp_kwargs):
        """
        Runs power flow. Defaults to three-phase.
        Returns a tiny summary dict with 3φ min/max voltages if available.
        """
        _dump_nan_refs(self.net)
        sanitize_net_3ph(self.net)
        if self.three_phase:
            try: 
                pp.runpp_3ph(self.net, **pp_kwargs, max_iteration=100)
            except Exception:
                print("hej")
                pp.runpp_3ph(self.net, init_vm_pu="results", **pp_kwargs, max_iteration=200)
            bus_tbl = getattr(self.net, "res_bus_3ph", None)
            if bus_tbl is not None and not bus_tbl.empty:
                # expect columns like 'va_pu','vb_pu','vc_pu'
                vmins = [bus_tbl.get(col).min() for col in ("va_pu","vb_pu","vc_pu") if col in bus_tbl]
                vmaxs = [bus_tbl.get(col).max() for col in ("va_pu","vb_pu","vc_pu") if col in bus_tbl]
                vmin = float(min(vmins)) if vmins else float("nan")
                vmax = float(max(vmaxs)) if vmaxs else float("nan")
            else:
                vmin = vmax = float("nan")
            # line loading often not in 3φ results; return NaN if absent
            loading = float("nan")
        else:
            pp.runpp(self.net, **pp_kwargs)
            vmin = float(self.net.res_bus["vm_pu"].min()) if not self.net.res_bus.empty else float("nan")
            vmax = float(self.net.res_bus["vm_pu"].max()) if not self.net.res_bus.empty else float("nan")
            loading = (float(self.net.res_line["loading_percent"].max())
                       if "loading_percent" in self.net.res_line else float("nan"))
        return {"vmin_pu": vmin, "vmax_pu": vmax, "max_line_loading_pct": loading}
    
    # Convenience: where to read results from
    @property
    def res_bus(self):
        """Return the appropriate bus results table (3φ or 1φ)."""
        return self.net.res_bus_3ph if self.three_phase and hasattr(self.net, "res_bus_3ph") else self.net.res_bus

    @property
    def res_line(self):
        """Return the appropriate line results table (3φ or 1φ)."""
        return self.net.res_line_3ph if self.three_phase and hasattr(self.net, "res_line_3ph") else self.net.res_line

    # ----- optional delegate for convenience -----
    def plot_one_line(self, **kwargs):
        from .plotting import plot_one_line
        return plot_one_line(self, **kwargs)

    def __repr__(self):
        return (f"<Substation {self.name} | 3φ={self.three_phase} "
                f"buses={len(self.busbars)} lines={len(self.lines)} "
                f"buslinks={len(self.buslinks)} loads={len(self.loads)} "
                f"ext_grids={len(self.ext_grids)} cts={len(self.cts)} "
                f"cbs={len(self.cbs)}>")