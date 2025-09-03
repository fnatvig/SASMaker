import pandapower as pp

class Busbar:
    """Wraps a pandapower bus; created on init."""
    def __init__(self, name: str, net, vn_kv: float, x: float = 0.0, y: float = 0.0,
                 draw_length: float | None = None,
                 draw_thickness: float | None = None,
                 draw_slots: int | None = None,
                 ext_grid: bool = False):
        self.name = name
        self._net = net
        self._devices = []
        self._bus_idx = pp.create_bus(net, vn_kv=vn_kv, name=name)
        # store coords (optional but useful for plotting)
        net.bus.at[self._bus_idx, "x"] = x
        net.bus.at[self._bus_idx, "y"] = y
        # plotting hints (do not affect pandapower)
        self._draw_length = draw_length
        self._draw_thickness = draw_thickness
        self._ext_grid = ext_grid
        self._draw_slots = int(draw_slots) if draw_slots is not None else 1

    @property
    def idx(self) -> int: return int(self._bus_idx)

    @property
    def vn_kv(self) -> float:
        return float(self._net.bus.at[self._bus_idx, "vn_kv"])

    @property
    def xy(self) -> tuple[float, float]:
        row = self._net.bus.loc[self._bus_idx]
        return float(row.get("x", 0.0)), float(row.get("y", 0.0))

    # visual helpers
    @property
    def draw_length(self): return self._draw_length
    @property
    def draw_thickness(self): return self._draw_thickness
    @property
    def draw_slots(self): return self._draw_slots

    def set_draw(self, *, length: float | None = None, thickness: float | None = None, slots: int | None = None):
        if length is not None: self._draw_length = float(length)
        if thickness is not None: self._draw_thickness = float(thickness)
        if slots is not None: self._draw_slots = int(slots)

    def __repr__(self):
        return f"<Busbar {self.name} idx={self.idx} vn={self.vn_kv} kV>"

