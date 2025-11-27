# sasmaker/lnode.py
from __future__ import annotations

class MMXU:
    """Measurements from a CT (kA)."""
    def __init__(self, ct):
        self._ct = ct

    def read(self):
        return self._ct.read_primary_current()

    def ia(self): return self.read()["Ia"]
    def ib(self): return self.read()["Ib"]
    def ic(self): return self.read()["Ic"]

class PTOC:
    """Instantaneous overcurrent (per-phase, no time)."""
    def __init__(self, pickup_ka: float = 1.5):
        self.pickup_ka = float(pickup_ka)
        self.enabled = True
        self.enable_a = True
        self.enable_b = True
        self.enable_c = True

    def evaluate(self, ia: float, ib: float, ic: float) -> bool:
        if not self.enabled:
            return False
        tripA = self.enable_a and (abs(ia) >= self.pickup_ka)
        tripB = self.enable_b and (abs(ib) >= self.pickup_ka)
        tripC = self.enable_c and (abs(ic) >= self.pickup_ka)
        return bool(tripA or tripB or tripC)

class PTRC:
    """Trip conditioning (latches a trip request)."""
    def __init__(self):
        self.trip = False

    def set_trip(self, val: bool):
        self.trip = bool(val)

class XCBR:
    """Breaker interface backed by a SASMaker CB."""
    def __init__(self, cb):
        self._cb = cb

    def open(self): self._cb.open()
    def close(self): self._cb.close()
    def closed(self) -> bool: return self._cb.closed
