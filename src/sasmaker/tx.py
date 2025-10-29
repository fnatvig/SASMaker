# tx.py
from __future__ import annotations

import pandapower as pp
import pandas as pd
from typing import Optional, Literal, Any, Tuple, Dict

Side = Literal["hv", "lv"]


# ----------------------------- helpers -----------------------------

def _bus_index(net: pp.pandapowerNet, b: Any) -> int:
    """
    Accepts:
      - plain bus index (int)
      - a Busbar-like object with .idx
      - a bus name (str) present in net.bus['name']
    Returns the integer bus index or raises TypeError/ValueError.
    """
    # Busbar-like object from SASMaker
    if hasattr(b, "idx"):
        return int(getattr(b, "idx"))

    # Plain integer index
    if isinstance(b, int):
        return b

    # Name lookup
    if isinstance(b, str):
        matches = net.bus.index[net.bus["name"] == b]
        if len(matches) == 0:
            raise ValueError(f"No bus named {b!r} in net.bus['name'].")
        return int(matches[0])

    # Fallback (numpy types etc.)
    try:
        return int(b)
    except Exception as e:
        raise TypeError(f"Unsupported bus specifier {b!r} (type {type(b).__name__}).") from e


def _bus_vn_kv(net: pp.pandapowerNet, b: Any) -> float:
    """Return the nominal voltage (kV) for a bus specified by index/name/Busbar."""
    bi = _bus_index(net, b)
    return float(net.bus.at[bi, "vn_kv"])


def _find_trafo_std_by_voltages(
    net: pp.pandapowerNet,
    hv_kv: float,
    lv_kv: float,
    tol: float = 1e-6
) -> Optional[str]:
    """
    Search existing trafo std types in `net` for one whose (vn_hv_kv, vn_lv_kv)
    matches (hv_kv, lv_kv) up to `tol`. Also allows swapped ordering.
    Returns the std type name or None if not found.
    """
    try:
        names = pp.std_types.available_std_types(net, "trafo")
    except Exception:
        names = []

    for nm in names:
        try:
            data = pp.std_types.load_std_type(net, nm, "trafo")
            v1 = float(data["vn_hv_kv"])
            v2 = float(data["vn_lv_kv"])
        except Exception:
            continue

        if abs(v1 - hv_kv) < tol and abs(v2 - lv_kv) < tol:
            return nm
        if abs(v1 - lv_kv) < tol and abs(v2 - hv_kv) < tol:
            return nm

    return None


# ------------------------------ TX -------------------------------

