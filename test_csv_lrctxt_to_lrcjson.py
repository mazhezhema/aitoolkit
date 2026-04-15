import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import csv_lrctxt_to_lrcjson as mod


class CsvLrctxtToLrcjsonTests(unittest.TestCase):
    def test_fetch_text_local_oversize_short_circuits_before_read_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "huge.txt"
            path.write_bytes(b"a" * 32)

            with mock.patch.object(Path, "read_text", side_effect=AssertionError("read_text should not be used")):
                text, err = mod.fetch_text(str(path), encoding="utf-8", timeout=1, max_bytes=10)

            self.assertIsNone(text)
            self.assertEqual(err, "TOO_LARGE>10")

    def test_fetch_text_local_falls_back_to_gb18030_when_utf8_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbk.txt"
            content = "[00:00.000]你好\n<1000,0>\n"
            path.write_bytes(content.encode("gb18030"))

            text, err = mod.fetch_text(str(path), encoding="utf-8", timeout=1, max_bytes=1024)

            self.assertEqual(err, "")
            self.assertEqual(text, content)

    def test_fetch_text_detailed_reports_fallback_decode_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbk.txt"
            content = "[00:00.000]你好\n<1000,0>\n"
            path.write_bytes(content.encode("gb18030"))

            text, err, decode_mode = mod.fetch_text_detailed(
                str(path),
                encoding="utf-8",
                timeout=1,
                max_bytes=1024,
                lossy_decode=False,
            )

            self.assertEqual(err, "")
            self.assertEqual(text, content)
            self.assertEqual(decode_mode, "fallback")

    def test_fetch_text_detailed_can_use_lossy_decode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lossy.txt"
            path.write_bytes(b"[00:00.000]\xff\xfe\n<1000,0>\n")

            text, err, decode_mode = mod.fetch_text_detailed(
                str(path),
                encoding="utf-8",
                timeout=1,
                max_bytes=1024,
                lossy_decode=True,
            )

            self.assertEqual(err, "")
            self.assertIn("\ufffd", text)
            self.assertEqual(decode_mode, "lossy")

    def test_process_row_converts_build_failure_to_process_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "song.txt"
            src.write_text("[00:00.000]hello\n<1000,0>\n", encoding="utf-8")

            with mock.patch.object(mod, "build_lrcjson", side_effect=RuntimeError("boom")):
                result = mod.process_row(
                    1,
                    str(src),
                    "songid",
                    encoding="utf-8",
                    timeout=1,
                    max_bytes=1024,
                    out_dir=Path(tmp) / "out",
                    dry_run=True,
                    used_paths={},
                    path_lock=threading.Lock(),
                )

            self.assertEqual(result["status"], "PROCESS_ERROR")
            self.assertIn("boom", result["detail"])

    def test_process_row_skip_existing_short_circuits_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            existing = mod.output_path_for_song(out_dir, "songid", "songid")
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("{}", encoding="utf-8")

            with mock.patch.object(mod, "fetch_text", side_effect=AssertionError("fetch_text should not be called")):
                result = mod.process_row(
                    1,
                    "https://example.com/songid.txt",
                    "songid",
                    encoding="utf-8",
                    timeout=1,
                    max_bytes=1024,
                    out_dir=out_dir,
                    dry_run=False,
                    used_paths={},
                    path_lock=threading.Lock(),
                    skip_existing=True,
                    retries=0,
                    retry_backoff=0.1,
                )

            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(result["detail"], "OUTPUT_EXISTS")

    def test_fetch_text_with_retry_retries_once_then_succeeds(self) -> None:
        with mock.patch.object(
            mod,
            "fetch_text_detailed",
            side_effect=[(None, "TIMEOUT", "failed"), ("hello", "", "exact")],
        ) as fetch_mock, mock.patch.object(mod.time, "sleep") as sleep_mock:
            text, err = mod.fetch_text_with_retry(
                "https://example.com/song.txt",
                encoding="utf-8",
                timeout=1,
                max_bytes=1024,
                retries=1,
                retry_backoff=0.5,
            )

        self.assertEqual((text, err), ("hello", ""))
        self.assertEqual(fetch_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.5)

    def test_process_row_require_remote_rejects_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "song.txt"
            src.write_text("[00:00.000]hello\n<1000,0>\n", encoding="utf-8")

            result = mod.process_row(
                1,
                str(src),
                "songid",
                encoding="utf-8",
                timeout=1,
                max_bytes=1024,
                out_dir=Path(tmp) / "out",
                dry_run=True,
                used_paths={},
                path_lock=threading.Lock(),
                require_remote=True,
            )

        self.assertEqual(result["status"], "SOURCE_ERROR")
        self.assertEqual(result["detail"], "NON_REMOTE_SOURCE")

    def test_process_row_require_remote_allows_https_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(mod, "fetch_text_with_retry_detailed", return_value=("hello", "", "exact")):
                with mock.patch.object(mod, "parse_lyrics_text", return_value=[{"text": "hello", "start": 0, "end": 1000, "duration": 1000, "normalized_text": "hello"}]):
                    with mock.patch.object(mod, "build_lrcjson", return_value={"version": 1, "song_id": "songid", "segments": []}):
                        result = mod.process_row(
                            1,
                            "https://example.com/songid.txt",
                            "songid",
                            encoding="utf-8",
                            timeout=1,
                            max_bytes=1024,
                            out_dir=Path(tmp) / "out",
                            dry_run=True,
                            used_paths={},
                            path_lock=threading.Lock(),
                            require_remote=True,
                        )

        self.assertEqual(result["status"], "OK")


if __name__ == "__main__":
    unittest.main()
