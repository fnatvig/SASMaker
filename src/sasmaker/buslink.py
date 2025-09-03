import pandapower as pp
from typing import Union

class BusLink:
    """
    Minimal intra-substation connection between two busbars.
    Backed by a pandapower bus-bus switch (et='b').
    """

    def __init__(self, name: str, net, bus_a_idx: Union[int, float], bus_b_idx: Union[int, float],
                 closed: bool = True):
        self.name = name
        self._net = net
        a = int(bus_a_idx)
        b = int(bus_b_idx)
        self._sw_idx = pp.create_switch(
            net, a, b, et='b', closed=bool(closed), name=name
        )

    @property
    def idx(self) -> int:
        return int(self._sw_idx)

    @property
    def buses(self) -> tuple[int, int]:
        # For et='b', 'bus' is one side and 'element' stores the other bus index
        row = self._net.switch.loc[self._sw_idx]
        return int(row["bus"]), int(row["element"])

    @property
    def closed(self) -> bool:
        return bool(self._net.switch.at[self._sw_idx, "closed"])

    @closed.setter
    def closed(self, val: bool) -> None:
        self._net.switch.at[self._sw_idx, "closed"] = bool(val)

    @property
    def in_service(self) -> bool:
        return bool(self._net.switch.at[self._sw_idx, "in_service"])

    @in_service.setter
    def in_service(self, val: bool) -> None:
        self._net.switch.at[self._sw_idx, "in_service"] = bool(val)

    def open(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def toggle(self) -> None:
        self.closed = not self.closed

    def __repr__(self) -> str:
        a, b = self.buses
        state = "closed" if self.closed else "open"
        return f"<BusLink {self.name} {a}↔{b} {state}>"
