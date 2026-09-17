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
    # A real ctx, so both sides of the scope comparison are project-relative -- which is
    # what production does: `_rel_path` builds the report's `excluded` paths against the
    # project root, and pairings are relativised against the same root. The test used to
    # pass `None` for ctx and an absolute path for the exclusion, and matched only
    # because `_relative_posix` handed back an absolute path in the no-root case. That
    # was the leak, so the pairing path is now the bare filename there and the two sides
    # no longer line up -- the coincidence this assertion rested on is gone.
    section = sc.run_semantic_pass(_ctx(tmp_path, code), [code],
                                   {"excluded": [{"path": code.name}]}, judge_fn=None)
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
    pairings = sc._pairings_for_files([bad, good], {}, tmp_path)
    assert {p.path for p in pairings} == {good.name}    # only the good file contributed blocks


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


def test_relative_posix_never_returns_an_absolute_path_without_a_root():
    """The docstring promises "never absolute"; the no-root branch used to break it.

    `run_semantic_pass` resolves the root with `getattr(ctx, "project_root", None)`, so a
    context that carries none arrives here as None. Returning `path.as_posix()` for that
    case put the full absolute path -- username and directory layout -- into the
    serialised report and the out-of-tree judge prompt.
    """
    got = sc._relative_posix(Path("/home/someone/work/proj/src/mod.py"), None)
    assert not got.startswith("/")
    assert "someone" not in got
    assert got == "mod.py"


def test_relative_posix_still_relativises_against_a_root(tmp_path: Path):
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    assert sc._relative_posix(target, tmp_path) == "src/mod.py"


def test_flagged_lines_names_weak_wrong_only():
    # #195: name the weak/wrong requirements by block_id + path:line so a reader acts without
    # --json; a covered block is not listed, and an unjudgeable block is not listed either (with
    # no judge wired every block is unjudgeable, so per-block rows would be pure noise).
    semantic = {
        "assessed": 3, "presumed_covered": 1,
        "findings": [
            {"block_id": "algo-a:inst-x", "path": "a.py", "start_line": 10,
             "verdict": sem.SEM_WRONG, "rationale": "r"},
            {"block_id": "algo-p:inst-q", "path": "p.py", "start_line": 15,
             "verdict": sem.SEM_PARTIAL, "rationale": "half"},        # partial -> listed too
            {"block_id": "algo-b:inst-y", "path": "b.py", "start_line": 20,
             "verdict": sem.SEM_COVERED, "rationale": "ok"},          # covered -> not listed
        ],
        "unjudgeable": [
            {"block_id": "algo-c:inst-z", "path": "c.py", "start_line": 30, "reason": "no judge"}],
    }
    joined = "\n".join(sc.flagged_lines(semantic))
    assert "algo-a:inst-x  wrong  a.py:10" in joined                 # the wrong finding, named
    assert "algo-p:inst-q  partial  p.py:15" in joined               # partial is weak/wrong too
    assert "algo-b:inst-y" not in joined                             # a covered block is not listed
    assert "algo-c:inst-z" not in joined                            # unjudgeable is not listed


def test_flagged_lines_tolerates_malformed_and_caps():
    assert sc.flagged_lines(None) == []                              # absent/malformed -> no lines
    assert sc.flagged_lines({"error": "boom"}) == []                 # errored pass -> no lines
    assert sc.flagged_lines({"findings": "nope"}) == []              # non-list findings -> no raise
    assert sc.flagged_lines({"findings": []}) == []                  # empty findings -> no lines
    assert sc.flagged_lines({"findings": [None, 7]}) == []           # non-dict rows skipped, no raise
    # a wrong/partial record missing (or null-ing) a required field is skipped, not rendered as
    # "None:None" — so the docstring's "malformed shape yields no lines" holds per-record too.
    assert sc.flagged_lines({"findings": [{"verdict": sem.SEM_WRONG}]}) == []            # all missing
    assert sc.flagged_lines({"findings": [{"verdict": sem.SEM_WRONG, "path": "a.py",
                                           "start_line": 10}]}) == []                    # block_id missing
    assert sc.flagged_lines({"findings": [{"verdict": sem.SEM_PARTIAL, "block_id": None,
                                           "path": "a.py", "start_line": 10}]}) == []    # block_id null
    assert sc.flagged_lines({"findings": [{"verdict": sem.SEM_WRONG, "block_id": "b:1",
                                           "path": "a.py", "start_line": None}]}) == []  # start_line null
    # an otherwise-complete record with NO verdict key at all is skipped, not raised on
    assert sc.flagged_lines({"findings": [{"block_id": "b:1", "path": "a.py",
                                           "start_line": 10}]}) == []                    # verdict absent
    # a boolean start_line is rejected even though bool subclasses int (True would render "a.py:True")
    assert sc.flagged_lines({"findings": [{"verdict": sem.SEM_WRONG, "block_id": "b:1",
                                           "path": "a.py", "start_line": True}]}) == []  # bool start_line
    # empty-string block_id/path (falsy but correct type) and a float start_line are skipped too
    assert sc.flagged_lines({"findings": [{"verdict": sem.SEM_WRONG, "block_id": "",
                                           "path": "a.py", "start_line": 10}]}) == []  # empty block_id
    assert sc.flagged_lines({"findings": [{"verdict": sem.SEM_WRONG, "block_id": "b:1",
                                           "path": "", "start_line": 10}]}) == []      # empty path
    assert sc.flagged_lines({"findings": [{"verdict": sem.SEM_WRONG, "block_id": "b:1",
                                           "path": "a.py", "start_line": 1.5}]}) == []  # float start_line
    big = {"findings": [{"block_id": f"b:{i}", "path": "p", "start_line": i,
                         "verdict": sem.SEM_WRONG} for i in range(sc._SEMANTIC_CAP + 5)]}
    lines = sc.flagged_lines(big)
    assert len(lines) == sc._SEMANTIC_CAP + 1                        # capped rows + the "+N more"
    assert "+5 more" in lines[-1]


