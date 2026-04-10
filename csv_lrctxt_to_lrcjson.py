#!/usr/bin/env python3
"""
CSV-driven batch: lrctxt URL or local path → lrcjson (sharded by SHA256(song_id)).

Input list file (often .txt): **no header**, one URL or path per line — same as a
single-column CSV; pass it with --csv. Optional second column = song_id when using
comma/tab-separated rows.

With a header row whose first cell is `url`, remaining rows use that column layout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from preprocess_lyrics import build_lrcjson, parse_lyrics_text

DEFAULT_MAX_BYTES = 2 * 1024 * 1024


def default_worker_count() -> int:
    """Concurrent downloads: bounded default for Linux/Windows servers and laptops."""
    n = os.cpu_count() or 2
    return min(32, max(4, n * 2))


def file_url_to_path(url: str) -> Path:
    """
    file:// → local Path. Uses url2pathname on Windows for drive letters (/C:/...).
    On POSIX, path is unquoted urlparse path (leading / kept).
    """
    p = urlparse(url)
    if p.scheme.lower() != "file":
        raise ValueError("not a file URL")
    if os.name == "nt":
        try:
            return Path(url2pathname(p.path))
        except (ValueError, OSError):
            raw = unquote(p.path)
            if len(raw) >= 3 and raw[0] == "/" and raw[2] == ":":
                return Path(raw[1:])
            return Path(unquote(p.path))
    return Path(unquote(p.path))


def _stderr(*args: object) -> None:
    print(*args, file=sys.stderr, flush=True)


def read_local_text_with_limit(
    path: Path,
    *,
    encoding: str,
    max_bytes: int,
) -> tuple[str | None, str]:
    """Read local file with a hard byte cap before decoding."""
    try:
        if path.stat().st_size > max_bytes:
            return None, f"TOO_LARGE>{max_bytes}"
    except FileNotFoundError:
        return None, "FILE_NOT_FOUND"
    except OSError as e:
        return None, f"FILE_IO:{e}"

    try:
        with path.open("rb") as f:
            data = f.read(max_bytes + 1)
    except FileNotFoundError:
        return None, "FILE_NOT_FOUND"
    except OSError as e:
        return None, f"FILE_IO:{e}"

    if len(data) > max_bytes:
        return None, f"TOO_LARGE>{max_bytes}"

    try:
        return data.decode(encoding), ""
    except UnicodeDecodeError as e:
        return None, f"DECODE:{e}"


def is_retryable_fetch_error(source: str, err: str) -> bool:
    """Retry only transient HTTP-ish failures; local read failures are not retried."""
    if not source.strip().lower().startswith(("http://", "https://")):
        return False
    if err == "TIMEOUT":
        return True
    if err.startswith("URL_ERROR:") or err.startswith("IO:"):
        return True
    if err.startswith("HTTP_"):
        code = err.removeprefix("HTTP_")
        return code == "429" or code.startswith("5")
    return False


def is_remote_source(source: str) -> bool:
    """True only for HTTP(S) sources."""
    return source.strip().lower().startswith(("http://", "https://"))


def fetch_text_with_retry(
    source: str,
    *,
    encoding: str,
    timeout: float,
    max_bytes: int,
    retries: int,
    retry_backoff: float,
) -> tuple[str | None, str]:
    """Fetch text with bounded retries for transient HTTP failures."""
    attempts = max(0, retries) + 1
    last_text: str | None = None
    last_err = ""
    for attempt in range(attempts):
        last_text, last_err = fetch_text(
            source,
            encoding=encoding,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        if not last_err:
            return last_text, ""
        if attempt == attempts - 1 or not is_retryable_fetch_error(source, last_err):
            break
        time.sleep(retry_backoff * (2 ** attempt))
    return last_text, last_err


def song_id_shard_hex(song_id: str) -> tuple[str, str]:
    """First two bytes of SHA256(utf-8 song_id) as aa, bb hex pairs."""
    h = hashlib.sha256(song_id.encode("utf-8")).hexdigest()
    return h[0:2], h[2:4]


def safe_song_id_filename(song_id: str) -> str:
    """Keep UTF-8 names; strip path separators and NUL."""
    s = song_id.replace("\x00", "").replace("/", "_").replace("\\", "_")
    for c in ':*?"<>|':
        s = s.replace(c, "_")
    s = s.strip() or "unknown"
    return s


def default_song_id_from_source(source: str) -> str | None:
    """URL/path basename without extension; returns None when missing."""
    source = source.strip()
    if source.lower().startswith(("http://", "https://")):
        p = urlparse(source)
        stem = Path(Path(p.path).name).stem
        value = unquote(stem).strip()
        return value or None
    if source.lower().startswith("file://"):
        try:
            value = file_url_to_path(source).stem.strip()
            return value or None
        except (ValueError, OSError):
            return None
    value = Path(source).stem.strip()
    return value or None


def fetch_text(
    source: str,
    *,
    encoding: str,
    timeout: float,
    max_bytes: int,
) -> tuple[str | None, str]:
    """
    Load lrctxt as string. Returns (text, error_message).
    error_message empty on success.
    """
    s = source.strip()
    if not s:
        return None, "EMPTY_SOURCE"

    if s.lower().startswith(("http://", "https://")):
        req = urllib.request.Request(
            s,
            headers={"User-Agent": "csv_lrctxt_to_lrcjson/1.0"},
            method="GET",
        )
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                data = resp.read(max_bytes + 1)
        except urllib.error.HTTPError as e:
            return None, f"HTTP_{e.code}"
        except urllib.error.URLError as e:
            return None, f"URL_ERROR:{e.reason!r}"
        except TimeoutError:
            return None, "TIMEOUT"
        except OSError as e:
            return None, f"IO:{e}"

        if len(data) > max_bytes:
            return None, f"TOO_LARGE>{max_bytes}"
        try:
            return data.decode(encoding), ""
        except UnicodeDecodeError as e:
            return None, f"DECODE:{e}"

    if s.lower().startswith("file://"):
        try:
            local = file_url_to_path(s)
        except (ValueError, OSError) as e:
            return None, f"FILE_URL:{e}"
    else:
        local = Path(os.path.expanduser(s))

    return read_local_text_with_limit(local, encoding=encoding, max_bytes=max_bytes)


def _sniff_csv_dialect(sample: str):
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


def iter_csv_stream(path: Path, encoding: str) -> Iterator[tuple[int, dict[str, str]]]:
    """
    Stream CSV rows (low memory for large files).
    Yields (1-based row index in file, record dict with url/song_id).
    """
    with path.open(newline="", encoding=encoding) as f:
        head = []
        for _ in range(3):
            line = f.readline()
            if not line:
                break
            head.append(line)
        sample = "".join(head)
        f.seek(0)
        dialect = _sniff_csv_dialect(sample)
        reader = csv.reader(f, dialect)
        rows_iter = iter(reader)
        first_row = next(rows_iter, None)
        if first_row is None:
            return

        first = [c.strip() for c in first_row]
        if first and first[0].lower() == "url":
            header = [c.strip().lower() or f"col{i}" for i, c in enumerate(first_row)]
            row_num = 1
            for row in rows_iter:
                row_num += 1
                rec = {
                    header[i]: (row[i].strip() if i < len(row) else "")
                    for i in range(len(header))
                }
                yield row_num, rec
            return

        row_num = 0
        row = first_row
        while row is not None:
            row_num += 1
            if row and str(row[0]).strip():
                yield row_num, {
                    "url": row[0].strip(),
                    "song_id": row[1].strip() if len(row) > 1 else "",
                }
            else:
                yield row_num, {"url": "", "song_id": ""}
            row = next(rows_iter, None)


def output_path_for_song(
    out_dir: Path,
    song_id: str,
    filename_stem: str,
) -> Path:
    aa, bb = song_id_shard_hex(song_id)
    return out_dir / aa / bb / f"{filename_stem}.json"


def process_row(
    row_index: int,
    source: str,
    song_id: str | None,
    *,
    encoding: str,
    timeout: float,
    max_bytes: int,
    out_dir: Path,
    dry_run: bool,
    used_paths: dict[str, str],
    path_lock: threading.Lock,
    skip_existing: bool = False,
    retries: int = 0,
    retry_backoff: float = 0.5,
    require_remote: bool = False,
) -> dict[str, Any]:
    """Process one CSV row; returns result dict for logging / errors."""
    explicit_sid = (song_id or "").strip()
    sid = explicit_sid or default_song_id_from_source(source)
    if not sid:
        return {
            "row": row_index,
            "song_id": "",
            "source": source,
            "status": "METADATA_ERROR",
            "detail": "MISSING_SONG_ID",
        }

    if require_remote and not is_remote_source(source):
        return {
            "row": row_index,
            "song_id": sid,
            "source": source,
            "status": "SOURCE_ERROR",
            "detail": "NON_REMOTE_SOURCE",
        }

    base_name = safe_song_id_filename(sid)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:8]
    with path_lock:
        out_path = output_path_for_song(out_dir, sid, base_name)
        key = str(out_path)
        if key in used_paths and used_paths[key] != source:
            out_path = output_path_for_song(out_dir, sid, f"{base_name}__{digest}")
            key = str(out_path)
        used_paths[key] = source

    if skip_existing and out_path.exists():
        return {
            "row": row_index,
            "song_id": sid,
            "source": source,
            "status": "SKIPPED",
            "detail": "OUTPUT_EXISTS",
            "out_path": str(out_path),
        }

    text, err = fetch_text_with_retry(
        source,
        encoding=encoding,
        timeout=timeout,
        max_bytes=max_bytes,
        retries=retries,
        retry_backoff=retry_backoff,
    )
    if err:
        low = source.strip().lower()
        is_http = low.startswith(("http://", "https://"))
        return {
            "row": row_index,
            "song_id": sid,
            "source": source,
            "status": "DOWNLOAD_FAIL" if is_http else "READ_FAIL",
            "detail": err,
        }

    if not text or not text.strip():
        return {
            "row": row_index,
            "song_id": sid,
            "source": source,
            "status": "EMPTY",
            "detail": "",
        }

    try:
        lyrics = parse_lyrics_text(text)
    except Exception as e:
        return {
            "row": row_index,
            "song_id": sid,
            "source": source,
            "status": "PARSE_ERROR",
            "detail": str(e),
        }

    if not lyrics:
        return {
            "row": row_index,
            "song_id": sid,
            "source": source,
            "status": "EMPTY",
            "detail": "NO_LYRIC_LINES",
        }

    try:
        payload = build_lrcjson(sid, lyrics)

        if not dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            rel_str = out_path.resolve().relative_to(out_dir.resolve()).as_posix()
        except ValueError:
            rel_str = out_path.as_posix()

        content_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    except Exception as e:
        return {
            "row": row_index,
            "song_id": sid,
            "source": source,
            "status": "PROCESS_ERROR",
            "detail": str(e),
        }

    return {
        "row": row_index,
        "song_id": sid,
        "source": source,
        "status": "OK",
        "detail": "",
        "relative_path": rel_str,
        "sha256_json": content_hash,
        "out_path": str(out_path),
    }


def _drain_completed(pending: dict[Any, bool]) -> list[dict[str, Any]]:
    done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
    results: list[dict[str, Any]] = []
    for fut in done:
        results.append(fut.result())
        del pending[fut]
    return results


def _missing_url_result(row_index: int) -> dict[str, Any]:
    return {
        "row": row_index,
        "song_id": "",
        "source": "",
        "status": "EMPTY",
        "detail": "MISSING_URL",
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="URL/path list → sharded lrcjson (no-header .txt one-per-line OK; use --csv path)"
    )
    ap.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Input list path (.txt or .csv): no header = one URL/path per line; or header row with 'url'",
    )
    ap.add_argument("--out-dir", required=True, type=Path, help="Output root (aa/bb shards)")
    ap.add_argument("--encoding", default="utf-8", help="Lyrics text encoding (HTTP body + local files)")
    ap.add_argument(
        "--csv-encoding",
        default=None,
        help="CSV file encoding (default: same as --encoding; use utf-8-sig for Excel UTF-8 BOM)",
    )
    ap.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Max lrctxt size")
    ap.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Concurrent row workers (default: {default_worker_count()}). Use 1 to disable parallelism.",
    )
    ap.add_argument(
        "--max-inflight",
        type=int,
        default=None,
        help="Max concurrent tasks while streaming CSV (default: 8 × workers). Caps memory for huge CSVs.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print paths only; do not write files")
    ap.add_argument("--manifest", action="store_true", help="Write manifest.jsonl under out-dir")
    ap.add_argument("--skip-existing", action="store_true", help="Skip rows whose target JSON already exists")
    ap.add_argument("--require-remote", action="store_true", help="Reject non-http(s) sources as SOURCE_ERROR")
    ap.add_argument("--retries", type=int, default=0, help="Retry transient HTTP fetch failures N times")
    ap.add_argument("--retry-backoff", type=float, default=0.5, help="Base retry backoff seconds (exponential)")
    ap.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Directory for errors.jsonl (default: --out-dir)",
    )
    ap.add_argument(
        "--progress-every",
        type=int,
        default=1,
        metavar="N",
        help="Stdout progress every N rows (1=every row). Failures still emit JSON on stderr.",
    )
    ap.add_argument("--quiet", action="store_true", help="No per-row stdout; only final summary")
    args = ap.parse_args()

    workers = args.workers if args.workers is not None else default_worker_count()
    max_inflight = args.max_inflight if args.max_inflight is not None else max(workers * 8, workers)

    log_dir = args.log_dir or args.out_dir
    csv_enc = args.csv_encoding or args.encoding
    out_abs = args.out_dir.resolve()

    if not args.dry_run:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

    try:
        csv_path = args.csv.resolve()
        stream = iter_csv_stream(csv_path, csv_enc)
    except OSError as e:
        _stderr(f"Failed to read CSV: {e}")
        return 2

    errors_path = log_dir / "errors.jsonl"
    manifest_path = args.out_dir / "manifest.jsonl"

    manifest_mode = "a" if (args.skip_existing and manifest_path.exists()) else "w"
    manifest_f = open(manifest_path, manifest_mode, encoding="utf-8") if (args.manifest and not args.dry_run) else None
    error_f = None

    used_paths: dict[str, str] = {}
    path_lock = threading.Lock()

    def one(i: int, rec: dict[str, str]) -> dict[str, Any]:
        src = rec.get("url", "").strip()
        sid = rec.get("song_id", "").strip()
        return process_row(
            i,
            src,
            sid or None,
            encoding=args.encoding,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
            out_dir=out_abs,
            dry_run=args.dry_run,
            used_paths=used_paths,
            path_lock=path_lock,
            skip_existing=args.skip_existing,
            retries=args.retries,
            retry_backoff=args.retry_backoff,
            require_remote=args.require_remote,
        )

    ok = 0
    skipped = 0
    pe = max(1, args.progress_every)
    total = 0
    next_emit = 1
    ready_by_row: dict[int, dict[str, Any]] = {}

    def emit_result(r: dict[str, Any]) -> None:
        nonlocal ok, skipped, total, error_f
        st = r["status"]
        sid = r.get("song_id", "")
        row_n = int(r["row"])
        total += 1
        if not args.quiet:
            if st != "OK" or pe == 1 or (row_n % pe == 0):
                print(f"row={row_n}\t{st}\t{sid}\t{r.get('source', '')[:80]}", flush=True)
        if st == "OK":
            ok += 1
        elif st == "SKIPPED":
            skipped += 1
        else:
            line = json.dumps(r, ensure_ascii=False)
            _stderr(line)
            if not args.dry_run:
                if error_f is None:
                    error_f = open(errors_path, "w", encoding="utf-8")
                error_f.write(line + "\n")
        if st == "OK" and manifest_f and r.get("relative_path"):
            man = {
                "song_id": r["song_id"],
                "source_url": r["source"],
                "relative_path": r["relative_path"],
                "sha256_json": r.get("sha256_json", ""),
            }
            manifest_f.write(json.dumps(man, ensure_ascii=False) + "\n")

    def queue_result(r: dict[str, Any]) -> None:
        nonlocal next_emit
        row_n = int(r["row"])
        ready_by_row[row_n] = r
        while next_emit in ready_by_row:
            emit_result(ready_by_row.pop(next_emit))
            next_emit += 1

    if workers <= 1:
        for idx, rec in stream:
            if not rec.get("url", "").strip():
                queue_result(_missing_url_result(idx))
            else:
                queue_result(one(idx, rec))
    else:
        pending: dict[Any, bool] = {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for idx, rec in stream:
                if not rec.get("url", "").strip():
                    queue_result(_missing_url_result(idx))
                    continue
                fut = ex.submit(one, idx, rec)
                pending[fut] = True
                while len(pending) >= max_inflight:
                    for result in _drain_completed(pending):
                        queue_result(result)
            while pending:
                for result in _drain_completed(pending):
                    queue_result(result)

    if manifest_f:
        manifest_f.close()
    if error_f:
        error_f.close()

    print(f"Done: {ok}/{total} OK, {skipped} skipped", flush=True)
    return 0 if (ok + skipped) == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
