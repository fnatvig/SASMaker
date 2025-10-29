# sasmaker/remote_ss_equiv_load.py
import pandapower as pp
import math
from .load import Load

class RemoteSS(Load):
    def __init__(self, name: str, net, bus_idx: int, p_mw: float, q_mvar: float,
                 draw_label: bool = True,
                 vm_pu: float = 1.01,
                 va_degree: float = 0.0,               # NEW
                 s_sc_mva: float = 1000.0,
                 xr: float = 8.0,
                 tie_len_km: float = 0.25,
                 r0_factor: float = 3.0,
                 x0_factor: float = 3.0,
                 c_nf_per_km: float = 10.0,
                 c0_nf_per_km: float = 5.0,
                 # --- OPTIONAL: auto-tune right now (during build) ---
                 tune_line_id: int | None = None,      # outgoing line id (your CT line)
                 tune_side_is_from: bool | None = None,# True if substation is line.from_bus
                 tune_target_p_mw: float | None = None,
                 tune_target_q_mvar: float | None = None,
                 tune_vm_bounds=(0.97, 1.06),
                 tune_va_bounds=(-20.0, 20.0),
                 tune_outer_loops: int = 3,
                 tune_bisect_steps: int = 10,
                 tune_tol_p_mw: float = 0.05,
                 tune_tol_q_mvar: float = 0.05):

        # 1) visible load
        super().__init__(name, net, bus_idx, p_mw, q_mvar, draw_label=draw_label)

        # 2) hidden source + tie
        self.src_bus_idx = pp.create_bus(net, vn_kv=float(net.bus.at[self.bus_idx, "vn_kv"]),
                                         name=f"{name}_SRC")
        self.ext_grid_idx = pp.create_ext_grid(
            net, bus=self.src_bus_idx, vm_pu=vm_pu, va_degree=va_degree, name=f"{name}_EG",
            s_sc_max_mva=s_sc_mva, s_sc_min_mva=s_sc_mva,
            rx_max=1.0/xr, rx_min=1.0/xr, r0x0_max=0.4, x0x_max=1.0
        )

        vn_kv = float(net.bus.at[self.bus_idx, "vn_kv"])
        z_abs = (vn_kv * 1e3)**2 / (s_sc_mva * 1e6)
        R = z_abs / math.sqrt(1.0 + xr**2); X = R * xr
        if tie_len_km <= 0: tie_len_km = 0.001
        r_per_km  = R / tie_len_km; x_per_km  = X / tie_len_km
        r0_per_km = r0_factor * r_per_km; x0_per_km = x0_factor * x_per_km

        self.tie_line_idx = pp.create_line_from_parameters(
            net, from_bus=self.src_bus_idx, to_bus=self.bus_idx, length_km=tie_len_km,
            r_ohm_per_km=r_per_km, x_ohm_per_km=x_per_km, c_nf_per_km=c_nf_per_km,
            r0_ohm_per_km=r0_per_km, x0_ohm_per_km=x0_per_km, c0_nf_per_km=c0_nf_per_km,
            max_i_ka=2.0, name=f"{name}_TIE"
        )

        self._remote_params = dict(vm_pu=vm_pu, va_degree=va_degree, s_sc_mva=s_sc_mva, xr=xr,
                                   tie_len_km=tie_len_km, r0_factor=r0_factor, x0_factor=x0_factor,
                                   c_nf_per_km=c_nf_per_km, c0_nf_per_km=c0_nf_per_km)

        # 3) optional: auto-tune NOW (before sim)
        if all(v is not None for v in (tune_line_id, tune_side_is_from, tune_target_p_mw, tune_target_q_mvar)):
            self._tune_before_sim(line_id=tune_line_id,
                                  substation_side_is_from=bool(tune_side_is_from),
                                  target_p_mw=float(tune_target_p_mw),
                                  target_q_mvar=float(tune_target_q_mvar),
                                  vm_bounds=tune_vm_bounds, va_bounds=tune_va_bounds,
                                  outer_loops=tune_outer_loops, bisect_steps=tune_bisect_steps,
                                  tol_p_mw=tune_tol_p_mw, tol_q_mvar=tune_tol_q_mvar)

    # --- knobs ---
    def set_remote_voltage(self, vm_pu: float):
        self._net.ext_grid.at[self.ext_grid_idx, "vm_pu"] = float(vm_pu)
        self._remote_params["vm_pu"] = float(vm_pu)

    def set_remote_angle(self, va_degree: float):
        self._net.ext_grid.at[self.ext_grid_idx, "va_degree"] = float(va_degree)
        self._remote_params["va_degree"] = float(va_degree)

    def set_remote_strength(self, s_sc_mva: float, xr: float | None = None):
        self._net.ext_grid.at[self.ext_grid_idx, "s_sc_max_mva"] = float(s_sc_mva)
        self._net.ext_grid.at[self.ext_grid_idx, "s_sc_min_mva"] = float(s_sc_mva)
        if xr is not None:
            rx = 1.0/float(xr)
            self._net.ext_grid.at[self.ext_grid_idx, "rx_max"] = rx
            self._net.ext_grid.at[self.ext_grid_idx, "rx_min"] = rx
            self._remote_params["xr"] = float(xr)
        self._remote_params["s_sc_mva"] = float(s_sc_mva)

    def remote_info(self) -> dict:
        return dict(src_bus=self.src_bus_idx,
                    ext_grid=self.ext_grid_idx,
                    tie_line=self.tie_line_idx,
                    **self._remote_params)

    # --- internal: tune now, before sim starts ---
    def _tune_before_sim(self, line_id: int, *, substation_side_is_from: bool,
                         target_p_mw: float, target_q_mvar: float,
                         vm_bounds=(0.97, 1.06), va_bounds=(-20.0, 20.0),
                         outer_loops=3, bisect_steps=10,
                         tol_p_mw=0.05, tol_q_mvar=0.05) -> None:

        pf = "from" if substation_side_is_from else "to"
        colsP = [f"p_{pf}_a_mw", f"p_{pf}_b_mw", f"p_{pf}_c_mw"]
        colsQ = [f"q_{pf}_a_mvar", f"q_{pf}_b_mvar", f"q_{pf}_c_mvar"]

        def measure():
            r = self._net.res_line_3ph.loc[line_id]
            return float(r[colsP].sum()), float(r[colsQ].sum())

        tolP = max(tol_p_mw, 0.01)
        tolQ = max(tol_q_mvar, 0.01)

        for _ in range(outer_loops):
            # 1) tune angle (hits P)
            lo, hi = va_bounds
            for _ in range(bisect_steps):
                mid = 0.5*(lo+hi)
                self.set_remote_angle(mid)
                ok = pp.runpp_3ph(self._net, max_iteration=100)
                if not ok:
                    # stabilize by slightly lifting remote voltage
                    self.set_remote_voltage(min(self._remote_params["vm_pu"]+0.005, vm_bounds[1]))
                    pp.runpp_3ph(self._net, max_iteration=100)
                P, Q = measure()
                if abs(P - target_p_mw) <= tolP:
                    break
                # probe hi-side monotonicity
                self.set_remote_angle(hi); pp.runpp_3ph(self._net, max_iteration=100); P_hi, _ = measure()
                # restore mid
                self.set_remote_angle(mid); pp.runpp_3ph(self._net, max_iteration=100)
                # decide half-interval
                if (P - target_p_mw) * (P_hi - target_p_mw) > 0:
                    hi = mid
                else:
                    lo = mid

            # 2) tune voltage (hits Q)
            lo, hi = vm_bounds
            for _ in range(bisect_steps):
                mid = 0.5*(lo+hi)
                self.set_remote_voltage(mid)
                ok = pp.runpp_3ph(self._net, max_iteration=100)
                if not ok:
                    lo = max(lo, 0.96); hi = min(hi, 1.07); continue
                P, Q = measure()
                if abs(Q - target_q_mvar) <= tolQ:
                    break
                self.set_remote_voltage(hi); pp.runpp_3ph(self._net, max_iteration=100); _, Q_hi = measure()
                self.set_remote_voltage(mid); pp.runpp_3ph(self._net, max_iteration=100)
                if (Q - target_q_mvar) * (Q_hi - target_q_mvar) > 0:
                    hi = mid
                else:
                    lo = mid
        # done; params are now “baked in” before sim
