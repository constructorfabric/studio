"""Tests for chunk-input command."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.commands import chunk_input as chunk_input_module
from studio.commands.chunk_input import cmd_chunk_input
from studio.utils.ui import set_json_mode


class TestChunkInputCommand(unittest.TestCase):
    def setUp(self):
        set_json_mode(True)

    def tearDown(self):
        set_json_mode(False)

    @staticmethod
    def _make_text(line_count: int) -> str:
        return "".join(f"line {idx}\n" for idx in range(1, line_count + 1))

    def test_chunks_large_file_into_300_line_parts(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.txt"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(650), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["total_lines"], 650)
            self.assertTrue(payload["plan_required"])
            self.assertEqual(payload["chunk_count"], 3)
            self.assertEqual([chunk["line_count"] for chunk in payload["chunks"]], [300, 300, 50])
            for chunk in payload["chunks"]:
                self.assertTrue(Path(chunk["path"]).is_file())
                self.assertEqual(Path(chunk["path"]).suffix, ".md")

    def test_combines_stdin_prompt_with_file_inputs(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(20), encoding="utf-8")

            buf = io.StringIO()
            with patch("sys.stdin", io.StringIO(self._make_text(15))), redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir",
                    str(out_dir),
                    "--include-stdin",
                    "--stdin-label",
                    "prompt-request",
                    "--max-lines",
                    "25",
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["total_sources"], 2)
            self.assertEqual(payload["direct_prompt_file"], (out_dir / "direct-prompt.md").resolve().as_posix())
            self.assertEqual(payload["sources"][0]["kind"], "stdin")
            self.assertEqual(payload["sources"][1]["kind"], "file")
            self.assertEqual(payload["chunk_count"], 2)

    def test_rerun_removes_stale_chunk_files(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(650), encoding="utf-8")

            first_buf = io.StringIO()
            with redirect_stdout(first_buf):
                first_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(first_rc, 0)
            self.assertEqual(len(list(out_dir.glob("*.md"))), 3)
            (out_dir / "999-99-stale-part-99.txt").write_text("stale\n", encoding="utf-8")
            (out_dir / "manifest.json").write_text("{}", encoding="utf-8")

            src.write_text(self._make_text(50), encoding="utf-8")
            second_buf = io.StringIO()
            with redirect_stdout(second_buf):
                second_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(second_rc, 0)
            payload = json.loads(second_buf.getvalue())
            self.assertEqual(payload["chunk_count"], 1)
            self.assertEqual(
                sorted(path.name for path in out_dir.iterdir() if path.is_file()),
                [payload["chunks"][0]["file"], "manifest.json"],
            )
            self.assertFalse((out_dir / "999-99-stale-part-99.txt").exists())
            self.assertTrue((out_dir / "manifest.json").exists())

    def test_changed_input_rewrites_manifest_and_chunks(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(650), encoding="utf-8")

            first_buf = io.StringIO()
            with redirect_stdout(first_buf):
                first_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(first_rc, 0)
            first_payload = json.loads(first_buf.getvalue())
            first_manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

            src.write_text(self._make_text(50), encoding="utf-8")
            second_buf = io.StringIO()
            with redirect_stdout(second_buf):
                second_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(second_rc, 0)
            second_payload = json.loads(second_buf.getvalue())
            second_manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertNotEqual(first_payload["input_signature"], second_payload["input_signature"])
            self.assertEqual(first_manifest["input_signature"], first_payload["input_signature"])
            self.assertEqual(second_manifest["input_signature"], second_payload["input_signature"])
            self.assertEqual(second_payload["package_manifest"], (out_dir / "manifest.json").resolve().as_posix())
            self.assertEqual(len(second_manifest["chunks"]), 1)
            self.assertEqual(second_payload["chunk_count"], 1)
            self.assertEqual(
                sorted(path.name for path in out_dir.iterdir() if path.is_file()),
                ["001-01-request-part-01.md", "manifest.json"],
            )

    def test_reads_stdin_when_no_paths(self):
        with TemporaryDirectory() as td:
            out_dir = Path(td) / "input"
            buf = io.StringIO()
            with patch("sys.stdin", io.StringIO(self._make_text(501))), redirect_stdout(buf):
                rc = cmd_chunk_input([
                    "--output-dir",
                    str(out_dir),
                    "--stdin-label",
                    "prompt-request",
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["total_sources"], 1)
            self.assertEqual(payload["sources"][0]["kind"], "stdin")
            self.assertEqual(payload["direct_prompt_file"], (out_dir / "direct-prompt.md").resolve().as_posix())
            self.assertEqual(payload["sources"][0]["stored_path"], (out_dir / "direct-prompt.md").resolve().as_posix())
            self.assertTrue((out_dir / "direct-prompt.md").is_file())
            self.assertEqual(payload["chunk_count"], 2)
            self.assertEqual(payload["sources"][0]["chunk_count"], 2)

    def test_file_inputs_do_not_read_stdin_without_include_stdin(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(20), encoding="utf-8")

            guarded_stdin = unittest.mock.Mock()
            guarded_stdin.read.side_effect = AssertionError("stdin.read should not be called")

            buf = io.StringIO()
            with patch("sys.stdin", guarded_stdin), redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir",
                    str(out_dir),
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["total_sources"], 1)
            self.assertIsNone(payload["direct_prompt_file"])
            guarded_stdin.read.assert_not_called()

    def test_missing_file_returns_error(self):
        with TemporaryDirectory() as td:
            out_dir = Path(td) / "input"
            missing = Path(td) / "missing.md"

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(missing),
                    "--output-dir",
                    str(out_dir),
                ])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Input file not found", payload["message"])

    def test_empty_stdin_returns_error(self):
        with TemporaryDirectory() as td:
            out_dir = Path(td) / "input"
            buf = io.StringIO()
            with patch("sys.stdin", io.StringIO("   \n")), redirect_stdout(buf):
                rc = cmd_chunk_input([
                    "--output-dir",
                    str(out_dir),
                ])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("No stdin input provided", payload["message"])

    def test_blank_file_emits_single_empty_chunk(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "blank.md"
            out_dir = Path(td) / "input"
            src.write_text("", encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir",
                    str(out_dir),
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["total_lines"], 0)
            self.assertEqual(payload["chunk_count"], 1)
            self.assertEqual(payload["chunks"][0]["start_line"], 1)
            self.assertEqual(payload["chunks"][0]["end_line"], 0)
            self.assertEqual(payload["chunks"][0]["line_count"], 0)
            self.assertEqual(Path(payload["chunks"][0]["path"]).read_text(encoding="utf-8"), "")

    def test_invalid_threshold_lines_returns_error(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(10), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir",
                    str(out_dir),
                    "--threshold-lines",
                    "0",
                ])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("--threshold-lines", payload["message"])

    def test_write_failure_returns_error(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(5), encoding="utf-8")

            buf = io.StringIO()
            with patch("studio.commands.chunk_input.Path.write_text", side_effect=OSError("boom")), redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir",
                    str(out_dir),
                ])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Failed to write chunks", payload["message"])

    def test_failed_swap_preserves_existing_package(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(12), encoding="utf-8")

            first_buf = io.StringIO()
            with redirect_stdout(first_buf):
                first_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir), "--max-lines", "6"])

            self.assertEqual(first_rc, 0)
            first_payload = json.loads(first_buf.getvalue())
            first_manifest_text = (out_dir / "manifest.json").read_text(encoding="utf-8")
            first_chunk_text = (out_dir / "001-01-request-part-01.md").read_text(encoding="utf-8")

            src.write_text(self._make_text(3), encoding="utf-8")
            second_buf = io.StringIO()
            with patch.object(chunk_input_module, "_write_package_manifest", side_effect=OSError("swap failed")), redirect_stdout(second_buf):
                second_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir), "--max-lines", "6"])

            self.assertEqual(second_rc, 1)
            second_payload = json.loads(second_buf.getvalue())
            self.assertEqual(second_payload["status"], "ERROR")
            self.assertIn("Failed to write chunks", second_payload["message"])
            self.assertEqual((out_dir / "manifest.json").read_text(encoding="utf-8"), first_manifest_text)
            self.assertEqual((out_dir / "001-01-request-part-01.md").read_text(encoding="utf-8"), first_chunk_text)
            self.assertEqual(
                json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))["input_signature"],
                first_payload["input_signature"],
            )

    def test_human_output_reports_direct_prompt_and_created_chunks(self):
        with TemporaryDirectory() as td:
            out_dir = Path(td) / "input"
            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            set_json_mode(False)
            with (
                patch("sys.stdin", io.StringIO("direct prompt without newline")),
                redirect_stdout(stdout_buf),
                redirect_stderr(stderr_buf),
            ):
                rc = cmd_chunk_input([
                    "--output-dir",
                    str(out_dir),
                    "--stdin-label",
                    "Prompt Request",
                ])

            self.assertEqual(rc, 0)
            self.assertEqual(stdout_buf.getvalue(), "")
            output = stderr_buf.getvalue()
            self.assertIn("Chunk Input", output)
            self.assertIn("direct_prompt_file", output)
            self.assertIn("created", output)
            self.assertEqual((out_dir / "direct-prompt.md").read_text(encoding="utf-8"), "direct prompt without newline\n")
            chunk_files = sorted(out_dir.glob("*.md"))
            self.assertTrue(any(path.name != "direct-prompt.md" for path in chunk_files))

    def test_output_dir_exists_as_file_returns_error_without_mutation(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_path = Path(td) / "input"
            src.write_text(self._make_text(10), encoding="utf-8")
            out_path.write_text("I am a regular file\n", encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir",
                    str(out_path),
                ])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("not a directory", payload["message"])
            self.assertTrue(out_path.is_file(), "original file must not be mutated")
            self.assertEqual(out_path.read_text(encoding="utf-8"), "I am a regular file\n")
            backup_candidates = list(Path(td).glob(f".{out_path.name}.backup-*"))
            self.assertEqual(backup_candidates, [], "no backup files should be created")

    def test_duplicate_label_collision_distinct_filenames(self):
        with TemporaryDirectory() as td:
            dir_a = Path(td) / "docs"
            dir_b = Path(td) / "notes"
            dir_a.mkdir()
            dir_b.mkdir()
            (dir_a / "request.md").write_text(self._make_text(5), encoding="utf-8")
            (dir_b / "request.md").write_text(self._make_text(5), encoding="utf-8")
            out_dir = Path(td) / "input"

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(dir_a / "request.md"),
                    str(dir_b / "request.md"),
                    "--output-dir",
                    str(out_dir),
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["chunk_count"], 2)
            filenames = [chunk["file"] for chunk in payload["chunks"]]
            self.assertEqual(len(filenames), len(set(filenames)), "chunk filenames must be distinct")
            self.assertIn("-01-", filenames[0])
            self.assertIn("-02-", filenames[1])

    def test_non_utf8_file_returns_error(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "binary.md"
            out_dir = Path(td) / "input"
            src.write_bytes(b"\x80\x81\x82\xff")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir",
                    str(out_dir),
                ])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ERROR")

    def test_include_stdin_without_file_paths_falls_back_to_stdin_only(self):
        with TemporaryDirectory() as td:
            out_dir = Path(td) / "input"
            buf = io.StringIO()
            with patch("sys.stdin", io.StringIO(self._make_text(10))), redirect_stdout(buf):
                rc = cmd_chunk_input([
                    "--output-dir",
                    str(out_dir),
                    "--include-stdin",
                    "--stdin-label",
                    "my-prompt",
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["total_sources"], 1)
            self.assertEqual(payload["sources"][0]["kind"], "stdin")
            self.assertTrue((out_dir / "direct-prompt.md").is_file())

    def test_chunks_large_file_source_chunk_count(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.txt"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(650), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["sources"][0]["chunk_count"], 3)

    def test_invalid_max_lines_returns_error(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(10), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir",
                    str(out_dir),
                    "--max-lines",
                    "0",
                ])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("--max-lines", payload["message"])

    def test_restore_failure_preserves_backup(self):
        """When swap fails and restore also fails, backup must not be deleted."""
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(12), encoding="utf-8")

            first_buf = io.StringIO()
            with redirect_stdout(first_buf):
                first_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir), "--max-lines", "6"])

            self.assertEqual(first_rc, 0)
            first_manifest_text = (out_dir / "manifest.json").read_text(encoding="utf-8")

            # Inject a user file to verify it survives
            (out_dir / "user-notes.txt").write_text("important\n", encoding="utf-8")

            src.write_text(self._make_text(3), encoding="utf-8")

            # Cause _write_package_manifest to fail (before swap), but also
            # sabotage the restore by making output_dir.replace fail after
            # backup_dir has been created.  We achieve this by making
            # staging_dir.replace(output_dir) raise *after* output_dir has
            # been moved to backup_dir.
            original_replace = Path.replace

            call_count = {"n": 0}

            def sabotaged_replace(self_path, target):
                call_count["n"] += 1
                # The first replace moves output_dir → backup_dir (succeeds).
                # The second replace moves staging → output_dir — we fail it.
                if call_count["n"] == 2:
                    raise OSError("disk full")
                # The third replace would be restore (backup → output_dir)
                # — we also fail it to simulate total restore failure.
                if call_count["n"] == 3:
                    raise OSError("still broken")
                return original_replace(self_path, target)

            second_buf = io.StringIO()
            with patch.object(Path, "replace", sabotaged_replace), redirect_stdout(second_buf):
                second_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir), "--max-lines", "6"])

            self.assertEqual(second_rc, 1)
            # output_dir was moved away and restore failed, so it should not exist
            self.assertFalse(out_dir.exists(), "output_dir should not exist after failed restore")

            # The backup directory must still exist with original data
            backup_candidates = list(Path(td).glob(".input.backup-*"))
            self.assertEqual(len(backup_candidates), 1, "backup dir must be preserved")
            backup_dir = backup_candidates[0]
            self.assertEqual(
                (backup_dir / "manifest.json").read_text(encoding="utf-8"),
                first_manifest_text,
            )
            self.assertEqual(
                (backup_dir / "user-notes.txt").read_text(encoding="utf-8"),
                "important\n",
            )

    def test_rerun_preserves_non_generated_files_in_output_dir(self):
        """Non-generated files and subdirs in output_dir survive a rerun."""
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(10), encoding="utf-8")

            first_buf = io.StringIO()
            with redirect_stdout(first_buf):
                first_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(first_rc, 0)

            # Place non-generated user data in the output directory
            (out_dir / "user-notes.txt").write_text("keep me\n", encoding="utf-8")
            subdir = out_dir / "extras"
            subdir.mkdir()
            (subdir / "data.csv").write_text("a,b,c\n", encoding="utf-8")

            # Rerun with different input
            src.write_text(self._make_text(5), encoding="utf-8")
            second_buf = io.StringIO()
            with redirect_stdout(second_buf):
                second_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(second_rc, 0)
            payload = json.loads(second_buf.getvalue())
            self.assertEqual(payload["chunk_count"], 1)

            # Non-generated files must still be present
            self.assertTrue((out_dir / "user-notes.txt").is_file())
            self.assertEqual((out_dir / "user-notes.txt").read_text(encoding="utf-8"), "keep me\n")
            self.assertTrue((out_dir / "extras" / "data.csv").is_file())
            self.assertEqual((out_dir / "extras" / "data.csv").read_text(encoding="utf-8"), "a,b,c\n")

            # Generated files must reflect the new run
            self.assertTrue((out_dir / "manifest.json").is_file())
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["chunks"]), 1)

            # No leftover backup directories
            backup_candidates = list(Path(td).glob(".input.backup-*"))
            self.assertEqual(backup_candidates, [], "backup should be cleaned up after success")


    def test_preservation_failure_does_not_fail_command(self):
        """If _preserve_non_generated raises, command still succeeds but keeps backup."""
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(10), encoding="utf-8")

            # First run to create output_dir with a user file
            first_buf = io.StringIO()
            with redirect_stdout(first_buf):
                first_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])
            self.assertEqual(first_rc, 0)
            (out_dir / "user-notes.txt").write_text("keep me\n", encoding="utf-8")

            # Second run with patched copy2 that fails during preservation
            src.write_text(self._make_text(5), encoding="utf-8")
            second_buf = io.StringIO()
            with patch("studio.commands.chunk_input.shutil.copy2", side_effect=OSError("copy failed")), redirect_stdout(second_buf):
                second_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(second_rc, 0)
            payload = json.loads(second_buf.getvalue())
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["chunk_count"], 1)

            # New chunks written successfully
            self.assertTrue((out_dir / "manifest.json").is_file())

            # Backup kept so user files are not silently lost
            backup_candidates = list(Path(td).glob(".input.backup-*"))
            self.assertEqual(len(backup_candidates), 1, "backup should be kept when preservation fails")
            self.assertTrue((backup_candidates[0] / "user-notes.txt").is_file(), "user file should survive in backup")


    def test_dry_run_returns_signature_without_writing_files(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(650), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir), "--dry-run"])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "OK")
            self.assertTrue(payload["dry_run"])
            self.assertIn("input_signature", payload)
            self.assertEqual(payload["total_lines"], 650)
            self.assertTrue(payload["plan_required"])
            self.assertEqual(payload["total_sources"], 1)
            # No files written
            self.assertFalse(out_dir.exists())

    def test_dry_run_signature_matches_write_signature(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(650), encoding="utf-8")

            dry_buf = io.StringIO()
            with redirect_stdout(dry_buf):
                dry_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir), "--dry-run"])

            self.assertEqual(dry_rc, 0)
            dry_payload = json.loads(dry_buf.getvalue())

            write_buf = io.StringIO()
            with redirect_stdout(write_buf):
                write_rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir)])

            self.assertEqual(write_rc, 0)
            write_payload = json.loads(write_buf.getvalue())

            self.assertEqual(dry_payload["input_signature"], write_payload["input_signature"])

    def test_stdin_label_does_not_affect_signature(self):
        """Different --stdin-label values must produce the same input_signature for identical content."""
        with TemporaryDirectory() as td:
            out_dir_a = Path(td) / "input-a"
            out_dir_b = Path(td) / "input-b"
            content = self._make_text(20)

            buf_a = io.StringIO()
            with patch("sys.stdin", io.StringIO(content)), redirect_stdout(buf_a):
                rc_a = cmd_chunk_input([
                    "--output-dir", str(out_dir_a),
                    "--stdin-label", "label-alpha",
                    "--dry-run",
                ])

            buf_b = io.StringIO()
            with patch("sys.stdin", io.StringIO(content)), redirect_stdout(buf_b):
                rc_b = cmd_chunk_input([
                    "--output-dir", str(out_dir_b),
                    "--stdin-label", "label-beta",
                    "--dry-run",
                ])

            self.assertEqual(rc_a, 0)
            self.assertEqual(rc_b, 0)
            payload_a = json.loads(buf_a.getvalue())
            payload_b = json.loads(buf_b.getvalue())
            self.assertEqual(payload_a["input_signature"], payload_b["input_signature"])

    def test_stdin_label_does_not_affect_write_signature(self):
        """Full write mode: different labels, same content → same signature."""
        with TemporaryDirectory() as td:
            out_dir_a = Path(td) / "input-a"
            out_dir_b = Path(td) / "input-b"
            content = self._make_text(20)

            buf_a = io.StringIO()
            with patch("sys.stdin", io.StringIO(content)), redirect_stdout(buf_a):
                rc_a = cmd_chunk_input([
                    "--output-dir", str(out_dir_a),
                    "--stdin-label", "label-alpha",
                ])

            buf_b = io.StringIO()
            with patch("sys.stdin", io.StringIO(content)), redirect_stdout(buf_b):
                rc_b = cmd_chunk_input([
                    "--output-dir", str(out_dir_b),
                    "--stdin-label", "label-beta",
                ])

            self.assertEqual(rc_a, 0)
            self.assertEqual(rc_b, 0)
            payload_a = json.loads(buf_a.getvalue())
            payload_b = json.loads(buf_b.getvalue())
            self.assertEqual(payload_a["input_signature"], payload_b["input_signature"])

    def test_dry_run_with_output_dir_as_file_fails(self):
        """--dry-run should still reject output-dir that is an existing non-directory."""
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_path = Path(td) / "input"
            src.write_text(self._make_text(10), encoding="utf-8")
            out_path.write_text("I am a regular file\n", encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cmd_chunk_input([
                    str(src),
                    "--output-dir", str(out_path),
                    "--dry-run",
                ])

            self.assertEqual(rc, 1)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("not a directory", payload["message"])
            # Original file untouched
            self.assertEqual(out_path.read_text(encoding="utf-8"), "I am a regular file\n")

    def test_dry_run_human_output(self):
        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(self._make_text(650), encoding="utf-8")

            set_json_mode(False)
            stderr_buf = io.StringIO()
            stdout_buf = io.StringIO()
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                rc = cmd_chunk_input([str(src), "--output-dir", str(out_dir), "--dry-run"])

            self.assertEqual(rc, 0)
            self.assertEqual(stdout_buf.getvalue(), "")
            output = stderr_buf.getvalue()
            self.assertIn("dry run", output)
            self.assertIn("input_signature", output)
            self.assertFalse(out_dir.exists())


class TestChunkInputCLI(unittest.TestCase):
    def tearDown(self):
        set_json_mode(False)

    def test_cli_help_lists_chunk_input(self):
        from studio.cli import main

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--json", "--help"])

        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertIn("chunk-input", payload.get("commands", {}))

    def test_cli_missing_required_output_dir_returns_json_error(self):
        from studio.cli import main

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            rc = main(["--json", "chunk-input"])

        self.assertEqual(rc, 1)
        payload = json.loads(stdout_buf.getvalue())
        self.assertEqual(payload["status"], "ERROR")
        self.assertIn("--output-dir", payload["message"])
        self.assertEqual(stderr_buf.getvalue(), "")

    def test_cli_dispatch_chunk_input(self):
        from studio.cli import main

        with TemporaryDirectory() as td:
            src = Path(td) / "request.md"
            out_dir = Path(td) / "input"
            src.write_text(TestChunkInputCommand._make_text(601), encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main([
                    "--json",
                    "chunk-input",
                    str(src),
                    "--output-dir",
                    str(out_dir),
                ])

            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "OK")
            self.assertEqual(payload["chunk_count"], 3)
