"""Tests for the advisory semantic-coverage pass (utils.semantic_coverage) and its wiring into
``spec-coverage``.

The headline invariant: attaching a semantic section — even one carrying a ``wrong`` verdict — never
changes the coverage status or exit code. The rest pin pairing construction, the no-judge default,
honest serialisation, and scope consumption.
"""
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils import semantic_coverage as sc
from studio.utils import eval_semantic as sem
from studio.commands.spec_coverage import cmd_spec_coverage
from studio.utils.artifacts_meta import ArtifactsMeta, CodebaseEntry, Kit, SystemNode

_ALGO = "cpt-studio-algo-fixture"
_REQ = "validate the user email address format and reject a malformed address before saving the record"


def _marked(tmp_path: Path, name: str = "mod.py") -> Path:
    """A file with two blocks of one algo: a strong block whose identifiers echo the requirement, and
    a weak block (compute_tax) with no overlap."""
    p = tmp_path / name
    p.write_text(
        f"# @cpt-begin:{_ALGO}:p1:inst-strong\n"
        "def validate_email_address_and_reject_malformed(record):\n"
        "    return save_record(record)\n"
        f"# @cpt-end:{_ALGO}:p1:inst-strong\n"
        f"# @cpt-begin:{_ALGO}:p1:inst-weak\n"
        "def compute_tax(amount):\n"
        "    return amount * lookup_rate(amount)\n"
        f"# @cpt-end:{_ALGO}:p1:inst-weak\n",
        encoding="utf-8")
    return p


# --- pairing construction --------------------------------------------------

def test_pairings_one_per_block_with_fields(tmp_path: Path) -> None:
    pairings = sc._pairings_for_files([_marked(tmp_path)], {})
    assert {p.block_id for p in pairings} == {f"{_ALGO}:strong", f"{_ALGO}:weak"}
    weak = next(p for p in pairings if p.block_id.endswith(":weak"))
    assert weak.inst == "weak"
    assert weak.path.endswith("mod.py")
    assert weak.start_line > 0
    assert "compute_tax" in weak.code
    assert weak.requirement is None            # empty definitions map → unresolved → unjudgeable


def test_pairings_resolve_requirement_from_definitions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sem, "resolve_requirement", lambda doc, bid: _REQ if bid == _ALGO else None)
    pairings = sc._pairings_for_files([_marked(tmp_path)], {_ALGO: tmp_path / "doc.md"})
    assert all(p.requirement == _REQ for p in pairings)


# --- run_semantic_pass -----------------------------------------------------

def test_no_judge_default_reports_unjudgeable_not_zero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sc, "_definition_map", lambda ctx: {})   # no requirements resolve
    section = sc.run_semantic_pass(None, [_marked(tmp_path)], {}, judge_fn=None)
    assert section["advisory"] is True
    assert section["assessed"] == 0
    assert section["findings"] == []
    assert len(section["unjudgeable"]) == 2                      # both blocks: no requirement


def test_serialises_a_wrong_finding_with_the_full_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sc, "_definition_map", lambda ctx: {_ALGO: tmp_path / "doc.md"})
    monkeypatch.setattr(sem, "resolve_requirement", lambda doc, bid: _REQ)
    section = sc.run_semantic_pass(None, [_marked(tmp_path)], {},
                                   judge_fn=lambda req: sem.SemanticReply(sem.SEM_WRONG, "r", ""))
    assert section["advisory"] is True
    assert sem.SEM_WRONG in [f["verdict"] for f in section["findings"]]
    assert section["presumed_covered"] >= 1                     # the identifier-echoing block
    assert set(section["findings"][0]) == {
        "block_id", "path", "start_line", "verdict", "rationale", "evidence_ok", "forced"}


def test_excluded_scope_is_honoured(tmp_path: Path, monkeypatch) -> None:
    code = _marked(tmp_path)
    monkeypatch.setattr(sc, "_definition_map", lambda ctx: {})
    section = sc.run_semantic_pass(None, [code], {"excluded": [{"path": str(code)}]}, judge_fn=None)
    assert section["skipped_excluded"] == 2                     # both blocks in the excluded file
    assert section["unjudgeable"] == []


