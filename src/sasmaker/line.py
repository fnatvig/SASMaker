import pandapower as pp

class Line:
    """Wraps a pandapower line; created on init."""

    def __init__(self, name: str, net, from_bus_idx: int, to_bus_idx: int,
                 length_km: float, std_type: str | None = None,
                 r_ohm_per_km: float | None = None,
                 x_ohm_per_km: float | None = None,
                 c_nf_per_km: float | None = None,
                 max_i_ka: float | None = None,
                 r0_ohm_per_km: float | None = None,
                 x0_ohm_per_km: float | None = None,
                 c0_nf_per_km: float | None = None):

        self.name = name
        self._net = net

        if std_type is not None:
            # Use pandapower’s built-in std_type definition
            self._line_idx = pp.create_line(
                net, from_bus_idx, to_bus_idx, length_km=length_km,
                std_type=std_type, name=name
            )
        else:
            # Require all parameters for 3-phase line
            if None in (r_ohm_per_km, x_ohm_per_km, c_nf_per_km, max_i_ka,
                        r0_ohm_per_km, x0_ohm_per_km, c0_nf_per_km):
                raise ValueError("When std_type is None, you must provide full 3φ parameters "
                                 "(r, x, c, max_i + r0, x0, c0).")

            self._line_idx = pp.create_line_from_parameters(
                net, from_bus_idx, to_bus_idx, length_km=length_km,
                r_ohm_per_km=r_ohm_per_km, x_ohm_per_km=x_ohm_per_km,
                c_nf_per_km=c_nf_per_km, max_i_ka=max_i_ka,
                r0_ohm_per_km=r0_ohm_per_km, x0_ohm_per_km=x0_ohm_per_km,
                c0_nf_per_km=c0_nf_per_km, name=name
            )

    @property
    def idx(self) -> int:
        return int(self._line_idx)

    @property
    def buses(self) -> tuple[int, int]:
        row = self._net.line.loc[self._line_idx]
        return int(row["from_bus"]), int(row["to_bus"])

    @property
    def length_km(self) -> float:
        return float(self._net.line.at[self._line_idx, "length_km"])

    def __repr__(self):
        fb, tb = self.buses
        return f"<Line {self.name} idx={self.idx} {fb}->{tb} L={self.length_km} km>"
