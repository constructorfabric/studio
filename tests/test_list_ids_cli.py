"""Unit coverage for `list-ids` hit collection and dedupe (OLE-41)."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.list_ids import _apply_hit_filters, _collect_artifact_hits, _dedupe_hits


def _default_args(**overrides: object) -> argparse.Namespace:
    base = {"kind": None, "pattern": None, "regex": False, "all": False}
    base.update(overrides)
    return argparse.Namespace(**base)


def test_list_ids_default_prefers_definition_over_earlier_reference() -> None:
    """A reference mentioned before its formal definition must not shadow it."""
    with TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "doc.md"
        artifact.write_text(
            "See `cpt-example-thing-x` for details.\n"
            "\n"
            "**ID**: `cpt-example-thing-x`\n",
            encoding="utf-8",
        )

        hits = _collect_artifact_hits([(artifact, "FEATURE")], set(), set())
        assert [h["type"] for h in hits] == ["reference", "definition"]

        default_hits = _apply_hit_filters(hits, _default_args())
        assert len(default_hits) == 1
        assert default_hits[0]["type"] == "definition"
        assert default_hits[0]["line"] == 3

        all_hits = _apply_hit_filters(hits, _default_args(all=True))
        assert [h["type"] for h in all_hits] == ["reference", "definition"]


def test_list_ids_default_keeps_reference_when_no_definition_exists() -> None:
    """IDs with no definition anywhere keep their first-seen hit (unchanged behavior)."""
    with TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "doc.md"
        artifact.write_text(
            "See `cpt-example-thing-y` for details.\n"
            "`cpt-example-thing-y`\n",
            encoding="utf-8",
        )

        hits = _collect_artifact_hits([(artifact, "FEATURE")], set(), set())
        default_hits = _apply_hit_filters(hits, _default_args())

        assert len(default_hits) == 1
        assert default_hits[0]["type"] == "reference"
        assert default_hits[0]["line"] == 1


def test_dedupe_hits_prefers_first_definition_when_multiple_exist() -> None:
    hits = [
        {"id": "cpt-x", "type": "reference", "line": 1},
        {"id": "cpt-x", "type": "definition", "line": 5, "artifact": "a.md"},
        {"id": "cpt-x", "type": "definition", "line": 9, "artifact": "b.md"},
    ]
    deduped = _dedupe_hits(hits)
    assert len(deduped) == 1
    assert deduped[0]["type"] == "definition"
    assert deduped[0]["line"] == 5


def test_dedupe_hits_surfaces_conflicting_definitions_instead_of_dropping_them(caplog) -> None:
    """A second definition-typed hit for the same ID must be surfaced, not silently lost."""
    import logging

    hits = [
        {"id": "cpt-x", "type": "definition", "line": 5, "artifact": "a.md"},
        {"id": "cpt-x", "type": "definition", "line": 9, "artifact": "b.md"},
    ]
    with caplog.at_level(logging.WARNING, logger="studio.commands.list_ids"):
        deduped = _dedupe_hits(hits)

    assert len(deduped) == 1
    assert deduped[0]["line"] == 5
    assert deduped[0]["duplicate_definitions"] == [{"artifact": "b.md", "line": 9}]
    assert any("duplicate definitions for cpt-x" in msg for msg in caplog.messages)


def test_dedupe_hits_no_conflict_field_when_single_definition() -> None:
    hits = [{"id": "cpt-x", "type": "definition", "line": 5, "artifact": "a.md"}]
    deduped = _dedupe_hits(hits)
    assert "duplicate_definitions" not in deduped[0]


def test_list_ids_default_surfaces_duplicate_definitions_end_to_end() -> None:
    """Two artifacts formally defining the same ID must be surfaced, not silently collapsed.

    Drives the real CLI entry point (main()) rather than calling _dedupe_hits
    directly, so a regression in the cmd_list_ids/_dedupe_hits wiring itself
    would be caught.
    """
    from studio.cli import main
    from studio.utils import toml_utils

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").mkdir()
        (root / "AGENTS.md").write_text(
            '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n',
            encoding="utf-8",
        )
        adapter = root / "adapter"
        (adapter / "config").mkdir(parents=True)
        (adapter / "config" / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")

        docs = root / "docs"
        docs.mkdir()
        (docs / "a.md").write_text("- [x] `p1` - **ID**: `cpt-test-req-1`\n", encoding="utf-8")
        (docs / "b.md").write_text("- [x] `p1` - **ID**: `cpt-test-req-1`\n", encoding="utf-8")

        toml_utils.dump(
            {
                "version": "1.0",
                "project_root": "..",
                "kits": {},
                "systems": [{
                    "name": "Test", "slug": "test",
                    "artifacts": [
                        {"path": "docs/a.md", "kind": "req"},
                        {"path": "docs/b.md", "kind": "req"},
                    ],
                }],
            },
            adapter / "config" / "artifacts.toml",
        )

        cwd = os.getcwd()
        try:
            os.chdir(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["list-ids"])
            assert rc == 0
            out = json.loads(buf.getvalue())
            assert out["count"] == 1
            hit = out["ids"][0]
            dup = hit["duplicate_definitions"]
            assert len(dup) == 1
            assert Path(dup[0]["artifact"]).name == "b.md"
            assert dup[0]["line"] == 1
        finally:
            os.chdir(cwd)


def _duplicate_definition_project(
    root: Path, *, bound_to_kit: bool, same_file: bool = False, split: bool = False,
) -> None:
    """Two registered artifacts that both define `cpt-test-item-1` — or, with *same_file*,
    `a.md` defining it twice (lines 1 and 3) and `b.md` defining something else. With
    *split*, `b.md` belongs to a second system that has no kit."""
    from studio.utils import toml_utils
    from _test_helpers import write_constraints_toml

    (root / ".git").mkdir()
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n',
        encoding="utf-8",
    )
    config = root / "adapter" / "config"
    config.mkdir(parents=True)
    (config / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir()
    definition = "- [x] `p1` - **ID**: `cpt-test-item-1`\n"
    if same_file:
        (docs / "a.md").write_text(definition + "\n" + definition, encoding="utf-8")
        (docs / "b.md").write_text("- [x] `p1` - **ID**: `cpt-test-item-2`\n", encoding="utf-8")
    else:
        for name in ("a.md", "b.md"):
            (docs / name).write_text(definition, encoding="utf-8")

    system: dict = {
        "name": "Test", "slug": "test",
        "artifacts": [{"path": "docs/a.md", "kind": "PRD"}, {"path": "docs/b.md", "kind": "PRD"}],
    }
    systems = [system]
    if split:
        system["artifacts"] = system["artifacts"][:1]
        systems.append({"name": "Loose", "slug": "loose", "artifacts": [{"path": "docs/b.md", "kind": "PRD"}]})
    kits: dict = {}
    if bound_to_kit:
        kits = {"sdlc": {"format": "CFS", "path": "kits/sdlc"}}
        system["kit"] = "sdlc"
        template_dir = root / "kits" / "sdlc" / "artifacts" / "PRD"
        template_dir.mkdir(parents=True)
        (template_dir / "template.md").write_text(
            "---\ncypilot-template:\n  version:\n    major: 1\n    minor: 0\n  kind: PRD\n---\n"
            "- [ ] `p1` - **ID**: `cpt-{system}-item-{slug}`\n",
            encoding="utf-8",
        )
        write_constraints_toml(root / "kits" / "sdlc", {
            "PRD": {"identifiers": {"item": {"template": "cpt-{system}-item-{slug}"}}},
        })
    toml_utils.dump(
        {"version": "1.0", "project_root": "..", "kits": kits, "systems": systems},
        config / "artifacts.toml",
    )


def _run_main(root: Path, argv: list) -> tuple:
    """Run the CLI in *root*: (exit code, parsed stdout, stderr lines)."""
    from studio.cli import main
    from studio.utils.ui import is_json_mode, set_json_mode

    cwd, saved_json_mode = os.getcwd(), is_json_mode()
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        os.chdir(root)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = main(argv)
    finally:
        set_json_mode(saved_json_mode)
        os.chdir(cwd)
    return rc, json.loads(stdout.getvalue()), stderr.getvalue().splitlines()


def test_duplicate_definition_contract_on_one_fixture() -> None:
    """The documented contract, both commands on one fixture: `list-ids` keeps the first
    definition, lists the other on the entry, and names both places on stderr; `validate`
    fails with `duplicate-definition` at each place, naming the other."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve()
        _duplicate_definition_project(root, bound_to_kit=True)
        a, b = root / "docs" / "a.md", root / "docs" / "b.md"
        rc, listed, stderr = _run_main(root, ["list-ids"])
        rc_validate, report, _ = _run_main(root, ["--json", "validate"])

    assert rc == 0
    assert [(h["artifact"], h["duplicate_definitions"]) for h in listed["ids"]] == [
        (str(a), [{"artifact": str(b), "line": 1}]),
    ]
    assert f"duplicate definitions for cpt-test-item-1: kept {a}:1, also defined at {b}:1" in stderr
    assert (rc_validate, report["status"]) == (2, "FAIL")
    assert sorted((e["code"], e["location"], e["message"]) for e in report["errors"]) == [
        ("duplicate-definition", f"{a}:1", f"Duplicate definition of `cpt-test-item-1` — also defined in: {b}"),
        ("duplicate-definition", f"{b}:1", f"Duplicate definition of `cpt-test-item-1` — also defined in: {a}"),
    ]