def test_summary_line_renders_counts_and_is_labelled_advisory() -> None:
    line = sc.summary_line({"assessed": 3, "presumed_covered": 5, "unjudgeable": [{}, {}],
                            "findings": [{"verdict": "wrong"}, {"verdict": "partial"},
                                         {"verdict": "covered"}]})
    assert "advisory" in line
    assert "3 judged" in line
    assert "5 presumed-covered" in line
    assert "2 unjudgeable" in line
    assert "2 weak/wrong" in line


# --- command wiring: the headline advisory-cannot-gate invariant ----------

def _ctx(tmp_path: Path, code_path: Path) -> MagicMock:
    meta = ArtifactsMeta(
        version=1, project_root=".", kits={"test": Kit("test", "CFS", "kits/test")},
        systems=[SystemNode(name="sys1", slug="sys1", kit="test", artifacts=[],
                            codebase=[CodebaseEntry(path=code_path.name, extensions=[".py"])],
                            children=[])])
    ctx = MagicMock()
    ctx.meta = meta
    ctx.project_root = tmp_path
    return ctx


def _run(ctx: MagicMock, argv: list) -> tuple:
    from studio.utils.ui import set_json_mode
    set_json_mode(True)
    with patch("studio.utils.context.get_context", return_value=ctx):
        with patch("sys.stdout", new_callable=StringIO) as out:
            code = cmd_spec_coverage(argv)
    return code, json.loads(out.getvalue())


def test_semantic_section_attaches_and_a_wrong_verdict_never_gates(tmp_path: Path) -> None:
    code_path = _marked(tmp_path)
    ctx = _ctx(tmp_path, code_path)
    wrong_section = {"advisory": True, "assessed": 1, "presumed_covered": 0, "unjudgeable": [],
                     "findings": [{"block_id": "x", "path": str(code_path), "start_line": 1,
                                   "verdict": "wrong", "rationale": "r", "evidence_ok": False,
                                   "forced": False}],
                     "skipped_excluded": 0, "schema_version": 1}
    with patch("studio.utils.semantic_coverage.run_semantic_pass", return_value=wrong_section):
        code_sem, rep_sem = _run(ctx, ["--semantic"])
    code_plain, rep_plain = _run(ctx, [])
    # the section is attached and advisory, carrying the wrong verdict
    assert rep_sem["semantic"]["advisory"] is True
    assert rep_sem["semantic"]["findings"][0]["verdict"] == "wrong"
    # …yet status and exit are byte-for-byte what they were without --semantic
    assert code_sem == code_plain
    assert rep_sem.get("status") == rep_plain.get("status")
    assert "semantic" not in rep_plain


def test_definition_map_built_from_artifact_definitions(tmp_path: Path, monkeypatch) -> None:
    # _definition_map scans the registered artifacts for cpt DEFINITION ids and maps id -> doc path.
    doc = tmp_path / "feature.md"
    doc.write_text("### My Algo\n\n- [x] `p1` - **ID**: `cpt-studio-algo-fixture`\n\nRequirement text.\n",
                   encoding="utf-8")
    monkeypatch.setattr(sc, "collect_artifacts_to_scan", lambda ctx: ([(doc, "feature")], {}))
    mapping = sc._definition_map(MagicMock())
    assert mapping.get(_ALGO) == doc


def test_pairings_skip_a_file_that_does_not_parse(tmp_path: Path) -> None:
    # A file with an unbalanced marker fails CodeFile.from_path (None) and is skipped, not a crash.
    bad = tmp_path / "bad.py"
    bad.write_text(f"# @cpt-begin:{_ALGO}:p1:inst-orphan\ndef f():\n    return 1\n", encoding="utf-8")  # no @cpt-end
    good = _marked(tmp_path)
    pairings = sc._pairings_for_files([bad, good], {})
    assert {p.path for p in pairings} == {str(good)}    # only the good file contributed blocks