class TX:
    """
    Two-winding transformer wrapper for pandapower.

    Attach modes:
      - attach_std(...): use an existing std type by name
      - attach_params(...): provide all electrical parameters explicitly
      - attach_auto(...): infer by bus voltages; reuse a matching std type if found,
                          otherwise create from parameters (and optionally register a std type)

    Example:
        tx = TX("T1").attach_auto(net, hv_bus=b_hv, lv_bus=b_lv, sn_mva=25.0)
        tx.step(+1)   # tap up one step (if taps configured)
        tx.open()     # set in_service = False
        mx, my = tx.midpoint_xy()  # for plotting
    """

    def __init__(self, name: Optional[str] = None):
        self.name: str = name or "TX"
        self._net: Optional[pp.pandapowerNet] = None
        self._idx: Optional[int] = None
        self._hv: Optional[int] = None
        self._lv: Optional[int] = None

    # ---------------------- creation / attach ----------------------

    def attach_std(self, net, *, hv_bus, lv_bus, std_type: str, in_service: bool = True):
        self._net = net
        self._hv = _bus_index(net, hv_bus)
        self._lv = _bus_index(net, lv_bus)
        self._idx = pp.create_transformer(
            net, hv_bus=self._hv, lv_bus=self._lv,
            std_type=std_type, name=self.name, in_service=bool(in_service)
        )
        # ensure columns exist
        for col in ("vector_group", "vk0_percent", "vkr0_percent", "mag0_percent", "mag0_rx"):
            if col not in net.trafo.columns:
                net.trafo[col] = pd.NA
        # sensible defaults if missing
        if pd.isna(net.trafo.at[self._idx, "vector_group"]):
            net.trafo.at[self._idx, "vector_group"] = "Dyn"
        if pd.isna(net.trafo.at[self._idx, "vk0_percent"]):
            net.trafo.at[self._idx, "vk0_percent"] = net.trafo.at[self._idx, "vk_percent"]
        if pd.isna(net.trafo.at[self._idx, "vkr0_percent"]):
            net.trafo.at[self._idx, "vkr0_percent"] = net.trafo.at[self._idx, "vkr_percent"]
        if pd.isna(net.trafo.at[self._idx, "mag0_percent"]):
            net.trafo.at[self._idx, "mag0_percent"] = 100.0
        if pd.isna(net.trafo.at[self._idx, "mag0_rx"]):
            net.trafo.at[self._idx, "mag0_rx"] = 0.1
        if pd.isna(net.trafo.at[self._idx, "si0_hv_partial"]):           
            net.trafo.at[self._idx, "si0_hv_partial"] = 0.9
        return self


    def attach_params(self, net, *, hv_bus, lv_bus, **params):
        self._net = net
        self._hv = _bus_index(net, hv_bus)
        self._lv = _bus_index(net, lv_bus)

        # defaults for 3-phase / zero-sequence modeling
        params.setdefault("vector_group", "Dyn")
        if "vk_percent" in params and "vk0_percent" not in params:
            params["vk0_percent"] = params["vk_percent"]
        if "vkr_percent" in params and "vkr0_percent" not in params:
            params["vkr0_percent"] = params["vkr_percent"]
        params.setdefault("mag0_percent", 100.0)
        params.setdefault("mag0_rx", 0.1)
        params.setdefault("si0_hv_partial", 0.9)

        self._idx = pp.create_transformer_from_parameters(
            net, hv_bus=self._hv, lv_bus=self._lv, name=self.name, **params
        )
        return self



    def attach_auto(
        self,
        net: pp.pandapowerNet,
        *,
        hv_bus: Any,
        lv_bus: Any,
        sn_mva: float = 25.0,
        in_service: bool = True,
        register_if_missing: bool = True,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> "TX":
        """
        Auto-pick transformer based on bus voltages.

        Steps:
          1) Look for an existing std type matching (vn_hv_kv, vn_lv_kv) of the buses.
          2) If found -> use it.
          3) Else -> create from parameters using `defaults` (or built-ins).
             If `register_if_missing=True`, register a canonical std type label
             like "25 MVA 66/20 kV" and then use it; otherwise create directly
             from parameters without registering.

        `defaults` can override the built-in parameter template (vk_percent, taps, etc.).
        """
        self._net = net
        self._hv = _bus_index(net, hv_bus)
        self._lv = _bus_index(net, lv_bus)

        hv_kv = _bus_vn_kv(net, hv_bus)
        lv_kv = _bus_vn_kv(net, lv_bus)

        # 1) try existing std type
        match = _find_trafo_std_by_voltages(net, hv_kv, lv_kv)
        if match:
            self._idx = pp.create_transformer(
                net,
                hv_bus=self._hv,
                lv_bus=self._lv,
                std_type=match,
                name=self.name,
                in_service=bool(in_service),
            )
            return self

        # 2) build parameter dict
        params: Dict[str, Any] = dict(
            sn_mva=sn_mva,
            vn_hv_kv=hv_kv,
            vn_lv_kv=lv_kv,
            vk_percent=10.0,
            vkr_percent=0.75,
            pfe_kw=20.0,
            i0_percent=0.10,
            shift_degree=0.0,
            vector_group="Dyn",
            vk0_percent=12.0,      # default = vk_percent
            vkr0_percent=0.25,     # default = vkr_percent
            mag0_percent=100.0,   # NEW
            mag0_rx=0.1,
            si0_hv_partial=0.9,
            # tap defaults (remove or edit if you don't want taps by default)
            tap_side="hv",
            tap_neutral=0,
            tap_min=-5,
            tap_max=5,
            tap_step_percent=1.5,
            tap_step_degree=0.0,
            tap_pos=1,
        )
        if defaults:
            params.update(defaults)

        if register_if_missing:
            # Create & reuse a canonical std-type name
            nm = f"{int(round(sn_mva))} MVA {int(round(hv_kv))}/{int(round(lv_kv))} kV"
            if nm not in pp.std_types.available_std_types(net, "trafo"):
                pp.create_std_type(net, params, name=nm, element="trafo")
            self._idx = pp.create_transformer(
                net,
                hv_bus=self._hv,
                lv_bus=self._lv,
                std_type=nm,
                name=self.name,
                in_service=bool(in_service),
            )
        else:
            print("hej")
            self._idx = pp.create_transformer_from_parameters(
                net,
                hv_bus=self._hv,
                lv_bus=self._lv,
                name=self.name,
                in_service=bool(in_service),
                **params,
            )

        return self

    # --------------------------- state -----------------------------

    @property
    def idx(self) -> int:
        if self._idx is None:
            raise RuntimeError("Transformer not attached to a network.")
        return int(self._idx)

    @property
    def in_service(self) -> bool:
        return bool(self._net.trafo.at[self.idx, "in_service"])

    @in_service.setter
    def in_service(self, val: bool) -> None:
        self._net.trafo.at[self.idx, "in_service"] = bool(val)

    def open(self) -> None:
        self.in_service = False

    def close(self) -> None:
        self.in_service = True

    def toggle(self) -> None:
        self.in_service = not self.in_service

    # ---------------------------- taps -----------------------------

    @property
    def has_tap(self) -> bool:
        row = self._net.trafo.loc[self.idx]
        # Presence of either side/step metadata suggests a tap changer exists
        return ("tap_side" in row and row["tap_side"] is not None) or \
               ("tap_step_percent" in row and row["tap_step_percent"] is not None)

    @property
    def tap_position(self) -> Optional[int]:
        if "tap_pos" not in self._net.trafo.columns:
            return None
        return self._net.trafo.at[self.idx, "tap_pos"]

    @tap_position.setter
    def tap_position(self, pos: int) -> None:
        if "tap_pos" not in self._net.trafo.columns:
            raise RuntimeError("This transformer has no taps configured (no 'tap_pos' column).")
        self._net.trafo.at[self.idx, "tap_pos"] = int(pos)

    def step(self, delta: int) -> None:
        tp = self.tap_position
        if tp is None:
            raise RuntimeError("No tap configuration present on this transformer.")
        self.tap_position = int(tp) + int(delta)

    # -------------------------- metadata ---------------------------

    @property
    def hv_bus(self) -> int:
        return int(self._net.trafo.at[self.idx, "hv_bus"])

    @property
    def lv_bus(self) -> int:
        return int(self._net.trafo.at[self.idx, "lv_bus"])

    def buses(self) -> Tuple[int, int]:
        """(hv_bus, lv_bus) indices."""
        return (self.hv_bus, self.lv_bus)

    # --------------------- plotting convenience --------------------

    def midpoint_xy(self) -> Tuple[float, float]:
        """
        Midpoint between HV and LV bus coordinates (for symbol placement).
        Requires net.bus to have 'x' and 'y' columns populated.
        """
        bx_h = float(self._net.bus.at[self.hv_bus, "x"])
        by_h = float(self._net.bus.at[self.hv_bus, "y"])
        bx_l = float(self._net.bus.at[self.lv_bus, "x"])
        by_l = float(self._net.bus.at[self.lv_bus, "y"])
        return (0.5 * (bx_h + bx_l), 0.5 * (by_h + by_l))
