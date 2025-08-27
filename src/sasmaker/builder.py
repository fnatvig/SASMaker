# sasmaker/builders.py
from .busbar import Busbar
from .substation import Substation

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

def snap_child_to_slot(sub: Substation, parent: Busbar, child: Busbar, *,
                       slot_idx: int, busbar_length: float, drop: float = 0.5) -> None:
    """
    Move 'child' busbar to be straight under the parent's chosen CP.
    Sets child's x to CP_x and y to parent.y - drop.
    """
    cps = cp_xs(parent, busbar_length=busbar_length)
    if slot_idx < 0 or slot_idx >= len(cps):
        raise IndexError(f"slot_idx {slot_idx} out of range for {len(cps)} slots")
    px, py = parent.xy
    cx = cps[slot_idx]
    # write directly to pp coords (that’s what plotting reads)
    sub.net.bus.at[child.idx, "x"] = float(cx)
    sub.net.bus.at[child.idx, "y"] = float(py - drop)

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