def test_semantic_summary_line_rendered_in_human_mode(tmp_path: Path, capsys) -> None:
    # In non-JSON mode the advisory summary line is printed; restore json mode for sibling tests.
    from studio.utils.ui import set_json_mode
    code_path = _marked(tmp_path)
    ctx = _ctx(tmp_path, code_path)
    section = {"advisory": True, "assessed": 0, "presumed_covered": 1,
               "unjudgeable": [{"block_id": "x"}], "findings": [], "skipped_excluded": 0,
               "schema_version": 1}
    set_json_mode(False)
    try:
        with patch("studio.utils.context.get_context", return_value=ctx):
            with patch("studio.utils.semantic_coverage.run_semantic_pass", return_value=section):
                cmd_spec_coverage(["--semantic"])
        out = capsys.readouterr().out
    finally:
        set_json_mode(True)
    assert "semantic (advisory, never gates)" in out


def test_semantic_pass_that_raises_never_gates(tmp_path: Path) -> None:
    # Fail-safe: an *exception* in the advisory pass (not just a wrong verdict) must leave the
    # structural status/exit byte-for-byte unchanged — it is swallowed and recorded as an advisory
    # error. Without exception isolation the crash would flip a computed PASS/exit-0 into a failure.
    code_path = _marked(tmp_path)
    ctx = _ctx(tmp_path, code_path)
    with patch("studio.utils.semantic_coverage.run_semantic_pass",
               side_effect=RuntimeError("boom")):
        code_raise, rep_raise = _run(ctx, ["--semantic"])
    code_plain, rep_plain = _run(ctx, [])
    assert code_raise == code_plain
    assert rep_raise.get("status") == rep_plain.get("status")
    assert rep_raise["semantic"] == {"advisory": True, "error": "boom"}


def test_summary_line_reports_an_advisory_error() -> None:
    # The advisory-error section (attached when the pass raised) renders as an honest one-liner,
    # not as "0 judged" which would read as a clean run.
    line = sc.summary_line({"advisory": True, "error": "boom"})
    assert "advisory" in line
    assert "errored" in line
    assert "boom" in line


def test_pairings_paths_are_project_relative(tmp_path: Path) -> None:
    # With a project_root, pairing paths are emitted project-relative POSIX so they match the
    # coverage report's relative scope arrays (excluded / whole_file_claims) rather than being an
    # unmatchable absolute path.
    code = _marked(tmp_path)
    pairings = sc._pairings_for_files([code], {}, project_root=tmp_path)
    assert pairings
    assert all(p.path == "mod.py" for p in pairings)


def test_pairings_path_falls_back_when_outside_project_root(tmp_path: Path) -> None:
    # A file that is not under project_root cannot be made relative — fall back to its own path
    # rather than crashing, so the pass degrades instead of failing.
    code = _marked(tmp_path)
    other_root = tmp_path / "elsewhere"
    other_root.mkdir()
    pairings = sc._pairings_for_files([code], {}, project_root=other_root)
    assert pairings
    # relative (never absolute — no local path leaks into the report or judge prompt), ends at the file
    assert all(not Path(p.path).is_absolute() for p in pairings)
    assert all(p.path.endswith("mod.py") for p in pairings)


