"""
Batch Lyrics → Animation Script Preprocessor
Scans a directory of .txt lyric files, outputs .json animation scripts.
"""
import sys
import json
from pathlib import Path
from preprocess_lyrics import parse_lyrics, lrcjson_dict, segments_from_lyrics


def process_one(txt_path: Path, out_dir: Path) -> dict:
    """Process a single lyrics file. Returns summary dict."""
    song_id = txt_path.stem
    try:
        lyrics = parse_lyrics(str(txt_path))
    except Exception as e:
        return {"song_id": song_id, "status": "PARSE_ERROR", "error": str(e)}

    if not lyrics:
        return {"song_id": song_id, "status": "EMPTY"}

    segments, chorus_idx = segments_from_lyrics(lyrics, window=3)
    output = lrcjson_dict(song_id, segments)

    out_path = out_dir / f"{song_id}.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    total_ms = segments[-1]["end"] if segments else 0
    state_totals = {}
    for seg in segments:
        d = seg["end"] - seg["start"]
        state_totals[seg["state"]] = state_totals.get(seg["state"], 0) + d

    chorus_count = sum(1 for s in segments if s["state"] == "chorus")
    sing_count = sum(1 for s in segments if s["state"] == "sing")
    overlap_count = sum(1 for i in range(1, len(segments)) if segments[i]["start"] < segments[i - 1]["end"])
    short_count = sum(1 for seg in segments if seg["end"] - seg["start"] < 2500)

    return {
        "song_id": song_id,
        "status": "OK",
        "lines": len(lyrics),
        "segments": len(segments),
        "duration_s": round(total_ms / 1000, 1),
        "idle_pct": round(state_totals.get("idle", 0) * 100 / max(total_ms, 1)),
        "sing_pct": round(state_totals.get("sing", 0) * 100 / max(total_ms, 1)),
        "chorus_pct": round(state_totals.get("chorus", 0) * 100 / max(total_ms, 1)),
        "chorus_sections": chorus_count,
        "sing_sections": sing_count,
        "chorus_lines": len([i for i in range(len(lyrics)) if i in chorus_idx]),
        "overlap_count": overlap_count,
        "short_segments": short_count,
    }


def main():
    # Line-buffered stdout: avoids "nothing prints for a long time" when piped or on some Windows consoles.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError, ValueError):
        pass

    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Users\ma\Desktop\lrctxt")
    output_dir = input_dir / "lrcjson"
    output_dir.mkdir(exist_ok=True)

    txt_files = sorted(input_dir.glob("*.txt"))
    print(f"Input:  {input_dir}", flush=True)
    print(f"Output: {output_dir}", flush=True)
    print(f"Files:  {len(txt_files)}", flush=True)
    print("=" * 90, flush=True)

    results = []
    for f in txt_files:
        r = process_one(f, output_dir)
        results.append(r)
        status = r["status"]
        if status == "OK":
            print(f"  [OK]  {r['song_id']}  "
                  f"{r['lines']:3d} lines  {r['segments']:2d} segs  "
                  f"{r['duration_s']:6.1f}s  "
                  f"idle={r['idle_pct']:2d}% sing={r['sing_pct']:2d}% chorus={r['chorus_pct']:2d}%  "
                  f"(chorus_sections={r['chorus_sections']})", flush=True)
        else:
            print(f"  [ERR] {r['song_id']}  {status}  {r.get('error','')}", flush=True)

    print("=" * 90, flush=True)

    # Quality checks
    print("\n=== Quality Check ===", flush=True)
    warnings = []
    for r in results:
        if r["status"] != "OK":
            warnings.append(f"  [FAIL] {r['song_id']}: {r['status']}")
            continue
        if r["chorus_pct"] == 0:
            warnings.append(f"  [WARN] {r['song_id']}: No chorus detected (0%)")
        if r["chorus_pct"] > 60:
            warnings.append(f"  [WARN] {r['song_id']}: Chorus > 60% ({r['chorus_pct']}%) - may be over-detected")
        if r["idle_pct"] > 80:
            warnings.append(f"  [WARN] {r['song_id']}: Idle > 80% ({r['idle_pct']}%) - very few lyrics?")
        if r["segments"] < 3:
            warnings.append(f"  [WARN] {r['song_id']}: Only {r['segments']} segments - too few?")
        if r["overlap_count"] > 0:
            warnings.append(f"  [WARN] {r['song_id']}: {r['overlap_count']} overlapping segments remain")
        if r["short_segments"] > 0:
            warnings.append(f"  [WARN] {r['song_id']}: {r['short_segments']} segments shorter than 2.5s remain")

    if warnings:
        for w in warnings:
            print(w, flush=True)
    else:
        print("  All files passed quality checks.", flush=True)

    # Summary
    ok_count = sum(1 for r in results if r["status"] == "OK")
    print(f"\n=== Summary ===", flush=True)
    print(f"  Processed: {ok_count}/{len(txt_files)} OK", flush=True)
    print(f"  Output dir: {output_dir}", flush=True)


if __name__ == "__main__":
    main()
