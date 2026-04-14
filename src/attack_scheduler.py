# schedule_attacks.py
from __future__ import annotations

from pathlib import Path
import random
from typing import List, Optional, Sequence, Tuple

from attack_config import AttackScenarioConfig


def _ied_name(x) -> str:
    return getattr(x, "name", str(x))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _unique_sorted(xs: Sequence[float]) -> List[float]:
    return sorted(set(float(x) for x in xs))


def _iter_attack_slots(
    t_end: int,
    period_s: int,
    t_start: int = 1,
    align_mod: Optional[int] = None,
) -> List[int]:
    """
    Generate candidate 'anchor' seconds.
    If align_mod is set, pick t where t % align_mod == 0 (like your old t%12==0).
    """
    slots = []
    for t in range(t_start, t_end + 1):
        if align_mod is not None:
            if t % align_mod == 0:
                slots.append(t)
        else:
            if (t - t_start) % period_s == 0:
                slots.append(t)
    return slots


def _pick_streams(rng: random.Random, streams: Sequence[str], k_range: Tuple[int, int]) -> List[str]:
    k = rng.randint(k_range[0], k_range[1])
    k = max(1, min(k, len(streams)))
    return rng.sample(list(streams), k=k)


def _pick_camouflage_anchor(
    rng: random.Random,
    candidates: Sequence[int],
    switching_times: Optional[Sequence[float]],
    camo_prob: float,
    camo_jitter_s: float,
) -> float:
    """
    Choose an anchor time.
    With probability camo_prob, draw near a switching time (if provided).
    Otherwise use a regular candidate slot.
    """
    if switching_times and rng.random() < camo_prob:
        sw = rng.choice(list(switching_times))
        return float(sw + rng.uniform(-camo_jitter_s, camo_jitter_s))
    return float(rng.choice(list(candidates)))

