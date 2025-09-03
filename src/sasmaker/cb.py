import pandapower as pp
import math
from typing import Optional, Literal, Union

TargetKind = Literal["line", "buslink"]

class CB:
    """
    Circuit breaker wrapper.

    Two modes:
      1) Line-end CB (et='l'): create and control a line-end switch at 'from' or 'to' bus.
      2) Buslink CB (et='b'): wrap an existing bus-bus switch (created by BusLink).
         No new switch is created; we control the same pp.switch row.

    Plotting helpers:
      - For line targets, endpoint_bus()/other_bus() work as before.
      - For buslink targets, use buses() to get the two bus indices.
      - endpoint_xy_and_dir() returns:
          * for line: bus-end position and unit direction along the line (as before)
          * for buslink: midpoint between the two buses and unit direction from A→B
    """

    def __init__(self, name: str):
        self.name = name
        self._net = None
        self._sw_idx: Optional[int] = None

        # line target
        self._line_id: Optional[int] = None
        self._side: Optional[str] = None  # 'from' | 'to'

        # buslink target
        self._bus_a: Optional[int] = None
        self._bus_b: Optional[int] = None

        self._target_kind: TargetKind = "line"  # default for backward compat

    # ---------------- configuration ----------------

    def attach_line(self, net, line_id: int, side: str, *, closed: bool = True):
        """Create & attach a line-end CB (et='l')."""
        if side not in ("from", "to"):
            raise ValueError("side must be 'from' or 'to'")
        self._net = net
        self._line_id = int(line_id)
        self._side = side
        self._target_kind = "line"

        line_tbl = net.line
        bus_idx = int(line_tbl.at[self._line_id, "from_bus" if side == "from" else "to_bus"])

        self._sw_idx = pp.create_switch(
            net, bus=bus_idx, element=self._line_id, et='l',
            closed=bool(closed), name=self.name
        )

    def attach_buslink(self, net, buslink: Union[int, "BusLink"], *, closed: Optional[bool] = None):
        """
        Wrap an existing bus-bus switch (et='b') created by BusLink.
        'buslink' can be the BusLink object or its pp.switch index.
        """
        self._net = net
        self._target_kind = "buslink"

        if hasattr(buslink, "idx"):
            self._sw_idx = int(buslink.idx)
        else:
            self._sw_idx = int(buslink)

        row = net.switch.loc[self._sw_idx]
        et = str(row["et"])
        if et != "b":
            raise ValueError(f"attach_buslink expects a bus-bus switch (et='b'), got et={et!r}")

        self._bus_a = int(row["bus"])
        self._bus_b = int(row["element"])

        if closed is not None:
            self.closed = bool(closed)

    # ---------------- state ----------------

    @property
    def closed(self) -> bool:
        return bool(self._net.switch.at[self._sw_idx, "closed"])

    @closed.setter
    def closed(self, val: bool) -> None:
        self._net.switch.at[self._sw_idx, "closed"] = bool(val)

    def open(self):  self.closed = False
    def close(self): self.closed = True
    def toggle(self): self.closed = not self.closed

    # ---------------- metadata ----------------

    @property
    def target_kind(self) -> TargetKind:
        return self._target_kind

    # ---------------- geometry / plotting helpers ----------------

    def endpoint_bus(self) -> int:
        """For line CBs: return the bus at this CB's endpoint."""
        if self._target_kind != "line":
            raise RuntimeError("endpoint_bus() only valid for line CBs")
        line_tbl = self._net.line
        return int(line_tbl.at[self._line_id, "from_bus" if self._side == "from" else "to_bus"])

    def other_bus(self) -> int:
        """For line CBs: return the opposite bus."""
        if self._target_kind != "line":
            raise RuntimeError("other_bus() only valid for line CBs")
        line_tbl = self._net.line
        return int(line_tbl.at[self._line_id, "to_bus" if self._side == "from" else "from_bus"])

    def buses(self) -> tuple[int, int]:
        """For buslink CBs: (bus_a, bus_b)."""
        if self._target_kind != "buslink":
            raise RuntimeError("buses() only valid for buslink CBs")
        return int(self._bus_a), int(self._bus_b)

    def endpoint_xy_and_dir(self):
        """
        For line CBs: (x_here, y_here, dx_unit, dy_unit) from endpoint toward the other bus.
        For buslink CBs: (x_mid, y_mid, dx_unit, dy_unit) along the buslink from A→B.
        """
        if self._target_kind == "line":
            b_here = self.endpoint_bus()
            b_other = self.other_bus()
            xh = float(self._net.bus.at[b_here, "x"]); yh = float(self._net.bus.at[b_here, "y"])
            xo = float(self._net.bus.at[b_other, "x"]); yo = float(self._net.bus.at[b_other, "y"])
            dx, dy = (xo - xh), (yo - yh)
            L = math.hypot(dx, dy)
            if L == 0: return xh, yh, 1.0, 0.0
            return xh, yh, dx/L, dy/L

        else:  # buslink
            a, b = self.buses()
            xa = float(self._net.bus.at[a, "x"]); ya = float(self._net.bus.at[a, "y"])
            xb = float(self._net.bus.at[b, "x"]); yb = float(self._net.bus.at[b, "y"])
            mx = 0.5 * (xa + xb); my = 0.5 * (ya + yb)
            dx, dy = (xb - xa), (yb - ya)
            L = math.hypot(dx, dy)
            ux, uy = (dx/L, dy/L) if L else (1.0, 0.0)
            return mx, my, ux, uy

    def __repr__(self):
        tgt = "?"
        if self._target_kind == "line":
            tgt = f"line={self._line_id} side={self._side}"
        else:
            tgt = f"buslink switch={self._sw_idx}"
        return f"<CB {self.name} {tgt} {'closed' if self.closed else 'open'}>"
