# sasmaker/vt.py
import math
from typing import Optional, Union, Iterable

class VT:
    """
    3-phase VT attached to ONE line endpoint ('from' or 'to'), with an
    associated IED responsible for it (by name). Can additionally show
    connections to *other* buses for reference/coupling in the diagram.
    """
    def __init__(self, name: str):
        self.name = name
        self._net = None
        self._line_id: Optional[int] = None
        self._side: Optional[str] = None
        self._ied_name: Optional[str] = None
        self._extra_buses: list[int] = []

    # --- configuration ---
    def attach_line(self, net, line_id: int, side: str,
                    ied: Optional[Union[str, "IED"]] = None,
                    link_buses: Optional[Iterable[Union[int, "BusBar"]]] = None):
        if side not in ("from", "to"):
            raise ValueError("side must be 'from' or 'to'")
        self._net = net
        self._line_id = int(line_id)
        self._side = side
        if ied is not None:
            self.set_ied(ied)
        if link_buses:
            self.add_link_buses(link_buses)
        return self

    def set_ied(self, ied: Union[str, "IED"]):
        self._ied_name = ied if isinstance(ied, str) else ied.name

    def add_link_buses(self, buses: Iterable[Union[int, "BusBar"]]):
        """
        Add extra bus indices (besides the measured endpoint) to draw VT
        symbols and dashed connections to the IED.
        """
        for b in buses:
            idx = int(b.idx) if hasattr(b, "idx") else int(b)
            if idx not in self._extra_buses:
                self._extra_buses.append(idx)

    @property
    def ied_name(self) -> Optional[str]:
        return self._ied_name

    @property
    def link_buses(self) -> list[int]:
        return list(self._extra_buses)

    # --- geometry helpers ---
    def endpoint_bus(self) -> int:
        if self._net is None or self._line_id is None or self._side is None:
            raise RuntimeError("VT is not attached.")
        line_tbl = self._net.line
        return int(line_tbl.at[self._line_id,
                               "from_bus" if self._side == "from" else "to_bus"])
    
    def get_bus_name(self) -> Optional[str]:
        return self._net.bus.loc[self.link_buses[0], "name"]

    def other_bus(self) -> int:
        line_tbl = self._net.line
        return int(line_tbl.at[self._line_id,
                               "to_bus" if self._side == "from" else "from_bus"])

    def endpoint_xy_and_dir(self):
        b_here = self.endpoint_bus()
        b_other = self.other_bus()
        xh = float(self._net.bus.at[b_here,  "x"]); yh = float(self._net.bus.at[b_here,  "y"])
        xo = float(self._net.bus.at[b_other, "x"]); yo = float(self._net.bus.at[b_other, "y"])
        dx, dy = (xo - xh), (yo - yh)
        L = math.hypot(dx, dy)
        if L == 0: return xh, yh, 1.0, 0.0
        return xh, yh, dx / L, dy / L
    
    # --- measurement ---
    def read_voltage(self) -> dict:

        if self._net is None:
            raise RuntimeError("VT not attached to any network")

        if self.link_buses[0] is not None:
            df = self._net.res_bus_3ph
            Va = float(df.at[self.link_buses[0], "vm_a_pu"])
            Vb = float(df.at[self.link_buses[0], "vm_b_pu"])
            Vc = float(df.at[self.link_buses[0], "vm_c_pu"])
            return {"Va": Va, "Vb": Vb, "Vc": Vc}
        