def test_flagged_lines_prioritises_wrong_over_partial_when_capped():
    # ainetx follow-up: severity outranks input order. Partials come FIRST in the input and there
    # are enough to fill the cap on their own; the wrong findings must still survive it.
    partials = [{"block_id": f"p:{i}", "path": "p.py", "start_line": i,
                 "verdict": sem.SEM_PARTIAL} for i in range(sc._SEMANTIC_CAP)]
    wrongs = [{"block_id": f"w:{i}", "path": "w.py", "start_line": i,
               "verdict": sem.SEM_WRONG} for i in range(3)]
    lines = sc.flagged_lines({"findings": partials + wrongs})        # 20 partials, then 3 wrongs
    shown = "\n".join(lines[:-1])                                    # drop the "+N more" row
    assert all(f"w:{i}" in shown for i in range(3))                  # every wrong survived the cap
    assert "+3 more" in lines[-1]                                    # 3 partials pushed past the cap
    # and within the shown rows, the wrong ones come before any partial
    first_partial = next(i for i, ln in enumerate(lines) if "p:" in ln)
    last_wrong = max(i for i, ln in enumerate(lines) if "w:" in ln)
    assert last_wrong < first_partial


class TestNoAbsolutePathReachesALogRecord:
    """`_relative_posix` promises "never absolute — so no local path leaks into the
    report or the out-of-tree judge prompt". #200 made the *return value* keep that
    promise; the log records beside it did not, and still carried the username and
    directory layout. A debug record is a narrower audience than a judge prompt, not a
    different rule.
    """

    def test_the_outside_root_notice_names_the_file_not_the_path(
            self, tmp_path: Path, caplog) -> None:
        import logging

        outside = tmp_path.parent / "elsewhere" / "mod.py"
        with caplog.at_level(logging.DEBUG, logger="studio.utils.semantic_coverage"):
            sc._relative_posix(outside, tmp_path)

        logged = " ".join(r.getMessage() for r in caplog.records)
        assert "outside project_root" in logged
        assert str(outside) not in logged
        assert str(tmp_path.parent) not in logged

    def test_a_duplicate_definition_warning_is_project_relative(
            self, tmp_path: Path, monkeypatch, caplog) -> None:
        import logging

        first, second = tmp_path / "a.md", tmp_path / "b.md"
        for path in (first, second):
            path.write_text(f"- [x] `p1` - **ID**: `{_ALGO}`\n", encoding="utf-8")
        monkeypatch.setattr(sc, "collect_artifacts_to_scan",
                            lambda ctx: ([(first, "feature"), (second, "feature")], {}))
        ctx = _ctx(tmp_path, first)

        with caplog.at_level(logging.WARNING, logger="studio.utils.semantic_coverage"):
            sc._definition_map(ctx)

        logged = " ".join(r.getMessage() for r in caplog.records)
        assert "defined in both" in logged
        assert str(tmp_path) not in logged, "the absolute project path must not be logged"
        assert "a.md" in logged and "b.md" in logged

    def test_an_unparseable_file_warning_is_project_relative(
            self, tmp_path: Path, caplog) -> None:
        import logging

        bad = tmp_path / "bad.py"
        bad.write_text(f"# @cpt-begin:{_ALGO}:p1:inst-orphan\ndef f():\n    pass\n",
                       encoding="utf-8")   # no @cpt-end

        with caplog.at_level(logging.WARNING, logger="studio.utils.semantic_coverage"):
            sc._pairings_for_files([bad], {}, tmp_path)

        logged = " ".join(r.getMessage() for r in caplog.records)
        assert "unparseable" in logged
        assert str(tmp_path) not in logged
        assert "bad.py" in logged
