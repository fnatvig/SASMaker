# sasmaker/ied.py
from __future__ import annotations
from typing import Optional, Dict
from .ct import CT
from .cb import CB
from .lnode import MMXU, PTOC, PTRC, XCBR 

class IED:
    """
    Minimal IED container with tiny logical nodes:
      - MMXU (measurements from CT)
      - PTOC (overcurrent)
      - PTRC (trip output)
      - XCBR (breaker interface)
    External comms (libiec61850) bind via datapoint_get/datapoint_set callbacks.
    """
    def __init__(self, name: str, ct: Optional[CT] = None, cb: Optional[CB] = None):
        self.name = name
        self.mmxu = MMXU(ct) if ct else None
        self.ptoc = PTOC()        # can be disabled by not arming it
        self.ptrc = PTRC()
        self.xcbr = XCBR(cb) if cb else None
        self.ct = ct.name if ct else None
        self.cb = cb.name if cb else None
        self.bb = ct.get_bus_name() if ct else None
        
        # simple datapoint registry {str: callable}
        self._dp_get: Dict[str, callable] = {}
        self._dp_set: Dict[str, callable] = {}

        self._wire_default_points()

    def _wire_default_points(self):
        # Expose a few common points for the comm layer to read/write.
        # Reads
        if self.mmxu:
            self._dp_get[f"{self.name}/MMXU1.A.phsA.cVal.mag.f"] = lambda: self.mmxu.ia()
            self._dp_get[f"{self.name}/MMXU1.A.phsB.cVal.mag.f"] = lambda: self.mmxu.ib()
            self._dp_get[f"{self.name}/MMXU1.A.phsC.cVal.mag.f"] = lambda: self.mmxu.ic()
        if self.xcbr:
            self._dp_get[f"{self.name}/XCBR1.Pos.stVal"] = lambda: 1 if self.xcbr.closed() else 0
        # Writes (controls)
        if self.xcbr:
            self._dp_set[f"{self.name}/XCBR1.Pos.ctlVal"] = \
                lambda val: self.xcbr.close() if val else self.xcbr.open()

    # --- external comm glue ---
    def datapoint_get(self, ref: str):
        fn = self._dp_get.get(ref)
        if fn is None:
            raise KeyError(ref)
        return fn()

    def datapoint_set(self, ref: str, value):
        fn = self._dp_set.get(ref)
        if fn is None:
            raise KeyError(ref)
        return fn(value)

    # --- logic tick ---
    def tick(self):
        """Pull measurements, evaluate protection, operate trip if armed."""
        ia = ib = ic = None
        if self.mmxu:
            meas = self.mmxu.read()
            ia, ib, ic = meas["Ia"], meas["Ib"], meas["Ic"]

        trip_req = False
        if self.ptoc and ia is not None:
            trip_req = self.ptoc.evaluate(ia, ib, ic)  # OR of phases (very minimal)

        if self.ptrc:
            if trip_req:
                print(self.name + " trip")
            self.ptrc.set_trip(trip_req)

        if self.ptrc.trip and self.xcbr:
            self.xcbr.open()  # operate the breaker