# sasmaker/cb.py
import pandapower as pp
import math
from typing import Optional, Literal, Union

TargetKind = Literal["line", "buslink", "tx"]

class CB:
    """
    Circuit breaker wrapper.

    Modes:
      1) Line-end CB (et='l'): create & control a line-end switch at 'from' or 'to' bus.
      2) Buslink CB (et='b'): wrap an existing bus-bus switch (created by BusLink).
      3) Transformer-end CB (et='t'): create & control a trafo-end switch on 'hv' or 'lv' bus.
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

        # transformer target
        self._trafo_id: Optional[int] = None
        self._tx_side: Optional[str] = None  # 'hv' | 'lv'

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
        self.prev_state = closed

        line_tbl = net.line
        bus_idx = int(line_tbl.at[self._line_id, "from_bus" if side == "from" else "to_bus"])

        self._sw_idx = pp.create_switch(
            net, bus=bus_idx, element=self._line_id, et="l",
            closed=bool(closed), name=self.name
        )
        return self

    def attach_buslink(self, net, buslink: Union[int, "BusLink"], *, closed: Optional[bool] = None):
        """
        Attach to a bus coupler.
        Supports:
          - legacy et='b' switch (pass switch index or the old BusLink object),
          - new short-line BusLink (has .line_idx and .buses()).
        """
        self._net = net
        self._target_kind = "buslink"
        self.prev_state = closed

        # --- NEW: line-backed coupler ---------------------------------------
        # Detect our new BusLink by presence of .line_idx
        if hasattr(buslink, "line_idx"):
            self._line_id = int(buslink.line_idx)
            a, b = buslink.buses
            self._bus_a, self._bus_b = int(a), int(b)
            # No switch row for this path
            self._sw_idx = None
            if closed is not None:
                net.line.at[self._line_id, "in_service"] = bool(closed)
            return self

        # --- LEGACY: switch-backed bus-bus (et='b') --------------------------
        if hasattr(buslink, "idx"):        # BusLink object from old class
            self._sw_idx = int(buslink.idx)
        else:                               # raw pp.switch index
            self._sw_idx = int(buslink)

        row = net.switch.loc[self._sw_idx]  # <-- your previous code
        et = str(row["et"])
        if et != "b":
            raise ValueError(f"attach_buslink expects a bus-bus switch (et='b'), got et={et!r}")

        self._bus_a = int(row["bus"])
        self._bus_b = int(row["element"])

        if closed is not None:
            self.closed = bool(closed)

        return self

    # NEW: transformer endpoint
    def attach_tx(self, net, trafo_id: int, side: str, *, closed: bool = True):
        """Create & attach a transformer-end CB (et='t') on 'hv' or 'lv' bus."""
        if side not in ("hv", "lv"):
            raise ValueError("side must be 'hv' or 'lv'")
        self._net = net
        self._trafo_id = int(trafo_id)
        self._tx_side = side
        self._target_kind = "tx"
        self.prev_state = closed

        tx_tbl = net.trafo
        bus_idx = int(tx_tbl.at[self._trafo_id, "hv_bus" if side == "hv" else "lv_bus"])

        self._sw_idx = pp.create_switch(
            net, bus=bus_idx, element=self._trafo_id, et="t",
            closed=bool(closed), name=self.name
        )
        return self

    # ---------------- state ----------------

    @property
    def closed(self) -> bool:
        if self._target_kind == "buslink" and self._sw_idx is None:
            # line-backed coupler: "closed" ↔ line in_service
            return bool(self._net.line.at[self._line_id, "in_service"])
        # else: switch-backed or line CB
        return bool(self._net.switch.at[self._sw_idx, "closed"])

    @closed.setter
    def closed(self, val: bool) -> None:
        val = bool(val)
        if self._target_kind == "buslink" and self._sw_idx is None:
            self._net.line.at[self._line_id, "in_service"] = val
        else:
            self._net.switch.at[self._sw_idx, "closed"] = val
    def open(self):  self.closed = False
    def close(self): self.closed = True
    def toggle(self): self.closed = not self.closed
    

    # ---------------- metadata ----------------

    @property
    def target_kind(self) -> TargetKind:
        return self._target_kind

    # ---------------- geometry / plotting helpers ----------------

    def endpoint_bus(self) -> int:
        """For line/tx CBs: return the bus at this CB's endpoint."""
        if self._target_kind == "line":
            line_tbl = self._net.line
            return int(line_tbl.at[self._line_id, "from_bus" if self._side == "from" else "to_bus"])
        if self._target_kind == "tx":
            tx_tbl = self._net.trafo
            return int(tx_tbl.at[self._trafo_id, "hv_bus" if self._tx_side == "hv" else "lv_bus"])
        raise RuntimeError("endpoint_bus() only valid for line or tx CBs")

    def other_bus(self) -> int:
        """For line/tx CBs: return the opposite bus."""
        if self._target_kind == "line":
            line_tbl = self._net.line
            return int(line_tbl.at[self._line_id, "to_bus" if self._side == "from" else "from_bus"])
        if self._target_kind == "tx":
            tx_tbl = self._net.trafo
            return int(tx_tbl.at[self._trafo_id, "lv_bus" if self._tx_side == "hv" else "hv_bus"])
        raise RuntimeError("other_bus() only valid for line or tx CBs")

    def buses(self) -> tuple[int, int]:
        """For buslink CBs: (bus_a, bus_b)."""
        if self._target_kind != "buslink":
            raise RuntimeError("buses() only valid for buslink CBs")
        if self._bus_a is None or self._bus_b is None:
            # try to resolve for line CB fallback (shouldn't happen for buslink)
            raise RuntimeError("bus endpoints are not set")
        return int(self._bus_a), int(self._bus_b)

    def endpoint_xy_and_dir(self):
        """
        For line/tx CBs: (x_here, y_here, dx_unit, dy_unit) from endpoint toward the other bus.
        For buslink CBs: (x_mid, y_mid, dx_unit, dy_unit) along the buslink from A→B.
        """
        if self._target_kind in ("line", "tx"):
            b_here = self.endpoint_bus()
            b_other = self.other_bus()
            xh = float(self._net.bus.at[b_here, "x"]); yh = float(self._net.bus.at[b_here, "y"])
            xo = float(self._net.bus.at[b_other, "x"]); yo = float(self._net.bus.at[b_other, "y"])
            dx, dy = (xo - xh), (yo - yh)
            L = math.hypot(dx, dy)
            if L == 0: return xh, yh, 1.0, 0.0
            return xh, yh, dx / L, dy / L

        # buslink
        a, b = self.buses()
        xa = float(self._net.bus.at[a, "x"]); ya = float(self._net.bus.at[a, "y"])
        xb = float(self._net.bus.at[b, "x"]); yb = float(self._net.bus.at[b, "y"])
        mx = 0.5 * (xa + xb); my = 0.5 * (ya + yb)
        dx, dy = (xb - xa), (yb - ya)
        L = math.hypot(dx, dy)
        ux, uy = (dx / L, dy / L) if L else (1.0, 0.0)
        return mx, my, ux, uy

    def __repr__(self):
        if self._target_kind == "line":
            tgt = f"line={self._line_id} side={self._side}"
        elif self._target_kind == "buslink":
            if self._sw_idx is None:
                tgt = f"buslink line={self._line_id} {self._bus_a}↔{self._bus_b}"
            else:
                tgt = f"buslink switch={self._sw_idx} {self._bus_a}↔{self._bus_b}"
        else:
            tgt = f"tx line={self._line_id} side={self._side}"
        return f"<CB {self.name} {tgt} {'closed' if self.closed else 'open'}>"

