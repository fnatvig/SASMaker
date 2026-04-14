from __future__ import annotations
from sasmaker.simulation import trigger_busbar_protection, trigger_ied_cb_trip, trigger_ied_cb_close

import random
from typing import List, Optional, Sequence, Tuple
import sys

def _stable_seed_from_scenario(s: str) -> int:
    acc = 0
    for ch in s:
        acc = (acc * 131 + ord(ch)) % (2**32 - 1)
    return acc

def _cycle_pick(items: Sequence[str], k: int, offset: int = 0) -> List[str]:
    """Pick k items in a round-robin way (repeats allowed), deterministic."""
    if not items:
        return []
    out = []
    n = len(items)
    for i in range(k):
        out.append(items[(offset + i) % n])
    return out

def _ied_name(x) -> str:

    return getattr(x, "name", str(x))

def _compress_or_stretch_ops(
    ops: List[Tuple[str, float, float]],
    t_start: float,
    t_end: float,
    fill_low_frac: float = 0.85,
) -> List[Tuple[str, float, float]]:
    """
    Make the ops occupy a reasonable fraction of [t_start, t_end] deterministically.
    - If ops exceed t_end -> compress.
    - If ops end too early (< fill_low_frac * (t_end-t_start)) -> stretch.
    Keeps ordering and relative spacing, does NOT change event count.
    """
    if not ops:
        return ops

    first_t = ops[0][1]
    last_close = ops[-1][2]
    if last_close <= first_t:
        return ops

    desired_last = t_start + fill_low_frac * (t_end - t_start)

    if last_close > t_end:
        scale = (t_end - t_start) / (last_close - first_t)
    elif last_close < desired_last:
        scale = (desired_last - t_start) / (last_close - first_t)
    else:
        return ops

    scaled = []
    for ied, tt, tc in ops:
        tt2 = t_start + (tt - first_t) * scale
        tc2 = t_start + (tc - first_t) * scale
        scaled.append((ied, float(tt2), float(tc2)))
    return scaled


def _window_allocation_321(
    rng: random.Random,
    non_idle_ids: List[int],
    n_ops_in_windows: int,
) -> Tuple[dict[int, int], set[int]]:
    """
    Deterministically allocate ops to non-idle windows with a fixed pattern.
    Default target pattern for 6 ops across 3 windows: (3,2,1).
    Returns:
      alloc: window_id -> number of ops
      dense_ids: set of windows considered "dense" (we use 1 dense window here)
    """
    if not non_idle_ids or n_ops_in_windows <= 0:
        return {}, set()

    # Choose an ordering of non-idle windows deterministically
    order = non_idle_ids[:]
    rng.shuffle(order)

    alloc: dict[int, int] = {wid: 0 for wid in non_idle_ids}
    dense_ids: set[int] = set()

    # Base pattern
    pattern = [3, 2, 1]

    # If fewer than 3 non-idle windows, fold the pattern
    if len(order) == 1:
        pattern_eff = [sum(pattern)]  # all 6 in one window
    elif len(order) == 2:
        pattern_eff = [pattern[0] + pattern[2], pattern[1]]  # 4 and 2
    else:
        pattern_eff = pattern[:]  # 3,2,1

    # Trim / scale pattern to match n_ops_in_windows exactly
    # (n_ops_in_windows should be 6 in your config, but keep robust)
    total = sum(pattern_eff)
    if total != n_ops_in_windows:
        # Scale by distributing +/- 1 in a deterministic round-robin over the pattern slots
        # until sums match.
        pattern_eff = pattern_eff[:]
        i = 0
        while sum(pattern_eff) < n_ops_in_windows:
            pattern_eff[i % len(pattern_eff)] += 1
            i += 1
        i = 0
        while sum(pattern_eff) > n_ops_in_windows:
            j = i % len(pattern_eff)
            if pattern_eff[j] > 0:
                pattern_eff[j] -= 1
            i += 1

    # Apply to the first k windows in the shuffled order
    for idx, cnt in enumerate(pattern_eff):
        wid = order[idx]
        alloc[wid] = cnt

    # Mark the densest window (the one with max alloc)
    max_cnt = max(alloc.values()) if alloc else 0
    for wid, cnt in alloc.items():
        if cnt == max_cnt and cnt > 0:
            dense_ids.add(wid)
            break  # exactly one dense window

    return alloc, dense_ids

