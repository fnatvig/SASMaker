# sasmaker/buslink.py
import pandapower as pp
from typing import Union, Optional

class BusLink:
    """
    Intra-substation bus coupler backed by a *short 3-phase line* (not et='b' switch).
    Pros: CT/CB/IED work exactly like on any line; PF produces currents.
    """

    def __init__(self,
                 name: str,
                 net,
                 bus_a_idx: Union[int, float],
                 bus_b_idx: Union[int, float],
                 *,
                 closed: bool = True,
                 # tiny, numerically safe impedance (per-km) + short length:
                 length_km: float = 0.001,
                 r_ohm_per_km: float = 0.001,
                 x_ohm_per_km: float = 0.005,
                 c_nf_per_km: float = 0.0,
                 max_i_ka: float = 3.0,
                 r0_ohm_per_km: float = 0.003, 
                 x0_ohm_per_km: float = 0.015,
                 c0_nf_per_km: float = 0.0,
                 type: str = "ol"):
        self.name = name
        self._net = net
        a = int(bus_a_idx)
        b = int(bus_b_idx)

        # create a short line with tiny impedance between buses
        self._line_idx = pp.create_line_from_parameters(
            net, from_bus=a, to_bus=b, length_km=float(length_km),
            r_ohm_per_km=float(r_ohm_per_km),
            x_ohm_per_km=float(x_ohm_per_km),
            c_nf_per_km=float(c_nf_per_km),
            max_i_ka=float(max_i_ka),
            r0_ohm_per_km=float(r0_ohm_per_km),
            x0_ohm_per_km=float(x0_ohm_per_km),
            c0_nf_per_km=float(c0_nf_per_km),
            name=name, type=type
        )

        # treat "closed" as "in_service" for the line
        net.line.at[self._line_idx, "in_service"] = bool(closed)

        # mark for plotting (optional: your plotter can use this to draw dashed)
        try:
            # store alongside line meta so the line layer can pick it up
            net.line.at[self._line_idx, "_is_coupler"] = True
        except Exception:
            pass

        # also expose a flag on the object (if you still draw from substation.buslinks)
        self._is_coupler = True

    # --- compatibility helpers ------------------------------------------------

    @property
    def idx(self) -> int:
        """Return underlying line index (kept name 'idx' for backwards compat)."""
        return int(self._line_idx)

    @property
    def line_idx(self) -> int:
        """Explicit line index accessor (use this for CB/CT attach_line)."""
        return int(self._line_idx)

    @property
    def buses(self) -> tuple[int, int]:
        row = self._net.line.loc[self._line_idx]
        return int(row["from_bus"]), int(row["to_bus"])

    # "closed" maps to line.in_service for intuitive open/close semantics
    @property
    def closed(self) -> bool:
        return bool(self._net.line.at[self._line_idx, "in_service"])

    @closed.setter
    def closed(self, val: bool) -> None:
        self._net.line.at[self._line_idx, "in_service"] = bool(val)

    # keep an explicit in_service alias for symmetry
    @property
    def in_service(self) -> bool:
        return self.closed

    @in_service.setter
    def in_service(self, val: bool) -> None:
        self.closed = bool(val)

    # operations
    def open(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def toggle(self) -> None:
        self.closed = not self.closed

    def __repr__(self) -> str:
        a, b = self.buses
        state = "closed" if self.closed else "open"
        return f"<BusLink {self.name} line#{self._line_idx} {a}↔{b} {state}>"
