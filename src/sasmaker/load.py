import pandapower as pp
import math
import random
random.seed(10)

class Load:
    """3φ load using pandapower's asymmetric_load (per-phase P/Q)."""
    def __init__(self, name: str, net, bus_idx: int, p_mw: float, q_mvar: float, draw_label: bool = True):
        self.name = name
        self._net = net
        self._bus_idx = int(bus_idx)
        self.base_p = float(p_mw)
        self.base_q = float(q_mvar)
        self.fa = 0.329
        self.fb = 0.333
        self.fc = 0.338
        self._draw_label = draw_label

        
        # Active power split
        pa = self.fa * p_mw
        pb = self.fb * p_mw
        pc = self.fc * p_mw
        
        qa = self.fa * q_mvar
        qb = self.fb * q_mvar
        qc = self.fc * q_mvar

        self.idx = pp.create_asymmetric_load(
            net,
            bus=self._bus_idx,        # use backing field here
            p_a_mw=pa, q_a_mvar=qa,
            p_b_mw=pb, q_b_mvar=qb,
            p_c_mw=pc, q_c_mvar=qc,
            name=name,
            in_service=True
        )

    @property
    def bus_idx(self) -> int:
        return self._bus_idx          # <-- return backing field (no recursion)

    def set_power(self, p_mw: float, q_mvar: float):
        """Overwrite per-phase powers with an equal split."""
        temp = random.random()
        
        if temp<0.3:
            pa = self.fa * p_mw
            pb = self.fb * p_mw
            pc = self.fc * p_mw
            qa = self.fa * q_mvar
            qb = self.fb * q_mvar
            qc = self.fc * q_mvar
        elif temp>0.6:
            pa = self.fc * p_mw
            pb = self.fa * p_mw
            pc = self.fb * p_mw
            qa = self.fc * q_mvar
            qb = self.fa * q_mvar
            qc = self.fb * q_mvar
        else: 
            pa = self.fb * p_mw
            pb = self.fc * p_mw
            pc = self.fa * p_mw
            qa = self.fb * q_mvar
            qb = self.fc * q_mvar
            qc = self.fa * q_mvar


        t = self._net.asymmetric_load
        i = self.idx
        t.at[i, "p_a_mw"] = pa; t.at[i, "q_a_mvar"] = qa
        t.at[i, "p_b_mw"] = pb; t.at[i, "q_b_mvar"] = qb
        t.at[i, "p_c_mw"] = pc; t.at[i, "q_c_mvar"] = qc


    def profile(self, base_p: float, base_q: float, t: float, period: float = 24.0):
        """
        Sinusoidal load profile
        """
        factor_p = 1.0 + 0.05*math.sin(2*math.pi * (t % period) / period)  # between 0.95 and 1.05
        factor_q = 1.0 + 0.05*math.sin(+2*math.pi * (t % period) / period + period/6)  # between 0.95 and 1.05
        self.set_power(base_p * factor_p, base_q * factor_q)

    def set_base(self, p_mw: float, q_mvar: float):
        self.base_p = float(p_mw); self.base_q = float(q_mvar)

    def apply(self):
        p = self.base_p * self.profile_mult * self.event_mult * self.noise_mult
        q = self.base_q * self.profile_mult * self.event_mult * self.noise_mult