def schedule_attacks(
        substation,
        attacker: Optional[str] = None, # None | "naive" | "multi" | "aware"
        t_end: int = 1200,
        base_dir: Path = Path("toolchain"),
        switching_times: Optional[Sequence[float]] = None, # For aware attacker only
) -> None:
    attacker = (attacker or "").strip().lower() if attacker is not None else None
    if attacker not in (None, "naive", "stealth", "aware"):
        raise ValueError(f"Unknown attacker: {attacker}")

    rng = random.Random(1)  # deterministic schedules

    ieds_all = [_ied_name(x) for x in list(substation.ieds)]
    cfgs0 = [AttackScenarioConfig.load_for_ied(ied, base_dir=base_dir) for ied in ieds_all]

    # Reset all configs
    for cfg in cfgs0:
        cfg.disable_all()
        cfg.clear_dos_attacks_keep_one_template_per_stream()
        cfg.save()

    if attacker is None:
        return
    
    cfgs = [AttackScenarioConfig.load_for_ied(ied, base_dir=base_dir) for ied in ieds_all]

    # -------------------------
    # Common helpers
    # -------------------------
    def clamp(x: float, lo: float, hi: float) -> float:
        return lo if x < lo else hi if x > hi else x

    def unique_sorted(xs: Optional[Sequence[float]]) -> Optional[List[float]]:
        if not xs:
            return None
        return sorted({float(x) for x in xs})

    def pick_streams(k_range: Tuple[int, int], pool: Tuple[str, ...]) -> List[str]:
        k = rng.randint(k_range[0], k_range[1])
        k = max(1, min(k, len(pool)))
        out = list(pool)
        rng.shuffle(out)
        return out[:k]

    def choose_anchor_times(*, t_end_eff: int, period_s: int, offset_s: int = 0) -> List[float]:
        """
        Deterministic-ish anchor slots to keep "budget cadence" comparable across attacker types.
        """
        anchors = []
        t = float(offset_s)
        while t < float(t_end_eff):
            anchors.append(t)
            t += float(period_s)
        return anchors

    def pick_camouflage_anchor(
        anchor: float,
        sw_times: Optional[List[float]],
        *,
        camo_prob: float,
        camo_jitter_s: float,
    ) -> float:
        """
        With probability camo_prob, move the anchor close to a randomly chosen switching time.
        """
        if not sw_times or rng.random() > camo_prob:
            return anchor

        t_sw = rng.choice(sw_times)
        return t_sw + rng.uniform(-camo_jitter_s, camo_jitter_s)

    def apply_attacks_for_ied(cfg, plan: List[dict]) -> int:
        """
        plan element fields expected:
          stream, t0, sum, pps, stNum, sqNum
        Returns number of attack packets scheduled.
        """
        n = 0
        for a in plan:
            cfg.configure_dos_attack(
                stream=a["stream"],
                t0=float(a["t0"]),
                sum=int(a["sum"]),
                pps=int(a["pps"]),
                payload_overrides={"stNum": int(a.get("stNum", 0)), "sqNum": int(a.get("sqNum", 0))},
            )
            n += int(a["sum"])
        return n
    
    # -------------------------
    # Attacker parameterization
    # -------------------------

    # Stream pool in your environment
    STREAMS = ("CTRL", "PROT", "MEAS")

    # “budget cadence”: how often we *consider* launching something
    # Keep this equal across stealth/aware for comparability.
    CADENCE_S = 12

    # Per attacker configs
    if attacker == "naive":
        # Very naive:
        # - attacks only occasionally
        # - but when it does, it injects long, loud, regular bursts
        # - no jitter, no camouflage, fixed counters
        pps = 25
        n_per = 60
        k_range = (1, 1)          # single stream only
        t0_jitter = 0.0
        camo_prob = 0.0
        st_sentinel = 0
        sq_sentinel = 0
        offsets_patterns = ((0.0,),)

        # Attack only every 4th anchor:
        # 1200 s / 12 s cadence = 100 anchors
        # 100 / 4 = 25 bursts
        # 25 * 60 = 1500 packets total
        naive_anchor_stride = 4

    elif attacker == "stealth":
        # distributed + jitter + microbursts; not synchronized
        # "protocol-aware-ish" part: you emulate more realistic burst sizes + timing jitter and you split across streams.
        pps_range = (8, 18)                 # lower per-stream rate
        n_per_range = (6, 18)               # microbursts
        k_range = (1, 2)                    # 1–2 streams per anchor
        t0_jitter = 2.0                     # seconds
        camo_prob = 0.25                    # mild camouflage (optional)
        camo_jitter = 2.0
        st_sentinel = rng.randint(5, 20)    # keep fixed (not synchronized)
        sq_sentinel = 0                     # keep fixed start (not synchronized)
        offsets_patterns = (
            (0.0,),
            (-0.6, 0.0),
            (-0.6, 0.0, 0.6),
            (-1.2, 0.0, 1.2),
        )
        offsets_weights = (0.45, 0.35, 0.10, 0.10)
    
    else:  # attacker == "aware"
        # synchronized + attacks during switching
        # stNum=-1 and sqNum=-1 means: "copy from legit stream" (your implemented behavior)
        pps_range = (6, 14)          # even lower per-stream, tries to blend
        n_per_range = (6, 18)
        k_range = (1, 2)
        t0_jitter = 1.0
        camo_prob = 0.75             # strong camouflage near switching
        camo_jitter = 1.5
        st_sentinel = -1             # sync stNum from legit
        sq_sentinel = -1             # sync sqNum from legit (+1)
        offsets_patterns = (
            (0.0,),
            (-0.6, 0.0),
            (-1.2, 0.0, 1.2),
        )
        offsets_weights = (0.55, 0.30, 0.15)

        sw_times = unique_sorted(switching_times)
        if not sw_times:
            # If you call aware without switching_times, it degenerates into stealth+sync.
            sw_times = None
    
    # -------------------------
    # Build schedule
    # -------------------------
    anchors = choose_anchor_times(t_end_eff=int(t_end), period_s=CADENCE_S, offset_s=0)
    if not anchors:
        raise ValueError("No anchors; check t_end and cadence.")

    ied_idx = 0
    n_total = 0

    # round-robin assignment across IEDs (keeps distribution even)
    for a0 in anchors:
        if ied_idx >= len(cfgs):
            ied_idx = 0
        cfg = cfgs[ied_idx]

        if attacker == "naive":
            # Only attack every 4th anchor to keep the total budget near 1500
            # while making each burst much more obvious and prolonged.
            anchor_idx = int(a0 // CADENCE_S)
            if anchor_idx % naive_anchor_stride == 0:
                stream = STREAMS[ied_idx % len(STREAMS)]
                t0 = clamp(a0 + t0_jitter, 0.0, float(t_end - 1))
                plan = [{
                    "stream": stream,
                    "t0": t0,
                    "sum": n_per,
                    "pps": pps,
                    "stNum": st_sentinel,
                    "sqNum": sq_sentinel,
                }]
                n_total += apply_attacks_for_ied(cfg, plan)
        else:
            # stealth/aware: camouflage + jitter + pick streams + pick offsets
            anchor = a0

            if attacker == "stealth":
                anchor = pick_camouflage_anchor(anchor, None, camo_prob=camo_prob, camo_jitter_s=camo_jitter)  # mild/none
            else:
                anchor = pick_camouflage_anchor(anchor, sw_times, camo_prob=camo_prob, camo_jitter_s=camo_jitter)

            anchor += rng.uniform(-t0_jitter, t0_jitter)
            anchor = clamp(anchor, 0.0, float(t_end - 1))

            picked = pick_streams(k_range, STREAMS)

            # pattern
            pattern = rng.choices(list(offsets_patterns), weights=list(offsets_weights), k=1)[0]
            offsets = list(pattern)[: len(picked)]
            rng.shuffle(picked)

            plan = []
            for stream, off in zip(picked, offsets):
                t0 = clamp(anchor + float(off), 0.0, float(t_end - 1))

                pps = rng.randint(*pps_range)
                n_per = rng.randint(*n_per_range)

                plan.append({
                    "stream": stream,
                    "t0": t0,
                    "sum": n_per,
                    "pps": pps,
                    "stNum": st_sentinel,
                    "sqNum": sq_sentinel,
                })

            n_total += apply_attacks_for_ied(cfg, plan)

        ied_idx += 1

    # Save all modified configs
    for cfg in cfgs:
        cfg.save()

    print(f"[attacks] attacker={attacker}  t_end={t_end}  NUMBER OF ATTACK PACKETS: {n_total}")












def schedule_attacks2(
    scenario: str,
    substation,
    *,
    mode: str = "baseline",  # "baseline" | "stealth"
    # common
    t_end: int = 600,
    base_dir: Path = Path("toolchain"),
    # baseline params (matches your old logic)
    baseline_pps: int = 25,
    baseline_n_per_burst: int = 50,
    baseline_align_mod: int = 12,
    baseline_triplet_offsets: Tuple[float, float, float] = (-3.0, 0.0, 3.0),
    # stealth params
    stealth_pps_range: Tuple[int, int] = (12, 28),
    stealth_n_per_burst_range: Tuple[int, int] = (6, 18),  # micro-bursts
    stealth_align_mod: int = 12,  # keep the same "budget cadence" if you want comparability
    stealth_t0_jitter_s: float = 2.0,
    stealth_streams: Tuple[str, ...] = ("CTRL", "PROT", "MEAS"),
    stealth_stream_k_range: Tuple[int, int] = (1, 2),  # pick 1–2 streams per anchor
    stealth_offset_patterns: Tuple[Tuple[float, ...], ...] = (
        (0.0,),                 # single
        (-0.6, 0.0),            # tight pair
        (-0.6, 0.0, 0.6),       # tight triplet (rarely picked if k_range limits)
        (-1.2, 0.0, 1.2),       # wider triplet
    ),
    stealth_pattern_weights: Tuple[float, ...] = (0.45, 0.35, 0.10, 0.10),
    stealth_camo_prob: float = 0.55,
    stealth_camo_jitter_s: float = 1.5,
    # Optional: provide approximate switching times to camouflage around (seconds)
    switching_times: Optional[Sequence[float]] = None,
) -> None:
    """
    Configure DoS/flooding attacks in AttackScenarioConfiguration.xml for each IED.

    - scenario="clear": disables all attacks, keeps one template per stream.
    - mode="baseline": reproduces your old periodic 3-burst pattern.
    - mode="stealth": micro-bursts + jitter + partial stream selection + optional camouflage near switching windows.

    Notes:
    - Uses round-robin IED assignment like your original script.
    - Keeps the overall “attack budget” comparable by using the same anchor cadence (default mod=12).
    """
    rng = None
    ieds_all = [_ied_name(x) for x in list(substation.ieds)]

    # Load + reset all configs
    cfgs0 = [AttackScenarioConfig.load_for_ied(ied, base_dir=base_dir) for ied in ieds_all]
    for cfg in cfgs0:
        cfg.disable_all()
        cfg.clear_dos_attacks_keep_one_template_per_stream()
        cfg.save()

    if scenario == "clear":
        return

    # Determine horizon by scenario if you kept your old naming
    if scenario == "test":
        rng = random.Random(1)
        t_end_eff = int(t_end)
    elif scenario == "source":
        rng = random.Random(2)
        t_end_eff = int(t_end)
    else:
        # allow arbitrary names, but keep consistent behavior
        t_end_eff = int(t_end)

    cfgs = [AttackScenarioConfig.load_for_ied(ied, base_dir=base_dir) for ied in ieds_all]

    # Candidate anchor times (seconds)
    if mode == "baseline":
        anchors = _iter_attack_slots(t_end_eff, period_s=baseline_align_mod, align_mod=baseline_align_mod)
    elif mode == "stealth":
        anchors = _iter_attack_slots(t_end_eff, period_s=stealth_align_mod, align_mod=stealth_align_mod)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    if not anchors:
        raise ValueError("No anchors generated. Check t_end / align_mod.")

    sw_times = _unique_sorted(switching_times) if switching_times else None

    ied_idx = 0
    n_total = 0

    for t in anchors:
        if ied_idx >= len(ieds_all):
            ied_idx = 0

        cfg = cfgs[ied_idx]

        if mode == "baseline":
            # Reproduce your old behavior exactly (except we iterate anchors directly)
            offsets = baseline_triplet_offsets
            streams = ("CTRL", "PROT", "MEAS")
            for s, off in zip(streams, offsets):
                t0 = float(t) + float(off)
                # clamp to file bounds
                t0 = _clamp(t0, 0.0, float(t_end_eff - 1))
                cfg.configure_dos_attack(stream=s, t0=t0, sum=baseline_n_per_burst, pps=baseline_pps)
                n_total += baseline_n_per_burst

        else:
            # -------------------------
            # STEALTH MODE:
            # - pick 1–2 streams
            # - micro-bursts (0.2–1.5 s typically)
            # - jitter start time
            # - optionally camouflage near switching windows
            # -------------------------
            anchor = _pick_camouflage_anchor(
                rng,
                candidates=anchors,
                switching_times=sw_times,
                camo_prob=stealth_camo_prob,
                camo_jitter_s=stealth_camo_jitter_s,
            )
            anchor += rng.uniform(-stealth_t0_jitter_s, stealth_t0_jitter_s)
            anchor = _clamp(anchor, 0.0, float(t_end_eff - 1))

            picked_streams = _pick_streams(rng, stealth_streams, stealth_stream_k_range)

            # pick an offset pattern; then map offsets to the selected streams
            pattern = rng.choices(list(stealth_offset_patterns), weights=list(stealth_pattern_weights), k=1)[0]

            # Use at most len(picked_streams) offsets; if pattern longer, truncate.
            offsets = list(pattern)[: len(picked_streams)]

            # Randomize which stream gets which offset (prevents "CTRL always first")
            rng.shuffle(picked_streams)

            for s, off in zip(picked_streams, offsets):
                pps = rng.randint(*stealth_pps_range)
                n_per = rng.randint(*stealth_n_per_burst_range)

                t0 = anchor + float(off)
                t0 = _clamp(t0, 0.0, float(t_end_eff - 1))

                cfg.configure_dos_attack(stream=s, t0=float(t0), sum=int(n_per), pps=int(pps))
                n_total += int(n_per)

        ied_idx += 1

    print(f"[attacks] mode={mode}  scenario={scenario}  NUMBER OF ATTACK PACKETS: {n_total}")
    for cfg in cfgs:
        cfg.save()


# -------------------------
# Example usage
# -------------------------
if __name__ == "__main__":
    # You would call schedule_attacks(...) from your simulation driver, not usually as __main__.
    pass