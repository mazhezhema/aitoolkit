"""
Test scoring engine against real lrctxt files.
Simulates three singer profiles:
  - 'good':  loud, steady
  - 'mid':   moderate, some gaps
  - 'lazy':  quiet, lots of gaps
"""
import os
import re
import random
import sys

LRCTXT_DIR = r"C:\Users\ma\Desktop\lrctxt"
SAMPLE_RATE = 16000
HOP_MS = 20
HOP_SAMPLES = SAMPLE_RATE * HOP_MS // 1000  # 320
EARLY_FRAMES = 200 // HOP_MS  # 10

# ── lrctxt parser ───────────────────────────────────────────────

def lrc_parse(text):
    """Parse lrctxt, merging consecutive lines with the same timestamp."""
    lines_out = []
    tokens_out = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        ts_m = re.match(r"\[(\d+):(\d+)\.(\d+)\]", raw)
        if not ts_m:
            continue
        mm, ss, ms = int(ts_m.group(1)), int(ts_m.group(2)), int(ts_m.group(3))
        start_ms = mm * 60000 + ss * 1000 + ms
        toks = [(int(d), int(s)) for d, s in re.findall(r"<(\d+),(\d+)>", raw)]
        if not toks:
            if not lines_out or lines_out[-1]["s"] != start_ms:
                lines_out.append({"s": start_ms, "e": start_ms,
                                  "toff": len(tokens_out), "tcnt": 0})
            continue
        if lines_out and lines_out[-1]["s"] == start_ms and lines_out[-1]["tcnt"] == 0:
            ln = lines_out[-1]
        else:
            ln = {"s": start_ms, "e": start_ms,
                  "toff": len(tokens_out), "tcnt": 0}
            lines_out.append(ln)
        cur = start_ms
        for dur, _ in toks:
            tokens_out.append((cur, cur + dur))
            cur += dur
            ln["tcnt"] += 1
        ln["e"] = cur
    final = []
    for ln in lines_out:
        if ln["tcnt"] > 0:
            final.append(ln)
    return final, tokens_out

# ── scoring engine (mirrors score_core.c) ───────────────────────

def frame_energy(samples):
    return sum(s * s for s in samples) // len(samples) if samples else 0

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def calibrate():
    cal_sum = 0
    for _ in range(15):
        noise = [random.randint(-50, 50) for _ in range(HOP_SAMPLES)]
        cal_sum += frame_energy(noise)
    noise_avg = cal_sum // 15
    thr_e = noise_avg * 4 + 100
    return thr_e, thr_e // 2

PROFILES = {
    "good":  {"amp_range": (6000, 14000), "gap_prob": 0.05},
    "mid":   {"amp_range": (2000, 8000),  "gap_prob": 0.25},
    "lazy":  {"amp_range": (500, 3000),   "gap_prob": 0.50},
}

