# sasmaker/ct.py
import math

class CT:
    """
    Minimal 3-phase CT attached to ONE line endpoint ('from' or 'to').
    Reads per-phase primary RMS currents (kA) from net.res_line_3ph.
    """
    def __init__(self, name: str):
        self.name = name
        self._net = None
        self._line_id = None
        self._side = None
        self_bus_id = None
        # map side -> result columns
        self._cols = {"to": ("i_a_to_ka","i_b_to_ka","i_c_to_ka"),
                      "from": ("i_a_from_ka","i_b_from_ka","i_c_from_ka")}
        self._cols_pwr = {"to": ("p_a_to_mw","p_b_to_mw","p_c_to_mw", 
                                 "q_a_to_mvar", "q_b_to_mvar", "q_c_to_mvar"),
                      "from": ("p_a_from_mw","p_b_from_mw","p_c_from_mw", 
                                 "q_a_from_mvar", "q_b_from_mvar", "q_c_from_mvar")}
        self._cols_bus = {"to": ("to_bus"),
                         "from": ("from_bus")}
        
        self._trafo_id = None          # <- add
        self._tx_side = None           # <- add
                     

    # --- configuration ---
    def attach_line(self, net, line_id: int, side: str):
        if side not in ("from", "to"):
            raise ValueError("side must be 'from' or 'to'")
        self._net = net
        self._line_id = int(line_id)
        self._side = side
        self._bus_id = self._net.line.iloc[int(line_id)][self._cols_bus[self._side]]

    def attach_tx(self, net, trafo_id: int, side: str):
        """Attach CT to transformer endpoint ('hv' or 'lv')."""
        if side not in ("hv", "lv"):
            raise ValueError("side must be 'hv' or 'lv'")
        self._net = net
        self._trafo_id = int(trafo_id)
        self._tx_side = side
        # clear any previous line attachment
        self._line_id = None
        self._side = None
        return self

    # --- measurement ---
    def read_primary_current(self) -> dict:
        """
        Return {'Ia','Ib','Ic'} in kA for the attached element/side.
        - Lines: res_line_3ph per-phase columns (self._cols mapping).
        - Transformers: res_trafo_3ph per-phase columns if available,
        otherwise res_trafo magnitude replicated to A/B/C.
        """
        if self._net is None:
            raise RuntimeError("CT not attached to any network")

        # -------- Line endpoint (unchanged) --------
        if self._line_id is not None:
            if self._side not in ("from", "to"):
                raise RuntimeError("Line CT missing side ('from'/'to').")
            cA, cB, cC = self._cols[self._side]  # e.g., ("i_from_a_ka", "i_from_b_ka", "i_from_c_ka")
            df = self._net.res_line_3ph
            Ia = float(df.at[self._line_id, cA])
            Ib = float(df.at[self._line_id, cB])
            Ic = float(df.at[self._line_id, cC])
            return {"Ia": Ia, "Ib": Ib, "Ic": Ic}

        # -------- Transformer endpoint --------
        if self._trafo_id is not None:
            if self._tx_side not in ("hv", "lv"):
                raise RuntimeError("Transformer CT missing side ('hv'/'lv').")

            # Prefer per-phase trafo results
            df3 = getattr(self._net, "res_trafo_3ph", None)
            if df3 is not None and self._trafo_id in df3.index:
                if self._tx_side == "hv":
                    cols = ("i_a_hv_ka", "i_b_hv_ka", "i_c_hv_ka")
                else:  # 'lv'
                    cols = ("i_a_lv_ka", "i_b_lv_ka", "i_c_lv_ka")

                missing = [c for c in cols if c not in df3.columns]
                if not missing:
                    Ia = float(df3.at[self._trafo_id, cols[0]])
                    Ib = float(df3.at[self._trafo_id, cols[1]])
                    Ic = float(df3.at[self._trafo_id, cols[2]])
                    return {"Ia": Ia, "Ib": Ib, "Ic": Ic}
                # fall through to magnitude if columns aren’t present in your pp version

            # Fallback: magnitude only (2-winding)
            df2 = getattr(self._net, "res_trafo", None)
            if df2 is not None and self._trafo_id in df2.index:
                col = "i_hv_ka" if self._tx_side == "hv" else "i_lv_ka"
                if col in df2.columns:
                    I = float(df2.at[self._trafo_id, col])
                    return {"Ia": I, "Ib": I, "Ic": I}

            # Optional: 3-winding magnitude (if you support CTs on 3W trafos)
            df3w = getattr(self._net, "res_trafo3w", None)
            if df3w is not None and self._trafo_id in df3w.index:
                side_map = {"hv": "i_hv_ka", "mv": "i_mv_ka", "lv": "i_lv_ka"}
                col = side_map.get(self._tx_side)
                if col and col in df3w.columns:
                    I = float(df3w.at[self._trafo_id, col])
                    return {"Ia": I, "Ib": I, "Ic": I}

            raise RuntimeError(
                f"No transformer results for trafo id {self._trafo_id} "
                "(expected res_trafo_3ph or res_trafo)."
            )

        raise RuntimeError("CT is not attached to a line or transformer")


    def read_power_flow(self) -> dict:
        """
        Return per-phase power at the attached endpoint as:
            {'Pa','Pb','Pc','Qa','Qb','Qc'}
        Units:
            - Lines: MW / MVAr from net.res_line_3ph
            - Transformers: MW / MVAr from net.res_trafo_3ph (preferred),
            else fall back to net.res_trafo or net.res_trafo3w (replicate total P/Q -> phases).
        """
        if self._net is None:
            raise RuntimeError("CT is not attached to any network")

        # ---------- Line endpoint ----------
        if self._line_id is not None:
            if self._side not in ("from", "to"):
                raise RuntimeError("Line CT missing side ('from'/'to').")
            cPa, cPb, cPc, cQa, cQb, cQc = self._cols_pwr[self._side]
            df = self._net.res_line_3ph
            Pa = float(df.at[self._line_id, cPa])
            Pb = float(df.at[self._line_id, cPb])
            Pc = float(df.at[self._line_id, cPc])
            Qa = float(df.at[self._line_id, cQa])
            Qb = float(df.at[self._line_id, cQb])
            Qc = float(df.at[self._line_id, cQc])
            return {"Pa": Pa, "Pb": Pb, "Pc": Pc, "Qa": Qa, "Qb": Qb, "Qc": Qc}

        # ---------- Transformer endpoint ----------
        if self._trafo_id is not None:
            if self._tx_side not in ("hv", "lv", "mv"):
                raise RuntimeError("Transformer CT missing side ('hv'/'lv'/'mv').")

            # Prefer per-phase trafo results (net.res_trafo_3ph)
            df3 = getattr(self._net, "res_trafo_3ph", None)
            if df3 is not None and self._trafo_id in df3.index:
                # Column names per pandapower docs you pasted:
                # HV: p_a_hv_mw, q_a_hv_mvar, ..., p_b_hv_mw, q_b_hv_mvar, ...
                # LV: p_a_lv_mw, q_a_lv_mvar, ...
                # (No MV here — MV per-phase is in res_trafo3w_3ph if you ever use that.)
                side = self._tx_side
                def cols(s):
                    return (
                        f"p_a_{s}_mw", f"p_b_{s}_mw", f"p_c_{s}_mw",
                        f"q_a_{s}_mvar", f"q_b_{s}_mvar", f"q_c_{s}_mvar"
                    )
                cPa, cPb, cPc, cQa, cQb, cQc = cols(side)
                missing = [c for c in (cPa, cPb, cPc, cQa, cQb, cQc) if c not in df3.columns]
                if not missing:
                    Pa = float(df3.at[self._trafo_id, cPa])
                    Pb = float(df3.at[self._trafo_id, cPb])
                    Pc = float(df3.at[self._trafo_id, cPc])
                    Qa = float(df3.at[self._trafo_id, cQa])
                    Qb = float(df3.at[self._trafo_id, cQb])
                    Qc = float(df3.at[self._trafo_id, cQc])
                    return {"Pa": Pa, "Pb": Pb, "Pc": Pc, "Qa": Qa, "Qb": Qb, "Qc": Qc}
                # fall through to magnitude if those exact columns aren’t present

            # Fallbacks when only aggregated side power is available
            # 2-winding: net.res_trafo has p_hv_mw, q_hv_mvar, p_lv_mw, q_lv_mvar
            df2 = getattr(self._net, "res_trafo", None)
            if df2 is not None and self._trafo_id in df2.index:
                smap = {
                    "hv": ("p_hv_mw", "q_hv_mvar"),
                    "lv": ("p_lv_mw", "q_lv_mvar"),
                    # 'mv' not present in 2-winding
                }
                if self._tx_side in smap and all(c in df2.columns for c in smap[self._tx_side]):
                    Ptot = float(df2.at[self._trafo_id, smap[self._tx_side][0]])
                    Qtot = float(df2.at[self._trafo_id, smap[self._tx_side][1]])
                    # Distribute equally across phases (best effort without 3φ detail)
                    Pa = Pb = Pc = Ptot / 3.0
                    Qa = Qb = Qc = Qtot / 3.0
                    return {"Pa": Pa, "Pb": Pb, "Pc": Pc, "Qa": Qa, "Qb": Qb, "Qc": Qc}

            # 3-winding: net.res_trafo3w has p_hv_mw / q_hv_mvar / p_mv_mw / q_mv_mvar / p_lv_mw / q_lv_mvar
            df3w = getattr(self._net, "res_trafo3w", None)
            if df3w is not None and self._trafo_id in df3w.index:
                prefix = f"{self._tx_side}_"
                pcol = f"p_{prefix}mw" if f"p_{prefix}mw" in df3w.columns else f"p_{self._tx_side}_mw"
                qcol = f"q_{prefix}mvar" if f"q_{prefix}mvar" in df3w.columns else f"q_{self._tx_side}_mvar"
                if pcol in df3w.columns and qcol in df3w.columns:
                    Ptot = float(df3w.at[self._trafo_id, pcol])
                    Qtot = float(df3w.at[self._trafo_id, qcol])
                    Pa = Pb = Pc = Ptot / 3.0
                    Qa = Qb = Qc = Qtot / 3.0
                    return {"Pa": Pa, "Pb": Pb, "Pc": Pc, "Qa": Qa, "Qb": Qb, "Qc": Qc}

            raise RuntimeError(
                f"No transformer power results for trafo id {self._trafo_id} "
                "(expected res_trafo_3ph or res_trafo / res_trafo3w)."
            )

        raise RuntimeError("CT is not attached to a line or transformer")

    
    def get_bus_name(self):
        """Return the name of the bus at the CT endpoint (works for line or transformer)."""
        if self._net is None:
            raise RuntimeError("CT is not attached.")
        b_idx = self.endpoint_bus()  # uses line or tx depending on what is attached
        # be robust if 'name' column is missing
        if "name" not in self._net.bus.columns:
            return f"bus{int(b_idx)}"
        return self._net.bus.at[b_idx, "name"]

    # --- geometry helpers used by plotting ---
    def endpoint_bus(self) -> int:
        if self._net is None:
            raise RuntimeError("CT is not attached.")
        if self._line_id is not None:
            line_tbl = self._net.line
            return int(line_tbl.at[self._line_id, "from_bus" if self._side == "from" else "to_bus"])
        if self._trafo_id is not None:
            tx_tbl = self._net.trafo
            return int(tx_tbl.at[self._trafo_id, "hv_bus" if self._tx_side == "hv" else "lv_bus"])
        raise RuntimeError("CT is not attached.")

    def other_bus(self) -> int:
        if self._line_id is not None:
            line_tbl = self._net.line
            return int(line_tbl.at[self._line_id, "to_bus" if self._side == "from" else "from_bus"])
        if self._trafo_id is not None:
            tx_tbl = self._net.trafo
            return int(tx_tbl.at[self._trafo_id, "lv_bus" if self._tx_side == "hv" else "hv_bus"])
        raise RuntimeError("CT is not attached.")

    def endpoint_xy_and_dir(self) -> tuple[float,float,float,float]:
        """
        Returns (x_bus, y_bus, dx_unit, dy_unit) where (dx_unit,dy_unit)
        points ALONG the line away from this endpoint.
        """
        b_here = self.endpoint_bus()
        b_other = self.other_bus()
        xh = float(self._net.bus.at[b_here,  "x"]); yh = float(self._net.bus.at[b_here,  "y"])
        xo = float(self._net.bus.at[b_other, "x"]); yo = float(self._net.bus.at[b_other, "y"])
        dx, dy = (xo - xh), (yo - yh)
        L = math.hypot(dx, dy)
        if L == 0:
            return xh, yh, 1.0, 0.0
        return xh, yh, dx / L, dy / L