@pytest.mark.parametrize(
    ("bound_to_kit", "same_file", "artifacts_validated"),
    [(False, False, 0), (True, True, 2)],
    ids=["kit-less-system", "same-file"],
)
def test_duplicate_definitions_validate_does_not_judge_are_still_listed(
    bound_to_kit: bool, same_file: bool, artifacts_validated: int,
) -> None:
    """The documented limits of the gate: `validate` checks only the artifacts of a system
    bound to an installed kit, and flags only definitions in different files. Either
    duplicate passes it; `list-ids` reads every registered artifact and still warns."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve()
        _duplicate_definition_project(root, bound_to_kit=bound_to_kit, same_file=same_file)
        _, listed, stderr = _run_main(root, ["list-ids"])
        rc_validate, report, _ = _run_main(root, ["--json", "validate"])

    assert "duplicate_definitions" in {h["id"]: h for h in listed["ids"]}["cpt-test-item-1"]
    assert any(line.startswith("duplicate definitions for cpt-test-item-1:") for line in stderr)
    assert (rc_validate, report["status"], report["error_count"], report["artifacts_validated"]) == (
        0, "PASS", 0, artifacts_validated,
    )


def test_duplicate_split_across_a_kit_boundary_fails_only_the_checked_side() -> None:
    """`validate` compares every registered artifact but reports only on the ones it
    checks. One definition in a kit-bound system and one in a kit-less system: the
    kit-bound artifact fails, naming the other; the kit-less one gets no finding."""
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve()
        _duplicate_definition_project(root, bound_to_kit=True, split=True)
        a, b = root / "docs" / "a.md", root / "docs" / "b.md"
        _, listed, _ = _run_main(root, ["list-ids"])
        rc_validate, report, _ = _run_main(root, ["--json", "validate"])

    assert listed["ids"][0]["duplicate_definitions"] == [{"artifact": str(b), "line": 1}]
    assert (rc_validate, report["status"]) == (2, "FAIL")
    assert [(e["code"], e["location"], e["message"]) for e in report["errors"]] == [
        ("duplicate-definition", f"{a}:1", f"Duplicate definition of `cpt-test-item-1` — also defined in: {b}"),
    ]


def test_list_ids_include_code_works_with_no_registered_artifacts() -> None:
    """A codebase-only project (no registered artifacts) must still return code hits."""
    from studio.cli import main
    from studio.utils import toml_utils

    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".git").mkdir()
        (root / "AGENTS.md").write_text(
            '<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "adapter"\n```\n',
            encoding="utf-8",
        )
        adapter = root / "adapter"
        (adapter / "config").mkdir(parents=True)
        (adapter / "config" / "AGENTS.md").write_text("# Test adapter\n", encoding="utf-8")

        src = root / "src"
        src.mkdir()
        (src / "impl.py").write_text(
            "# @cpt-begin:cpt-test-req-1:p1:inst-do-work\n"
            "print('working')\n"
            "# @cpt-end:cpt-test-req-1:p1:inst-do-work\n",
            encoding="utf-8",
        )

        toml_utils.dump(
            {
                "version": "1.0",
                "project_root": "..",
                "kits": {},
                "systems": [{
                    "name": "Test", "slug": "test",
                    "artifacts": [],
                    "codebase": [{"path": "src", "extensions": [".py"]}],
                }],
            },
            adapter / "config" / "artifacts.toml",
        )

        cwd = os.getcwd()
        try:
            os.chdir(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["list-ids", "--include-code"])
            assert rc == 0
            out = json.loads(buf.getvalue())
            code_hits = [h for h in out.get("ids", []) if h.get("type") == "code_reference"]
            assert len(code_hits) == 1
            assert code_hits[0]["id"] == "cpt-test-req-1"
        finally:
            os.chdir(cwd)