def benign_switching(sim, substation, scenario, t_end):

    if scenario == "test":     

        t = [70.0, 92.0, 140.0, 162.0,
             210.0, 213.0, 218.0, 222.0, 227.0, 235.0,
             275.0, 277.0, 282.0, 286.0, 291.0, 298.0,
             540.0, 542.0, 547.0, 549.0, 554.0, 562.0,
             610.0, 613.0, 619.0, 621.0, 626.0, 634.0,
             690.0, 691.0, 693.0, 697.0, 699.0, 707.0,
             930.0, 932.0, 936.0, 939.0, 943.0, 948.0,
             1010.0, 1012.0, 1016.0, 1020.0, 1024.0, 1031.0,
             1110.0]

        # --- Warm-up: quiet period before any switching ---
        # (no events) t=0..60

        # =========================
        # Island A (early): 70..300
        # =========================

        # Baseline single-feeder events (clean, one per section)
        trigger_ied_cb_trip(sim,  "IED4", t0=70);   trigger_ied_cb_close(sim, "IED4", t0=92)
        trigger_ied_cb_trip(sim,  "IED7", t0=140);  trigger_ied_cb_close(sim, "IED7", t0=162)

        # Overlap block 1
        trigger_ied_cb_close(sim, "IED3", t0=210)
        trigger_ied_cb_trip(sim,  "IED5", t0=213);  trigger_ied_cb_close(sim, "IED5", t0=218)
        trigger_ied_cb_trip(sim,  "IED8", t0=222);  trigger_ied_cb_close(sim, "IED8", t0=227)
        trigger_ied_cb_trip(sim,  "IED3", t0=235)

        # Overlap block 2
        trigger_ied_cb_close(sim, "IED3", t0=275)
        trigger_ied_cb_trip(sim,  "IED9", t0=277);  trigger_ied_cb_close(sim, "IED9", t0=282)
        trigger_ied_cb_trip(sim,  "IED6", t0=286);  trigger_ied_cb_close(sim, "IED6", t0=291)
        trigger_ied_cb_trip(sim,  "IED3", t0=298)

        # --- Idle gap (attack-friendly quiet window) ---
        # (no events) t=300..520


        # =========================
        # Island B (mid): 520..760
        # =========================

        # Overlap block 3 (burstier on section 1)
        trigger_ied_cb_close(sim, "IED3", t0=540)
        trigger_ied_cb_trip(sim,  "IED4", t0=542);  trigger_ied_cb_close(sim, "IED4", t0=547)
        trigger_ied_cb_trip(sim,  "IED5", t0=549);  trigger_ied_cb_close(sim, "IED5", t0=554)
        trigger_ied_cb_trip(sim,  "IED3", t0=562)

        # Overlap block 4 (burstier on section 2)
        trigger_ied_cb_close(sim, "IED3", t0=610)
        trigger_ied_cb_trip(sim,  "IED7", t0=613);  trigger_ied_cb_close(sim, "IED7", t0=619)
        trigger_ied_cb_trip(sim,  "IED8", t0=621);  trigger_ied_cb_close(sim, "IED8", t0=626)
        trigger_ied_cb_trip(sim,  "IED3", t0=634)

        # Overlap block 5 (mixed order, collisions)
        trigger_ied_cb_close(sim, "IED3", t0=690)
        trigger_ied_cb_trip(sim,  "IED6", t0=691)
        trigger_ied_cb_trip(sim,  "IED9", t0=693)
        trigger_ied_cb_close(sim, "IED9", t0=697)
        trigger_ied_cb_close(sim, "IED6", t0=699)
        trigger_ied_cb_trip(sim,  "IED3", t0=707)

        # --- Idle gap (another quiet window) ---
        # (no events) t=710..900


        # ==========================
        # Island C (late): 900..1160
        # ==========================

        # Coupler stress 1
        trigger_ied_cb_close(sim, "IED3", t0=930)
        trigger_ied_cb_trip(sim,  "IED4", t0=932)
        trigger_ied_cb_trip(sim,  "IED8", t0=936)
        trigger_ied_cb_close(sim, "IED4", t0=939)
        trigger_ied_cb_close(sim, "IED8", t0=943)
        trigger_ied_cb_trip(sim,  "IED3", t0=948)

        # Coupler stress 2
        trigger_ied_cb_close(sim, "IED3", t0=1010)
        trigger_ied_cb_trip(sim,  "IED5", t0=1012)
        trigger_ied_cb_trip(sim,  "IED7", t0=1016)
        trigger_ied_cb_close(sim, "IED5", t0=1020)
        trigger_ied_cb_close(sim, "IED7", t0=1024)
        trigger_ied_cb_trip(sim,  "IED3", t0=1031)

        # Optional: one late single-feeder event (keeps tail from being “too perfect”)
        trigger_ied_cb_trip(sim,  "IED4", t0=1110);  trigger_ied_cb_close(sim, "IED4", t0=1132)

        # --- End: decoupled, then quiet tail ---
        # (no events) t=1132..1200

        return t
    elif scenario == "val":
        # --- VALIDATION (benign-only), 600 s total ---
        # Goal: choose threshold at a target FPR using benign data only.
        # Design: mostly quiet + a small amount of representative switching + one coupled overlap.

        # --- Warm-up / quiet baseline ---
        # (no events) t=0..120


        # =========================
        # Island A (early): 120..240
        # =========================

        # One clean single-feeder event
        trigger_ied_cb_trip(sim,  "IED4", t0=140);  trigger_ied_cb_close(sim, "IED4", t0=162)

        # Another clean single-feeder event (other section)
        trigger_ied_cb_trip(sim,  "IED7", t0=200);  trigger_ied_cb_close(sim, "IED7", t0=222)


        # --- Quiet gap (lets you observe steady-state again) ---
        # (no events) t=222..320


        # =========================
        # Island B (mid): 320..420
        # =========================

        # One moderate coupled overlap window (single op per side, not "stress")
        trigger_ied_cb_close(sim, "IED3", t0=340)
        trigger_ied_cb_trip(sim,  "IED5", t0=343);  trigger_ied_cb_close(sim, "IED5", t0=349)
        trigger_ied_cb_trip(sim,  "IED8", t0=353);  trigger_ied_cb_close(sim, "IED8", t0=359)
        trigger_ied_cb_trip(sim,  "IED3", t0=368)


        # --- Quiet tail (important for stable low-FPR thresholding) ---
        # (no events) t=368..600
    elif scenario == "train":
        # --- TRAIN (benign-only), 1200 s total ---
        # Goal: learn normal heartbeat + occasional realistic switching + a few coupled overlaps
        # Not goal: saturate with rare stress patterns

        # --- Warm-up: quiet baseline ---
        # (no events) t=0..120


        # =========================
        # Island A (early): 120..320
        # =========================

        # Two clean single-feeder events (one per section)
        trigger_ied_cb_trip(sim,  "IED4", t0=140);  trigger_ied_cb_close(sim, "IED4", t0=162)
        trigger_ied_cb_trip(sim,  "IED7", t0=210);  trigger_ied_cb_close(sim, "IED7", t0=232)

        # One moderate coupled overlap window (single op per side)
        trigger_ied_cb_close(sim, "IED3", t0=270)
        trigger_ied_cb_trip(sim,  "IED5", t0=273);  trigger_ied_cb_close(sim, "IED5", t0=279)
        trigger_ied_cb_trip(sim,  "IED8", t0=283);  trigger_ied_cb_close(sim, "IED8", t0=289)
        trigger_ied_cb_trip(sim,  "IED3", t0=298)


        # --- Long idle gap ---
        # (no events) t=300..560


        # =========================
        # Island B (mid): 560..760
        # =========================

        # Another pair of clean single-feeder events (different feeders than Island A)
        trigger_ied_cb_trip(sim,  "IED6", t0=600);  trigger_ied_cb_close(sim, "IED6", t0=622)
        trigger_ied_cb_trip(sim,  "IED9", t0=670);  trigger_ied_cb_close(sim, "IED9", t0=692)

        # Short coupled overlap window (lighter than test)
        trigger_ied_cb_close(sim, "IED3", t0=720)
        trigger_ied_cb_trip(sim,  "IED4", t0=723);  trigger_ied_cb_close(sim, "IED4", t0=729)
        trigger_ied_cb_trip(sim,  "IED3", t0=740)


        # --- Long idle gap ---
        # (no events) t=740..960


        # ==========================
        # Island C (late): 960..1120
        # ==========================

        # One “mild” couple/decouple cycle with a single feeder op inside
        # (Training should see the coupler used, but not the full stress pattern repeatedly)
        trigger_ied_cb_close(sim, "IED3", t0=1000)
        trigger_ied_cb_trip(sim,  "IED8", t0=1003); trigger_ied_cb_close(sim, "IED8", t0=1010)
        trigger_ied_cb_trip(sim,  "IED3", t0=1022)

        # One final single-feeder op near the end
        trigger_ied_cb_trip(sim,  "IED5", t0=1090); trigger_ied_cb_close(sim, "IED5", t0=1112)

        # --- Quiet tail ---
        # (no events) t=1112..1200
        return 