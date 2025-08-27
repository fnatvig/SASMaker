import pandapower as pp

class Load:
    """
    Minimal three-phase load.
    - Always uses pandapower.create_asymmetric_load
    - Provide total P/Q; splits equally across phases by default
    """
    def __init__(self, name: str, net, bus_idx: int,
                 p_mw: float, q_mvar: float = 0.0,
                 phase_split: tuple[float, float, float] = (1/3, 1/3, 1/3),
                 in_service: bool = True):
        self.name = name
        self._net = net
        self._bus_idx = int(bus_idx)

        sa, sb, sc = phase_split
        if abs(sa + sb + sc - 1.0) > 1e-9:
            raise ValueError("phase_split must sum to 1.0")

        pa, pb, pc = p_mw * sa, p_mw * sb, p_mw * sc
        qa, qb, qc = q_mvar * sa, q_mvar * sb, q_mvar * sc

        self._idx = pp.create_asymmetric_load(
            net, bus=bus_idx,
            p_a_mw=pa, p_b_mw=pb, p_c_mw=pc,
            q_a_mvar=qa, q_b_mvar=qb, q_c_mvar=qc,
            in_service=in_service, name=name
        )

    @property
    def idx(self) -> int:       # element index in net.asymmetric_load
        return int(self._idx)

    @property
    def bus_idx(self) -> int:   # the bus this load is attached to
        return int(self._bus_idx)

    def set_power(self, p_mw: float, q_mvar: float = 0.0,
                  phase_split: tuple[float, float, float] = (1/3, 1/3, 1/3)):
        """Update total P/Q with optional new split."""
        sa, sb, sc = phase_split
        if abs(sa + sb + sc - 1.0) > 1e-9:
            raise ValueError("phase_split must sum to 1.0")
        pa, pb, pc = p_mw * sa, p_mw * sb, p_mw * sc
        qa, qb, qc = q_mvar * sa, q_mvar * sb, q_mvar * sc
        net = self._net
        net.asymmetric_load.at[self._idx, "p_a_mw"] = pa
        net.asymmetric_load.at[self._idx, "p_b_mw"] = pb
        net.asymmetric_load.at[self._idx, "p_c_mw"] = pc
        net.asymmetric_load.at[self._idx, "q_a_mvar"] = qa
        net.asymmetric_load.at[self._idx, "q_b_mvar"] = qb
        net.asymmetric_load.at[self._idx, "q_c_mvar"] = qc

    def __repr__(self):
        return f"<Load {self.name} idx={self.idx}>"
