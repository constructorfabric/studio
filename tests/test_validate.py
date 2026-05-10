"""Tests for validation related utility functions.

NOTE: Tests for validation module (cascade, common, traceability, cdsl) were removed
because the validation module is not used by CLI commands and was deleted.
Only tests for CLI and utils functions are kept.
"""

import sys
import json
from pathlib import Path
import io
import contextlib
import unittest
from unittest.mock import MagicMock
from tempfile import TemporaryDirectory


# Add skills/cypilot/scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from cypilot.utils.files import (
    find_cypilot_directory,
    find_project_root,
    load_artifacts_registry,
    load_project_config,
    load_text,
)

from cypilot import cli as cypilot_cli


def _bootstrap_registry(project_root: Path, *, entries: list) -> None:
    (project_root / ".git").mkdir(exist_ok=True)
    # New layout: cypilot_path variable in root AGENTS.md TOML block
    (project_root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = "adapter"\n```\n',
        encoding="utf-8",
    )
    adapter_dir = project_root / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    (adapter_dir / "config").mkdir(exist_ok=True)
    (adapter_dir / "config" / "AGENTS.md").write_text(
        "# Cypilot Adapter: Test\n",
        encoding="utf-8",
    )
    (adapter_dir / "config" / "artifacts.toml").write_text(
        _make_artifacts_toml(entries),
        encoding="utf-8",
    )


def _make_artifacts_toml(entries: list) -> str:
    """Build a minimal artifacts.toml from a list of legacy entry dicts."""
    lines = ['version = "1.0"', 'project_root = ".."', '']
    for e in entries:
        kind = e.get("kind", e.get("type", "UNKNOWN"))
        path = e.get("path", "")
        lines.append('[[systems]]')
        lines.append(f'name = "Test"')
        lines.append(f'slug = "test"')
        lines.append(f'kit = "k"')
        lines.append('')
        lines.append('[[systems.artifacts]]')
        lines.append(f'path = "{path}"')
        lines.append(f'kind = "{kind}"')
        lines.append(f'traceability = "FULL"')
        lines.append('')
    if not entries:
        lines.append('[[systems]]')
        lines.append('name = "Test"')
        lines.append('slug = "test"')
        lines.append('kit = "k"')
        lines.append('')
    return '\n'.join(lines) + '\n'


class TestMain(unittest.TestCase):
    """Tests for main validation entry point."""
    def test_main_exit_code_fail(self):
        """Test that main() returns error code on validation failure."""
        with TemporaryDirectory() as td:
            root = Path(td)
            prd = root / "architecture" / "PRD.md"
            prd.parent.mkdir(parents=True, exist_ok=True)
            # Use disallowed link notation
            prd.write_text("# PRD\n\nSee @/some/path for details.\n", encoding="utf-8")

            _bootstrap_registry(
                root,
                entries=[
                    {"kind": "PRD", "system": "Test", "path": "architecture/PRD.md", "format": "Cypilot"},
                ],
            )

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cypilot_cli.main([
                    "validate",
                    "--artifact",
                    str(prd),
                ])
            # validate returns 1 or 2 on error
            self.assertIn(code, [1, 2])


class TestParsingUtils(unittest.TestCase):
    """Tests for utils/parsing.py"""

    def test_parse_required_sections(self):
        from cypilot.utils.parsing import parse_required_sections
        with TemporaryDirectory() as td:
            req = Path(td) / "req.md"
            req.write_text("### Section A: Intro\n### Section B: Body\n", encoding="utf-8")
            result = parse_required_sections(req)
            self.assertEqual(result, {"A": "Intro", "B": "Body"})

    def test_split_by_section_letter_with_offsets(self):
        import re
        from cypilot.utils.parsing import split_by_section_letter_with_offsets
        section_re = re.compile(r"^##\s+([A-Z])\.\s+(.+)?$", re.IGNORECASE)
        text = "# Header\n\n## A. First\n\nContent A.\n\n## B. Second\n\nContent B.\n"
        order, sections, offsets = split_by_section_letter_with_offsets(text, section_re)
        self.assertEqual(order, ["A", "B"])
        self.assertIn("A", sections)
        self.assertIn("B", sections)
        self.assertIn("A", offsets)
        self.assertIn("B", offsets)



class TestFilesUtilsCoverage(unittest.TestCase):
    def test_find_project_root_none_when_no_markers(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            self.assertIsNone(find_project_root(root))

    def test_load_project_config_returns_none_when_no_agents_md(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            # No AGENTS.md at all → load_project_config returns None
            self.assertIsNone(load_project_config(root))

    def test_find_cypilot_directory_returns_none_when_config_path_invalid(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir(exist_ok=True)
            # AGENTS.md points to a non-existent directory
            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = "missing-adapter"\n```\n',
                encoding="utf-8",
            )
            self.assertIsNone(find_cypilot_directory(root))

    def test_load_artifacts_registry_error_branches(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            adapter = root / "adapter"
            adapter.mkdir(parents=True, exist_ok=True)

            reg, err = load_artifacts_registry(adapter)
            self.assertIsNone(reg)
            self.assertIsNotNone(err)

            (adapter / "artifacts.json").write_text("not-json", encoding="utf-8")
            reg, err = load_artifacts_registry(adapter)
            self.assertIsNone(reg)
            self.assertIsNotNone(err)

            (adapter / "artifacts.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
            reg, err = load_artifacts_registry(adapter)
            self.assertIsNone(reg)
            self.assertIsNotNone(err)

            (adapter / "artifacts.json").write_text(json.dumps({"version": "1.0", "artifacts": []}), encoding="utf-8")
            reg, err = load_artifacts_registry(adapter)
            self.assertIsNotNone(reg)
            self.assertIsNone(err)

    def test_load_text_not_a_file(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            subdir = root / "subdir"
            subdir.mkdir()
            content, err = load_text(subdir)
            self.assertEqual(content, "")
            self.assertIsNotNone(err)


class TestFindArtifactInSystem(unittest.TestCase):
    """Tests for _find_artifact_in_system helper."""

    def test_finds_existing_artifact(self):
        from cypilot.commands.validate import _find_artifact_in_system
        from cypilot.utils.artifacts_meta import SystemNode, Artifact

        with TemporaryDirectory() as td:
            root = Path(td)
            design = root / "architecture" / "DESIGN.md"
            design.parent.mkdir(parents=True, exist_ok=True)
            design.write_text("# Design\n", encoding="utf-8")

            node = SystemNode(
                name="test", slug="test", kit="sdlc",
                artifacts=[Artifact(path="architecture/DESIGN.md", kind="DESIGN", traceability="FULL")],
            )
            result = _find_artifact_in_system(node, "DESIGN", root)
            self.assertIsNotNone(result)
            self.assertIn("DESIGN.md", result)

    def test_returns_none_for_missing_artifact(self):
        from cypilot.commands.validate import _find_artifact_in_system
        from cypilot.utils.artifacts_meta import SystemNode, Artifact

        with TemporaryDirectory() as td:
            root = Path(td)
            node = SystemNode(
                name="test", slug="test", kit="sdlc",
                artifacts=[Artifact(path="architecture/DESIGN.md", kind="DESIGN", traceability="FULL")],
            )
            result = _find_artifact_in_system(node, "DESIGN", root)
            self.assertIsNone(result)

    def test_returns_none_for_wrong_kind(self):
        from cypilot.commands.validate import _find_artifact_in_system
        from cypilot.utils.artifacts_meta import SystemNode, Artifact

        with TemporaryDirectory() as td:
            root = Path(td)
            prd = root / "architecture" / "PRD.md"
            prd.parent.mkdir(parents=True, exist_ok=True)
            prd.write_text("# PRD\n", encoding="utf-8")

            node = SystemNode(
                name="test", slug="test", kit="sdlc",
                artifacts=[Artifact(path="architecture/PRD.md", kind="PRD", traceability="FULL")],
            )
            result = _find_artifact_in_system(node, "DESIGN", root)
            self.assertIsNone(result)

    def test_searches_children(self):
        from cypilot.commands.validate import _find_artifact_in_system
        from cypilot.utils.artifacts_meta import SystemNode, Artifact

        with TemporaryDirectory() as td:
            root = Path(td)
            design = root / "sub" / "DESIGN.md"
            design.parent.mkdir(parents=True, exist_ok=True)
            design.write_text("# Design\n", encoding="utf-8")

            child = SystemNode(
                name="sub", slug="sub", kit="sdlc",
                artifacts=[Artifact(path="sub/DESIGN.md", kind="DESIGN", traceability="FULL")],
            )
            parent = SystemNode(name="test", slug="test", kit="sdlc", children=[child])
            result = _find_artifact_in_system(parent, "DESIGN", root)
            self.assertIsNotNone(result)

    def test_returns_none_for_non_system_node(self):
        from cypilot.commands.validate import _find_artifact_in_system

        with TemporaryDirectory() as td:
            result = _find_artifact_in_system("not-a-node", "DESIGN", Path(td))
            self.assertIsNone(result)


class TestSuggestPathFromAutodetect(unittest.TestCase):
    """Tests for _suggest_path_from_autodetect helper."""

    def test_suggests_path_simple_pattern(self):
        from cypilot.commands.validate import _suggest_path_from_autodetect
        from cypilot.utils.artifacts_meta import SystemNode, AutodetectRule, AutodetectArtifactPattern

        rule = AutodetectRule(
            system_root="{project_root}",
            artifacts_root="{system_root}/architecture",
            artifacts={"DESIGN": AutodetectArtifactPattern(pattern="DESIGN.md", traceability="FULL")},
        )
        node = SystemNode(name="test", slug="test", kit="sdlc", autodetect=[rule])
        result = _suggest_path_from_autodetect(node, "DESIGN")
        self.assertEqual(result, "architecture/DESIGN.md")

    def test_suggests_path_glob_pattern(self):
        from cypilot.commands.validate import _suggest_path_from_autodetect
        from cypilot.utils.artifacts_meta import SystemNode, AutodetectRule, AutodetectArtifactPattern

        rule = AutodetectRule(
            system_root="{project_root}",
            artifacts_root="{system_root}/architecture",
            artifacts={"ADR": AutodetectArtifactPattern(pattern="ADR/*.md", traceability="FULL")},
        )
        node = SystemNode(name="test", slug="test", kit="sdlc", autodetect=[rule])
        result = _suggest_path_from_autodetect(node, "ADR")
        self.assertEqual(result, "architecture/ADR.md")

    def test_returns_none_for_unknown_kind(self):
        from cypilot.commands.validate import _suggest_path_from_autodetect
        from cypilot.utils.artifacts_meta import SystemNode, AutodetectRule, AutodetectArtifactPattern

        rule = AutodetectRule(
            artifacts={"PRD": AutodetectArtifactPattern(pattern="PRD.md", traceability="FULL")},
        )
        node = SystemNode(name="test", slug="test", kit="sdlc", autodetect=[rule])
        result = _suggest_path_from_autodetect(node, "DESIGN")
        self.assertIsNone(result)

    def test_returns_none_for_non_system_node(self):
        from cypilot.commands.validate import _suggest_path_from_autodetect
        result = _suggest_path_from_autodetect("not-a-node", "DESIGN")
        self.assertIsNone(result)

    def test_returns_none_for_empty_autodetect(self):
        from cypilot.commands.validate import _suggest_path_from_autodetect
        from cypilot.utils.artifacts_meta import SystemNode

        node = SystemNode(name="test", slug="test", kit="sdlc", autodetect=[])
        result = _suggest_path_from_autodetect(node, "DESIGN")
        self.assertIsNone(result)

    def test_substitutes_system_slug(self):
        from cypilot.commands.validate import _suggest_path_from_autodetect
        from cypilot.utils.artifacts_meta import SystemNode, AutodetectRule, AutodetectArtifactPattern

        rule = AutodetectRule(
            system_root="{project_root}/{system}",
            artifacts_root="{system_root}/docs",
            artifacts={"DESIGN": AutodetectArtifactPattern(pattern="DESIGN.md", traceability="FULL")},
        )
        node = SystemNode(name="My App", slug="myapp", kit="sdlc", autodetect=[rule])
        result = _suggest_path_from_autodetect(node, "DESIGN")
        self.assertEqual(result, "myapp/docs/DESIGN.md")

    def test_returns_none_for_empty_pattern(self):
        from cypilot.commands.validate import _suggest_path_from_autodetect
        from cypilot.utils.artifacts_meta import SystemNode, AutodetectRule, AutodetectArtifactPattern

        rule = AutodetectRule(
            artifacts={"DESIGN": AutodetectArtifactPattern(pattern="", traceability="FULL")},
        )
        node = SystemNode(name="test", slug="test", kit="sdlc", autodetect=[rule])
        result = _suggest_path_from_autodetect(node, "DESIGN")
        self.assertIsNone(result)


class TestEnrichTargetArtifactPaths(unittest.TestCase):
    """Tests for _enrich_target_artifact_paths helper."""

    def test_skips_non_artifacts_meta(self):
        from cypilot.commands.validate import _enrich_target_artifact_paths

        issues = [{"code": "ref-missing-from-kind", "target_kind": "DESIGN", "path": "/tmp/PRD.md"}]
        _enrich_target_artifact_paths(issues, meta=None, project_root=Path("/tmp"))
        self.assertNotIn("target_artifact_path", issues[0])

    def test_skips_non_matching_code(self):
        from cypilot.commands.validate import _enrich_target_artifact_paths
        from cypilot.utils.artifacts_meta import ArtifactsMeta

        meta = ArtifactsMeta.__new__(ArtifactsMeta)
        meta._systems = []
        meta._kits = {}
        meta._artifact_index = {}

        issues = [{"code": "some-other-code", "message": "unrelated"}]
        _enrich_target_artifact_paths(issues, meta=meta, project_root=Path("/tmp"))
        self.assertNotIn("target_artifact_path", issues[0])

    def test_enriches_with_existing_artifact(self):
        from cypilot.commands.validate import _enrich_target_artifact_paths
        from cypilot.utils.artifacts_meta import ArtifactsMeta, SystemNode, Artifact

        with TemporaryDirectory() as td:
            root = Path(td)
            prd = root / "architecture" / "PRD.md"
            design = root / "architecture" / "DESIGN.md"
            prd.parent.mkdir(parents=True, exist_ok=True)
            prd.write_text("# PRD\n", encoding="utf-8")
            design.write_text("# Design\n", encoding="utf-8")

            node = SystemNode(
                name="test", slug="test", kit="sdlc",
                artifacts=[
                    Artifact(path="architecture/PRD.md", kind="PRD", traceability="FULL"),
                    Artifact(path="architecture/DESIGN.md", kind="DESIGN", traceability="FULL"),
                ],
            )
            meta = ArtifactsMeta.__new__(ArtifactsMeta)
            meta._systems = [node]
            meta._kits = {}
            meta._ignore_patterns = []
            meta._artifacts_by_path = {"architecture/PRD.md": (node.artifacts[0], node)}

            issues = [{
                "code": "ref-missing-from-kind",
                "target_kind": "DESIGN",
                "path": str(prd),
            }]
            _enrich_target_artifact_paths(issues, meta=meta, project_root=root)
            self.assertIn("target_artifact_path", issues[0])

    def test_enriches_with_suggested_path(self):
        from cypilot.commands.validate import _enrich_target_artifact_paths
        from cypilot.utils.artifacts_meta import (
            ArtifactsMeta, SystemNode, Artifact,
            AutodetectRule, AutodetectArtifactPattern,
        )

        with TemporaryDirectory() as td:
            root = Path(td)
            prd = root / "architecture" / "PRD.md"
            prd.parent.mkdir(parents=True, exist_ok=True)
            prd.write_text("# PRD\n", encoding="utf-8")

            rule = AutodetectRule(
                system_root="{project_root}",
                artifacts_root="{system_root}/architecture",
                artifacts={"DESIGN": AutodetectArtifactPattern(pattern="DESIGN.md", traceability="FULL")},
            )
            node = SystemNode(
                name="test", slug="test", kit="sdlc",
                artifacts=[Artifact(path="architecture/PRD.md", kind="PRD", traceability="FULL")],
                autodetect=[rule],
            )
            meta = ArtifactsMeta.__new__(ArtifactsMeta)
            meta._systems = [node]
            meta._kits = {}
            meta._ignore_patterns = []
            meta._artifacts_by_path = {"architecture/PRD.md": (node.artifacts[0], node)}

            issues = [{
                "code": "ref-missing-from-kind",
                "target_kind": "DESIGN",
                "path": str(prd),
            }]
            _enrich_target_artifact_paths(issues, meta=meta, project_root=root)
            self.assertIn("target_artifact_suggested_path", issues[0])
            self.assertEqual(issues[0]["target_artifact_suggested_path"], "architecture/DESIGN.md")


class TestRunContentLanguageCheck(unittest.TestCase):
    """Regression tests for _run_content_language_check error handling."""

    def _call(self, ws_return, artifacts=None):
        from unittest.mock import patch
        from cypilot.commands.validate import _run_content_language_check

        if artifacts is None:
            artifacts = []

        with patch("cypilot.utils.workspace.find_workspace_config", return_value=ws_return):
            return _run_content_language_check(artifacts, Path("/fake/root"))

    def test_broken_config_returns_error_not_empty_list(self):
        """find_workspace_config() -> (None, 'bad config') must produce a validation error."""
        results = self._call((None, "bad config"))
        self.assertEqual(len(results), 1)
        self.assertIn("file-load-error", str(results[0].get("code", "")))

    def test_broken_config_error_message_contains_reason(self):
        results = self._call((None, "TOML parse error"))
        self.assertIn("TOML parse error", str(results[0].get("message", "")))

    def test_no_config_file_returns_empty(self):
        """(None, None) means no workspace config — silent skip, not an error."""
        results = self._call((None, None))
        self.assertEqual(results, [])

    def test_config_without_validation_section_returns_empty(self):
        mock_cfg = MagicMock()
        mock_cfg.validation = None
        results = self._call((mock_cfg, None))
        self.assertEqual(results, [])

    def test_config_with_empty_languages_returns_empty(self):
        mock_cfg = MagicMock()
        mock_cfg.validation.allowed_content_languages = []
        results = self._call((mock_cfg, None))
        self.assertEqual(results, [])

    def test_skips_non_md_artifacts(self):
        """Non-.md artifacts must be skipped (line 971-972 path)."""
        from unittest.mock import patch
        from cypilot.commands.validate import _run_content_language_check

        mock_cfg = MagicMock()
        mock_cfg.validation.allowed_content_languages = ["en"]

        with TemporaryDirectory() as td:
            root = Path(td)
            py_file = root / "code.py"
            py_file.write_text("print('hello')\n", encoding="utf-8")
            artifacts = [(py_file, Path("/t"), "CODE", "FULL", "kit")]
            with patch("cypilot.utils.workspace.find_workspace_config", return_value=(mock_cfg, None)):
                results = _run_content_language_check(artifacts, root)
            self.assertEqual(results, [])

    def test_md_with_disallowed_chars_returns_violation(self):
        """An .md file containing disallowed chars produces a CONTENT_LANGUAGE_VIOLATION error."""
        from unittest.mock import patch
        from cypilot.commands.validate import _run_content_language_check

        mock_cfg = MagicMock()
        mock_cfg.validation.allowed_content_languages = ["en"]

        with TemporaryDirectory() as td:
            root = Path(td)
            md = root / "doc.md"
            # Cyrillic content not allowed under "en"
            md.write_text("# Title\n\nПривет мир\n", encoding="utf-8")
            artifacts = [(md, Path("/t"), "PRD", "FULL", "kit")]
            with patch("cypilot.utils.workspace.find_workspace_config", return_value=(mock_cfg, None)):
                results = _run_content_language_check(artifacts, root)
            self.assertGreaterEqual(len(results), 1)
            self.assertIn("language", str(results[0].get("category", "")) + str(results[0]))

    def test_md_within_allowed_returns_empty(self):
        """An .md file with only English chars and "en" allowed returns no violations."""
        from unittest.mock import patch
        from cypilot.commands.validate import _run_content_language_check

        mock_cfg = MagicMock()
        mock_cfg.validation.allowed_content_languages = ["en"]

        with TemporaryDirectory() as td:
            root = Path(td)
            md = root / "doc.md"
            md.write_text("# Title\n\nHello World\n", encoding="utf-8")
            artifacts = [(md, Path("/t"), "PRD", "FULL", "kit")]
            with patch("cypilot.utils.workspace.find_workspace_config", return_value=(mock_cfg, None)):
                results = _run_content_language_check(artifacts, root)
            self.assertEqual(results, [])

    def test_lang_scan_error_for_unreadable_file(self):
        """Triggers LangScanError branch (lines 983-990) when scan_file raises."""
        from unittest.mock import patch
        from cypilot.commands.validate import _run_content_language_check
        from cypilot.utils.content_language import LangScanError

        mock_cfg = MagicMock()
        mock_cfg.validation.allowed_content_languages = ["en"]

        with TemporaryDirectory() as td:
            root = Path(td)
            md = root / "broken.md"
            md.write_text("anything\n", encoding="utf-8")
            artifacts = [(md, Path("/t"), "PRD", "FULL", "kit")]

            def _raise(p, _ranges):
                raise LangScanError(p, OSError("simulated I/O failure"))

            with patch("cypilot.utils.workspace.find_workspace_config", return_value=(mock_cfg, None)), \
                 patch("cypilot.utils.content_language.scan_file", side_effect=_raise):
                results = _run_content_language_check(artifacts, root)
            self.assertEqual(len(results), 1)
            self.assertIn("Cannot read file", str(results[0].get("message", "")))


class TestCmdValidateArtifactArg(unittest.TestCase):
    """Cover early-exit branches in cmd_validate driven by --artifact arg."""

    def test_artifact_not_found_returns_error(self):
        """Hits lines 187-188: artifact path doesn't exist."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _bootstrap_registry(
                root,
                entries=[
                    {"kind": "PRD", "system": "Test", "path": "architecture/PRD.md", "format": "Cypilot"},
                ],
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cypilot_cli.main([
                    "validate",
                    "--artifact",
                    str(root / "does-not-exist.md"),
                ])
            # ERROR exit code
            self.assertIn(code, [1, 2])
            # JSON output should mention "not found"
            output = buf.getvalue()
            self.assertIn("not found", output.lower())


if __name__ == "__main__":
    unittest.main()
