import pandapower as pp

class BusLink:
    """
    Minimal intra-substation connection between two busbars.
    Backed by a pandapower bus-bus switch (et='b').
    """
    def __init__(self, name: str, net, bus_a_idx: int, bus_b_idx: int, closed: bool = True):
        self.name = name
        self._net = net
        # create a bus-bus switch
        self._sw_idx = pp.create_switch(net, bus_a_idx, bus_b_idx, et='b', closed=closed, name=name)

    @property
    def idx(self) -> int:
        return int(self._sw_idx)

    @property
    def buses(self) -> tuple[int, int]:
        row = self._net.switch.loc[self._sw_idx]
        return int(row["bus"]), int(row["element"])  # for et='b', element stores the other bus

    @property
    def closed(self) -> bool:
        return bool(self._net.switch.at[self._sw_idx, "closed"])

    def open(self):  self._net.switch.at[self._sw_idx, "closed"] = False
    def close(self): self._net.switch.at[self._sw_idx, "closed"] = True

    def __repr__(self):
        a, b = self.buses
        state = "closed" if self.closed else "open"
        return f"<BusLink {self.name} {a}↔{b} {state}>"
