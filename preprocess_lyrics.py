"""
Lyrics → Animation Script Preprocessor
Input:  逐字歌词 txt (KRC-like format)
Output: JSON animation script with idle/sing/chorus segments
"""
import re
import json
import sys
from collections import Counter
from pathlib import Path


NORMALIZE_RE = re.compile(r"[\s，。！？、；：,.!?~…·“”\"'‘’（）()【】\-\u3000]+")


def parse_timestamp(ts_str: str) -> int:
    """[mm:ss.mmm] → milliseconds"""
    m = re.match(r"\[(\d+):(\d+)\.(\d+)\]", ts_str)
    if not m:
        return -1
    minutes, seconds, millis = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return minutes * 60000 + seconds * 1000 + millis


def parse_tokens(token_line: str) -> list[tuple[int, int]]:
    """Extract all <duration, space> pairs from a token line."""
    return [(int(t), int(s)) for t, s in re.findall(r"<(\d+),(\d+)>", token_line)]


def normalize_lyric_text(text: str) -> str:
    """Normalize text for repetition matching."""
    return NORMALIZE_RE.sub("", text).lower()


def parse_lyrics(filepath: str) -> list[dict]:
    """Parse lyrics file into structured lines."""
    lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        ts_match = re.match(r"(\[\d+:\d+\.\d+\])(.*)", line)
        if not ts_match:
            i += 1
            continue

        ts_str = ts_match.group(1)
        text = ts_match.group(2).strip()
        start_ms = parse_timestamp(ts_str)

        # <t,s> tokens may be on the same line (after text) or on the next line
        tokens = parse_tokens(line)
        if not tokens and i + 1 < len(lines):
            tokens = parse_tokens(lines[i + 1])
            i += 1

        total_duration = sum(t for t, _ in tokens) if tokens else 0
        end_ms = start_ms + total_duration

        result.append({
            "text": text,
            "normalized_text": normalize_lyric_text(text),
            "start": start_ms,
            "end": end_ms,
            "duration": total_duration,
        })
        i += 1

    return result


def _block_duration(lyrics_lines: list[dict], start_idx: int, length: int) -> int:
    end_idx = start_idx + length - 1
    return lyrics_lines[end_idx]["end"] - lyrics_lines[start_idx]["start"]


def _find_repeated_patterns(
    lyrics_lines: list[dict],
    min_block_lines: int = 2,
    max_block_lines: int = 8,
) -> list[dict]:
    """Find repeated contiguous lyric blocks using normalized text."""
    texts = [line["normalized_text"] for line in lyrics_lines]
    patterns: dict[str, dict] = {}
    n = len(texts)

    for i in range(n):
        if not texts[i]:
            continue
        for j in range(i + 1, n):
            if texts[i] != texts[j]:
                continue

            match_len = 0
            while (
                i + match_len < n
                and j + match_len < n
                and texts[i + match_len]
                and texts[i + match_len] == texts[j + match_len]
            ):
                match_len += 1

            upper = min(match_len, max_block_lines)
            for length in range(min_block_lines, upper + 1):
                key = "||".join(texts[i:i + length])
                pattern = patterns.setdefault(
                    key,
                    {
                        "key": key,
                        "line_count": length,
                        "starts": set(),
                        "durations": [],
                    },
                )
                pattern["starts"].update({i, j})

    result = []
    for pattern in patterns.values():
        starts = sorted(pattern["starts"])
        line_count = pattern["line_count"]
        if len(starts) < 2:
            continue

        durations = [_block_duration(lyrics_lines, start, line_count) for start in starts]
        avg_duration = sum(durations) / len(durations)
        result.append(
            {
                "line_count": line_count,
                "starts": starts,
                "avg_duration": avg_duration,
                "score": len(starts) * line_count * avg_duration,
            }
        )

    return result


def detect_chorus_by_repetition(lyrics_lines: list[dict], window: int = 3) -> set[int]:
    """
    Detect chorus by repeated normalized lyric blocks.
    Filters out very short hooks and over-long repeated verses.
    """
    if len(lyrics_lines) < 4:
        return set()

    song_duration = lyrics_lines[-1]["end"]
    max_chorus_duration = song_duration * 0.60
    selected_indices: set[int] = set()
    selected_duration = 0

    patterns = _find_repeated_patterns(
        lyrics_lines,
        min_block_lines=max(2, window - 1),
        max_block_lines=max(window + 3, 6),
    )

    eligible_patterns = [
        pattern
        for pattern in patterns
        if 8_000 <= pattern["avg_duration"] <= 60_000
    ]
    eligible_patterns.sort(key=lambda item: (-item["score"], item["avg_duration"]))

    for pattern in eligible_patterns:
        candidate_indices = set()
        for start in pattern["starts"]:
            for offset in range(pattern["line_count"]):
                candidate_indices.add(start + offset)

        new_indices = candidate_indices - selected_indices
        if not new_indices:
            continue

        new_duration = sum(lyrics_lines[idx]["duration"] for idx in new_indices)
        if selected_duration and selected_duration + new_duration > max_chorus_duration:
            continue

        selected_indices.update(candidate_indices)
        selected_duration += new_duration

    return refine_chorus_indices(lyrics_lines, selected_indices)


