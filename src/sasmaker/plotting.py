import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from math import isclose

def _edge_point_towards(x, y, L, T, x_to, y_to):
    dx, dy = (x_to - x), (y_to - y)
    if dx == 0 and dy == 0: return (x, y)
    if abs(dx) * T >= abs(dy) * L:  # left/right
        ex = x + (L/2 if dx > 0 else -L/2)
        t = 0 if dx == 0 else (ex - x) / dx
        ey = y + t * dy
    else:                            # top/bottom
        ey = y + (T/2 if dy > 0 else -T/2)
        t = 0 if dy == 0 else (ey - y) / dy
        ex = x + t * dx
    return (ex, ey)

def _edge_point_vertical(x_bar, y_bar, L, T, *, top: bool, x_target: float):
    half = L / 2.0
    x_hit = min(max(x_target, x_bar - half), x_bar + half)
    y_edge = y_bar + (T/2 if top else -T/2)
    return (x_hit, y_edge)

def _draw_busbar(ax, x, y, L, T=0.01, color="black"):
    rect = Rectangle((x - L/2, y - T/2), L, T, facecolor=color, edgecolor=color, zorder=20)
    ax.add_patch(rect)

def plot_one_line(substation, *,
                  busbar_length=0.2,            # ← “single” length (base unit)
                  busbar_thickness=0.01,
                  line_width=1.5, line_color="black",
                  buslink_width=1.0, buslink_color="#555555", buslink_style="--",
                  label_buses=True, label_lines=False, label_buslinks=False,
                  show=True):
    """One-line view with connection points (CPs) every 'busbar_length'.
       If a busbar has draw_slots = N, its visual length is N * busbar_length and it exposes N CPs:
         single:  [½L]-[CP]-[½L]
         double:  [½L]-[CP]-[L]-[CP]-[½L]
         triple:  [½L]-[CP]-[L]-[CP]-[L]-[CP]-[½L]
       Lines & loads start from the nearest CP on the correct edge.
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    # --- gather coords & per-bus visual sizes and CPs ---
    bus_xy, bus_L, bus_T, bus_CPX = {}, {}, {}, {}
    for bb in substation.busbars.values():
        x, y = bb.xy
        slots = getattr(bb, "draw_slots", None)
        L = (slots * busbar_length) if (slots and slots > 0) else (getattr(bb, "draw_length", None) or busbar_length)
        T = getattr(bb, "draw_thickness", None) or busbar_thickness

        _draw_busbar(ax, x, y, L, T)
        bus_xy[bb.idx] = (x, y)
        bus_L[bb.idx]  = L
        bus_T[bb.idx]  = T

        # compute CPs along the bar
        if slots and slots > 0:
            left = x - L/2.0
            cpx = [left + (busbar_length*0.5) + k*busbar_length for k in range(slots)]
        else:
            # treat as “single” visually (1 CP at center)
            cpx = [x]
        bus_CPX[bb.idx] = cpx

        if label_buses:
            if bb._ext_grid:
                ax.text(x, y + T*1.2, f"{bb.name}",
                        ha="center", va="bottom", fontsize=9, zorder=100)
            else:
                ax.text(x, y + T*1.2, f"{bb.name}-{bb.vn_kv}kV",
                        ha="center", va="bottom", fontsize=9, zorder=100)

    def _nearest_cp_x(bus_idx: int, x_target: float) -> float:
        cpx = bus_CPX[bus_idx]
        return min(cpx, key=lambda xx: abs(xx - x_target))

    # epsilon to detect “x-aligned” (choose vertical routing)
    EPS = 1e-9

    # --- draw feeder/transmission lines (snap to CPs) ---
    for name, ln in substation.lines.items():
        fb, tb = ln.buses
        x1, y1 = bus_xy[fb]; L1, T1 = bus_L[fb], bus_T[fb]
        x2, y2 = bus_xy[tb]; L2, T2 = bus_L[tb], bus_T[tb]

        # If x aligned, draw vertical parent→child using CP nearest to child x
        if abs(x1 - x2) <= EPS and y1 != y2:
            # parent = higher y
            if y1 > y2:
                sx, sy = _edge_point_vertical(x1, y1, L1, T1, top=False, x_target=_nearest_cp_x(fb, x2))
                ex, ey = _edge_point_vertical(x2, y2, L2, T2, top=True,  x_target=x2)
            else:
                sx, sy = _edge_point_vertical(x2, y2, L2, T2, top=False, x_target=_nearest_cp_x(tb, x1))
                ex, ey = _edge_point_vertical(x1, y1, L1, T1, top=True,  x_target=x1)
            ax.plot([sx, ex], [sy, ey], linewidth=line_width, color=line_color, zorder=2)
        else:
            # generic: start at CP on the correct edge (top/bottom), then straight segment
            # pick edge by relative y (if almost equal, fall back to “towards”)
            if not isclose(y1, y2, abs_tol=1e-12):
                top1 = y2 > y1
                top2 = y1 > y2
                s1 = _edge_point_vertical(x1, y1, L1, T1, top=top1, x_target=_nearest_cp_x(fb, x2))
                s2 = _edge_point_vertical(x2, y2, L2, T2, top=top2, x_target=_nearest_cp_x(tb, x1))
                ax.plot([s1[0], s2[0]], [s1[1], s2[1]], linewidth=line_width, color=line_color, zorder=2)
            else:
                # same height → keep your previous edge projection
                p1 = _edge_point_towards(x1, y1, L1, T1, x2, y2)
                p2 = _edge_point_towards(x2, y2, L2, T2, x1, y1)
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], linewidth=line_width, color=line_color, zorder=2)

        if label_lines:
            # midpoint label
            xm = (x1 + x2) / 2.0; ym = (y1 + y2) / 2.0
            ax.text(xm, ym, name, fontsize=8, ha="center", va="center", zorder=4)

    # --- draw intra-substation bus links (dashed) — leave as before (edge-to-edge) ---
    for name, bl in substation.buslinks.items():
        a, b = bl.buses
        x1, y1 = bus_xy[a]; L1, T1 = bus_L[a], bus_T[a]
        x2, y2 = bus_xy[b]; L2, T2 = bus_L[b], bus_T[b]
        p1 = _edge_point_towards(x1, y1, L1, T1, x2, y2)
        p2 = _edge_point_towards(x2, y2, L2, T2, x1, y1)
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]],
                linewidth=buslink_width, color=buslink_color, linestyle=buslink_style,
                zorder=2, alpha=1.0 if bl.closed else 0.3)
        if label_buslinks:
            xm, ym = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
            ax.text(xm, ym, f"{name} ({'closed' if bl.closed else 'open'})",
                    fontsize=8, ha="center", va="center", zorder=4)

    # --- draw loads: stub from the nearest CP on the bottom edge ---
    for name, ld in substation.loads.items():
        b = ld.bus_idx
        x, y = float(substation.net.bus.at[b, "x"]), float(substation.net.bus.at[b, "y"])
        Lb, Tb = bus_L[b], bus_T[b]
        cp_x = _nearest_cp_x(b, x)           # snap to nearest CP
        sx, sy = _edge_point_vertical(x, y, Lb, Tb, top=False, x_target=cp_x)
        stub_len = 0.05
        ex, ey = cp_x, sy - stub_len
        ax.plot([sx, ex], [sy, ey], color="black", linewidth=1.5, zorder=2)
        ax.scatter([ex], [ey], marker="v", color="black", s=40, zorder=3)
        ax.text(ex, ey - 0.05, name, ha="center", va="top", fontsize=8, zorder=4)

    # --- draw CBs: support line-end *and* buslink CBs ------------------------
    cb_plot_pos = {}  # name -> (px, py)

    def _draw_cb_symbol(px, py, *, closed: bool, size=0.015, color="#FF0000"):
        # small square; filled if closed, outlined with a diagonal "gap" if open
        rect_x = [px - size, px + size, px + size, px - size]
        rect_y = [py - size, py - size, py + size, py + size]
        if closed:
            ax.fill(rect_x + [rect_x[0]], rect_y + [rect_y[0]], linewidth=1.2, color=color, zorder=101)
        else:
            ax.fill(rect_x + [rect_x[0]], rect_y + [rect_y[0]],
                    facecolor="white", edgecolor=color, linewidth=1.2, zorder=101)
            # diagonal gap line
            # ax.plot([px - size*0.7, px + size*0.7],
            #         [py + size*0.7, py - size*0.7],
            #         color=color, linewidth=1.2, zorder=102)

    for name, cb in substation.cbs.items():
        target_kind = getattr(cb, "target_kind", "line")

        if target_kind == "line":
            # ----- line-end CB (your old logic, but wrapped) -----
            b_here = cb.endpoint_bus()
            xh, yh = bus_xy[b_here]
            Lh, Th = bus_L[b_here], bus_T[b_here]
            # decide top/bottom by other bus
            try:
                b_oth = cb.other_bus()
                xo, yo = bus_xy[b_oth]
                top_edge = (yo > yh)
                target_x = xo
            except Exception:
                _, _, _, uy = cb.endpoint_xy_and_dir()
                top_edge = (uy > 0.0)
                target_x = xh

            # anchor at nearest CP
            cp_x = _nearest_cp_x(b_here, target_x)
            sx, sy = _edge_point_vertical(xh, yh, Lh, Th, top=top_edge, x_target=cp_x)

            sign = 1.0 if top_edge else -1.0
            gap = max(Th * 1.5, 0.08)
            px, py = cp_x, sy + sign * gap
            cb_plot_pos[name] = (px, py)

            # short stem + symbol + label
            ax.plot([sx, px], [sy, py], linewidth=1.0, color=line_color, zorder=5)
            _draw_cb_symbol(px, py, closed=cb.closed)
            ax.text(px, py + sign * 0.03, name, fontsize=8,
                    ha="center", va=("bottom" if sign > 0 else "top"), zorder=10)

        else:
            # ----- buslink CB: place at midpoint between the two buses -----
            a, b = cb.buses()
            xa, ya = bus_xy[a]; xb, yb = bus_xy[b]
            mx, my = (xa + xb) * 0.5, (ya + yb) * 0.5
            cb_plot_pos[name] = (mx, my)

            # draw a short stub along the line between buses for visual context
            ax.plot([xa, xb], [ya, yb], linestyle=":", color="#888888", linewidth=0.8, zorder=1, alpha=0.6)

            _draw_cb_symbol(mx, my, closed=cb.closed)
            # offset label slightly orthogonal to link so it doesn't sit on the symbol
            dx, dy = xb - xa, yb - ya
            L = (dx**2 + dy**2) ** 0.5 or 1.0
            nx, ny = -dy / L, dx / L  # normal
            ax.text(mx + nx * 0.03, my + ny * 0.03, name, fontsize=8,
                    ha="center", va="center", zorder=105)

    # --- draw CTs: snap to nearest CP (x fixed), offset only normal to the busbar ---
    ct_plot_pos = {}
    for name, ct in substation.cts.items():
        b_here = ct.endpoint_bus()
        xh, yh = bus_xy[b_here]
        Lh, Th = bus_L[b_here], bus_T[b_here]

        try:
            b_oth = ct.other_bus()
            xo, yo = bus_xy[b_oth]
            top_edge = (yo > yh)
            target_x = xo
        except Exception:
            _, _, _, uy = ct.endpoint_xy_and_dir()
            top_edge = (uy > 0.0)
            target_x = xh

        cp_x = _nearest_cp_x(b_here, target_x)
        sx, sy = _edge_point_vertical(xh, yh, Lh, Th, top=top_edge, x_target=cp_x)

        sign = 1.0 if top_edge else -1.0
        gap = max(Th * 3.0, 0.16)
        px, py = cp_x, sy + sign * gap

        ct_plot_pos[name] = (px, py)
        ax.plot([cp_x, px], [sy, py], linewidth=1.0, color=line_color, zorder=5)
        ax.scatter([px], [py], marker="o", s=80, facecolors="none",
                   edgecolors="black", linewidths=1.5, zorder=6)
        ax.text(px, py + sign * 0.025, name, fontsize=8,
                ha="center", va=("bottom" if sign > 0 else "top"), zorder=7)

    # --- draw IEDs: rounded box aligned to bay CP; dashed links to CB/CT -----
    def _ied_anchor_from_endpoint(bus_idx: int, other_bus_idx: int | None):
        xh, yh = bus_xy[bus_idx]
        Lh, Th = bus_L[bus_idx], bus_T[bus_idx]
        if other_bus_idx is not None and other_bus_idx in bus_xy:
            xo, yo = bus_xy[other_bus_idx]
            top_edge = (yo > yh)
            target_x = xo
        else:
            top_edge = False
            target_x = xh
        cp_x = _nearest_cp_x(bus_idx, target_x)
        sx, sy = _edge_point_vertical(xh, yh, Lh, Th, top=top_edge, x_target=cp_x)
        sign = 1.0 if top_edge else -1.0
        return cp_x, sx, sy, sign, Th

    for ied_name, ied in substation.ieds.items():
        cb_obj = getattr(ied, "xcbr", None)
        cb_src = getattr(cb_obj, "_cb", None) if cb_obj else None
        ct_obj = getattr(ied, "mmxu", None)
        ct_src = getattr(ct_obj, "_ct", None) if ct_obj else None

        # Figure bay anchor using CB if possible, else CT; handle buslink/line cases
        b_here = b_oth = None
        if cb_src is not None and getattr(cb_src, "target_kind", "line") == "line":
            b_here = cb_src.endpoint_bus()
            b_oth  = cb_src.other_bus()
        elif ct_src is not None:
            b_here = ct_src.endpoint_bus()
            b_oth  = ct_src.other_bus()
        elif cb_src is not None and getattr(cb_src, "target_kind", "line") == "buslink":
            # anchor to whichever bus is lower to keep consistent vertical layout
            a, b = cb_src.buses()
            b_here = a
            b_oth  = b

        if b_here is None:
            continue  # not wired

        cp_x, sx, sy, sign, Th = _ied_anchor_from_endpoint(b_here, b_oth)

        # place IED further out than CT (order: bus -> CB -> CT -> IED)
        gap_ied = max(Th * 2.2, 0.14)
        py_ied = sy + sign * gap_ied

        # IED box
        box_w = 0.09
        box_h = 0.04
        box_x = cp_x - 2 * box_w
        box_y = py_ied - box_h / 2.0

        box = FancyBboxPatch(
            (box_x, box_y),
            box_w, box_h,
            boxstyle="round,pad=0.01,rounding_size=0.01",
            facecolor="white", edgecolor="black", linewidth=1.2, zorder=110
        )
        ax.add_patch(box)
        ax.text(box_x + box_w/2, box_y + box_h/2, ied_name,
                ha="center", va="center", fontsize=8, zorder=111)

        # dashed links to whichever exist
        def _maybe_link(target_pos_dict, target_name):
            if target_name is None:
                return
            pos = target_pos_dict.get(target_name)
            if pos is None:
                return
            tx, ty = pos
            ax.plot([box_x + box_w, tx], [box_y + box_h/2, ty],
                    linestyle="--", linewidth=0.8, color="#000000", zorder=10)

        cb_name = None
        if cb_src is not None:
            # find CB's registered name (by identity)
            cb_name = next((n for n, obj in substation.cbs.items() if obj is cb_src), None)

        ct_name = None
        if ct_src is not None:
            ct_name = next((n for n, obj in substation.cts.items() if obj is ct_src), None)

        _maybe_link(cb_plot_pos, cb_name)
        _maybe_link(ct_plot_pos, ct_name)


    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    ax.set_title(f"{substation.name} — one-line view")
    if show:
        plt.tight_layout(); plt.show()
    return ax
