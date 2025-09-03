import pandapower as pp
import math

class Load:
    """3φ load using pandapower's asymmetric_load (per-phase P/Q)."""
    def __init__(self, name: str, net, bus_idx: int, p_mw: float, q_mvar: float):
        self.name = name
        self._net = net
        self._bus_idx = int(bus_idx)   # <-- backing field
        self.base_p = float(p_mw)
        self.base_q = float(q_mvar)


        # equal per-phase split by default
        pa = p_mw / 3.0
        qa = q_mvar / 3.0

        self.idx = pp.create_asymmetric_load(
            net,
            bus=self._bus_idx,        # use backing field here
            p_a_mw=pa, q_a_mvar=qa,
            p_b_mw=pa, q_b_mvar=qa,
            p_c_mw=pa, q_c_mvar=qa,
            name=name,
            in_service=True
        )

    @property
    def bus_idx(self) -> int:
        return self._bus_idx          # <-- return backing field (no recursion)

    def set_power(self, p_mw: float, q_mvar: float):
        """Overwrite per-phase powers with an equal split."""
        pa = p_mw / 3.0
        qa = q_mvar / 3.0
        t = self._net.asymmetric_load
        i = self.idx
        t.at[i, "p_a_mw"] = pa; t.at[i, "q_a_mvar"] = qa
        t.at[i, "p_b_mw"] = pa; t.at[i, "q_b_mvar"] = qa
        t.at[i, "p_c_mw"] = pa; t.at[i, "q_c_mvar"] = qa


    def profile(self, base_p: float, base_q: float, t: float, period: float = 24.0):
        """
        Daily sinusoidal profile. 
        t in hours, period defaults to 24h.
        """
        factor_p = 1.0 + 0.05*math.sin(2*math.pi * (t % period) / period)  # between 0.95 and 1.05
        factor_q = 1.0 + 0.05*math.sin(+2*math.pi * (t % period) / period + period/6)  # between 0.95 and 1.05
        self.set_power(base_p * factor_p, base_q * factor_q)

    def set_base(self, p_mw: float, q_mvar: float):
        self.base_p = float(p_mw); self.base_q = float(q_mvar)

    def apply(self):
        p = self.base_p * self.profile_mult * self.event_mult * self.noise_mult
        q = self.base_q * self.profile_mult * self.event_mult * self.noise_mult