def test_pairings_survive_a_relpath_failure(tmp_path: Path, monkeypatch) -> None:
    # If os.path.relpath itself raises (Windows cross-drive), the file falls back to its bare name
    # rather than the exception sinking the whole pairing loop for every file.
    code = _marked(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()

    def _boom(*_a, **_k):
        raise ValueError("cross-drive")

    monkeypatch.setattr("os.path.relpath", _boom)
    pairings = sc._pairings_for_files([code], {}, project_root=other)
    assert pairings
    assert all(p.path == "mod.py" for p in pairings)


def test_semantic_never_gates_a_structurally_failing_run(tmp_path: Path) -> None:
    # The never-gates invariant on the FAIL / exit-2 side: --semantic must leave a run that the
    # structural gate already fails byte-for-byte unchanged (previously only proven for exit-0).
    p = tmp_path / "mod.py"
    p.write_text(
        f"# @cpt-begin:{_ALGO}:p1:inst-strong\n"
        "def validate_email_address_and_reject_malformed(record):\n"
        "    return save_record(record)\n"
        f"# @cpt-end:{_ALGO}:p1:inst-strong\n"
        "def uncovered():\n"          # code outside any marker → drags coverage below 100%
        "    return 1\n",
        encoding="utf-8")
    ctx = _ctx(tmp_path, p)
    code_sem, rep_sem = _run(ctx, ["--min-coverage", "100", "--semantic"])
    code_plain, rep_plain = _run(ctx, ["--min-coverage", "100"])
    assert code_sem == code_plain == 2
    assert rep_sem.get("status") == rep_plain.get("status") == "FAIL"
    assert rep_sem["semantic"]["advisory"] is True
    assert "semantic" not in rep_plain


def test_pairings_dedup_duplicate_file_registrations(tmp_path: Path) -> None:
    # A file registered more than once must not double-count its marked blocks.
    code = _marked(tmp_path)
    once = sc._pairings_for_files([code], {})
    twice = sc._pairings_for_files([code, code], {})
    assert len(twice) == len(once)


def test_definition_map_warns_on_duplicate_cpt_definition(tmp_path: Path, monkeypatch, caplog) -> None:
    # Two artifacts defining the same cpt id: the first wins, and the collision is logged (not silent).
    doc1 = tmp_path / "a.md"
    doc2 = tmp_path / "b.md"
    doc1.write_text("x", encoding="utf-8")
    doc2.write_text("x", encoding="utf-8")
    monkeypatch.setattr(sc, "collect_artifacts_to_scan", lambda ctx: ([(doc1, "f"), (doc2, "f")], {}))
    monkeypatch.setattr(sc, "scan_cpt_ids", lambda p: [{"type": "definition", "id": _ALGO}])
    with caplog.at_level("WARNING"):
        mapping = sc._definition_map(MagicMock())
    assert mapping[_ALGO] == doc1
    assert any("defined in both" in r.message for r in caplog.records)


def test_semantic_pass_runs_end_to_end_unmocked(tmp_path: Path) -> None:
    # End-to-end with run_semantic_pass NOT mocked: real _definition_map + _pairings_for_files +
    # assess over a real ctx. With no judge wired, blocks are unjudgeable; the section is real and
    # the run never degrades to the error shape.
    code_path = _marked(tmp_path)
    ctx = _ctx(tmp_path, code_path)
    _code, rep = _run(ctx, ["--semantic"])
    sem = rep["semantic"]
    assert sem["advisory"] is True
    assert "error" not in sem
    assert sem["schema_version"] >= 1
    assert sem["assessed"] + sem["presumed_covered"] + len(sem["unjudgeable"]) >= 1


def test_semantic_section_attaches_on_empty_scope(tmp_path: Path) -> None:
    # --semantic must still attach a section when the codebase resolves to no files, so the flag's
    # presence is consistent (the early empty-scope return used to skip it).
    meta = ArtifactsMeta(
        version=1, project_root=".", kits={"test": Kit("test", "CFS", "kits/test")},
        systems=[SystemNode(name="sys1", slug="sys1", kit="test", artifacts=[],
                            codebase=[], children=[])])
    ctx = MagicMock()
    ctx.meta = meta
    ctx.project_root = tmp_path
    _code, rep = _run(ctx, ["--semantic"])
    assert "semantic" in rep
    assert rep["semantic"]["advisory"] is True


def test_human_error_section_renders_without_summary_line(tmp_path: Path, capsys) -> None:
    # When the semantic section is an advisory error (e.g. an import failure), human mode renders it
    # WITHOUT importing/calling summary_line — which could re-raise after status/exit are set.
    from studio.utils.ui import set_json_mode
    code_path = _marked(tmp_path)
    ctx = _ctx(tmp_path, code_path)
    err_section = {"advisory": True, "error": "boom-import"}
    set_json_mode(False)
    try:
        with patch("studio.utils.context.get_context", return_value=ctx):
            with patch("studio.utils.semantic_coverage.run_semantic_pass", return_value=err_section):
                with patch("studio.utils.semantic_coverage.summary_line",
                           side_effect=AssertionError("summary_line must not be called for an error section")):
                    cmd_spec_coverage(["--semantic"])
        out = capsys.readouterr().out
    finally:
        set_json_mode(True)
    assert "errored" in out
    assert "boom-import" in out
