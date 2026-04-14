"""
Detailed per-line scoring demo for a single song.
Shows the user experience: every line gets a score card.
"""
import os, re, random

SAMPLE_RATE = 16000
HOP_MS = 20
HOP_SAMPLES = SAMPLE_RATE * HOP_MS // 1000
EARLY_FRAMES = 200 // HOP_MS
COMBO_THR = 82

def lrc_parse(text):
    lines_out, tokens_out = [], []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        ts_m = re.match(r"\[(\d+):(\d+)\.(\d+)\]", raw)
        if ts_m:
            mm, ss, ms = int(ts_m.group(1)), int(ts_m.group(2)), int(ts_m.group(3))
            start_ms = mm * 60000 + ss * 1000 + ms
            toks = [(int(d), int(s)) for d, s in re.findall(r"<(\d+),(\d+)>", raw)]
            tok_off = len(tokens_out)
            cur = start_ms
            for dur, _ in toks:
                tokens_out.append((cur, cur + dur))
                cur += dur
            lines_out.append({"s": start_ms, "e": cur if toks else start_ms,
                              "toff": tok_off, "tcnt": len(toks)})
        else:
            toks = [(int(d), int(s)) for d, s in re.findall(r"<(\d+),(\d+)>", raw)]
            if toks and lines_out:
                ln = lines_out[-1]
                cur = ln["e"] if ln["tcnt"] > 0 else ln["s"]
                for dur, _ in toks:
                    tokens_out.append((cur, cur + dur))
                    cur += dur
                    ln["tcnt"] += 1
                ln["e"] = cur
    return lines_out, tokens_out

def clamp(x, lo, hi): return max(lo, min(hi, x))
def frame_energy(samples): return sum(s * s for s in samples) // len(samples)

def get_lyric_text(raw_lines, idx):
    count = 0
    for raw in raw_lines:
        raw = raw.strip()
        if not raw:
            continue
        ts_m = re.match(r"\[(\d+):(\d+)\.(\d+)\](.*)$", raw)
        if ts_m:
            text = ts_m.group(4).strip()
            if text and not text.startswith("<"):
                if count == idx:
                    return text
                count += 1
    return ""


def main():
    path = r"C:\Users\ma\Desktop\lrctxt\7198065.txt"
    with open(path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    lines, tokens = lrc_parse(raw_text)
    raw_lines = raw_text.splitlines()

    cal_sum = 0
    for _ in range(15):
        noise = [random.randint(-50, 50) for _ in range(HOP_SAMPLES)]
        cal_sum += frame_energy(noise)
    noise_avg = cal_sum // 15
    thr_e = noise_avg * 4 + 100
    onset_thr = thr_e // 2

    profiles = {
        "good": {"amp": (6000, 14000), "gap": 0.05},
        "mid":  {"amp": (2000, 8000),  "gap": 0.25},
        "lazy": {"amp": (500, 3000),   "gap": 0.50},
    }

    for pname, pcfg in profiles.items():
        print(f"\n{'='*72}")
        print(f"  Singer Profile: {pname.upper()}")
        print(f"  Song: 7198065.txt ({len(lines)} lines, {len(tokens)} tokens)")
        print(f"{'='*72}")

        random.seed(42)
        combo = 0
        max_combo = 0
        prev_e = 0
        lyric_idx = 0

        for li, ln in enumerate(lines):
            la = {"cnt": 0, "voiced": 0, "sum_e": 0, "max_e": 0,
                  "min_e": 0x7FFFFFFF, "onset_max": 0}
            seg_scores = []

            for j in range(ln["tcnt"]):
                tk = tokens[ln["toff"] + j]
                dur = tk[1] - tk[0]
                n_frames = max(1, dur // HOP_MS)

                sa = {"cnt": 0, "voiced": 0, "sum_e": 0, "max_e": 0,
                      "min_e": 0x7FFFFFFF, "onset_max": 0}

                for fi in range(n_frames):
                    if random.random() < pcfg["gap"]:
                        amp = random.randint(10, 60)
                    else:
                        amp = random.randint(*pcfg["amp"])
                    samples = [random.randint(-amp, amp) for _ in range(HOP_SAMPLES)]
                    e = frame_energy(samples)
                    voiced = 1 if e > thr_e else 0
                    onset = max(0, e - prev_e)

                    for acc, frm_idx in [(sa, fi), (la, la["cnt"])]:
                        acc["cnt"] += 1
                        acc["voiced"] += voiced
                        acc["sum_e"] += e
                        if e > acc["max_e"]: acc["max_e"] = e
                        if e < acc["min_e"]: acc["min_e"] = e
                        if frm_idx < EARLY_FRAMES and onset > acc["onset_max"]:
                            acc["onset_max"] = onset
                    prev_e = e

                cnt = max(sa["cnt"], 1)
                p = sa["voiced"] * 100 // cnt
                base = 68 + p * 22 // 100
                bonus = 5 if sa["onset_max"] > onset_thr else 0
                seg_avg_e = sa["sum_e"] // cnt
                e_bonus = clamp(seg_avg_e * 3 // max(thr_e, 1), 0, 3)
                ss = clamp(base + bonus + e_bonus, 68, 95)
                seg_scores.append(ss)

                if ss >= COMBO_THR:
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

            lyric = get_lyric_text(raw_lines, li)
            t_str = f"{ln['s']//60000:02d}:{(ln['s']%60000)//1000:02d}.{ln['s']%1000:03d}"
            seg_str = ",".join(str(s) for s in seg_scores)

            rating = "S" if total >= 90 else "A" if total >= 84 else "B" if total >= 78 else "C"
            emoji = {"S": "**", "A": "+", "B": "~", "C": "-"}[rating]

            print(f"\n  [{t_str}] {lyric}")
            print(f"    Segments({len(seg_scores)}): [{seg_str}]")
            print(f"    {emoji} 技巧={tech} 感情={emo} 气场={vibe} 节奏={rhythm}  "
                  f"总分={total}({rating})  combo={combo}")

        print(f"\n  --- Summary: MaxCombo={max_combo} ---")


if __name__ == "__main__":
    main()
