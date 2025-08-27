import pandapower as pp
import math

class CB:
    """
    Minimal 3-phase circuit breaker attached to ONE line endpoint ('from' or 'to').
    Backed by a pandapower switch (et='l').
    """
    def __init__(self, name: str):
        self.name = name
        self._net = None
        self._line_id = None
        self._side = None
        self._sw_idx = None  # pp.switch index

    # --- configuration ---
    def attach_line(self, net, line_id: int, side: str, *, closed: bool = True):
        if side not in ("from", "to"):
            raise ValueError("side must be 'from' or 'to'")
        self._net = net
        self._line_id = int(line_id)
        self._side = side

        line_tbl = net.line
        bus_idx = int(line_tbl.at[self._line_id, "from_bus" if side == "from" else "to_bus"])

        self._sw_idx = pp.create_switch(
            net, bus=bus_idx, element=self._line_id, et='l',
            closed=bool(closed), name=self.name
        )

    # --- state ---
    @property
    def closed(self) -> bool:
        return bool(self._net.switch.at[self._sw_idx, "closed"])

    def open(self):  self._net.switch.at[self._sw_idx, "closed"] = False
    def close(self): self._net.switch.at[self._sw_idx, "closed"] = True

    # --- geometry (for plotting) ---
    def endpoint_bus(self) -> int:
        line_tbl = self._net.line
        return int(line_tbl.at[self._line_id, "from_bus" if self._side == "from" else "to_bus"])

    def other_bus(self) -> int:
        line_tbl = self._net.line
        return int(line_tbl.at[self._line_id, "to_bus" if self._side == "from" else "from_bus"])

    def endpoint_xy_and_dir(self):
        b_here = self.endpoint_bus()
        b_other = self.other_bus()
        xh = float(self._net.bus.at[b_here, "x"]); yh = float(self._net.bus.at[b_here, "y"])
        xo = float(self._net.bus.at[b_other, "x"]); yo = float(self._net.bus.at[b_other, "y"])
        dx, dy = (xo - xh), (yo - yh)
        L = math.hypot(dx, dy)
        if L == 0: return xh, yh, 1.0, 0.0
        return xh, yh, dx/L, dy/L

    def __repr__(self):
        return f"<CB {self.name} line={self._line_id} side={self._side} {'closed' if self.closed else 'open'}>"