def build_segments(
    lyrics_lines: list[dict],
    chorus_indices: set[int],
    idle_gap_ms: int = 4000,
) -> list[dict]:
    """
    Build animation segments from parsed lyrics.
    - Gaps > idle_gap_ms between lines → idle
    - Chorus-marked lines → chorus
    - Everything else → sing
    """
    if not lyrics_lines:
        return []

    segments: list[dict] = []

    # Add leading idle (before first lyric)
    first_start = lyrics_lines[0]["start"]
    if first_start > 0:
        segments.append({"start": 0, "end": first_start, "state": "idle"})

    for i, line in enumerate(lyrics_lines):
        state = "chorus" if i in chorus_indices else "sing"
        next_start = lyrics_lines[i + 1]["start"] if i + 1 < len(lyrics_lines) else None
        line_end = line["end"] if next_start is None else min(line["end"], next_start)
        line_end = max(line["start"], line_end)

        # Check gap before this line (from previous line's end)
        if i > 0:
            prev_next_start = line["start"]
            prev_end = min(lyrics_lines[i - 1]["end"], prev_next_start)
            gap = line["start"] - prev_end
            if gap >= idle_gap_ms:
                segments.append({"start": prev_end, "end": line["start"], "state": "idle"})

        segments.append({"start": line["start"], "end": line_end, "state": state})

    return segments


def merge_adjacent(segments: list[dict]) -> list[dict]:
    """Merge consecutive segments with the same state."""
    if not segments:
        return []
    merged = [segments[0].copy()]
    for seg in segments[1:]:
        if seg["state"] == merged[-1]["state"] and seg["start"] <= merged[-1]["end"] + 500:
            merged[-1]["end"] = max(merged[-1]["end"], seg["end"])
        else:
            merged.append(seg.copy())
    return merged


def fill_gaps(segments: list[dict]) -> list[dict]:
    """Fill small gaps between segments with the previous state to ensure continuity."""
    if not segments:
        return []
    filled = [segments[0].copy()]
    for seg in segments[1:]:
        prev = filled[-1]
        if seg["start"] > prev["end"]:
            gap = seg["start"] - prev["end"]
            if gap < 4000:
                prev["end"] = seg["start"]
            else:
                filled.append({"start": prev["end"], "end": seg["start"], "state": "idle"})
        filled.append(seg.copy())
    return filled


def refine_chorus_indices(lyrics_lines: list[dict], chorus_indices: set[int]) -> set[int]:
    """Trim overly long chorus groups to their most repeated core lines."""
    if not chorus_indices:
        return chorus_indices

    text_count = Counter(line["normalized_text"] for line in lyrics_lines if line["normalized_text"])
    sorted_indices = sorted(chorus_indices)
    groups: list[list[int]] = []

    current_group = [sorted_indices[0]]
    for idx in sorted_indices[1:]:
        if idx == current_group[-1] + 1:
            current_group.append(idx)
        else:
            groups.append(current_group)
            current_group = [idx]
    groups.append(current_group)

    refined = set()
    for group in groups:
        group_start = lyrics_lines[group[0]]["start"]
        group_end = lyrics_lines[group[-1]]["end"]
        group_duration = group_end - group_start
        if group_duration <= 55_000:
            refined.update(group)
            continue

        core = {
            idx
            for idx in group
            if text_count.get(lyrics_lines[idx]["normalized_text"], 0) >= 3
        }
        if not core:
            max_count = max(text_count.get(lyrics_lines[idx]["normalized_text"], 0) for idx in group)
            core = {
                idx
                for idx in group
                if text_count.get(lyrics_lines[idx]["normalized_text"], 0) == max_count and max_count >= 2
            }

        expanded = set()
        for idx in core:
            expanded.update(range(max(group[0], idx - 1), min(group[-1], idx + 1) + 1))

        refined.update(expanded or group)

    return refined


def sanitize_segments(segments: list[dict]) -> list[dict]:
    """Sort segments and remove overlaps by clamping later starts."""
    if not segments:
        return []

    ordered = sorted(segments, key=lambda item: (item["start"], item["end"]))
    sanitized = []

    for seg in ordered:
        if seg["end"] <= seg["start"]:
            continue
        if not sanitized:
            sanitized.append(seg.copy())
            continue

        prev = sanitized[-1]
        if seg["state"] == prev["state"] and seg["start"] <= prev["end"]:
            prev["end"] = max(prev["end"], seg["end"])
            continue

        seg_copy = seg.copy()
        seg_copy["start"] = max(seg_copy["start"], prev["end"])
        if seg_copy["end"] <= seg_copy["start"]:
            continue
        sanitized.append(seg_copy)

    return sanitized


