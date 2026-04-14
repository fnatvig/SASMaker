# sasmaker/builder.py
from .busbar import Busbar
from .substation import Substation

# --- robust coordinate setter (call this instead of child.xy = (...)) ---
def _set_busbar_xy(sub: "Substation", bb: "Busbar", x: float, y: float) -> None:
    x = float(x); y = float(y)
    # 1) update Busbar object
    if hasattr(bb, "set_xy") and callable(bb.set_xy):
        bb.set_xy(x, y)
    elif hasattr(bb, "x") and hasattr(bb, "y"):
        try:
            setattr(bb, "x", x); setattr(bb, "y", y)
        except Exception:
            if hasattr(bb, "_x") and hasattr(bb, "_y"):
                bb._x, bb._y = x, y
            else:
                object.__setattr__(bb, "x", x); object.__setattr__(bb, "y", y)
    elif hasattr(bb, "_x") and hasattr(bb, "_y"):
        bb._x, bb._y = x, y
    else:
        object.__setattr__(bb, "x", x); object.__setattr__(bb, "y", y)

    # 2) mirror to pandapower net
    bus_df = sub.net.bus
    if "x" not in bus_df.columns: bus_df["x"] = float("nan")
    if "y" not in bus_df.columns: bus_df["y"] = float("nan")
    if bb.idx not in bus_df.index:
        raise KeyError(f"Bus index {bb.idx} not found in net.bus.index")
    bus_df.loc[bb.idx, ["x", "y"]] = [x, y]


def cp_xs(parent: Busbar, *, busbar_length: float) -> list[float]:
    """
    Return CP x-positions for a busbar:
      - if parent.draw_slots = N: N CPs spread with the "single length" = busbar_length
      - else: one CP at the bar center
    """
    x, _y = parent.xy
    slots = getattr(parent, "draw_slots", None)
    if slots and slots > 0:
        L = slots * busbar_length
        left = x - L/2.0
        return [left + (busbar_length * 0.5) + k * busbar_length for k in range(slots)]
    else:
        return [x]


def snap_child_to_slot(
    sub: "Substation",
    parent: "Busbar",
    child: "Busbar",
    *,
    slot_idx: int,                # parent CP to align under (0..parent_slots-1)
    drop: float = 0.5,            # vertical distance; positive = below parent
    busbar_length: float = 0.2,   # MUST match plot_one_line(...)
    child_slot_idx: int | None = None,  # which child CP to use (default = “middle”)
) -> None:
    """
    Place 'child' so that child.CP[child_slot_idx] is exactly under parent.CP[slot_idx].
    Works for any (odd/even) draw_slots on both parent and child.
    """

    # --- parent CP target x ---
    parent_cpx = cp_xs(parent, busbar_length=busbar_length)
    if not (0 <= slot_idx < len(parent_cpx)):
        raise IndexError(f"slot_idx {slot_idx} out of range for parent with {len(parent_cpx)} slots")
    target_x = parent_cpx[slot_idx]

    # --- child CP geometry ---
    c_slots = int(getattr(child, "draw_slots", 1) or 1)
    Lc = c_slots * busbar_length if c_slots > 0 else busbar_length

    # pick default child CP if not provided:
    if child_slot_idx is None:
        # odd: true middle; even: left of the two middle CPs (pick 1 for the right one)
        child_slot_idx = (c_slots // 2) if (c_slots % 2 == 1) else (c_slots // 2 - 1)

    if not (0 <= child_slot_idx < c_slots):
        raise IndexError(f"child_slot_idx {child_slot_idx} out of range for child with {c_slots} slots")

    # Solve for child center x such that:
    # child_CP[k] = (child_center - Lc/2) + (busbar_length*0.5) + k*busbar_length == target_x
    child_center_x = target_x - (busbar_length * 0.5) - child_slot_idx * busbar_length + (Lc / 2.0)

    # New coordinates (vertically below parent by 'drop')
    _px, py = parent.xy
    new_x = float(child_center_x)
    new_y = float(py - drop)

    # Update busbar + net
    _set_busbar_xy(sub, child, new_x, new_y)


def arrange_children_centered(sub: Substation, parent: Busbar, children: list[Busbar], *,
                              busbar_length: float, drop: float = 0.5) -> None:
    """
    Center the given children across the parent's available CPs.
    If children <= slots: picks centered CPs left→right.
    If children > slots: raise (ask caller to increase draw_slots).
    """
    cps = cp_xs(parent, busbar_length=busbar_length)
    n_slots = len(cps)
    n_child = len(children)
    if n_child > n_slots:
        raise ValueError(f"{parent.name}: {n_child} children but only {n_slots} CPs. "
                         f"Increase draw_slots (currently {getattr(parent, 'draw_slots', None)}).")

    # choose centered indices, e.g. slots=[0,1,2,3,4], n_child=2 -> pick [1,3]
    if n_child == 0:
        return
    if n_child == n_slots:
        chosen = list(range(n_slots))
    else:
        # spread using round-robin across slots (centered)
        step = n_slots / (n_child + 1)
        chosen = [round((i+1) * step) for i in range(n_child)]
        # clamp to valid indices and make unique/ordered
        chosen = sorted(max(0, min(n_slots-1, idx)) for idx in chosen)

        # if duplicates happen due to rounding on small slot counts,
        # fix by nudging to nearest free slot.
        used = set()
        fixed = []
        for idx in chosen:
            j = idx
            while j in used:
                # try expand right then left
                right = j+1
                left  = j-1
                if right < n_slots and right not in used:
                    j = right
                elif left >= 0 and left not in used:
                    j = left
                else:
                    break
            used.add(j); fixed.append(j)
        chosen = fixed

    # apply positions
    px, py = parent.xy
    for child, slot_idx in zip(children, chosen):
        cx = cps[slot_idx]
        sub.net.bus.at[child.idx, "x"] = float(cx)
        sub.net.bus.at[child.idx, "y"] = float(py - drop)
