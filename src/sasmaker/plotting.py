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

def _vertical_segment_between(bus_xy, bus_L, bus_T, bus_CPX, _pick_cp_x, top_idx: int, bot_idx: int):
    """
    Return (sx, sy, ex, ey) so the connection between top and bottom buses is EXACTLY vertical.
    We pick a CP on the top bus nearest to the bottom bus x, then reuse that exact x on the bottom.
    """
    xt, yt = bus_xy[top_idx]; Lt, Tt = bus_L[top_idx], bus_T[top_idx]
    xb, yb = bus_xy[bot_idx]; Lb, Tb = bus_L[bot_idx], bus_T[bot_idx]

    # choose CP on the top bus nearest to bottom bus x (tie-aware)
    shared_x = _pick_cp_x(top_idx, xb)

    # top edge goes downward, bottom edge goes upward — at the same x
    s = _edge_point_vertical(xt, yt, Lt, Tt, top=False, x_target=shared_x)  # from top bus bottom edge
    e = _edge_point_vertical(xb, yb, Lb, Tb, top=True,  x_target=shared_x)  # to bottom bus top edge
    sx, sy = s; ex, ey = e
    return sx, sy, ex, ey


def _draw_busbar(ax, x, y, L, T=0.01, color="black"):
    rect = Rectangle((x - L/2, y - T/2), L, T, facecolor=color, edgecolor=color, zorder=20)
    ax.add_patch(rect)

def _draw_vt_symbol(ax, x, y, size=0.018, zorder=160):
    # two little coils stacked vertically
    r = size
    ax.add_patch(plt.Circle((x, y + r*1.2*0.5), r, facecolor="white", ec="black", lw=1.2, zorder=zorder+1))
    ax.add_patch(plt.Circle((x, y - r*1.2*0.5), r, facecolor="white", ec="black", lw=1.2, zorder=zorder))
    ax.add_patch(plt.Circle((x, y - r*1.2*0.5), r, fill=False, ec="black", lw=1.2, zorder=zorder+2))


def _plot_manhattan(ax, x0, y0, x1, y1, *, up_first=True,
                    linestyle="--", color="#000000", linewidth=0.8, zorder=10):
    """
    Draw a simple orthogonal (Manhattan) polyline from (x0,y0) to (x1,y1)
    using two segments:
      - if up_first=True:  (x0,y0) -> (x0,y1) -> (x1,y1)  (vertical, then horizontal)
      - if up_first=False: (x0,y0) -> (x1,y0) -> (x1,y1)  (horizontal, then vertical)
    """
    if up_first:
        xs = [x0, x0, x1]
        ys = [y0, y1, y1]
    else:
        xs = [x0, x1, x1]
        ys = [y0, y0, y1]
    ax.plot(xs, ys, linestyle=linestyle, linewidth=linewidth, color=color, zorder=zorder)

def _normalize_bus_list(raw_list, substation):
    """Accept ints, busbar objects (with .idx), or names; return list[int] bus ids."""
    out = []
    for b in (raw_list or []):
        if isinstance(b, int):
            out.append(int(b))
        elif hasattr(b, "idx"):
            out.append(int(getattr(b, "idx")))
        elif isinstance(b, str):
            match = next((bb.idx for bb in substation.busbars.values() if bb.name == b), None)
            if match is not None:
                out.append(int(match))
    return out

