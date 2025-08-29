# sasmaker/util.py
import pandas as pd

BUS_REF_COLS = {"bus", "from_bus", "to_bus", "hv_bus", "lv_bus"}

def _fix_ref_cols(df, name):
    if df is None or df.empty:
        return
    # cast any bus reference columns to int64 (no floats allowed)
    for c in set(df.columns) & BUS_REF_COLS:
        if df[c].dtype != "int64":
            df[c] = pd.to_numeric(df[c], errors="raise").astype("int64")
        if df[c].isna().any():
            raise ValueError(f"NaN in {name}.{c}")
    # element references (e.g., switch.element) must be int64 too
    if "element" in df.columns and df["element"].dtype != "int64":
        df["element"] = pd.to_numeric(df["element"], errors="raise").astype("int64")
    # in_service must be bool
    if "in_service" in df.columns and df["in_service"].dtype != bool:
        df["in_service"] = df["in_service"].astype(bool)

def sanitize_net_3ph(net):
    # bus index int64, in_service bool
    if not net.bus.empty:
        if net.bus.index.dtype != "int64":
            net.bus.index = pd.to_numeric(net.bus.index, errors="raise").astype("int64")
        if "in_service" in net.bus and net.bus["in_service"].dtype != bool:
            net.bus["in_service"] = net.bus["in_service"].astype(bool)

    # scan common 3φ tables
    for name in ("line_3ph","line","ext_grid_3ph","ext_grid",
                 "load_3ph","load","shunt_3ph","shunt",
                 "trafo_3ph","trafo","switch","impedance"):
        df = getattr(net, name, None)
        if df is not None:
            _fix_ref_cols(df, name)