def compress_short_segments(segments: list[dict], min_segment_ms: int = 2_500) -> list[dict]:
    """Merge tiny segments into neighbors to avoid jumpy state changes."""
    if len(segments) <= 1:
        return segments

    items = [segment.copy() for segment in segments]
    changed = True
    while changed and len(items) > 1:
        changed = False
        idx = 0
        while idx < len(items):
            segment = items[idx]
            duration = segment["end"] - segment["start"]
            if duration >= min_segment_ms:
                idx += 1
                continue

            prev_seg = items[idx - 1] if idx > 0 else None
            next_seg = items[idx + 1] if idx + 1 < len(items) else None

            if prev_seg and next_seg and prev_seg["state"] == next_seg["state"]:
                prev_seg["end"] = next_seg["end"]
                del items[idx:idx + 2]
                changed = True
                idx = max(idx - 1, 0)
                continue

            if prev_seg and next_seg:
                prev_duration = prev_seg["end"] - prev_seg["start"]
                next_duration = next_seg["end"] - next_seg["start"]
                if prev_duration >= next_duration:
                    prev_seg["end"] = segment["end"]
                    del items[idx]
                    changed = True
                    idx = max(idx - 1, 0)
                    continue

                next_seg["start"] = segment["start"]
                del items[idx]
                changed = True
                continue

            if prev_seg:
                prev_seg["end"] = segment["end"]
                del items[idx]
                changed = True
                idx = max(idx - 1, 0)
                continue

            if next_seg:
                next_seg["start"] = segment["start"]
                del items[idx]
                changed = True
                continue

            idx += 1

        items = merge_adjacent(sanitize_segments(items))

    return items


def format_time(ms: int) -> str:
    """Format ms to mm:ss.mmm for readability."""
    m = ms // 60000
    s = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{m:02d}:{s:02d}.{millis:03d}"


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else r"D:\dev\aitoolkit\aitoolkit\7285583.txt"

    print(f"Parsing: {filepath}")
    lyrics = parse_lyrics(filepath)
    print(f"Found {len(lyrics)} lyric lines")
    print(f"Time range: {format_time(lyrics[0]['start'])} ~ {format_time(lyrics[-1]['end'])}")
    print()

    # Show parsed lines
    print("=== Parsed Lyrics ===")
    for i, l in enumerate(lyrics):
        print(f"  [{i:2d}] {format_time(l['start'])} ~ {format_time(l['end'])}  "
              f"({l['duration']:5d}ms)  {l['text']}")
    print()

    # Detect chorus
    chorus_idx = detect_chorus_by_repetition(lyrics, window=3)
    print(f"=== Chorus Detection ===")
    print(f"Chorus lines (by repetition): {sorted(chorus_idx)}")
    for i in sorted(chorus_idx):
        print(f"  [{i:2d}] {lyrics[i]['text']}")
    print()

    # Build segments
    segments = build_segments(lyrics, chorus_idx)
    segments = fill_gaps(segments)
    segments = sanitize_segments(segments)
    segments = merge_adjacent(segments)
    segments = compress_short_segments(segments)

    # Print timeline
    print("=== Animation Timeline ===")
    state_icons = {"idle": "[---]", "sing": "[SNG]", "chorus": "[CHO]"}
    for seg in segments:
        icon = state_icons.get(seg["state"], "[???]")
        duration = seg["end"] - seg["start"]
        bar_len = max(1, duration // 2000)
        bar = "#" * bar_len
        print(f"  {format_time(seg['start'])} ~ {format_time(seg['end'])}  "
              f"{icon} {seg['state']:7s}  ({duration/1000:.1f}s)  {bar}")
    print()

    # Output JSON
    song_id = Path(filepath).stem
    output = {
        "version": 1,
        "song_id": song_id,
        "segments": segments,
    }

    out_path = Path(filepath).with_suffix(".json")
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written: {out_path}")

    # Summary
    total_by_state = {}
    for seg in segments:
        d = seg["end"] - seg["start"]
        total_by_state[seg["state"]] = total_by_state.get(seg["state"], 0) + d
    print(f"\n=== Summary ===")
    total = sum(total_by_state.values())
    for state, ms in sorted(total_by_state.items()):
        print(f"  {state:7s}: {ms/1000:6.1f}s  ({ms*100/total:.0f}%)")
    print(f"  {'TOTAL':7s}: {total/1000:6.1f}s")


if __name__ == "__main__":
    main()
