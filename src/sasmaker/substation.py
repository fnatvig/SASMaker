import pandapower as pp

from .busbar import Busbar
from .line import Line
from .buslink import BusLink
from .load import Load
from .ct import CT
from .cb import CB
from .ied import IED

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
        self.cbs: dict[str, CB] = {}
        self.ieds: dict[str, IED] = {}
        self.three_phase = True

    # ----- creation helpers -----
    def add_busbar(self,
                name: str,
                vn_kv: float,
                x: float = 0.0,
                y: float = 0.0,
                draw_length: float | None = None,
                draw_thickness: float | None = None,
                draw_slots: int | None = None):
        bb = Busbar(name, self.net, vn_kv, x, y,
                    draw_length=draw_length,
                    draw_thickness=draw_thickness,
                    draw_slots=draw_slots)
        self.busbars[name] = bb
        return bb

    def add_line(self, name: str, from_busbar: Busbar, to_busbar: Busbar,
                length_km: float, *, std_type: str | None = None) -> Line:
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
                r_ohm_per_km=0.12, x_ohm_per_km=0.38, c_nf_per_km=8.0, max_i_ka=1.0,
                r0_ohm_per_km=0.36, x0_ohm_per_km=1.14, c0_nf_per_km=5.0
            )
        self.lines[name] = ln
        return ln
    
    def add_buslink(self, name: str, a: Busbar, b: Busbar, *, closed: bool = True) -> BusLink:
        bl = BusLink(name, self.net, a.idx, b.idx, closed=closed)
        self.buslinks[name] = bl
        return bl
    
    def add_ext_grid(self, name: str, at_busbar: Busbar,
                 vm_pu: float = 1.0, va_degree: float = 0.0,
                 in_service: bool = True) -> int:
        """Create an external grid with sane defaults for 3φ studies."""
        eg_idx = pp.create_ext_grid(
            self.net, at_busbar.idx,
            vm_pu=vm_pu, va_degree=va_degree, in_service=in_service, name=name,
            s_sc_max_mva=1000, s_sc_min_mva=500,
            rx_max=0.1, rx_min=0.1,
            r0x0_max=0.4, x0x_max=1.0
        )
        self.ext_grids[name] = eg_idx
        return eg_idx
    
    def add_load(self, name: str, at_busbar: Busbar,
                 p_mw: float, q_mvar: float = 0.0,
                 phase_split: tuple[float, float, float] = (1/3, 1/3, 1/3),
                 in_service: bool = True) -> Load:
        """Create a minimal 3φ load at a busbar (equal split by default)."""
        ld = Load(name, self.net, at_busbar.idx, p_mw, q_mvar, phase_split, in_service)
        self.loads[name] = ld
        return ld
    
    def add_ct(self, name: str, line, side: str) -> CT:
        """
        Create a CT on a given Line endpoint.
        Usage: s.add_ct("CT1", line_obj, side="from")
        """
        ct = CT(name)
        ct.attach_line(self.net, line_id=line.idx, side=side)
        self.cts[name] = ct
        return ct
    
    def add_cb(self, name: str, line, side: str, *, closed: bool = True) -> CB:
        cb = CB(name)
        cb.attach_line(self.net, line_id=line.idx, side=side, closed=closed)
        self.cbs[name] = cb
        return cb
    
    def add_ied(self, name: str, *, ct=None, cb=None) -> IED:
        ied = IED(name, ct=ct, cb=cb)
        self.ieds[name] = ied
        return ied
    
        # ----- power flow + helpers (3φ by default) -----
    def run_powerflow(self, **pp_kwargs):
        """
        Runs power flow. Defaults to three-phase.
        Returns a tiny summary dict with 3φ min/max voltages if available.
        """
        if self.three_phase:
            pp.runpp_3ph(self.net, **pp_kwargs)
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