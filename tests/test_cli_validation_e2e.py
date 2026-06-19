"""Public CLI e2e coverage for validation and alias command surfaces."""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

import studio.cli as cli


def _bootstrap_project(root: Path, *, systems: list[dict] | None = None, kits: dict | None = None) -> Path:
    from studio.utils import toml_utils

    (root / ".git").mkdir()
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n<!-- /@cf:root-agents -->\n',
        encoding="utf-8",
    )
    adapter = root / "adapter"
    config_dir = adapter / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")
    (adapter / "kits" / "test").mkdir(parents=True, exist_ok=True)

    registry_kits = kits if kits is not None else {"test": {"format": "CFS", "path": "kits/test"}}
    common = {
        "version": "1.0",
        "project_root": "..",
        "kits": registry_kits,
    }
    toml_utils.dump(common, config_dir / "core.toml")
    artifacts = dict(common)
    artifacts["systems"] = systems or []
    toml_utils.dump(artifacts, config_dir / "artifacts.toml")
    return adapter


def _snapshot_files(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(p for p in root.rglob("*") if p.is_file())
    }


def _run_main(argv: list[str], *, cwd: Path) -> tuple[int, str, str]:
    from studio.utils.ui import is_json_mode, set_json_mode

    stdout = io.StringIO()
    stderr = io.StringIO()
    old_cwd = Path.cwd()
    saved_json_mode = is_json_mode()
    try:
        os.chdir(cwd)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(argv)
        return exit_code, stdout.getvalue(), stderr.getvalue()
    finally:
        set_json_mode(saved_json_mode)
        os.chdir(old_cwd)


