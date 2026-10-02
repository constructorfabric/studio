"""
Tests for commands/where_defined.py and commands/where_used.py.

Covers: cmd_where_defined, cmd_where_used, _human_where_defined, _human_where_used.
"""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.get_content import cmd_get_content
from studio.commands.list_ids import cmd_list_ids
from studio.commands.where_defined import cmd_where_defined, _human_where_defined
from studio.commands.where_used import cmd_where_used, _human_where_used
from studio.utils.context import StudioContext as CypilotContext, set_context
from studio.utils.ui import is_json_mode, set_json_mode
from studio.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_project(root: Path) -> Path:
    """Bootstrap a minimal Constructor Studio project. Returns adapter dir."""
    (root / ".git").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n',
        encoding="utf-8",
    )
    adapter = root / "adapter"
    adapter.mkdir(parents=True, exist_ok=True)
    (adapter / "config").mkdir(exist_ok=True)
    (adapter / "config" / "AGENTS.md").write_text("# Adapter\n", encoding="utf-8")

    from studio.utils import toml_utils
    toml_utils.dump({
        "version": "1.0",
        "project_root": "..",
        "kits": {"cypilot": {"format": "CFS", "path": "kits/sdlc"}},
        "systems": [{
            "name": "Test",
            "kits": "cypilot",
            "artifacts": [{"path": "architecture/PRD.md", "kind": "PRD"}],
        }],
    }, adapter / "config" / "artifacts.toml")

    # Create the artifact with a defined + referenced ID
    art_dir = root / "architecture"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "PRD.md").write_text(
        "- [x] `p1` - **ID**: `cpt-test-item-1`\n"
        "<!-- @cpt-ref: cpt-test-item-1 -->\n",
        encoding="utf-8",
    )

    # Kit structure
    kit_dir = root / "kits" / "sdlc" / "artifacts" / "PRD"
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "template.md").write_text(
        "---\ncypilot-template:\n  version:\n    major: 1\n    minor: 0\n  kind: PRD\n---\n"
        "- [ ] `p1` - **ID**: `cpt-{system}-item-{slug}`\n",
        encoding="utf-8",
    )
    from _test_helpers import write_constraints_toml
    write_constraints_toml(root / "kits" / "sdlc", {
        "PRD": {"identifiers": {"item": {"template": "cpt-{system}-item-{slug}"}}},
    })
    return adapter


def _with_context(root: Path):
    """Load CypilotContext from project root and set as global."""
    ctx = CypilotContext.load(root)
    set_context(ctx)
    return ctx


class _ContextTestBase(unittest.TestCase):
    """Base that isolates global context around each test."""

    def setUp(self):
        set_context(None)

    def tearDown(self):
        set_context(None)


# =========================================================================
# cmd_where_defined
# =========================================================================

