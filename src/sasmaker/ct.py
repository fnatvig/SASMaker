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
                     

    # --- configuration ---
    def attach_line(self, net, line_id: int, side: str):
        if side not in ("from", "to"):
            raise ValueError("side must be 'from' or 'to'")
        self._net = net
        self._line_id = int(line_id)
        self._side = side
        self._bus_id = self._net.line.iloc[int(line_id)][self._cols_bus[self._side]]

    # --- measurement ---
    def read_primary_current(self) -> dict:
        """Return {'Ia','Ib','Ic'} in kA from net.res_line_3ph for this endpoint."""
        if any(x is None for x in (self._net, self._line_id, self._side)):
            raise RuntimeError("CT is not attached. Call attach_line(...) first.")
        cA, cB, cC = self._cols[self._side]
        row = self._net.res_line_3ph
        Ia = float(row.at[self._line_id, cA])
        Ib = float(row.at[self._line_id, cB])
        Ic = float(row.at[self._line_id, cC])
        return {"Ia": Ia, "Ib": Ib, "Ic": Ic}

    def read_power_flow(self) -> dict:
        """Return {'Pa','Pb','Pc', 'Qa', 'Qb', 'Qc'} in kA from net.res_line_3ph for this endpoint."""
        if any(x is None for x in (self._net, self._line_id, self._side)):
            raise RuntimeError("CT is not attached. Call attach_line(...) first.")
        cA, cB, cC, cD, cE, cF = self._cols_pwr[self._side]
        row = self._net.res_line_3ph
        Pa = float(row.at[self._line_id, cA])
        Pb = float(row.at[self._line_id, cB])
        Pc = float(row.at[self._line_id, cC])
        Qa = float(row.at[self._line_id, cD])
        Qb = float(row.at[self._line_id, cE])
        Qc = float(row.at[self._line_id, cF])
        return {"Pa": Pa, "Pb": Pb, "Pc": Pc,
                "Qa": Qa, "Qb": Qb, "Qc": Qc}
    
    def get_bus_name(self):
        return self._net.bus.iloc[self._bus_id]["name"]

    # --- geometry helpers used by plotting ---
    def endpoint_bus(self) -> int:
        if self._net is None or self._line_id is None or self._side is None:
            raise RuntimeError("CT is not attached.")
        line_tbl = self._net.line
        return int(line_tbl.at[self._line_id, "from_bus" if self._side == "from" else "to_bus"])

    def other_bus(self) -> int:
        line_tbl = self._net.line
        return int(line_tbl.at[self._line_id, "to_bus" if self._side == "from" else "from_bus"])

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