def simulate_song(lines, tokens, thr_e, onset_thr, profile):
    cfg = PROFILES[profile]
    combo = 0
    max_combo = 0
    prev_e = 0
    combo_thr = 82

    seg_scores = []
    line_results = []

    for ln in lines:
        la = {"cnt": 0, "voiced": 0, "sum_e": 0, "max_e": 0,
              "min_e": 0x7FFFFFFF, "onset_max": 0}
        line_frames = 0

        for j in range(ln["tcnt"]):
            tk = tokens[ln["toff"] + j]
            dur = tk[1] - tk[0]
            n_frames = max(1, dur // HOP_MS)

            sa = {"cnt": 0, "voiced": 0, "sum_e": 0, "max_e": 0,
                  "min_e": 0x7FFFFFFF, "onset_max": 0}
            seg_frames = 0

            for fi in range(n_frames):
                if random.random() < cfg["gap_prob"]:
                    amp = random.randint(10, 60)
                else:
                    amp = random.randint(*cfg["amp_range"])
                samples = [random.randint(-amp, amp) for _ in range(HOP_SAMPLES)]
                e = frame_energy(samples)
                voiced = 1 if e > thr_e else 0
                onset = max(0, e - prev_e)

                for acc, frm in [(sa, seg_frames), (la, line_frames)]:
                    acc["cnt"] += 1
                    acc["voiced"] += voiced
                    acc["sum_e"] += e
                    if e > acc["max_e"]: acc["max_e"] = e
                    if e < acc["min_e"]: acc["min_e"] = e
                    if frm < EARLY_FRAMES and onset > acc["onset_max"]:
                        acc["onset_max"] = onset

                seg_frames += 1
                line_frames += 1
                prev_e = e

            # seg end
            cnt = max(sa["cnt"], 1)
            p = sa["voiced"] * 100 // cnt
            base = 68 + p * 22 // 100
            bonus = 5 if sa["onset_max"] > onset_thr else 0
            seg_avg_e = sa["sum_e"] // cnt
            e_bonus = clamp(seg_avg_e * 3 // max(thr_e, 1), 0, 3)
            ss = clamp(base + bonus + e_bonus, 68, 95)
            seg_scores.append(ss)

            if ss >= combo_thr:
                combo += 1
            else:
                combo = 0
            if combo > max_combo:
                max_combo = combo

        # line end
        cnt = max(la["cnt"], 1)
        avg_e = la["sum_e"] // cnt

        tp = la["voiced"] * 100 // cnt
        tech = clamp(70 + tp * 25 // 100, 70, 95)

        dyn = la["max_e"] - min(la["min_e"], la["max_e"])
        raw = min(100, dyn * 100 // avg_e) if avg_e > 0 else 0
        vp = la["voiced"] * 100 // cnt
        ep = raw * vp // 100
        emo = clamp(70 + ep * 25 // 100, 70, 95)

        raw_pr = min(100, max(0, la["max_e"] * 100 // avg_e - 100)) if avg_e > 0 else 0
        pr = raw_pr * vp // 100
        vibe = clamp(70 + pr * 25 // 100, 70, 95)

        rp = clamp(la["onset_max"] * 100 // max(onset_thr, 1), 0, 200)
        rhythm = 74 + rp * 18 // 200
        rhythm = clamp(rhythm, 74, 92)

        total = (tech * 30 + emo * 30 + vibe * 25 + rhythm * 15) // 100
        total = clamp(total, 72, 96)

        line_results.append({
            "tech": tech, "emo": emo, "vibe": vibe,
            "rhythm": rhythm, "total": total,
        })

    return seg_scores, line_results, max_combo


def main():
    thr_e, onset_thr = calibrate()

    txt_files = sorted(f for f in os.listdir(LRCTXT_DIR) if f.endswith(".txt"))
    if not txt_files:
        print("No .txt files found.")
        return

    print(f"{'File':<16} {'Profile':<7} {'Lines':>5} {'Tokens':>6}  "
          f"{'SegAvg':>6} {'Tech':>4} {'Emo':>4} {'Vibe':>4} {'Rhy':>4} "
          f"{'Total':>5} {'MaxCombo':>8}")
    print("-" * 90)

    for fname in txt_files:
        path = os.path.join(LRCTXT_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        lines, tokens = lrc_parse(text)
        if not lines:
            print(f"{fname:<16} (no parseable lines)")
            continue

        for profile in ["good", "mid", "lazy"]:
            random.seed(42)
            seg_scores, line_results, max_combo = simulate_song(
                lines, tokens, thr_e, onset_thr, profile)

            avg_seg = sum(seg_scores) // max(len(seg_scores), 1)
            avg_tech = sum(r["tech"] for r in line_results) // max(len(line_results), 1)
            avg_emo = sum(r["emo"] for r in line_results) // max(len(line_results), 1)
            avg_vibe = sum(r["vibe"] for r in line_results) // max(len(line_results), 1)
            avg_rhy = sum(r["rhythm"] for r in line_results) // max(len(line_results), 1)
            avg_total = sum(r["total"] for r in line_results) // max(len(line_results), 1)

            label = fname if profile == "good" else ""
            print(f"{label:<16} {profile:<7} {len(lines):>5} {len(tokens):>6}  "
                  f"{avg_seg:>6} {avg_tech:>4} {avg_emo:>4} {avg_vibe:>4} {avg_rhy:>4} "
                  f"{avg_total:>5} {max_combo:>8}")

    print()
    print("SegAvg = average segment score (68-95)")
    print("Tech/Emo/Vibe/Rhy/Total = average line-level scores")
    print("MaxCombo = longest streak of segment scores >= 78")


if __name__ == "__main__":
    main()