class TestCmdWhereDefined(_ContextTestBase):

    def test_empty_id_returns_error(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = cmd_where_defined(["--id", ""])
        self.assertEqual(rc, 1)
        out = json.loads(stdout.getvalue())
        self.assertEqual(out["status"], "ERROR")

    def test_no_id_returns_error(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = cmd_where_defined([])
        self.assertEqual(rc, 1)

    def test_both_positional_and_flag_warns(self):
        """When both positional and --id are given, positional wins."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            stdout = io.StringIO()
            with self.assertLogs("studio.utils.context", level="WARNING") as logs:
                with redirect_stdout(stdout):
                    cmd_where_defined(["cpt-test-item-1", "--id", "cpt-other"])
            self.assertTrue(any("using positional" in message for message in logs.output))

    def test_artifact_not_found(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = cmd_where_defined(["--id", "test", "--artifact", "/nonexistent/file.md"])
        self.assertEqual(rc, 1)
        out = json.loads(stdout.getvalue())
        self.assertEqual(out["status"], "ERROR")

    def test_artifact_no_context(self):
        with TemporaryDirectory() as td:
            art = Path(td) / "art.md"
            art.write_text("test\n", encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_defined(["--id", "test", "--artifact", str(art)])
            self.assertEqual(rc, 1)

    def test_artifact_not_in_registry(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            unregistered = root / "random.md"
            unregistered.write_text("content\n", encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = cmd_where_defined(["--id", "test", "--artifact", str(unregistered)])
                self.assertEqual(rc, 1)
                out = json.loads(stdout.getvalue())
                self.assertIn("not in Constructor Studio registry", out.get("message", ""))
            finally:
                os.chdir(cwd)

    def test_artifact_outside_project(self):
        """Artifact exists but is outside project root."""
        with TemporaryDirectory() as td1, TemporaryDirectory() as td2:
            root = Path(td1)
            _setup_project(root)
            outside = Path(td2) / "outside.md"
            outside.write_text("content\n", encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = cmd_where_defined(["--id", "test", "--artifact", str(outside)])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)

    def test_no_context_returns_error(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = cmd_where_defined(["--id", "test"])
                self.assertEqual(rc, 1)
                out = json.loads(stdout.getvalue())
                self.assertEqual(out["status"], "ERROR")
            finally:
                os.chdir(cwd)

    def test_found_single_definition(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_defined(["cpt-test-item-1"])
            self.assertEqual(rc, 0)
            out = json.loads(stdout.getvalue())
            self.assertEqual(out["status"], "FOUND")
            self.assertEqual(out["count"], 1)

    def test_not_found_returns_2(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_defined(["cpt-nonexistent-id"])
            self.assertEqual(rc, 2)
            out = json.loads(stdout.getvalue())
            self.assertEqual(out["status"], "NOT_FOUND")

    def test_ambiguous_multiple_definitions(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            adapter = _setup_project(root)
            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"cypilot": {"format": "CFS", "path": "kits/sdlc"}},
                "systems": [{
                    "name": "Test",
                    "kits": "cypilot",
                    "artifacts": [
                        {"path": "architecture/PRD.md", "kind": "PRD"},
                        {"path": "architecture/DESIGN.md", "kind": "DESIGN"},
                    ],
                }],
            }, adapter / "config" / "artifacts.toml")
            (root / "architecture" / "DESIGN.md").write_text(
                "- [x] `p1` - **ID**: `cpt-test-item-1`\n",
                encoding="utf-8",
            )
            _with_context(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_defined(["cpt-test-item-1"])
            self.assertEqual(rc, 2)
            out = json.loads(stdout.getvalue())
            self.assertEqual(out["status"], "AMBIGUOUS")
            self.assertEqual(out["count"], 2)

    def test_with_artifact_flag_found(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            art_path = root / "architecture" / "PRD.md"
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = cmd_where_defined(["--id", "cpt-test-item-1", "--artifact", str(art_path)])
                self.assertEqual(rc, 0)
                out = json.loads(stdout.getvalue())
                self.assertEqual(out["status"], "FOUND")
            finally:
                os.chdir(cwd)

    def test_no_artifacts_to_scan(self):
        """All registered artifacts are missing from disk."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            (root / "architecture" / "PRD.md").unlink()
            _with_context(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_defined(["cpt-test-item-1"])
            self.assertEqual(rc, 0)
            out = json.loads(stdout.getvalue())
            self.assertEqual(out["status"], "NO_ARTIFACTS")
            self.assertEqual(out["artifacts_scanned"], 0)


# =========================================================================
# cmd_where_used
# =========================================================================

class TestCmdWhereUsed(_ContextTestBase):

    def test_empty_id_returns_error(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = cmd_where_used(["--id", ""])
        self.assertEqual(rc, 1)
        out = json.loads(stdout.getvalue())
        self.assertEqual(out["status"], "ERROR")

    def test_no_id_returns_error(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = cmd_where_used([])
        self.assertEqual(rc, 1)

    def test_both_positional_and_flag_warns(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            stdout = io.StringIO()
            with self.assertLogs("studio.utils.context", level="WARNING") as logs:
                with redirect_stdout(stdout):
                    cmd_where_used(["cpt-test-item-1", "--id", "cpt-other"])
            self.assertTrue(any("using positional" in message for message in logs.output))

    def test_artifact_not_found(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = cmd_where_used(["--id", "test", "--artifact", "/nonexistent/file.md"])
        self.assertEqual(rc, 1)

    def test_artifact_no_context(self):
        with TemporaryDirectory() as td:
            art = Path(td) / "art.md"
            art.write_text("test\n", encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_used(["--id", "test", "--artifact", str(art)])
            self.assertEqual(rc, 1)

    def test_artifact_not_in_registry(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            unregistered = root / "random.md"
            unregistered.write_text("content\n", encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = cmd_where_used(["--id", "test", "--artifact", str(unregistered)])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)

    def test_no_context_returns_error(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = cmd_where_used(["--id", "test"])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)

    def test_found_references(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_used(["cpt-test-item-1"])
            self.assertEqual(rc, 0)
            out = json.loads(stdout.getvalue())
            self.assertGreaterEqual(out["count"], 0)

    def test_include_definitions(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_used(["cpt-test-item-1", "--include-definitions"])
            self.assertEqual(rc, 0)
            out = json.loads(stdout.getvalue())
            self.assertGreaterEqual(out["count"], 1)

    def test_no_references_found(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_used(["cpt-nonexistent-id"])
            self.assertEqual(rc, 0)
            out = json.loads(stdout.getvalue())
            self.assertEqual(out["count"], 0)

    def test_with_artifact_flag(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            art_path = root / "architecture" / "PRD.md"
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = cmd_where_used(["--id", "cpt-test-item-1", "--artifact", str(art_path), "--include-definitions"])
                self.assertEqual(rc, 0)
            finally:
                os.chdir(cwd)

    def test_no_artifacts_to_scan(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            (root / "architecture" / "PRD.md").unlink()
            _with_context(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cmd_where_used(["cpt-test-item-1"])
            self.assertEqual(rc, 0)
            out = json.loads(stdout.getvalue())
            self.assertEqual(out["artifacts_scanned"], 0)

    def test_artifact_outside_project(self):
        with TemporaryDirectory() as td1, TemporaryDirectory() as td2:
            root = Path(td1)
            _setup_project(root)
            outside = Path(td2) / "outside.md"
            outside.write_text("content\n", encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(str(root))
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    rc = cmd_where_used(["--id", "test", "--artifact", str(outside)])
                self.assertEqual(rc, 1)
            finally:
                os.chdir(cwd)


# =========================================================================
# Human formatters (need human mode)
# =========================================================================

class _HumanModeBase(unittest.TestCase):
    def setUp(self):
        set_json_mode(False)

    def tearDown(self):
        set_json_mode(True)


class TestHumanWhereDefined(_HumanModeBase):

    def test_found_with_checked(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _human_where_defined({
                "status": "FOUND", "id": "cpt-x", "artifacts_scanned": 1, "count": 1,
                "definitions": [{"artifact": "/tmp/A.md", "artifact_type": "PRD", "line": 10, "checked": True}],
            })
        out = buf.getvalue()
        self.assertIn("cpt-x", out)
        self.assertIn("10", out)

    def test_not_found(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _human_where_defined({
                "status": "NOT_FOUND", "id": "cpt-missing", "artifacts_scanned": 2,
                "count": 0, "definitions": [],
            })
        out = buf.getvalue()
        self.assertIn("not found", out.lower())

    def test_ambiguous(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _human_where_defined({
                "status": "AMBIGUOUS", "id": "cpt-dup", "artifacts_scanned": 2, "count": 2,
                "definitions": [
                    {"artifact": "/tmp/A.md", "artifact_type": "PRD", "line": 1, "checked": False},
                    {"artifact": "/tmp/B.md", "artifact_type": "DESIGN", "line": 5, "checked": False},
                ],
            })
        out = buf.getvalue()
        self.assertIn("Ambiguous", out)

    def test_no_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _human_where_defined({
                "status": "FOUND", "id": "cpt-x", "artifacts_scanned": 1, "count": 1,
                "definitions": [{"artifact": "/tmp/A.md", "artifact_type": "PRD", "line": "", "checked": False}],
            })
        # Should not crash


class TestHumanWhereUsed(_HumanModeBase):

    def test_found_with_checked(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _human_where_used({
                "id": "cpt-x", "artifacts_scanned": 1, "count": 1,
                "references": [{"artifact": "/tmp/A.md", "artifact_type": "PRD", "line": 10, "type": "reference", "checked": True}],
            })
        out = buf.getvalue()
        self.assertIn("cpt-x", out)

    def test_no_refs(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _human_where_used({
                "id": "cpt-missing", "artifacts_scanned": 2, "count": 0, "references": [],
            })
        out = buf.getvalue()
        self.assertIn("No references", out)

    def test_no_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _human_where_used({
                "id": "cpt-x", "artifacts_scanned": 1, "count": 1,
                "references": [{"artifact": "/tmp/A.md", "artifact_type": "PRD", "line": "", "type": "ref", "checked": False}],
            })
        # Should not crash


# =========================================================================
# The documented contracts — architecture/specs/cli.md, query commands (#292, #348)
# =========================================================================

class TestDocumentedContracts(_ContextTestBase):
    """Each test pins one statement the CLI spec makes about a query command's JSON
    shape or exit code, against the real command. The spec was rewritten from these
    commands' actual output; these keep it that way."""

    def setUp(self):
        super().setUp()
        self._json_was = __import__("studio.utils.ui", fromlist=["is_json_mode"]).is_json_mode()
        set_json_mode(True)

    def tearDown(self):
        set_json_mode(self._json_was)
        super().tearDown()

    @staticmethod
    def _run(cmd, argv):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = cmd(argv)
        return rc, json.loads(stdout.getvalue())

    # ---- where-defined ---------------------------------------------------
    def test_where_defined_found_shape(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            rc, out = self._run(cmd_where_defined, ["cpt-test-item-1"])
        self.assertEqual(rc, 0)
        self.assertEqual(set(out), {"status", "id", "artifacts_scanned", "count", "definitions"})
        self.assertEqual(out["status"], "FOUND")
        self.assertEqual(out["count"], len(out["definitions"]), 1)
        record = out["definitions"][0]
        self.assertEqual(set(record), {"artifact", "artifact_type", "line", "kind", "checked"})
        self.assertIsNone(record["kind"])  # documented: this command does not infer it
        self.assertTrue(Path(record["artifact"]).is_absolute())

    def test_where_defined_not_found_keeps_the_shape_and_exits_2(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            rc, out = self._run(cmd_where_defined, ["cpt-test-item-nowhere"])
        self.assertEqual(rc, 2)
        self.assertEqual(set(out), {"status", "id", "artifacts_scanned", "count", "definitions"})
        self.assertEqual((out["status"], out["count"], out["definitions"]), ("NOT_FOUND", 0, []))

    def test_a_link_form_definition_is_listed_by_type_and_is_not_a_definition(self):
        """`list-ids` lists it as `definition-link-form`, with its checkbox and priority;
        `where-defined` does not count it, so an ID defined only that way is NOT_FOUND."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            (root / "architecture" / "PRD.md").write_text(
                "- [x] `p1` - **ID**: [`cpt-test-item-linked`](spec.md)\n", encoding="utf-8")
            _with_context(root)
            rc_list, listed = self._run(cmd_list_ids, ["--pattern", "linked"])
            rc_def, defined = self._run(cmd_where_defined, ["cpt-test-item-linked"])
        self.assertEqual(rc_list, 0)
        self.assertEqual(
            [(h["id"], h["type"], h["checked"], h.get("priority")) for h in listed["ids"]],
            [("cpt-test-item-linked", "definition-link-form", True, "p1")],
        )
        self.assertEqual((rc_def, defined["status"], defined["count"]), (2, "NOT_FOUND", 0))

    def test_where_defined_ambiguous_lists_all_and_exits_2(self):
        with TemporaryDirectory() as td:
            first, second = Path(td) / "a.md", Path(td) / "b.md"
            for path in (first, second):
                path.write_text("# Doc\n\n**ID**: `cpt-test-item-1`\n", encoding="utf-8")
            with patch(
                "studio.commands.where_defined.resolve_target_and_artifacts",
                return_value=("cpt-test-item-1", object(), [(first, "PRD"), (second, "PRD")], {}, None),
            ):
                rc, out = self._run(cmd_where_defined, ["cpt-test-item-1"])
        self.assertEqual(rc, 2)
        self.assertEqual(out["status"], "AMBIGUOUS")
        self.assertEqual(out["count"], len(out["definitions"]), 2)

    # ---- list-ids ----------------------------------------------------------
    def test_list_ids_no_match_is_an_empty_answer_with_exit_0(self):
        """A real scan with nothing matching — not the hand-built dict the human
        renderer's tests use."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            rc, out = self._run(cmd_list_ids, ["--pattern", "zzz-matches-nothing"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, {"count": 0, "artifacts_scanned": 1, "ids": []})

    def test_an_argument_the_parser_rejects_exits_2_with_nothing_on_stdout(self):
        """Documented under Exit Codes: argparse's own rejections exit 2 with a usage
        message on stderr and an empty stdout, for all four query commands. Where 2 also
        means not found, the empty stdout is what tells the two apart."""
        cases = [
            ["list-ids", "--bogus"],
            ["where-used", "cpt-test-item-1", "--bogus"],
            ["where-defined", "cpt-test-item-1", "--bogus"],
            ["get-content", "--code", "impl.py"],  # --id is required
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                stdout, stderr = io.StringIO(), io.StringIO()
                json_was = is_json_mode()
                try:
                    with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                        main(["--json", *argv])
                finally:
                    set_json_mode(json_was)
                self.assertEqual(caught.exception.code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn(f"{argv[0]}: error:", stderr.getvalue())

    def test_list_ids_invalid_regex_is_the_error_object_before_any_scan(self):
        """An invalid `--pattern` under `--regex` used to escape as a traceback with
        nothing on stdout. It is now the JSON error with exit 1, checked first: even with
        no project there, the pattern is what gets reported. A valid one still filters."""
        with TemporaryDirectory() as td:
            no_project = Path(td) / "empty"
            no_project.mkdir()
            answers = [self._run_main(no_project, ["list-ids", "--pattern", bad, "--regex"])
                       for bad in ("(", "a\\")]
            root = Path(td) / "project"
            root.mkdir()
            _setup_project(root)
            rc_ok, matched, _ = self._run_main(root, ["list-ids", "--pattern", r"item-\d$", "--regex"])
        for rc, out, stderr in answers:
            self.assertEqual(rc, 1)
            self.assertEqual(out["status"], "ERROR")
            self.assertTrue(out["message"].startswith("Invalid --pattern regular expression: "), out)
            self.assertNotIn("Traceback", stderr)
        self.assertEqual((rc_ok, [h["id"] for h in matched["ids"]]), (0, ["cpt-test-item-1"]))

    # ---- get-content -------------------------------------------------------
    @staticmethod
    def _marked_code(td: Path) -> Path:
        """Two blocks for one ID, so "the first block" is distinguishable from "a block"."""
        code = td / "impl.py"
        code.write_text(
            "# @cpt-algo:cpt-test-algo-a:p1\n"
            "def outer():\n"
            "    # @cpt-begin:cpt-test-algo-a:p1:inst-one\n"
            "    one = 1\n"
            "    # @cpt-end:cpt-test-algo-a:p1:inst-one\n"
            "    # @cpt-begin:cpt-test-algo-a:p1:inst-two\n"
            "    two = 2\n"
            "    # @cpt-end:cpt-test-algo-a:p1:inst-two\n"
            "    return one + two\n",
            encoding="utf-8",
        )
        return code

    def test_get_content_code_without_inst_returns_the_first_block_with_null_inst(self):
        with TemporaryDirectory() as td:
            code = self._marked_code(Path(td))
            rc, first = self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--code", str(code)])
            rc_two, second = self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--code", str(code), "--inst", "two"])
        self.assertEqual((rc, rc_two), (0, 0))
        self.assertEqual(set(first), {"status", "id", "inst", "text"})
        self.assertIsNone(first["inst"])
        self.assertEqual(first["text"].strip(), "one = 1")   # the first block, not the whole scope
        self.assertEqual(second["inst"], "two")               # the bare id selects the block
        self.assertEqual(second["text"].strip(), "two = 2")

    def test_get_content_unknown_inst_is_not_found_never_another_block(self):
        """Before the fix an unmatched `--inst` returned the ID's first block as FOUND,
        under the name that was asked for."""
        with TemporaryDirectory() as td:
            code = self._marked_code(Path(td))
            rc, out = self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--code", str(code), "--inst", "absent"])
        self.assertEqual(rc, 2)
        self.assertEqual(out, {"status": "NOT_FOUND", "id": "cpt-test-algo-a", "inst": "absent"})

    def test_get_content_empty_inst_is_an_instruction_asked_for_not_an_omitted_option(self):
        """`--inst ""` and `--inst inst-` both ask for the empty instruction, which no
        marker has. A truthiness check once served the first block as FOUND for the first
        spelling while the second was NOT_FOUND."""
        with TemporaryDirectory() as td:
            code = self._marked_code(Path(td))
            answers = [
                self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--code", str(code), "--inst", inst])
                for inst in ("", "inst-")
            ]
        self.assertEqual(answers, [
            (2, {"status": "NOT_FOUND", "id": "cpt-test-algo-a", "inst": ""}),
            (2, {"status": "NOT_FOUND", "id": "cpt-test-algo-a", "inst": "inst-"}),
        ])

    def test_get_content_inst_accepts_the_prefixed_spelling(self):
        """The option's help once showed `inst-validate-input`, a spelling that could never
        match because the parser stores `validate-input`. Both spellings now select it."""
        with TemporaryDirectory() as td:
            code = self._marked_code(Path(td))
            rc, prefixed = self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--code", str(code), "--inst", "inst-two"])
            _, bare = self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--code", str(code), "--inst", "two"])
        self.assertEqual(rc, 0)
        self.assertEqual(prefixed["inst"], "inst-two")  # echoed as given
        self.assertEqual(prefixed["text"].strip(), "two = 2")
        self.assertEqual(prefixed["text"], bare["text"])

    def test_get_content_inst_is_looked_up_among_this_ids_blocks_only(self):
        """Instruction names repeat across IDs in one file — `document.py` has an
        `inst-read-file` in two algorithms. The lookup used to take the first block with
        that name, whichever ID it belonged to."""
        with TemporaryDirectory() as td:
            code = Path(td) / "two_algos.py"
            code.write_text(
                "# @cpt-begin:cpt-test-algo-first:p1:inst-read\n"
                "first_read = 1\n"
                "# @cpt-end:cpt-test-algo-first:p1:inst-read\n"
                "# @cpt-begin:cpt-test-algo-second:p1:inst-read\n"
                "second_read = 2\n"
                "# @cpt-end:cpt-test-algo-second:p1:inst-read\n",
                encoding="utf-8",
            )
            rc, out = self._run(cmd_get_content, ["--id", "cpt-test-algo-second", "--code", str(code), "--inst", "read"])
            rc_other, other = self._run(cmd_get_content, ["--id", "cpt-test-algo-third", "--code", str(code), "--inst", "read"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["text"].strip(), "second_read = 2")
        self.assertEqual((rc_other, other["status"]), (2, "NOT_FOUND"))  # the name exists, but not for this ID

    def test_get_content_code_wins_when_both_paths_are_given(self):
        """The id is defined in the registered artifact and absent from the code file;
        the answer comes from the code file."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            code = self._marked_code(root)
            rc, out = self._run(cmd_get_content, [
                "--id", "cpt-test-item-1",
                "--artifact", str(root / "architecture" / "PRD.md"),
                "--code", str(code),
            ])
        self.assertEqual(rc, 2)
        self.assertEqual(out, {"status": "NOT_FOUND", "id": "cpt-test-item-1", "inst": None})

    def test_get_content_inst_is_ignored_with_artifact(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            rc, out = self._run(cmd_get_content, [
                "--id", "cpt-test-item-1",
                "--artifact", str(root / "architecture" / "PRD.md"),
                "--inst", "inst-anything",
            ])
        self.assertEqual((rc, out["status"]), (0, "FOUND"))  # the lookup still succeeds
        self.assertNotIn("inst", out)  # the artifact branch never saw the flag

    def test_get_content_neither_path_is_an_error(self):
        rc, out = self._run(cmd_get_content, ["--id", "cpt-test-item-1"])
        self.assertEqual(rc, 1)
        self.assertEqual(out["status"], "ERROR")

    def test_get_content_unparsable_code_file_exits_1(self):
        with TemporaryDirectory() as td:
            code = Path(td) / "broken.py"
            code.write_text("# @cpt-begin:cpt-test-algo-a:p1:inst-one\nx = 1\n", encoding="utf-8")
            rc, out = self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--code", str(code)])
        self.assertEqual(rc, 1)
        self.assertEqual(out["status"], "ERROR")
        self.assertIn("marker-begin-no-end", out["message"])

    def test_get_content_code_needs_no_project_but_artifact_does(self):
        """Documented asymmetry: `--code` reads the file directly, `--artifact` resolves
        a registered artifact. Run from a directory that is not a Studio project."""
        with TemporaryDirectory() as td:
            outside = Path(td)
            code = self._marked_code(outside)
            doc = outside / "doc.md"
            doc.write_text("# A\n\n**ID**: `cpt-test-algo-a`\n\nbody\n", encoding="utf-8")
            cwd = os.getcwd()
            try:
                os.chdir(outside)
                rc_code, from_code = self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--code", str(code)])
                rc_miss, missing = self._run(cmd_get_content, ["--id", "cpt-test-algo-absent", "--code", str(code)])
                rc_art, from_artifact = self._run(cmd_get_content, ["--id", "cpt-test-algo-a", "--artifact", str(doc)])
            finally:
                os.chdir(cwd)
        self.assertEqual((rc_code, from_code["status"]), (0, "FOUND"))
        self.assertEqual(from_code["text"], "    one = 1")  # the exact block, not just a status
        # No project, and an ID the file does not mark: not-found from the file alone,
        # with no fallback to any artifact index.
        self.assertEqual((rc_miss, missing), (2, {"status": "NOT_FOUND", "id": "cpt-test-algo-absent", "inst": None}))
        self.assertEqual((rc_art, from_artifact["status"]), (1, "ERROR"))
        self.assertIn("not initialized", from_artifact["message"])

    # ---- list-ids, --include-code ---------------------------------------------
    def _list_ids_with_code_scan(self, argv, scan_result):
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            argv = [a.replace("<PRD>", str(root / "architecture" / "PRD.md")) for a in argv]
            with patch("studio.commands.list_ids.scan_registered_codebase_references",
                       return_value=scan_result) as scan:
                rc, out = self._run(cmd_list_ids, argv)
        return rc, out, scan

    def test_list_ids_source_is_an_error_outside_a_workspace_unless_artifact_is_given(self):
        """Documented: `--source` needs workspace mode — and `--artifact` wins, so with
        both the source is never consulted and the would-be error does not happen."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            _with_context(root)
            rc, alone = self._run(cmd_list_ids, ["--source", "anything"])
            rc_both, both = self._run(cmd_list_ids, [
                "--artifact", str(root / "architecture" / "PRD.md"), "--source", "anything"])
        self.assertEqual((rc, alone["status"]), (1, "ERROR"))
        self.assertIn("workspace", alone["message"])
        self.assertEqual(rc_both, 0)
        self.assertEqual((both["artifacts_scanned"], both["count"]), (1, 1))

    def test_list_ids_code_records_and_the_dedupe_that_hides_them(self):
        """Documented: code hits are `type: code_reference` with `marker_type`; without
        `--all` one survives only for an ID no artifact mentions."""
        code_hits = [
            {"id": "cpt-test-item-1", "kind": "item", "type": "code_reference", "artifact_type": "CODE",
             "line": 3, "artifact": "/repo/src/a.py", "marker_type": "block", "phase": 1, "inst": "one"},
            {"id": "cpt-test-only-in-code", "kind": "algo", "type": "code_reference", "artifact_type": "CODE",
             "line": 1, "artifact": "/repo/src/b.py", "marker_type": "scope", "phase": 1},
        ]
        rc, deduped, _ = self._list_ids_with_code_scan(["--include-code"], (code_hits, 2, 0))
        rc_all, everything, _ = self._list_ids_with_code_scan(["--include-code", "--all"], (code_hits, 2, 0))
        self.assertEqual((rc, rc_all), (0, 0))
        by_id = {h["id"]: h for h in deduped["ids"]}
        self.assertEqual(by_id["cpt-test-item-1"]["type"], "definition")  # the artifact's definition wins
        self.assertEqual(by_id["cpt-test-only-in-code"]["type"], "code_reference")
        self.assertEqual(by_id["cpt-test-only-in-code"]["marker_type"], "scope")
        # `--all`: the exact occurrence set — the artifact's definition as well as both
        # code records — not just a count of one type, which would miss a dropped record.
        self.assertEqual(
            sorted((h["id"], h["type"], h["artifact_type"]) for h in everything["ids"]),
            [("cpt-test-item-1", "code_reference", "CODE"),
             ("cpt-test-item-1", "definition", "PRD"),
             ("cpt-test-only-in-code", "code_reference", "CODE")],
        )

    def test_list_ids_an_artifact_reference_outranks_a_code_record(self):
        """The order-dependent case the definition-wins rule does not cover: an ID an
        artifact only *references* and code also marks. Artifacts are read first, so
        without `--all` the artifact's reference is the entry, not the code record."""
        with TemporaryDirectory() as td:
            root = Path(td)
            _setup_project(root)
            prd = root / "architecture" / "PRD.md"
            prd.write_text(prd.read_text(encoding="utf-8") + "\n`cpt-test-item-refonly`\n", encoding="utf-8")
            _with_context(root)
            code_hit = {"id": "cpt-test-item-refonly", "kind": "item", "type": "code_reference",
                        "artifact_type": "CODE", "line": 1, "artifact": "/repo/src/c.py", "marker_type": "scope"}
            with patch("studio.commands.list_ids.scan_registered_codebase_references",
                       return_value=([code_hit], 1, 0)):
                rc, out = self._run(cmd_list_ids, ["--include-code", "--pattern", "refonly"])
        self.assertEqual(rc, 0)
        self.assertEqual([(h["id"], h["type"]) for h in out["ids"]], [("cpt-test-item-refonly", "reference")])

    @staticmethod
    def _run_main(root: Path, argv):
        """Through the real entry point, which routes warnings to stderr:
        (exit code, parsed JSON, stderr text)."""
        cwd, json_was = os.getcwd(), is_json_mode()
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            os.chdir(root)
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = main(["--json", *argv])
        finally:
            set_json_mode(json_was)
            os.chdir(cwd)
        return rc, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_both_id_forms_the_positional_wins_and_only_stderr_says_so(self):
        """For both commands: given both forms the positional wins, and the warning goes to
        stderr, never into the JSON. An empty positional falls through to `--id`."""
        warning = "Both positional ID and --id given; using positional"
        for command in ("where-used", "where-defined"):
            with self.subTest(command=command), TemporaryDirectory() as td:
                root = Path(td)
                _setup_project(root)
                rc, out, stderr = self._run_main(root, [command, "cpt-test-item-1", "--id", "cpt-test-item-nowhere"])
                rc_empty, fallthrough, stderr_empty = self._run_main(root, [command, "", "--id", "cpt-test-item-1"])
                self.assertEqual((rc, out["id"]), (0, "cpt-test-item-1"))
                self.assertIn(warning, stderr.splitlines())
                self.assertNotIn("positional", json.dumps(out))
                self.assertEqual((rc_empty, fallthrough["id"]), (0, "cpt-test-item-1"))
                self.assertNotIn(warning, stderr_empty)

    def test_get_content_not_found_is_scoped_to_the_file_given(self):
        """`--artifact`: defined elsewhere is still not found here. `--code`: artifact
        definitions are never consulted, so a code-only ID is found."""
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            root = Path(td)
            adapter = _setup_project(root)
            other = root / "architecture" / "OTHER.md"
            other.write_text("# Other\n\nno definitions here\n", encoding="utf-8")
            # Register OTHER.md for real, so the lookup goes through the registry rather
            # than a patched resolver.
            registry = adapter / "config" / "artifacts.toml"
            data = toml_utils.load(registry)
            data["systems"][0]["artifacts"].append({"path": "architecture/OTHER.md", "kind": "PRD"})
            toml_utils.dump(data, registry)
            _with_context(root)
            only_in_code = root / "only.py"
            only_in_code.write_text(
                "# @cpt-algo:cpt-test-only-in-code:p1\n"
                "def f():\n"
                "    # @cpt-begin:cpt-test-only-in-code:p1:inst-one\n"
                "    one = 1\n"
                "    # @cpt-end:cpt-test-only-in-code:p1:inst-one\n",
                encoding="utf-8",
            )
            rc_art, from_other = self._run(cmd_get_content, ["--id", "cpt-test-item-1", "--artifact", str(other)])
            rc_code, from_code = self._run(cmd_get_content, ["--id", "cpt-test-only-in-code", "--code", str(only_in_code)])
        # Defined in PRD.md, not in OTHER.md: the exact documented payload.
        self.assertEqual((rc_art, from_other), (2, {"status": "NOT_FOUND", "id": "cpt-test-item-1"}))
        self.assertEqual((rc_code, from_code["status"]), (0, "FOUND"))  # in no artifact at all

    def test_list_ids_code_files_skipped_appears_only_when_nonzero(self):
        rc, clean, _ = self._list_ids_with_code_scan(["--include-code"], ([], 3, 0))
        rc2, skipped, _ = self._list_ids_with_code_scan(["--include-code"], ([], 3, 2))
        self.assertEqual((rc, rc2), (0, 0))
        self.assertEqual(clean["code_files_scanned"], 3)
        self.assertNotIn("code_files_skipped", clean)
        self.assertEqual(skipped["code_files_skipped"], 2)

    def test_list_ids_include_code_is_a_no_op_with_artifact_but_still_reports_zero(self):
        """Pins a wart, not a wish: the scan is skipped, yet `code_files_scanned` is
        emitted as 0 — unlike `where-used`, which omits both counters. Documented as
        such; if list-ids is aligned with where-used, this test and the spec change
        together."""
        rc, out, scan = self._list_ids_with_code_scan(["--artifact", "<PRD>", "--include-code"], ([], 3, 2))
        self.assertEqual(rc, 0)
        scan.assert_not_called()
        self.assertEqual(out["code_files_scanned"], 0)   # not 3: the scan never ran
        self.assertNotIn("code_files_skipped", out)


if __name__ == "__main__":
    unittest.main()