def _recompute_ied_center(ied_name, substation, bus_xy, bus_L, bus_T,
                          cb_plot_pos, ct_plot_pos, _ied_anchor_from_endpoint):
    """Best-effort: compute the IED box center if it wasn't recorded."""
    ied = substation.ieds.get(ied_name)
    if ied is None:
        return None

    # Try the buslink special case first (uses already-plotted CB/CT if available)
    cb_obj = getattr(ied, "xcbr", None)
    cb_src = getattr(cb_obj, "_cb", None) if cb_obj else None
    ct_obj = getattr(ied, "mmxu", None)
    ct_src = getattr(ct_obj, "_ct", None) if ct_obj else None

    if cb_src is not None and getattr(cb_src, "target_kind", "line") == "buslink":
        cb_name = next((n for n, o in substation.cbs.items() if o is cb_src), None)
        p_cb = cb_plot_pos.get(cb_name)

        p_ct = None
        if ct_src is not None:
            ct_name = next((n for n, o in substation.cts.items() if o is ct_src), None)
            p_ct = ct_plot_pos.get(ct_name)

        if p_cb:
            # anchor between CB and CT if possible, else at CB
            ax_anchor_x, ax_anchor_y = (p_cb[0], p_cb[1]) if not p_ct else ((p_cb[0]+p_ct[0])*0.5, (p_cb[1]+p_ct[1])*0.5)

            # push “above” the coupler like in the IED-draw branch
            a, b = cb_src.buses()
            xa, ya = bus_xy[a]; xb, yb = bus_xy[b]
            dx, dy = xb - xa, yb - ya
            L = (dx*dx + dy*dy) ** 0.5 or 1.0
            nx, ny = -dy / L, dx / L
            if ny < 0:
                nx, ny = -nx, -ny
            offset = 0.18
            return (ax_anchor_x + nx*offset, ax_anchor_y + ny*offset)

    # Otherwise reproduce the generic IED placement math to get the center
    # Prefer CB if present; else CT
    dev_src = cb_src or ct_src
    if dev_src is None:
        return None

    try:
        b_here = dev_src.endpoint_bus()
    except Exception:
        return None

    b_oth = None
    if hasattr(dev_src, "other_bus"):
        try:
            b_oth = dev_src.other_bus()
        except Exception:
            b_oth = None

    cp_x, sx, sy, sign, Th = _ied_anchor_from_endpoint(b_here, b_oth)
    gap_ied = max(bus_T[b_here] * 2.2, 0.1)
    py_ied = sy + sign * gap_ied

    # Use same box dims as in plot code to reconstruct the center
    box_w = 0.21
    box_h = 0.07
    box_x = cp_x - box_w * 1.6
    box_y = py_ied + sign * box_h * 2.6
    cx = box_x + 1.1 * box_w / 2.0
    cy = box_y + 0.9 * box_h / 2.0
    return (cx, cy)


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

    buslink_segments_by_pair = {}   # (min(a,b), max(a,b)) -> (sx,sy,ex,ey)
    buslink_segments_by_line = {}   # optional if your BusLink exposes a _line_id
    buslink_line_ids = set()

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
            if bb._draw_label:
                if slots==1:
                    ax.text(x, y + T*1.2, f"{bb.name}",
                        ha="center", va="bottom", fontsize=10, zorder=100)    
                else:
                    ax.text(x-(slots*busbar_length*0.5), y + T*1.2, f"{bb.name}",
                            ha="left", va="bottom", fontsize=10, zorder=100)


        def _nearest_cp_x(bus_idx: int, x_target: float) -> float:
            """
            Choose a CP x on this bus using:
            1) exact CP match (within EPS) if one exists
            2) else nearest CP
            3) deterministic tie-break (leftmost), optionally honoring a preferred CP
                if the Busbar object has attribute _preferred_cp (int index).
            """
            cpx = bus_CPX[bus_idx]

            # (1) exact match?
            for xx in cpx:
                if abs(xx - x_target) <= EPS:
                    return xx

            # (2) nearest with tie handling
            dists = [abs(xx - x_target) for xx in cpx]
            dmin = min(dists)
            candidates = [xx for xx, d in zip(cpx, dists) if abs(d - dmin) <= EPS]

            # (3) optional preference (if set by snapping code)
            bb_obj = next((bb for bb in substation.busbars.values() if bb.idx == bus_idx), None)
            if bb_obj is not None:
                pref_idx = getattr(bb_obj, "_preferred_cp", None)
                if isinstance(pref_idx, int) and 0 <= pref_idx < len(cpx):
                    pref_x = cpx[pref_idx]
                    if any(abs(cx - pref_x) <= EPS for cx in candidates):
                        return pref_x

            # deterministic: leftmost among ties
            return min(candidates)



    # epsilon to detect “x-aligned” (choose vertical routing)
    EPS = 1e-9

    # record the exact x used at each line endpoint (used by normal line CTs)
    endpoint_anchor_x: dict[tuple[int, str], float] = {}

    # maps underlying short-line index -> (sx, sy, ex, ey)
    buslink_segments: dict[int, tuple[float, float, float, float]] = {}

    # --- draw feeder/transmission lines (snap to CPs) ---
    for name, ln in substation.lines.items():
        fb, tb = ln.buses
        x1, y1 = bus_xy[fb]; L1, T1 = bus_L[fb], bus_T[fb]
        x2, y2 = bus_xy[tb]; L2, T2 = bus_L[tb], bus_T[tb]

        # If buses at different heights -> FORCE vertical using a shared CP x
        if not isclose(y1, y2, abs_tol=1e-12):
            # determine which is on top
            if y1 > y2:
                sx, sy, ex, ey = _vertical_segment_between(bus_xy, bus_L, bus_T, bus_CPX, _nearest_cp_x, fb, tb)
            else:
                sx, sy, ex, ey = _vertical_segment_between(bus_xy, bus_L, bus_T, bus_CPX, _nearest_cp_x, tb, fb)
            ax.plot([sx, ex], [sy, ey], linewidth=line_width, color=line_color, zorder=2)

            line_idx = getattr(ln, "idx", None)
            if line_idx is not None:
                endpoint_anchor_x[(int(line_idx), "from")] = float(sx)
                endpoint_anchor_x[(int(line_idx), "to")]   = float(ex)
        else:
            # same height → horizontal edge-to-edge via projection
            p1 = _edge_point_towards(x1, y1, L1, T1, x2, y2)
            p2 = _edge_point_towards(x2, y2, L2, T2, x1, y1)
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], linewidth=line_width, color=line_color, zorder=2)

        if label_lines:
            # midpoint label
            xm = (x1 + x2) / 2.0; ym = (y1 + y2) / 2.0
            ax.text(xm, ym, name, fontsize=10, ha="center", va="center", zorder=4)

    # --- draw intra-substation bus links (line-backed couplers) ---
    for name, bl in substation.buslinks.items():
        a, b = bl.buses
        x1, y1 = bus_xy[a]; L1, T1 = bus_L[a], bus_T[a]
        x2, y2 = bus_xy[b]; L2, T2 = bus_L[b], bus_T[b]

        # Same routing rule as lines: vertical if different y, else horizontal projection
        if not isclose(y1, y2, abs_tol=1e-12):
            if y1 > y2:
                sx, sy, ex, ey = _vertical_segment_between(bus_xy, bus_L, bus_T, bus_CPX, _nearest_cp_x, a, b)
            else:
                sx, sy, ex, ey = _vertical_segment_between(bus_xy, bus_L, bus_T, bus_CPX, _nearest_cp_x, b, a)
        else:
            p1 = _edge_point_towards(x1, y1, L1, T1, x2, y2)
            p2 = _edge_point_towards(x2, y2, L2, T2, x1, y1)
            sx, sy = p1; ex, ey = p2

        ax.plot([sx, ex], [sy, ey],
                linewidth=buslink_width, color=buslink_color, linestyle=buslink_style,
                zorder=2, alpha=1.0 if bl.closed else 0.3)
        
        # record segments for later (CB/CT placement)
        lid = getattr(bl, "_line_id", None)
        if lid is not None:
            lid = int(lid)
            buslink_segments_by_line[lid] = (sx, sy, ex, ey)
            buslink_line_ids.add(lid)
        key = tuple(sorted((int(a), int(b))))
        buslink_segments_by_pair[key] = (sx, sy, ex, ey)

        if label_buslinks:
            xm, ym = (sx + ex) * 0.5, (sy + ey) * 0.5
            ax.text(xm, ym, f"{name} ({'closed' if bl.closed else 'open'})",
                    fontsize=10, ha="center", va="center", zorder=4)
            
    # --- draw transformers (snap like lines; symbol at midpoint) -----------------
    from matplotlib.patches import Circle
    import math
    def _draw_tx_symbol(ax, mx, my, dx, dy, size=0.06):
        """
        Classic transformer symbol: two circles (coils) aligned *along* the lead.
        - `size` controls overall footprint; radius is derived from it.
        - The circles are centered on the connection axis (rotated 90° vs previous version).
        """
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L          # unit vector along the lead

        # coil geometry
        radius = size * 0.45             # coil radius
        gap    = -size * 0.25             # distance between coils (edge to edge)
        center_offset = radius + gap / 2.0

        # Centers placed ALONG the lead (± along ux, uy)
        c1x, c1y = mx + ux * center_offset, my + uy * center_offset   # HV side
        c2x, c2y = mx - ux * center_offset, my - uy * center_offset   # LV side

        # Draw the two coils (unfilled circles)
        circ1 = Circle((c1x, c1y), radius, facecolor="white", edgecolor="black", linewidth=1.6, zorder=115)
        circ2 = Circle((c2x, c2y), radius, facecolor="white", edgecolor="black", linewidth=1.6, zorder=114)
        circ3 = Circle((c2x, c2y), radius, fill=False, edgecolor="black", linewidth=1.6, zorder=116)
        ax.add_patch(circ1)
        ax.add_patch(circ2)
        ax.add_patch(circ3)

    for name, tx in getattr(substation, "txs", {}).items():
        hv, lv = tx.buses()
        xh, yh = bus_xy[hv]; Lh, Th = bus_L[hv], bus_T[hv]
        xl, yl = bus_xy[lv]; Ll, Tl = bus_L[lv], bus_T[lv]

        # FORCE vertical if buses are at different heights; else snap CP-to-CP horizontally
        if not isclose(yh, yl, abs_tol=1e-12):
            if yh > yl:
                sx, sy, ex, ey = _vertical_segment_between(bus_xy, bus_L, bus_T, bus_CPX, _nearest_cp_x, hv, lv)
            else:
                sx, sy, ex, ey = _vertical_segment_between(bus_xy, bus_L, bus_T, bus_CPX, _nearest_cp_x, lv, hv)
        else:
            # same row → horizontal CP-to-CP (both on bottom edge looks neat; tweak if you prefer top/nearest)
            cpx_h = _nearest_cp_x(hv, xl)
            cpx_l = _nearest_cp_x(lv, xh)
            s = _edge_point_vertical(xh, yh, Lh, Th, top=False, x_target=cpx_h)
            e = _edge_point_vertical(xl, yl, Ll, Tl, top=False, x_target=cpx_l)
            sx, sy = s; ex, ey = e

        # lead line
        ax.plot([sx, ex], [sy, ey],
                linewidth=line_width, color="black",
                zorder=110, alpha=1.0 if tx.in_service else 0.35)

        # symbol + label at midpoint
        size = 0.16
        mx, my = (sx + ex)*0.5, (sy + ey) * 0.5
        _draw_tx_symbol(ax, mx, my, ex - sx, ey - sy, size=size)
        radius = size*0.45
        ax.text(mx+(2*radius), my-0.02, name, fontsize=10, ha="center", va="bottom", zorder=130)



    # --- draw loads: stub from the nearest CP on the bottom edge ---
    for name, ld in substation.loads.items():
        b = ld.bus_idx
        x, y = float(substation.net.bus.at[b, "x"]), float(substation.net.bus.at[b, "y"])
        Lb, Tb = bus_L[b], bus_T[b]
        cp_x = _nearest_cp_x(b, x)           # snap to nearest CP
        sx, sy = _edge_point_vertical(x, y, Lb, Tb, top=False, x_target=cp_x)
        stub_len = 0.1
        ex, ey = cp_x, sy - stub_len
        ax.plot([sx, ex], [sy, ey], color="black", linewidth=1.5, zorder=2)
        ax.scatter([ex], [ey], marker="v", color="black", s=40, zorder=3)
        if ld._draw_label:
            ax.text(ex, ey - 0.05, name, ha="center", va="top", fontsize=10, zorder=4)

    # --- draw CBs: support line-end *and* buslink CBs ------------------------
    cb_plot_pos = {}  # name -> (px, py)

    def _draw_cb_symbol(px, py, *, closed: bool, size=0.015, color="#FF0000"):
        # small square; filled if closed, outlined with a diagonal "gap" if open
        rect_x = [px - size, px + size, px + size, px - size]
        rect_y = [py - size, py - size, py + size, py + size]
        if closed:
            ax.fill(rect_x + [rect_x[0]], rect_y + [rect_y[0]], linewidth=1.2, color=color, zorder=1011)
        else:
            ax.fill(rect_x + [rect_x[0]], rect_y + [rect_y[0]],
                    facecolor="white", edgecolor=color, linewidth=1.2, zorder=1011)
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
            ax.plot([sx, px], [sy, py], linewidth=1.0, color=line_color, zorder=3)
            _draw_cb_symbol(px, py, closed=cb.closed)
            ax.text(px+0.05, py-sign*0.02, name, fontsize=10,
                    ha="left", va=("bottom" if sign > 0 else "top"), zorder=10)
            
        elif target_kind == "tx":
            # ----- transformer-end CB: use the same shared CP x as the transformer lead -----
            b_here = cb.endpoint_bus()
            xh, yh = bus_xy[b_here]; Lh, Th = bus_L[b_here], bus_T[b_here]

            # find HV/LV buses for this transformer
            tx_tbl = cb._net.trafo
            tid = cb._trafo_id
            hv = int(tx_tbl.at[tid, "hv_bus"])
            lv = int(tx_tbl.at[tid, "lv_bus"])

            # decide which is geometrically on top
            y_hv = bus_xy[hv][1]; y_lv = bus_xy[lv][1]
            top_idx, bot_idx = (hv, lv) if y_hv > y_lv else (lv, hv)

            # compute the shared CP x exactly like the transformer lead does:
            shared_x = _nearest_cp_x(top_idx, bus_xy[bot_idx][0])

            # the CB attaches on the top/bottom edge depending on which bus it sits on
            top_edge = (b_here == bot_idx)  # bottom bus: connect upward; top bus: connect downward

            cp_x = shared_x
            sx, sy = _edge_point_vertical(xh, yh, Lh, Th, top=top_edge, x_target=cp_x)

            sign = 1.0 if top_edge else -1.0
            gap = max(Th * 1.5, 0.08)
            px, py = cp_x, sy + sign * gap
            cb_plot_pos[name] = (px, py)

            ax.plot([sx, px], [sy, py], linewidth=1.0, color=line_color, zorder=5)
            _draw_cb_symbol(px, py, closed=cb.closed)
            ax.text(px+0.05, py - sign*0.02, name, fontsize=10,
                    ha="left", va=("bottom" if sign > 0 else "top"), zorder=1000)

        elif target_kind == "buslink":
            a, b = cb.buses()
            key = tuple(sorted((a, b)))

            # Prefer segment keyed by line_id (if available), else by bus-pair
            seg = None
            lid = getattr(cb, "_line_id", None)
            if lid is not None:
                seg = buslink_segments_by_line.get(int(lid))
            if seg is None:
                seg = buslink_segments_by_pair.get(key)

            if seg is None:
                # fallback (shouldn't happen): use centers
                xa, ya = bus_xy[a]; xb, yb = bus_xy[b]
                seg = (xa, ya, xb, yb)

            sx, sy, ex, ey = seg
            dx, dy = (ex - sx), (ey - sy)
            L = (dx*dx + dy*dy) ** 0.5 or 1.0
            ux, uy = dx / L, dy / L

            # center if NO CT on this buslink; else keep 0.55 as before
            has_ct = any(getattr(ct, "_line_id", None) == lid for ct in substation.cts.values())
            
            t = 0.5 if not has_ct else 0.55

            px = sx + t * dx
            py = sy + t * dy
            cb_plot_pos[name] = (px, py)

            # faint context line (same segment you used to draw the buslink)
            ax.plot([sx, ex], [sy, ey], linestyle=":", color="#888888",
                    linewidth=0.8, zorder=1, alpha=0.6)

            _draw_cb_symbol(px, py, closed=cb.closed)

            # label slightly above the line using the upward normal
            nx, ny = -uy, ux
            if ny < 0: nx, ny = -nx, -ny
            ax.text(px + nx * 0.03, py - ny * 0.06, name, fontsize=10,
                    ha="center", va="center", zorder=105)

    # --- draw CTs: snap to nearest CP for normal lines/tx; sit ON segment for buslinks ---
    ct_plot_pos = {}
    for name, ct in substation.cts.items():

        # Try to resolve a BUSLINK segment for this CT
        seg = None
        lid = getattr(ct, "_line_id", None)
        if lid is not None:
            seg = buslink_segments_by_line.get(int(lid))

        if seg is None:
            # fall back by the two bus indices of the line the CT is on
            try:
                line_tbl = ct._net.line
                li = int(ct._line_id)
                a = int(line_tbl.at[li, "from_bus"])
                b = int(line_tbl.at[li, "to_bus"])
                key = tuple(sorted((a, b)))
                seg = buslink_segments_by_pair.get(key)
            except Exception:
                seg = None

        if seg is not None:
            # ---- draw CT ON the buslink segment at 0.45 / 0.55 ----
            sx, sy, ex, ey = seg
            dx, dy = (ex - sx), (ey - sy)
            L = (dx*dx + dy*dy) ** 0.5 or 1.0
            ux, uy = dx / L, dy / L

            side = getattr(ct, "_side", "from")
            t = 0.45 if side == "from" else 0.55
            px = sx + t * dx
            py = sy + t * dy

            # symbol
            ax.scatter([px], [py], marker="o", s=80,
                    facecolors="white", edgecolors="black",
                    linewidths=1.5, zorder=1)

            # label “above” the coupler using the same upward-normal rule as CBs
            nx, ny = -uy, ux
            if ny < 0: nx, ny = -nx, -ny
            ax.text(px + nx*0.03, py - ny*0.06, name, fontsize=10,
                    ha="right", va="center", zorder=7)

            ct_plot_pos[name] = (px, py)
            continue  # handled; skip the legacy stub logic

        b_here = ct.endpoint_bus()
        xh, yh = bus_xy[b_here]
        Lh, Th = bus_L[b_here], bus_T[b_here]

        is_tx = hasattr(ct, "_trafo_id") and (ct._trafo_id is not None)
        if is_tx:
            # (a) transformer endpoint: reuse the transformer's shared CP x
            tx_tbl = ct._net.trafo
            tid = ct._trafo_id
            hv = int(tx_tbl.at[tid, "hv_bus"])
            lv = int(tx_tbl.at[tid, "lv_bus"])

            y_hv = bus_xy[hv][1]; y_lv = bus_xy[lv][1]
            top_idx, bot_idx = (hv, lv) if y_hv > y_lv else (lv, hv)
            shared_x = _nearest_cp_x(top_idx, bus_xy[bot_idx][0])

            # CT sits on top edge if it's on the bottom bus; bottom edge if on the top bus
            top_edge = (b_here == bot_idx)
            target_x = shared_x
        else:
            # (b) line endpoint: your existing logic
            try:
                b_oth = ct.other_bus()
                xo, yo = bus_xy[b_oth]
                top_edge = (yo > yh)
                target_x = xo
            except Exception:
                _, _, _, uy = ct.endpoint_xy_and_dir()
                top_edge = (uy > 0.0)
                target_x = xh

        # Prefer the *exact* x used by the lead for this line endpoint (works for couplers too)
        cp_x = None
        line_id = getattr(ct, "_line_id", None)
        side    = getattr(ct, "_side", None)
        if line_id is not None and side in ("from", "to"):
            cp_x = endpoint_anchor_x.get((int(line_id), side), None)
        if cp_x is None:
            cp_x = _nearest_cp_x(b_here, target_x)

        sx, sy = _edge_point_vertical(xh, yh, Lh, Th, top=top_edge, x_target=cp_x)

        sign = 1.0 if top_edge else -1.0
        gap = max(Th * 3.0, 0.16)
        px, py = cp_x, sy + sign * gap

        ct_plot_pos[name] = (px, py)
        ax.plot([cp_x, px], [sy, py], linewidth=1.0, color=line_color, zorder=5)
        ax.scatter([px], [py], marker="o", s=80, facecolors="none",
                   edgecolors="black", linewidths=1.5, zorder=6)
        ax.text(px+0.05, py - sign * 0.02, name, fontsize=10,
                ha="left", va=("bottom" if sign > 0 else "top"), zorder=7)

    # --- draw IEDs: rounded box aligned to bay CP; dashed links to CB/CT -----
    def _ied_anchor_from_endpoint(bus_idx: int, other_bus_idx: int | None):
        """
        Return (cp_x, sx, sy, sign, Th) for placing an IED box/stub.

        Transformer-aware:
        If bus_idx and other_bus_idx are the two ends of a transformer, we anchor the IED
        using the *same shared CP x* that the transformer lead uses and choose the edge
        toward the transformer (top bus anchors downward, bottom bus anchors upward).

        Otherwise, keep the previous behavior (nearest CP toward the other bus).
        """
        xh, yh = bus_xy[bus_idx]
        Lh, Th = bus_L[bus_idx], bus_T[bus_idx]

        # --- detect if (bus_idx, other_bus_idx) is a trafo pair
        is_tx_pair = False
        hv = lv = None
        if other_bus_idx is not None and other_bus_idx in bus_xy:
            try:
                tx_tbl = substation.net.trafo
                if tx_tbl is not None and len(tx_tbl) > 0:
                    for _, row in tx_tbl.iterrows():
                        a = int(row["hv_bus"]); b = int(row["lv_bus"])
                        if (a == bus_idx and b == other_bus_idx) or (a == other_bus_idx and b == bus_idx):
                            is_tx_pair = True
                            hv, lv = a, b
                            break
            except Exception:
                is_tx_pair = False

        if is_tx_pair:
            # Use the exact CP-x used by the transformer lead
            y_hv = bus_xy[hv][1]; y_lv = bus_xy[lv][1]
            top_idx, bot_idx = (hv, lv) if y_hv > y_lv else (lv, hv)
            shared_x = _nearest_cp_x(top_idx, bus_xy[bot_idx][0])

            # If we're on the bottom bus -> anchor upward (top_edge=True); else downward
            top_edge = (bus_idx == bot_idx)
            cp_x = shared_x
            sx, sy = _edge_point_vertical(xh, yh, Lh, Th, top=top_edge, x_target=cp_x)
            sign = 1.0 if top_edge else -1.0
            return cp_x, sx, sy, sign, Th

        # --- legacy line/buslink behavior
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

    ied_centers = {}
    for ied_name, ied in substation.ieds.items():
        cb_obj = getattr(ied, "xcbr", None)
        cb_src = getattr(cb_obj, "_cb", None) if cb_obj else None
        ct_obj = getattr(ied, "mmxu", None)
        ct_src = getattr(ct_obj, "_ct", None) if ct_obj else None

        # ---- SPECIAL CASE: IED on a BUSLINK: place between the CT and CB ----
        if cb_src is not None and getattr(cb_src, "target_kind", "line") == "buslink":
            # identity -> names so we can look up plotted positions
            cb_name = next((n for n, obj in substation.cbs.items() if obj is cb_src), None)

            # if this IED also has a CT, grab it (buslink CT plotting stored its pos)
            ct_name = None
            if ct_src is not None:
                ct_name = next((n for n, obj in substation.cts.items() if obj is ct_src), None)

            # positions of CB & CT on the coupler (if present)
            p_cb = cb_plot_pos.get(cb_name)
            p_ct = ct_plot_pos.get(ct_name) if ct_name else None

            # if both exist, anchor halfway between them; else fall back to coupler midpoint
            if p_cb and p_ct:
                ax_anchor_x = 0.5 * (p_cb[0] + p_ct[0])
                ax_anchor_y = 0.5 * (p_cb[1] + p_ct[1])
            else:
                # compute midpoint of the buslink itself
                a, b = cb_src.buses()
                xa, ya = bus_xy[a]; xb, yb = bus_xy[b]
                ax_anchor_x = 0.5 * (xa + xb)
                ax_anchor_y = 0.5 * (ya + yb)

            # "upward" normal to the buslink so the box sits above the line (same rule as CB labels)
            a, b = cb_src.buses()
            xa, ya = bus_xy[a]; xb, yb = bus_xy[b]
            dx, dy = xb - xa, yb - ya
            L = (dx*dx + dy*dy) ** 0.5 or 1.0
            nx, ny = -dy / L, dx / L
            if ny < 0:     # ensure visually above
                nx, ny = -nx, -ny

            # place the IED box slightly above the anchor point
            offset = 0.18
            cx = ax_anchor_x + nx * offset
            cy = ax_anchor_y + ny * offset

            # box geometry
            box_w = 0.21
            box_h = 0.07
            box_x = cx - box_w * 0.5
            box_y = cy - box_h * 0.5

            box = FancyBboxPatch(
                (box_x, box_y), box_w, box_h,
                boxstyle="round,pad=0.01,rounding_size=0.01",
                facecolor="white", edgecolor="black", linewidth=1.2, zorder=110
            )
            ied_centers[ied_name] = (box_x + box_w/2, box_y + box_h/2)
            ax.add_patch(box)
            ax.text(box_x + box_w/2, box_y + box_h/2, ied_name,
                    ha="center", va="center", fontsize=10, zorder=111)

            # dashed links from IED to BOTH CB and CT (when present)
            if p_cb:
                ax.plot([box_x + box_w/2, p_cb[0]], [box_y + box_h/2, p_cb[1]],
                        linestyle="--", linewidth=0.8, color="#000000", zorder=10)
            if p_ct:
                ax.plot([box_x + box_w/2, p_ct[0]], [box_y + box_h/2, p_ct[1]],
                        linestyle="--", linewidth=0.8, color="#000000", zorder=10)

            continue  # handled; skip generic IED placement

        # ---- Figure bay anchor using CB if possible, else CT ----
        # Transformer-aware: if device is on a trafo side, reuse the transformer's shared CP x
        net = substation.net

        # prefer CB if present; else CT
        dev_src = None
        if cb_src is not None:
            dev_src = cb_src
        elif ct_src is not None:
            dev_src = ct_src

        is_tx = False
        tid = None
        b_here = b_oth = None

        if dev_src is not None:
            # line / tx endpoint buses (works for both)
            b_here = dev_src.endpoint_bus()
            # Only safe for line; for trafo we'll compute anchor differently
            if hasattr(dev_src, "other_bus"):
                try:
                    b_oth = dev_src.other_bus()
                except Exception:
                    b_oth = None

            # detect transformer attachment
            if hasattr(dev_src, "_trafo_id") and getattr(dev_src, "_trafo_id") is not None:
                is_tx = True
                tid = int(getattr(dev_src, "_trafo_id"))
        #
        if is_tx and tid is not None:
            # --- transformer-side IED anchor: same shared-x as the transformer lead ---
            tx_tbl = net.trafo
            hv = int(tx_tbl.at[tid, "hv_bus"])
            lv = int(tx_tbl.at[tid, "lv_bus"])

            y_hv = bus_xy[hv][1]; y_lv = bus_xy[lv][1]
            top_idx, bot_idx = (hv, lv) if y_hv > y_lv else (lv, hv)

            shared_x = _nearest_cp_x(top_idx, bus_xy[bot_idx][0])

            xh, yh = bus_xy[b_here]
            Lh, Th = bus_L[b_here], bus_T[b_here]
            top_edge = (b_here == bot_idx)

            cp_x = shared_x
            sx, sy = _edge_point_vertical(xh, yh, Lh, Th, top=top_edge, x_target=cp_x)
            sign = 1.0 if top_edge else -1.0

        else:
            # --- legacy (line/buslink) anchor ---
            if b_here is None:
                continue
            cp_x, sx, sy, sign, Th = _ied_anchor_from_endpoint(b_here, b_oth)
            Lh, Th = bus_L[b_here], bus_T[b_here]

        #

        # cp_x, sx, sy, sign, Th = _ied_anchor_from_endpoint(b_here, b_oth)

        # place IED further out than CT (order: bus -> CB -> CT -> IED)
        gap_ied = max(Th * 2.2, 0.1)
        py_ied = sy + sign*gap_ied

        # IED box
        box_w = 0.21
        box_h = 0.07
        box_x = cp_x - box_w*1.6
        box_y = py_ied+sign*box_h*2.6

        box = FancyBboxPatch(
            (box_x, box_y),
            box_w, box_h,
            boxstyle="round,pad=0.01,rounding_size=0.01",
            facecolor="white", edgecolor="black", linewidth=1.2, zorder=110
        )
        ied_centers[ied_name] = (box_x + box_w/2, box_y + box_h/2)
        ax.add_patch(box)
        ax.text(box_x + 1.1*box_w/2, box_y + 0.9*box_h/2, ied_name,
                ha="center", va="center", fontsize=10, zorder=111)

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
    
    # --- draw VTs: symbol at measured endpoint + at each extra bus ---
    # --- VTs (one symbol; dashed links from IED to one or more buses) ------------
    for vt_name, vt in getattr(substation, "vts", {}).items():
        ied_name = (getattr(vt, "ied_name", None) or "").strip()
        

        # Normalize buses to int ids (accept ids / objects / names)
        bus_list = _normalize_bus_list(getattr(vt, "link_buses", []), substation)
        if not ied_name or not bus_list:
            continue

        # Find (or recompute) the IED center
        center = ied_centers.get(ied_name)
        if center is None:
            center = _recompute_ied_center(
                ied_name, substation, bus_xy, bus_L, bus_T, cb_plot_pos, ct_plot_pos, _ied_anchor_from_endpoint
            )
        if center is None:
            # still nothing; skip quietly
            continue

        cx, cy = center
        anchor_bus = bus_list[0]
        extra_buses = bus_list[1:]


        # helper: nearest CP x on a bus to a target x
        def _nearest_cp_to(bus_idx: int, x_target: float) -> float:
            cpx = bus_CPX[bus_idx]
            dmin = min(abs(xx - x_target) for xx in cpx)
            candidates = [xx for xx in cpx if abs(xx - x_target) <= dmin + 1e-12]
            return min(candidates)

        # ----- anchor bus: put the symbol right off its edge at nearest CP -----
        bx, by = bus_xy[anchor_bus]
        Lb, Tb = bus_L[anchor_bus], bus_T[anchor_bus]
        cp_x = _nearest_cp_to(anchor_bus, cx)
        top_edge = (by > cy)  # bus above IED -> attach on bottom edge
        sx, sy = _edge_point_vertical(bx, by, Lb, Tb, top=top_edge, x_target=cp_x)

        # short stem and symbol
        sign = 1.0 if top_edge else -1.0
        stem = max(Tb * 2.2, 0.1)
        vx, vy = sx, sy - sign * stem
        ax.plot([sx, vx], [sy, vy], linestyle="--", linewidth=0.8, color="#000", zorder=150)
        _draw_vt_symbol(ax, vx, vy, size=0.02, zorder=160)
        ax.text(vx + 0.03, vy, vt_name, fontsize=10, va="center", ha="left", zorder=161)

        # dashed link IED <-> anchor bus (orthogonal; choose direction so it lifts toward the IED)
        _plot_manhattan(ax, sx, sy, cx, cy,
                        up_first=(sy < cy), linestyle="--", color="#000", linewidth=0.8, zorder=1)

        # ----- extra buses: just dashed links to their nearest CPs -----
        for b in extra_buses:
            bx, by = bus_xy[b]
            Lb, Tb = bus_L[b], bus_T[b]
            cp_x = _nearest_cp_to(b, cx)
            top_edge = (by > cy)
            exs, eys = _edge_point_vertical(bx, by, Lb, Tb, top=top_edge, x_target=cp_x)
            stem = max(Tb * 2.2, 0.1)
            sign = 1.0 if top_edge else -1.0
            vx, vy = exs, eys - sign * stem
            _draw_vt_symbol(ax, vx, vy, size=0.02, zorder=160)
            ax.text(vx + 0.03, vy, vt_name, fontsize=10, va="center", ha="left", zorder=161)
            _plot_manhattan(ax, exs, eys, cx, cy,
                            up_first=(eys < cy), linestyle="--", color="#000", linewidth=0.8, zorder=1)


    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    ax.set_title(f"{substation.name} — one-line view")
    if show:
        plt.tight_layout(); plt.show()
    return ax