class TestCLIValidateTocE2E(unittest.TestCase):
    def test_validate_toc_pass_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc = root / "good.md"
            doc.write_text(
                "# Title\n\n"
                "## Table of Contents\n\n"
                "1. [Section](#section)\n\n"
                "---\n\n"
                "## Section\n",
                encoding="utf-8",
            )
            before = doc.read_text(encoding="utf-8")

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate-toc", "--max-level", "2", str(doc)],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["results"][0]["status"], "PASS")
            self.assertEqual(doc.read_text(encoding="utf-8"), before)
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".gitignore").exists())
            self.assertEqual(stderr, "")

    def test_validate_toc_fail_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc = root / "bad.md"
            doc.write_text("# Title\n\n## Missing TOC\n", encoding="utf-8")
            before = doc.read_text(encoding="utf-8")

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate-toc", str(doc)],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["results"][0]["status"], "FAIL")
            self.assertGreater(payload["error_count"], 0)
            self.assertEqual(doc.read_text(encoding="utf-8"), before)
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".gitignore").exists())
            self.assertEqual(stderr, "")

    def test_validate_toc_missing_file_is_reported_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing = root / "missing.md"
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate-toc", str(missing)],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["error_count"], 1)
            self.assertEqual(payload["results"][0]["status"], "ERROR")
            self.assertEqual(payload["results"][0]["message"], "File not found")
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_validate_toc_warn_only_is_read_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc = root / "stale.md"
            doc.write_text(
                "# Title\n\n"
                "## Table of Contents\n\n"
                "1. [Section B](#section-b)\n"
                "2. [Section A](#section-a)\n\n"
                "---\n\n"
                "## Section A\n\n"
                "## Section B\n",
                encoding="utf-8",
            )
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate-toc", "--max-level", "2", str(doc)],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "WARN")
            self.assertEqual(payload["error_count"], 0)
            self.assertGreaterEqual(payload["warning_count"], 1)
            result = payload["results"][0]
            self.assertEqual(result["status"], "WARN")
            self.assertIn("warnings", result)
            self.assertTrue(any(w["code"] == "toc-stale" for w in result["warnings"]))
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_validate_toc_multi_file_mixed_results_are_reported(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            good = root / "good.md"
            stale = root / "stale.md"
            bad = root / "bad.md"
            good.write_text(
                "# Title\n\n"
                "## Table of Contents\n\n"
                "1. [Section](#section)\n\n"
                "---\n\n"
                "## Section\n",
                encoding="utf-8",
            )
            stale.write_text(
                "# Title\n\n"
                "## Table of Contents\n\n"
                "1. [Section B](#section-b)\n"
                "2. [Section A](#section-a)\n\n"
                "---\n\n"
                "## Section A\n\n"
                "## Section B\n",
                encoding="utf-8",
            )
            bad.write_text("# Title\n\n## Missing TOC\n", encoding="utf-8")
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate-toc", "--max-level", "2", str(good), str(stale), str(bad)],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["files_validated"], 3)
            self.assertEqual(payload["error_count"], 1)
            self.assertGreaterEqual(payload["warning_count"], 1)
            statuses = {Path(item["file"]).name: item["status"] for item in payload["results"]}
            self.assertEqual(statuses, {"good.md": "PASS", "stale.md": "WARN", "bad.md": "FAIL"})
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_validate_toc_verbose_includes_empty_details(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            doc = root / "good.md"
            doc.write_text(
                "# Title\n\n"
                "## Table of Contents\n\n"
                "1. [Section](#section)\n\n"
                "---\n\n"
                "## Section\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = _run_main(
                ["--json", "validate-toc", "--verbose", "--max-level", "2", str(doc)],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            result = payload["results"][0]
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["warnings"], [])
            self.assertEqual(stderr, "")


class TestCLISpecCoverageE2E(unittest.TestCase):
    def test_spec_coverage_filters_systems_without_mutating_sources(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(
                root,
                systems=[
                    {
                        "name": "API",
                        "slug": "api",
                        "kit": "test",
                        "codebase": [{"path": "src/api", "extensions": [".py"]}],
                    },
                    {
                        "name": "Web",
                        "slug": "web",
                        "kit": "test",
                        "codebase": [{"path": "src/web", "extensions": [".py"]}],
                    },
                ],
            )
            api_file = root / "src" / "api" / "app.py"
            web_file = root / "src" / "web" / "app.py"
            api_file.parent.mkdir(parents=True, exist_ok=True)
            web_file.parent.mkdir(parents=True, exist_ok=True)
            api_file.write_text("x = 1\n", encoding="utf-8")
            web_file.write_text("# @cpt-algo:cpt-web-flow:p1\nx = 1\n", encoding="utf-8")
            api_before = api_file.read_text(encoding="utf-8")
            web_before = web_file.read_text(encoding="utf-8")

            exit_code, stdout, stderr = _run_main(
                ["--json", "spec-coverage", "--system", "web"],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["summary"]["total_files"], 1)
            self.assertIn("src/web/app.py", payload["files"])
            self.assertNotIn("src/api/app.py", payload["files"])
            self.assertEqual(api_file.read_text(encoding="utf-8"), api_before)
            self.assertEqual(web_file.read_text(encoding="utf-8"), web_before)
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertIn('cf-studio-path = "adapter"', (root / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertFalse((root / ".gitignore").exists())
            self.assertEqual(stderr, "")

    def test_spec_coverage_unknown_system_fails_without_mutating_sources(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(
                root,
                systems=[
                    {
                        "name": "Web",
                        "slug": "web",
                        "kit": "test",
                        "codebase": [{"path": "src/web", "extensions": [".py"]}],
                    },
                ],
            )
            web_file = root / "src" / "web" / "app.py"
            web_file.parent.mkdir(parents=True, exist_ok=True)
            web_file.write_text("# @cpt-algo:cpt-web-flow:p1\nx = 1\n", encoding="utf-8")
            web_before = web_file.read_text(encoding="utf-8")

            exit_code, stdout, stderr = _run_main(
                ["--json", "spec-coverage", "--system", "missing"],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["unknown_systems"], ["missing"])
            self.assertEqual(web_file.read_text(encoding="utf-8"), web_before)
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".gitignore").exists())
            self.assertEqual(stderr, "")

    def test_spec_coverage_output_writes_report_only(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(
                root,
                systems=[
                    {
                        "name": "Web",
                        "slug": "web",
                        "kit": "test",
                        "codebase": [{"path": "src/web", "extensions": [".py"]}],
                    },
                ],
            )
            source_file = root / "src" / "web" / "app.py"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("# @cpt-algo:cpt-web-flow:p1\nx = 1\n", encoding="utf-8")
            source_before = source_file.read_text(encoding="utf-8")
            report_path = root / "coverage-report.json"

            exit_code, stdout, stderr = _run_main(
                ["spec-coverage", "--output", str(report_path)],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(source_file.read_text(encoding="utf-8"), source_before)
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".gitignore").exists())

    def test_spec_coverage_min_coverage_threshold_fails(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(
                root,
                systems=[
                    {
                        "name": "Web",
                        "slug": "web",
                        "kit": "test",
                        "codebase": [{"path": "src/web", "extensions": [".py"]}],
                    },
                ],
            )
            source_file = root / "src" / "web" / "app.py"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text(
                "# @cpt-begin:cpt-web-flow:p1:inst-a\n"
                "x = 1\n"
                "# @cpt-end:cpt-web-flow:p1:inst-a\n"
                "y = 2\n",
                encoding="utf-8",
            )
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "spec-coverage", "--min-coverage", "75"],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["summary"]["coverage_pct"], 50.0)
            self.assertTrue(any("coverage 50.00% < 75.00%" in item for item in payload["threshold_failures"]))
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_spec_coverage_min_file_coverage_threshold_fails(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(
                root,
                systems=[
                    {
                        "name": "Web",
                        "slug": "web",
                        "kit": "test",
                        "codebase": [{"path": "src/web", "extensions": [".py"]}],
                    },
                ],
            )
            low = root / "src" / "web" / "low.py"
            high = root / "src" / "web" / "high.py"
            low.parent.mkdir(parents=True, exist_ok=True)
            low.write_text(
                "# @cpt-begin:cpt-web-flow:p1:inst-a\n"
                "x = 1\n"
                "# @cpt-end:cpt-web-flow:p1:inst-a\n"
                "y = 2\n",
                encoding="utf-8",
            )
            high.write_text(
                "# @cpt-begin:cpt-web-flow:p1:inst-a\n"
                "x = 1\n"
                "y = 2\n"
                "# @cpt-end:cpt-web-flow:p1:inst-a\n",
                encoding="utf-8",
            )
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "spec-coverage", "--min-file-coverage", "75"],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(
                any("file src/web/low.py coverage 50.00% < 75.00%" in item for item in payload["threshold_failures"])
            )
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_spec_coverage_min_granularity_threshold_fails(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(
                root,
                systems=[
                    {
                        "name": "Web",
                        "slug": "web",
                        "kit": "test",
                        "codebase": [{"path": "src/web", "extensions": [".py"]}],
                    },
                ],
            )
            source_file = root / "src" / "web" / "granularity.py"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            body = "".join(f"line_{i} = {i}\n" for i in range(1, 31))
            source_file.write_text(
                "# @cpt-begin:cpt-web-flow:p1:inst-a\n"
                f"{body}"
                "# @cpt-end:cpt-web-flow:p1:inst-a\n",
                encoding="utf-8",
            )
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "spec-coverage", "--min-granularity", "0.5"],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertAlmostEqual(payload["summary"]["granularity_score"], 0.3333, places=4)
            self.assertTrue(any("granularity 0.3333 < 0.5000" in item for item in payload["threshold_failures"]))
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_spec_coverage_min_file_granularity_threshold_fails(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(
                root,
                systems=[
                    {
                        "name": "Web",
                        "slug": "web",
                        "kit": "test",
                        "codebase": [{"path": "src/web", "extensions": [".py"]}],
                    },
                ],
            )
            low = root / "src" / "web" / "low_granularity.py"
            high = root / "src" / "web" / "high_granularity.py"
            low.parent.mkdir(parents=True, exist_ok=True)
            low.write_text(
                "# @cpt-begin:cpt-web-flow:p1:inst-a\n"
                + "".join(f"line_{i} = {i}\n" for i in range(1, 31))
                + "# @cpt-end:cpt-web-flow:p1:inst-a\n",
                encoding="utf-8",
            )
            high.write_text(
                "# @cpt-begin:cpt-web-flow:p1:inst-a\n"
                "x = 1\n"
                "# @cpt-end:cpt-web-flow:p1:inst-a\n"
                "# @cpt-begin:cpt-web-flow:p1:inst-b\n"
                "y = 2\n"
                "# @cpt-end:cpt-web-flow:p1:inst-b\n",
                encoding="utf-8",
            )
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "spec-coverage", "--min-file-granularity", "0.5"],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(
                any(
                    "file src/web/low_granularity.py granularity 0.3333 < 0.5000" in item
                    for item in payload["threshold_failures"]
                )
            )
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_spec_coverage_verbose_includes_file_details(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(
                root,
                systems=[
                    {
                        "name": "Web",
                        "slug": "web",
                        "kit": "test",
                        "codebase": [{"path": "src/web", "extensions": [".py"]}],
                    },
                ],
            )
            source_file = root / "src" / "web" / "verbose.py"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text(
                "# @cpt-begin:cpt-web-flow:p1:inst-a\n"
                "x = 1\n"
                "# @cpt-end:cpt-web-flow:p1:inst-a\n"
                "y = 2\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = _run_main(
                ["--json", "spec-coverage", "--verbose"],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout)
            entry = payload["files"]["src/web/verbose.py"]
            self.assertEqual(entry["scope_markers"], 0)
            self.assertEqual(entry["block_markers"], 1)
            self.assertEqual(entry["covered_ranges"], [[2, 2]])
            self.assertEqual(entry["uncovered_ranges"], [[4, 4]])
            self.assertEqual(stderr, "")


class TestCLICheckLanguageE2E(unittest.TestCase):
    def test_check_language_uses_default_project_root_and_leaves_doc_unchanged(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(root)
            doc = root / "architecture" / "PRD.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text("# PRD\n\nПривет мир\n", encoding="utf-8")
            before = doc.read_text(encoding="utf-8")

            exit_code, stdout, stderr = _run_main(
                ["--json", "check-language"],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["files_scanned"], 1)
            self.assertEqual(payload["violation_count"], 1)
            self.assertEqual(payload["allowed_languages"], ["en"])
            self.assertEqual(doc.read_text(encoding="utf-8"), before)
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".gitignore").exists())
            self.assertEqual(stderr, "")

    def test_check_language_override_passes_without_creating_reports(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(root)
            doc = root / "architecture" / "notes.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text("# Notes\n\nHello\nПривет\n", encoding="utf-8")
            before = doc.read_text(encoding="utf-8")
            report_path = root / "language-report.json"

            exit_code, stdout, stderr = _run_main(
                ["--json", "check-language", "--languages", "en,ru", str(doc)],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(doc.read_text(encoding="utf-8"), before)
            self.assertFalse(report_path.exists())
            self.assertFalse((root / "CLAUDE.md").exists())
            self.assertFalse((root / ".gitignore").exists())
            self.assertEqual(stderr, "")

    def test_check_language_unknown_language_errors_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(root)
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "check-language", "--languages", "en,xx_invalid"],
                cwd=root,
            )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn("Unknown language code(s): xx_invalid", payload["message"])
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_check_language_missing_path_errors_without_writes(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(root)
            missing = root / "architecture" / "missing.md"
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "check-language", "--languages", "en", str(missing)],
                cwd=root,
            )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "ERROR")
            self.assertIn(str(missing), payload["message"])
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_check_language_ignore_pattern_skips_violations(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(root)
            ignored = root / "architecture" / "translations" / "ru.md"
            clean = root / "architecture" / "notes.md"
            ignored.parent.mkdir(parents=True, exist_ok=True)
            ignored.write_text("# RU\n\nПривет мир\n", encoding="utf-8")
            clean.write_text("# Notes\n\nHello world\n", encoding="utf-8")
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "check-language", "--languages", "en", "--ignore", "*/translations/*.md"],
                cwd=root,
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["files_scanned"], 2)
            self.assertEqual(payload["violation_count"], 0)
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_check_language_quiet_violation_contract(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(root)
            doc = root / "architecture" / "PRD.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text("# PRD\n\nПривет мир\n", encoding="utf-8")
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["check-language", "--quiet"],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            self.assertNotIn("Allowed languages", stdout)
            self.assertNotIn("Files scanned", stdout)
            self.assertIn("FAIL", stdout)
            self.assertIn("PRD.md", stdout)
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")

    def test_check_language_real_violation_reports_details(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _bootstrap_project(root)
            doc = root / "architecture" / "PRD.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text("# PRD\n\nПривет мир\n", encoding="utf-8")
            before = _snapshot_files(root)

            exit_code, stdout, stderr = _run_main(
                ["--json", "check-language", str(doc)],
                cwd=root,
            )

            self.assertEqual(exit_code, 2)
            payload = json.loads(stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertEqual(payload["file_count"], 1)
            self.assertEqual(payload["violation_count"], 1)
            violation = payload["violations"][0]
            self.assertEqual(Path(violation["path"]).name, "PRD.md")
            self.assertEqual(violation["line"], 3)
            self.assertIn("Привет", violation["preview"])
            self.assertEqual(_snapshot_files(root), before)
            self.assertEqual(stderr, "")


class TestCLIAliasBehaviorE2E(unittest.TestCase):
    def test_aliases_forward_args_and_do_not_create_files_outside_projects(self):
        cases = [
            ("validate-code", "_cmd_validate", ["--artifact", "architecture/PRD.md", "--verbose"]),
            ("validate-rules", "_cmd_validate_kits", ["kits/test", "--kit", "test", "--verbose"]),
            ("self-check", "_cmd_validate_kits", ["--kit", "test", "--verbose"]),
        ]
        for alias, target_name, forwarded_args in cases:
            with self.subTest(alias=alias):
                seen: dict[str, object] = {}

                def _fake(argv: list[str]) -> int:
                    from studio.utils.ui import is_json_mode

                    seen["argv"] = argv
                    seen["json_mode"] = is_json_mode()
                    return 17

                with TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    before_entries = sorted(p.name for p in root.iterdir())
                    with patch.object(cli, target_name, side_effect=_fake):
                        exit_code, stdout, stderr = _run_main(
                            ["--json", alias, *forwarded_args],
                            cwd=root,
                        )

                    self.assertEqual(exit_code, 17)
                    self.assertEqual(seen["argv"], forwarded_args)
                    self.assertTrue(seen["json_mode"])
                    self.assertEqual(stdout, "")
                    self.assertEqual(stderr, "")
                    self.assertEqual(sorted(p.name for p in root.iterdir()), before_entries)
                    self.assertFalse((root / "CLAUDE.md").exists())
                    self.assertFalse((root / ".gitignore").exists())


if __name__ == "__main__":
    unittest.main()
