"""Tests for the change-summary command — the advisory digest.

The command's one hard promise is structural: exit 0 on every path except a usage
error, a stated reason and denominator on every degraded line, and a ceiling that is
never padded to. So these tests force each failure the behaviour matrix names and
assert the exit code did not move, then cover the perspectives the story requires:
unit, integration through the real CLI, golden regression, edge, invariant, privacy,
fail-safe, determinism and scope reporting.

Git fixtures come from the window suite and the marker fixture from the linkage suite
rather than being copied — `tests/` is on `sys.path` via conftest.
"""

from __future__ import annotations

import io
import json
import os
import re
import socket
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from studio import cli
from studio.commands import change_summary as cmd
from studio.utils import change_summary as core
from studio.utils import decision_log
from studio.utils.ui import is_json_mode, set_json_mode
from test_change_summary_core import (
    _event, _git, _make_repo, _make_studio_project, _point_ref, _write_log,
)
from test_change_summary_links import MARKER, _code


# --------------------------------------------------------------------------- helpers

FIXED_DATE = "2026-01-01T00:00:00+00:00"

DEFAULT_EVENTS = [
    _event("2026-06-01T00:00:00+00:00", "run1", "validation"),
    _event("2026-06-01T00:00:01+00:00", "run1", "review"),
    _event("2026-06-01T00:00:02+00:00", "run2", "validation"),
    _event("2026-06-01T00:00:03+00:00", "run2", "invocation"),   # telemetry, not a decision
]


def _project_repo(tmp_path: Path, monkeypatch, *, with_work: bool = True, events=None) -> Path:
    """A git repo that is also a Studio project, one commit ahead of its base ref, with
    a project-local decision log.

    Commit dates and identity are pinned, so the fixture — and therefore the golden
    digest, sha included — is byte-identical across machines and runs.
    """
    monkeypatch.setenv("GIT_AUTHOR_DATE", FIXED_DATE)
    monkeypatch.setenv("GIT_COMMITTER_DATE", FIXED_DATE)
    monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
    repo = _make_repo(tmp_path / "r")
    _make_studio_project(repo)
    (repo / ".gitignore").write_text(".studio/.cache/\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "project")
    _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
    if with_work:
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        (repo / "plain.py").write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "work")
    log = decision_log.default_log_path(repo)
    assert log is not None, "the fixture must be a project the real resolver recognises"
    log.parent.mkdir(parents=True, exist_ok=True)
    _write_log(log, DEFAULT_EVENTS if events is None else events)
    return repo


def _run(argv: list, *, cwd: Path | None = None) -> tuple[int, str]:
    """Drive the real CLI. JSON mode follows `--json` in argv, as it does for a user."""
    saved = is_json_mode()
    set_json_mode(False)
    out = io.StringIO()
    old_cwd = Path.cwd()
    try:
        if cwd is not None:
            os.chdir(cwd)
        with redirect_stdout(out):
            rc = cli.main(argv)
    finally:
        os.chdir(old_cwd)
        set_json_mode(saved)
    return rc, out.getvalue()


def _lines(text: str) -> list:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _digest(repo: Path, *extra: str) -> tuple[int, list]:
    rc, out = _run(["change-summary", "--root", str(repo), *extra])
    return rc, _lines(out)


def _payload(repo: Path, *extra: str) -> tuple[int, dict]:
    rc, out = _run(["change-summary", "--json", "--root", str(repo), *extra])
    return rc, json.loads(out)


# -------------------------------------------------------------------- the full digest

class TestTheDigestReadsTheBranch:

    def test_a_branch_with_work_yields_the_golden_digest(self, tmp_path, monkeypatch):
        """Regression fixture. Pinned dates make the base sha itself reproducible."""
        repo = _project_repo(tmp_path, monkeypatch)
        base = _git(repo, "rev-parse", "upstream/main")[:8]
        # Git renders the pinned UTC instant as `Z` or `+00:00` depending on its version;
        # the digest reports git's own spelling, so the golden asks git rather than guessing.
        since = _git(repo, "show", "-s", "--format=%cI", "upstream/main")

        rc, lines = _digest(repo)

        assert rc == 0
        assert lines == [
            f"window: since {since} against upstream/main @ {base}",
            "changes: 2 file(s): 1 reference requirements",
            "markers: 1 of 2 changed files carry requirement markers",
            f"requirements: {MARKER}",
            "why: 3 decision(s) in 2 run(s): validation ×2, review ×1",
            "runs: run1 ×2, run2 ×1",
        ]

    def test_json_carries_the_same_lines_and_the_data_behind_them(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)
        _, human = _digest(repo)

        rc, data = _payload(repo)

        assert rc == 0
        assert data["status"] == "OK"
        assert data["lines"] == human
        assert data["omitted"] == 0
        assert (data["changes"]["changed"], data["changes"]["examined"], data["changes"]["marked"]) == (2, 2, 1)
        assert data["changes"]["not_a_file"] == 0
        assert data["requirements"] == [MARKER]
        assert data["decisions"]["decisions"] == 3
        assert data["decisions"]["events"] == 4, "telemetry is in the payload, just not in 'why'"
        assert data["decisions"]["runs"] == [
            {"run_id": "run1", "decisions": 2}, {"run_id": "run2", "decisions": 1},
        ]
        assert [f["path"] for f in data["changes"]["files"]] == ["m.py", "plain.py"]

    def test_the_marker_line_counts_files_not_directions(self, tmp_path, monkeypatch):
        """A file that both references and declares is one marked file, not two."""
        report = core.LinkReport(
            files=(core.FileLink(path="a", references=("x",), defines=("y",)),
                   core.FileLink(path="b")),
            changed=2, examined=2, linked=1, declaring=1, available=True, reason=core.REASON_OK,
        )

        assert cmd._marked(report) == 1
        assert "markers: 1 of 2 changed files carry requirement markers" in cmd._changes_lines(report)


# --------------------------------------------------------- every matrix row exits zero

class TestEveryMatrixRowExitsZeroWithAStatedReason:
    """The advisory invariant, enforced rather than promised: each degradation the
    behaviour matrix names is forced here, and the exit code must not move."""

    def test_a_disabled_log_is_stated_and_the_other_lines_still_print(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)
        monkeypatch.setenv("CFS_DECISION_LOG", "off")

        rc, lines = _digest(repo)

        assert rc == 0
        assert f"decisions: unavailable ({core.REASON_LOG_DISABLED})" in lines
        assert any(line.startswith("markers: 1 of 2") for line in lines), "git and marker lines survive"

    def test_a_corrupt_log_states_how_many_lines_it_skipped(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)
        log = decision_log.default_log_path(repo)
        with log.open("a", encoding="utf-8") as handle:
            handle.write("{oops\n")

        rc, lines = _digest(repo)

        assert rc == 0
        assert "decision log: 1 unparseable line(s) skipped" in lines
        assert any(line.startswith("why: 3 decision(s)") for line in lines), "parses what it can"

    def test_no_changes_is_one_line_not_an_empty_digest(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch, with_work=False)

        rc, lines = _digest(repo)

        assert rc == 0
        assert lines == ["no changes against upstream/main"]

    def test_changed_files_without_markers_state_zero_of_n(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch, with_work=False)
        (repo / "plain.py").write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", "plain.py")
        _git(repo, "commit", "-q", "-m", "plain")

        rc, lines = _digest(repo)

        assert rc == 0
        assert "markers: 0 of 1 changed files carry requirement markers" in lines
        assert not any(line.startswith("requirements:") for line in lines), "no line without data"

    def test_not_a_git_repository_is_one_stated_line_with_the_remedy(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        project = _make_studio_project(tmp_path / "p")

        rc, lines = _digest(project)

        assert rc == 0
        assert lines == [
            f"window: unavailable ({core.REASON_NOT_A_REPO}); --since <timestamp> scopes decisions without git",
        ]

    def test_the_remedy_works_where_git_does_not(self, tmp_path, monkeypatch):
        """`--since` on a non-repo: decisions are scoped by time, and the change dimension
        says plainly why it has nothing to diff against."""
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        project = _make_studio_project(tmp_path / "p")
        log = decision_log.default_log_path(project)
        log.parent.mkdir(parents=True, exist_ok=True)
        _write_log(log, DEFAULT_EVENTS)

        rc, lines = _digest(project, "--since", "2026-01-01T00:00:00+00:00")

        assert rc == 0
        assert f"changes: unavailable ({core.REASON_NO_BASE_COMMIT})" in lines
        assert "why: 3 decision(s) in 2 run(s): validation ×2, review ×1" in lines

    def test_git_unavailable_is_stated_not_raised(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)

        def _no_git(*_a, **_k):
            raise OSError("git: not found")
        monkeypatch.setattr(core.subprocess, "run", _no_git)

        rc, lines = _digest(repo)

        assert rc == 0
        assert lines[0].startswith(f"window: unavailable ({core.REASON_GIT_UNAVAILABLE})")

    def test_outside_a_studio_project_is_a_clean_no_op_with_a_reason(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)

        rc, lines = _digest(tmp_path)

        assert rc == 0
        assert lines == [f"{core.REASON_NOT_A_PROJECT}: nothing to summarise"]

    def test_a_bad_base_ref_is_refused_with_its_reason(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)

        rc, lines = _digest(repo, "--base", "does-not-exist")

        assert rc == 0
        assert lines[0].startswith(f"window: unavailable ({core.REASON_BASE_REF_UNKNOWN})")

    def test_a_usage_error_is_the_only_non_zero_exit(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)

        rc, out = _run(["change-summary", "--json", "--root", str(repo), "--nonsense"])

        assert rc == 2
        assert json.loads(out)["status"] == "ERROR"

    @pytest.mark.parametrize("fixture,extra,exit_code,window", [
        ("work", [], 0, "available"),
        ("no-work", [], 0, "no-changes"),
        ("work", ["--base", "upstream/main"], 0, "available"),
        ("work", ["--base", "no-such-ref"], 0, core.REASON_BASE_REF_UNKNOWN),
        ("work", ["--since", "yesterday"], 0, core.REASON_INVALID_SINCE),
        ("no-repo", [], 0, core.REASON_NOT_A_REPO),
        ("work", ["--nonsense"], 2, "usage"),
        # The parser fails in more ways than an unknown flag, and each must still be the
        # *only* non-zero exit this command produces. An option given without its value
        # is the form a person actually hits, and it was the one row missing.
        ("work", ["--base"], 2, "usage"),
        ("work", ["--since"], 2, "usage"),
        ("work", ["--root"], 2, "usage"),
        ("work", ["stray-positional"], 2, "usage"),
    ], ids=["default-base+changes", "default-base+none", "named-base", "unknown-base",
            "bad-since", "not-a-repo", "usage-unknown-flag", "usage-base-no-value",
            "usage-since-no-value", "usage-root-no-value", "usage-unexpected-argument"])
    def test_the_exit_and_status_truth_table(self, fixture, extra, exit_code, window, tmp_path, monkeypatch):
        """The behaviour matrix as one table: every row asserts its exit code and, in the
        JSON rendering, the status and the window's availability or stated reason — so a
        row cannot change its exit or status without this table going red."""
        if fixture == "no-repo":
            root = _make_studio_project(tmp_path / "p")
        else:
            root = _project_repo(tmp_path, monkeypatch, with_work=(fixture == "work"))

        rc, out = _run(["change-summary", "--json", "--root", str(root), *extra])
        data = json.loads(out)

        assert rc == exit_code
        if window == "usage":
            assert data["status"] == "ERROR"
        elif window == "available":
            assert data["status"] == "OK" and data["window"]["available"] is True
        elif window == "no-changes":
            assert data["status"] == "OK" and data["lines"] == ["no changes against upstream/main"]
        else:
            assert data["status"] == "OK" and data["window"]["available"] is False
            assert data["window"]["reason"] == window


# ------------------------------------------------------------------- the ceiling

class TestTheCeilingIsACeilingNotAQuota:

    def test_at_or_under_the_ceiling_nothing_is_cut(self):
        lines = [f"line {i}" for i in range(cmd.LINE_CEILING)]

        assert cmd._apply_ceiling(lines) == (lines, 0)
        assert cmd._apply_ceiling(lines[:3]) == (lines[:3], 0)

    def test_over_the_ceiling_the_last_line_says_how_many_were_cut(self):
        lines = [f"line {i}" for i in range(cmd.LINE_CEILING + 1)]

        kept, omitted = cmd._apply_ceiling(lines)

        assert len(kept) == cmd.LINE_CEILING
        assert omitted == 2, "the omission line itself takes a slot"
        assert kept[-1] == "(+2 more line(s) omitted; --json carries everything)"
        assert kept[:-1] == lines[: cmd.LINE_CEILING - 1]

    def test_the_ceiling_cuts_the_run_breakdown_before_any_integrity_line(self):
        """What the ceiling sacrifices first has to be the least load-bearing line.

        The four "decision log:" lines are how the digest admits it could not see
        everything -- unreadable lines, undated events, events with no run id, a shared
        log. Emitted after the run breakdown they were structurally the *first* thing
        cut, so a large enough change set made the digest stop reporting that three log
        lines were unreadable in order to keep printing which runs they came from.

        Stated precisely, because the ordering is a priority and not a guarantee: the
        breakdown is now last, so it is the first line the ceiling takes. A deep enough
        overflow still reaches an integrity line -- the omission summary occupies a slot
        of its own, so the smallest overflow already costs two lines -- and what covers
        that case is the omission count itself plus the JSON, which carries every one of
        these counts as a field whatever the human rendering had room for.
        """
        selection = core.EventSelection(
            events=(_event("2026-06-01T00:00:00+00:00", "run1", "validation"),),
            runs=("run1",), skipped_lines=3, undated=2, runless=1,
            log_overridden=True, available=True, reason=core.REASON_OK,
        )

        lines = cmd._decision_lines(selection)

        integrity = [i for i, line in enumerate(lines) if line.startswith("decision log:")]
        breakdown = [i for i, line in enumerate(lines) if line.startswith("runs: ")]
        assert len(integrity) == 4, "all four degradations are in force"
        assert breakdown == [len(lines) - 1], "the breakdown is last, so it is cut first"
        assert max(integrity) < breakdown[0], "every integrity line outranks the breakdown"

        # And in a render that overflows, the breakdown is what went.
        kept, omitted = cmd._apply_ceiling(["window: ..."] * 5 + lines)

        assert omitted, "the fixture must actually overflow"
        assert not [line for line in kept if line.startswith("runs: ")]
        assert len([line for line in kept if line.startswith("decision log:")]) == 3, (
            "the breakdown first, then integrity lines only as the overflow deepens"
        )

    @pytest.mark.parametrize("over", [-1, 0, 1, 2, 10])
    def test_the_reported_count_is_the_count_of_lines_genuinely_not_returned(self, over):
        """The invariant behind the number, across the boundary, derived independently.

        The count above is pinned at one length; a review read that as an off-by-one and
        proposed `len(lines) - LINE_CEILING`, which would report 1 where two source lines
        are genuinely absent. So `dropped` here is counted by asking which of the input
        strings are missing from the output — never from the formula — and must equal
        what the digest says it omitted. Understating is the failure that matters: this
        command exists so that what it drops is visible.
        """
        lines = [f"line {i}" for i in range(cmd.LINE_CEILING + over)]

        kept, omitted = cmd._apply_ceiling(list(lines))

        dropped = len([line for line in lines if line not in kept])
        assert omitted == dropped, "the stated omission is the real one"
        assert len(kept) <= cmd.LINE_CEILING, "a ceiling, not a quota"

    def test_the_ceiling_is_enforced_on_the_real_path(self, tmp_path, monkeypatch):
        """Lowered, so the real digest overflows; the arithmetic is tested above."""
        repo = _project_repo(tmp_path, monkeypatch)
        monkeypatch.setattr(cmd, "LINE_CEILING", 3)

        rc, data = _payload(repo)

        assert rc == 0
        assert len(data["lines"]) == 3
        assert data["omitted"] == 4
        assert data["lines"][-1] == "(+4 more line(s) omitted; --json carries everything)"

    def test_a_real_overflow_reports_the_same_omission_in_both_renderings(self, tmp_path, monkeypatch):
        """More than ten lines composed through `_digest_lines` itself at the default
        ceiling — every degradation the log can carry, plus a capped scan with a
        requirement — and the count the last human line states must be the count the
        payload carries. Lowering the ceiling to force the cut tested the arithmetic on a
        fixture too small to overflow on its own."""
        monkeypatch.setattr(cmd, "_project_gate", lambda _root: None)
        monkeypatch.setattr(core, "resolve_window", lambda *_a, **_k: core.ChangeWindow(
            project_root=str(tmp_path), base_ref="upstream/main", base_sha="0123456789ab",
            since="2026-01-01T00:00:00+00:00", available=True, reason=core.REASON_OK,
        ))
        monkeypatch.setattr(core, "select_events", lambda _window: core.EventSelection(
            events=(_event("2026-06-01T00:00:00+00:00", "run1", "validation"),), runs=("run1",),
            undated=1, runless=1, skipped_lines=1, log_overridden=True, available=True, reason=core.REASON_OK,
        ))
        monkeypatch.setattr(core, "link_changed_files", lambda _window: core.LinkReport(
            files=(core.FileLink(path="m.py", status="M", references=("cpt-x-1",), defines=(), reason=""),),
            changed=13, examined=9, linked=1, truncated=4, available=True, reason=core.REASON_OK,
        ))

        data = cmd.compose_digest(tmp_path)

        assert len(data["lines"]) == cmd.LINE_CEILING
        last = data["lines"][-1]
        assert last.startswith("(+") and last.endswith(" more line(s) omitted; --json carries everything)")
        assert int(last[2:].split(" ", 1)[0]) == data["omitted"] > 0

    def test_no_line_is_emitted_without_data_behind_it(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)

        _, lines = _digest(repo)

        # The non-empty guard comes first because it is what gives the other three
        # assertions their force: `all([])` is True and `not any(...)` is vacuously true
        # on an empty list, so a regression suppressing the whole digest satisfied every
        # one of them. This fixture always yields the window, changes and markers lines.
        assert len(lines) >= 3, f"the digest itself must be present: {lines}"
        assert not any(line.startswith("decision log:") for line in lines), "nothing was skipped or undated"
        assert not any(line.startswith("changes: scan capped") for line in lines)
        assert all(lines), "no blank lines"

    def test_requirements_are_capped_and_counted_not_truncated_silently(self):
        ids = [f"cpt-x-{i}" for i in range(7)]

        line = cmd._requirements_line(ids)

        assert line == "requirements: cpt-x-0, cpt-x-1, cpt-x-2, cpt-x-3, cpt-x-4 (+2 more)"
        assert cmd._requirements_line([]) is None

    @pytest.mark.parametrize("count,suffix", [(5, ""), (6, " (+1 more)")])
    def test_the_requirements_cap_boundary(self, count, suffix):
        """Exactly at the cap nothing is cut; one over cuts one — where an off-by-one in
        the slice or the arithmetic would first show."""
        ids = [f"cpt-x-{i}" for i in range(count)]

        assert cmd._requirements_line(ids) == "requirements: " + ", ".join(ids[:5]) + suffix

    @pytest.mark.parametrize("count,suffix", [(3, ""), (4, " (+1 more)")])
    def test_the_runs_cap_boundary(self, count, suffix):
        selection = core.EventSelection(
            events=tuple(_event(f"2026-06-01T00:00:0{i}+00:00", f"run{i}", "validation") for i in range(count)),
            runs=tuple(f"run{i}" for i in range(count)), available=True, reason=core.REASON_OK,
        )

        lines = cmd._decision_lines(selection)

        assert lines[1] == "runs: " + ", ".join(f"run{i} ×1" for i in range(3)) + suffix

    def test_runs_sharing_a_prefix_are_told_apart(self):
        """Two runs with the same first eight characters used to render as two identical
        labels; the prefix now grows until the shown ids differ, as git does for shas."""
        selection = core.EventSelection(
            events=(_event("2026-06-01T00:00:00+00:00", "abcdefgh1111", "validation"),
                    _event("2026-06-01T00:00:01+00:00", "abcdefgh2222", "review")),
            runs=("abcdefgh1111", "abcdefgh2222"), available=True, reason=core.REASON_OK,
        )

        assert cmd._decision_lines(selection)[1] == "runs: abcdefgh1 ×1, abcdefgh2 ×1"
        assert cmd._run_prefix_width(["abcdefgh1111", "12345678"]) == 8

    def test_a_folded_run_sharing_a_prefix_still_widens_the_shown_one(self):
        """The prefix is a handle into the log, so it must be unique among every run in
        the window, not only the three shown: a fourth run folded into "(+1 more)" that
        shared eight characters with a shown one left that label matching two runs."""
        runs = ("abcdefgh1111", "r2", "r3", "abcdefgh2222")
        events = tuple(
            _event(f"2026-06-01T00:00:0{i}+00:00", run_id, "validation") for i, run_id in enumerate(runs)
        )
        selection = core.EventSelection(events=events, runs=runs, available=True, reason=core.REASON_OK)

        assert cmd._decision_lines(selection)[1] == "runs: abcdefgh1 ×1, r2 ×1, r3 ×1 (+1 more)"


# -------------------------------------------------------- the digest never counts itself

class TestTheDigestNeverCountsItself:

    def test_consecutive_runs_are_byte_identical_although_each_logs_an_invocation(
        self, tmp_path, monkeypatch,
    ):
        """The dispatcher records an `invocation` for every command, this one included.
        Run from inside the project so those land in the very log the digest reads."""
        repo = _project_repo(tmp_path, monkeypatch)
        log = decision_log.default_log_path(repo)

        human = [_run(["change-summary"], cwd=repo) for _ in range(3)]
        as_json = [_run(["change-summary", "--json"], cwd=repo) for _ in range(3)]

        assert {rc for rc, _ in human + as_json} == {0}
        assert len({out for _, out in human}) == 1, "byte-identical across runs"
        assert len({out for _, out in as_json}) == 1, \
            "the payload's totals too — telemetry is excluded from 'why', but only the " \
            "self-exclusion keeps the event count from growing by one per run"
        own = [line for line in log.read_text(encoding="utf-8").splitlines()
               if '"command": "change-summary"' in line]
        assert len(own) == 6, "the exclusion did the work, not an unwritten log"

    def test_the_whole_event_population_is_partitioned_in_both_renderings(self):
        """One fixture holding every category, asserted in both renderings at once.

        Two independent rules act here and each existing test exercised a slice of the
        result, so a regression could retain self events or misclassify a foreign
        command's telemetry without any single assertion failing on the *partition*:

        * a **decision** (`validation`, `r1`) — counted, and its run is named;
        * **read telemetry** (`r1`) — kept among `events`, not a decision;
        * a **foreign command's invocation** (`resolve-vars`, `r2`) — survives the
          self-exclusion, which is by command, and is dropped by the telemetry rule,
          which is by kind. This is the case the two rules disagree on;
        * **this command's own invocation** (`change-summary`, `r9`) — gone entirely,
          so `r9` exists in `runs` yet must not appear in either rendering;
        * a **telemetry-only run** (`r2`, and `r9` before exclusion) — no decisions, so
          absent from the run breakdown while its events still count.
        """
        selection = core.EventSelection(
            events=(
                _event("2026-06-01T00:00:00+00:00", "r1", "validation"),
                _event("2026-06-01T00:00:01+00:00", "r1", "read"),
                {**_event("2026-06-01T00:00:02+00:00", "r2", "invocation"), "command": "resolve-vars"},
                {**_event("2026-06-01T00:00:03+00:00", "r9", "invocation"), "command": "change-summary"},
            ),
            runs=("r1", "r2", "r9"), available=True, reason=core.REASON_OK,
        )

        lines = cmd._decision_lines(selection)
        payload = cmd._decisions_payload(selection)

        assert lines == ["why: 1 decision(s) in 1 run(s): validation ×1", "runs: r1 ×1"]
        assert payload["events"] == 3, "the read and the foreign invocation stay; our own is gone"
        assert payload["decisions"] == 1, "only the validation"
        assert payload["by_event"] == {"invocation": 1, "read": 1, "validation": 1}, (
            "exactly one invocation survives -- the foreign one, not ours"
        )
        assert payload["runs"] == [{"run_id": "r1", "decisions": 1}], (
            "the telemetry-only runs carry no decisions, so they are not named"
        )
        assert "r2" not in lines[1] and "r9" not in lines[1]

    def test_every_change_summary_invocation_is_excluded_whatever_its_run(self):
        """By kind, not by instance: another process's read of the log is no more a
        decision than this one's, and excluding only the current run's would let the
        previous run's read surface in the next digest and break the determinism above."""
        selection = core.EventSelection(
            events=(
                {**_event("2026-06-01T00:00:00+00:00", "r1", "invocation"), "command": "change-summary"},
                {**_event("2026-06-01T00:00:01+00:00", "r2", "invocation"), "command": "change-summary"},
                _event("2026-06-01T00:00:02+00:00", "r1", "validation"),
            ),
            runs=("r1", "r2"), available=True, reason=core.REASON_OK,
        )

        payload = cmd._decisions_payload(selection)

        assert (payload["events"], payload["decisions"]) == (1, 1), "both reads gone, the decision kept"
        assert payload["runs"] == [{"run_id": "r1", "decisions": 1}]

    def test_a_window_with_only_telemetry_says_so_with_its_denominator(self):
        selection = core.EventSelection(
            events=(_event("2026-06-01T00:00:00+00:00", "r1", "invocation"),),
            runs=("r1",), available=True, reason=core.REASON_OK,
        )

        assert cmd._decision_lines(selection) == [
            "why: no decisions recorded in this window (1 event(s) in it)",
        ]

    def test_the_no_decisions_line_counts_the_window_not_the_whole_log(self):
        """The number is the window's population; the word said it was the log's.

        `selection.scanned` is every parseable event in the log, in or out of the
        window. `events` is what fell inside it with this command's own invocations
        dropped. The line printed the second and called it "scanned", so a log holding
        a hundred older entries reported "0 event(s) scanned" having scanned all
        hundred — a denominator that was not one.
        """
        selection = core.EventSelection(
            events=(_event("2026-06-01T00:00:00+00:00", "r1", "invocation"),),
            runs=("r1",), scanned=100, available=True, reason=core.REASON_OK,
        )

        line = cmd._decision_lines(selection)[0]

        assert line == "why: no decisions recorded in this window (1 event(s) in it)"
        assert "scanned" not in line, "the count is the window's, so the word must not claim the log's"
        assert "100" not in line, "and the log's own total must not appear -- see the next test"

    def test_the_payload_omits_the_log_total_because_it_grows_every_run(self, tmp_path, monkeypatch):
        """`scanned` is the denominator a reader might reasonably expect here, and it is
        left out on purpose rather than by oversight.

        It counts this command's own logged invocations, so carrying it would make two
        consecutive digests of an unchanged repository differ by one — the determinism
        `_is_own_invocation` exists to hold. There is no self-excluded variant to offer
        instead: the selection keeps no events from outside the window, so their
        invocations cannot be identified and subtracted.

        Asserted as an absence because adding it looks like an improvement. It is the
        change this test exists to stop.
        """
        repo = _project_repo(tmp_path, monkeypatch)

        rc, data = _payload(repo)

        assert rc == 0
        assert "scanned" not in data["decisions"], (
            "exporting the log total would break run-to-run byte-identity"
        )
        assert {"events", "decisions", "undated", "runless", "skipped_lines"} <= set(data["decisions"]), (
            "the stable counts are all carried"
        )


# ------------------------------------------------------------------ scope reporting

class TestEveryDegradedLineCarriesItsDenominator:

    def test_a_deleted_file_is_counted_in_the_changes_line(self, tmp_path, monkeypatch):
        """`a.txt` is in the base commit, so removing it is a deletion *against the base*;
        removing a file the branch itself added would simply vanish from the diff."""
        repo = _project_repo(tmp_path, monkeypatch)
        _git(repo, "rm", "-q", "a.txt")

        rc, data = _payload(repo)

        assert rc == 0
        assert data["changes"]["deleted"] == 1
        assert data["lines"][1] == "changes: 3 file(s): 1 reference requirements; 1 deleted"
        assert data["lines"][2] == "markers: 1 of 3 changed files carry requirement markers"

    def test_every_non_zero_tally_is_named_and_every_zero_one_is_not(self):
        report = core.LinkReport(
            files=(), changed=9, examined=9, linked=2, declaring=1, excluded=3, deleted=1,
            unreadable=1, not_a_file=1, available=True, reason=core.REASON_OK,
        )

        assert cmd._changes_lines(report) == [
            "changes: 9 file(s): 2 reference requirements; 1 declare requirements; "
            "3 excluded by the project's scope policy; 1 deleted; 1 yielded no marker information; "
            "1 not regular files",
            "markers: 0 of 9 changed files carry requirement markers",
        ]

    def test_the_two_exclusion_rules_are_independent_where_they_diverge(self, tmp_path, monkeypatch):
        """Two rules drop events, by different tests, and the divergent case pins both.

        `_is_own_invocation` drops an event by *command* -- this command's own reads, so
        a digest never reports its own footprint. `_TELEMETRY_EVENTS` drops by *kind*,
        so any `invocation` or `read` is not a decision whoever issued it. An
        `invocation` from another command is where they disagree: it survives the first
        rule and not the second, so it must be counted among `events` and in `by_event`
        while contributing nothing to `decisions`. Asserting only the agreeing cases
        would let either rule be widened into the other without a test noticing.
        """
        events = [
            _event("2026-06-01T00:00:00+00:00", "run1", "validation"),
            {**_event("2026-06-01T00:00:01+00:00", "run1", "invocation"), "command": "resolve-vars"},
            {**_event("2026-06-01T00:00:02+00:00", "run1", "invocation"), "command": "change-summary"},
        ]
        repo = _project_repo(tmp_path, monkeypatch, events=events)

        rc, data = _payload(repo)

        decisions = data["decisions"]
        assert rc == 0
        assert decisions["by_event"].get("invocation") == 1, (
            "another command's invocation is retained; this command's own is not"
        )
        assert decisions["events"] == 2, "the validation and the foreign invocation"
        assert decisions["decisions"] == 1, "only the validation is a decision"
        assert [r["run_id"] for r in decisions["runs"]] == ["run1"]

    def test_the_aggregate_count_is_not_labelled_as_one_of_its_causes(self, tmp_path, monkeypatch):
        """`unreadable` holds every reason no marker could be established, so a file
        whose *scope* could not be determined is counted there too. Labelling the count
        "could not be read or parsed" told a reader a scope-policy failure was a
        file-access one. The per-file reason must still name the real cause, which is
        what makes the aggregate label honest rather than merely vaguer.
        """
        repo = _project_repo(tmp_path, monkeypatch)
        (repo / "scopeless.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(core, "_in_project_scope", lambda *_a, **_k: None)

        rc, data = _payload(repo)

        assert rc == 0
        assert data["changes"]["unreadable"] >= 1, "a scope failure lands in the aggregate"
        reasons = {f["reason"] for f in data["changes"]["files"]}
        assert core.REASON_SCOPE_UNKNOWN in reasons, "the row keeps its own cause"
        changes = [line for line in data["lines"] if line.startswith("changes:")]
        assert any("yielded no marker information" in line for line in changes)
        assert not any("could not be read or parsed" in line for line in changes), (
            "the aggregate must not be named after one of its causes"
        )

    def test_a_capped_scan_names_the_population_its_tallies_describe(self):
        """`changed` is every file git reported; the tallies were computed over the
        `examined` subset. "300 of 1,500" must not read as a breakdown of 1,500."""
        report = core.LinkReport(
            files=(), changed=13, examined=9, linked=2, truncated=4,
            available=True, reason=core.REASON_OK,
        )

        assert cmd._changes_lines(report) == [
            "changes: 13 file(s); 9 examined: 2 reference requirements",
            "markers: 0 of 9 examined files carry requirement markers",
            "changes: scan capped; 4 more file(s) were not examined",
        ]

    def test_the_cap_is_rendered_honestly_on_the_real_path(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)
        monkeypatch.setattr(core, "MAX_CHANGED_ENTRIES", 1)

        rc, data = _payload(repo)

        assert rc == 0
        assert (data["changes"]["changed"], data["changes"]["examined"], data["changes"]["truncated"]) == (2, 1, 1)
        assert data["lines"][1].startswith("changes: 2 file(s); 1 examined")
        assert data["lines"][2].endswith("of 1 examined files carry requirement markers")
        assert "changes: scan capped; 1 more file(s) were not examined" in data["lines"]

    def test_undated_and_shared_log_conditions_each_get_a_line(self):
        selection = core.EventSelection(
            events=(), runs=(), undated=2, runless=3, skipped_lines=1, log_overridden=True,
            available=True, reason=core.REASON_OK,
        )

        assert cmd._decision_lines(selection) == [
            "why: no decisions recorded in this window (0 event(s) in it)",
            "decision log: 1 unparseable line(s) skipped",
            "decision log: 2 undated event(s) excluded",
            "decision log: 3 event(s) carry no run id",
            "decision log: shared via CFS_DECISION_LOG; decisions are not attributable to this project",
        ]

    def test_runless_decisions_are_labelled_in_full_not_by_a_prefix(self):
        """A decision with no run id lands in the unattributed bucket; cut to eight
        characters its label read `(unattri`, which told a reader nothing, and the plain
        digest never said such events existed while the payload counted them."""
        selection = core.EventSelection(
            events=(_event("2026-06-01T00:00:00+00:00", "", "validation"),),
            runs=(), runless=1, available=True, reason=core.REASON_OK,
        )

        lines = cmd._decision_lines(selection)

        # By content, not by index: the run breakdown now follows the integrity lines so
        # the ceiling cuts it before them, and this test is about the label, not the order.
        assert f"runs: {core.RUN_UNATTRIBUTED} ×1" in lines
        assert "decision log: 1 event(s) carry no run id" in lines

    def test_the_window_line_names_its_source(self):
        assert cmd._window_line(core.ChangeWindow(
            base_ref="upstream/main", base_sha="0123456789ab", since="2026-01-01T00:00:00+00:00",
            available=True, reason=core.REASON_OK,
        )) == "window: since 2026-01-01T00:00:00+00:00 against upstream/main @ 01234567"
        assert cmd._window_line(core.ChangeWindow(
            since="2026-01-01T00:00:00+00:00", available=True, reason=core.REASON_OK,
        )) == "window: since 2026-01-01T00:00:00+00:00 (explicit; no base commit to diff against)"


# ------------------------------------------------------------------------- privacy

class TestPrivacy:

    def test_the_digest_needs_no_network(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)

        def _no_socket(*_a, **_k):
            raise AssertionError("a socket was opened")
        monkeypatch.setattr(socket, "socket", _no_socket)

        rc, lines = _digest(repo)

        assert rc == 0
        assert len(lines) == 6

    def test_an_undecodable_filename_cannot_crash_either_rendering(self, tmp_path, monkeypatch):
        """Git paths are decoded with `surrogateescape` so a legal non-UTF-8 name round-
        trips; a lone surrogate then raised `UnicodeEncodeError` inside `print`, past the
        last-resort guard, in the one mode meant for scripts. The output stream here
        encodes strictly, as a real stdout does — a `StringIO` would not have noticed."""
        if os.name == "nt":
            pytest.skip("arbitrary bytes are not legal in Windows file names")
        repo = _project_repo(tmp_path, monkeypatch)
        (repo / os.fsdecode(b"bad\xff.py")).write_text("x = 1\n", encoding="utf-8")

        def _run_strict(argv):
            saved = is_json_mode()
            set_json_mode(False)
            raw = io.BytesIO()
            strict = io.TextIOWrapper(raw, encoding="utf-8", errors="strict", write_through=True)
            try:
                with redirect_stdout(strict):
                    rc = cli.main(argv)
            finally:
                set_json_mode(saved)
            strict.flush()
            return rc, raw.getvalue().decode("utf-8")

        rc_json, out_json = _run_strict(["change-summary", "--json", "--root", str(repo)])
        rc_human, out_human = _run_strict(["change-summary", "--root", str(repo)])

        assert (rc_json, rc_human) == (0, 0)
        payload = json.loads(out_json)
        assert "bad\\xff.py" in [f["path"] for f in payload["changes"]["files"]], "escaped, not dropped"
        assert payload["changes"]["changed"] == 3
        assert _lines(out_human)

    def test_a_surrogate_from_the_log_is_escaped_not_a_whole_digest_lost(self, tmp_path, monkeypatch):
        """`surrogateescape` only re-encodes the surrogates it made (U+DC80–U+DCFF). A
        `"\\ud800"` that a log line carries through `json.loads` is a different kind, and
        encoding it raised — so one bad event field replaced the whole digest with the
        last-resort reason instead of one escaped value in the decisions dimension."""
        assert cmd._json_safe("\ud800") == "\\ud800"
        assert cmd._json_safe(os.fsdecode(b"bad\xff.py")) == "bad\\xff.py"
        repo = _project_repo(tmp_path, monkeypatch, events=[
            _event("2026-06-01T00:00:00+00:00", "run1", "validation"),
            _event("2026-06-01T00:00:01+00:00", "run1", "\ud800odd"),
        ])

        rc, data = _payload(repo)

        assert rc == 0
        assert "reason" not in data, "the decisions dimension is stated, not the digest lost"
        assert data["decisions"]["by_event"] == {"\\ud800odd": 1, "validation": 1}

    def test_a_named_base_and_an_explicit_bound_compose(self, tmp_path, monkeypatch):
        """`--since` alone needs no git; with `--base` the base still anchors the diff.
        The base used to be ignored silently, and the changes dimension went missing."""
        repo = _project_repo(tmp_path, monkeypatch)
        base = _git(repo, "rev-parse", "upstream/main")[:8]

        rc, lines = _digest(repo, "--base", "upstream/main", "--since", "2026-01-01T00:00:00+00:00")

        assert rc == 0
        assert lines[0] == f"window: since 2026-01-01T00:00:00+00:00 against upstream/main @ {base}"
        assert lines[1].startswith("changes: 2 file(s)"), "the diff is anchored, not lost"

    def test_the_escape_is_exact_and_survives_json(self):
        """The contract is `\\xNN` per undecodable byte, every byte, round-tripping through
        JSON; a test that only checked the digest did not crash could not tell a lost
        byte from a kept one."""
        path = "bad" + b"\xff\xfe".decode("utf-8", "surrogateescape") + ".py"

        safe = cmd._json_safe({"path": path})

        assert safe == {"path": "bad\\xff\\xfe.py"}
        assert json.loads(json.dumps(safe)) == safe

    def test_a_surrogate_that_is_not_a_filename_byte_is_escaped_and_said(self, caplog):
        """The fallback for a lone surrogate `surrogateescape` did not make — a corrupt log
        line's `\\ud800` — leaves a trail at warning; the routine filename case stays quiet."""
        with caplog.at_level("WARNING", logger="studio"):
            escaped = cmd._json_safe("\ud800x")
            routine = cmd._json_safe(b"\xff".decode("utf-8", "surrogateescape"))

        assert escaped == "\\ud800x"
        assert routine == "\\xff"
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1 and "lone surrogate" in warnings[0]

    def test_no_output_carries_a_path_home_user_or_author(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)
        home = os.path.expanduser("~")
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""

        rc_human, human = _run(["change-summary", "--root", str(repo)])
        rc_json, as_json = _run(["change-summary", "--json", "--root", str(repo)])

        assert (rc_human, rc_json) == (0, 0), "a digest was produced; an error text would prove nothing"
        assert json.loads(as_json)["window"]["available"] is True
        for text in (human, as_json):
            assert str(tmp_path) not in text, "no absolute path, in either rendering"
            assert home not in text
            if user and user not in MARKER:
                assert not re.search(rf"\b{re.escape(user)}\b", text)
            assert "Test User" not in text and "test@example.com" not in text, "no commit author"

    def test_degraded_inputs_carry_no_path_either(self, tmp_path, monkeypatch):
        """The degraded fields are where a path would leak if anywhere: a file that could
        not be read carries a reason, and a shared log carries the fact of its override.
        With both in force, neither the project root, the override path, the home
        directory nor the user may appear in the serialised payload."""
        repo = _project_repo(tmp_path, monkeypatch)
        (repo / "bin.py").write_bytes(b"x = 1\n\x00binary")
        elsewhere = tmp_path / "elsewhere-shared" / "log.jsonl"
        elsewhere.parent.mkdir()
        # Every degradation at once, not just the two file/log ones: an event whose
        # timestamp will not parse and one carrying no run id are separate reported
        # fields, and they were only ever exercised at unit level against an
        # `EventSelection` -- never through the real serialisation alongside these
        # path assertions, which is where a leak would actually surface.
        undated = dict(_event("not-a-timestamp", "run3", "validation"))
        runless = dict(_event("2026-06-01T00:00:04+00:00", "", "review"))
        _write_log(elsewhere, [*DEFAULT_EVENTS, undated, runless])
        monkeypatch.setenv("CFS_DECISION_LOG", str(elsewhere))
        home = os.path.expanduser("~")
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""

        rc, out = _run(["change-summary", "--json", "--root", str(repo)])
        data = json.loads(out)

        assert rc == 0
        assert data["decisions"]["log_overridden"] is True, "the override was in force"
        assert data["decisions"]["undated"] >= 1, "an undated event was in force"
        assert data["decisions"]["runless"] >= 1, "a runless event was in force"
        assert [f["reason"] for f in data["changes"]["files"] if f["path"] == "bin.py"] == [core.REASON_FILE_UNREADABLE]
        for needle in (str(tmp_path), str(elsewhere), home):
            assert needle not in out
        if user and user not in MARKER:
            assert not re.search(rf"\b{re.escape(user)}\b", out)


# ---------------------------------------------------------------------- fail-safe

class TestFailSafe:

    def test_a_stage_that_raises_yields_a_stated_reason_and_exit_zero(self, tmp_path, monkeypatch):
        """The last-resort guard: advisory must hold even against a defect the other
        tests did not foresee. The exception's text — which could carry a path — is
        not repeated; its type is."""
        repo = _project_repo(tmp_path, monkeypatch)

        def _boom(*_a, **_k):
            raise RuntimeError(f"secret {tmp_path}")
        monkeypatch.setattr(core, "resolve_window", _boom)

        rc, out = _run(["change-summary", "--root", str(repo)])

        assert rc == 0
        assert _lines(out) == ["digest unavailable (RuntimeError); nothing to summarise"]
        assert str(tmp_path) not in out

    def test_a_project_check_that_fails_is_not_reported_as_not_a_project(
        self, tmp_path, monkeypatch, caplog,
    ):
        """A permission error on the check is a fact about the machine; "not a Studio
        project" is a fact about the directory. Folding one into the other sent a
        developer on a flaky mount looking for a missing project — and the only trace
        was a debug line nobody sees."""
        def _boom(*_a, **_k):
            raise OSError("permission denied on /secret/mount")
        monkeypatch.setattr(cmd, "find_studio_directory", _boom)

        with caplog.at_level("WARNING", logger="studio"):
            reason = cmd._project_gate(tmp_path)

        assert reason == f"{cmd.REASON_PROJECT_UNCHECKED} (OSError)"
        assert reason != core.REASON_NOT_A_PROJECT
        assert any(r.levelname == "WARNING" and "could not check" in r.getMessage()
                   for r in caplog.records), "surfaced, not buried at debug"
        assert "/secret/mount" not in reason, "the type, not the message — it can carry a path"

    def test_a_failed_project_check_still_exits_zero_with_its_reason(self, tmp_path, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("unreadable")
        monkeypatch.setattr(cmd, "find_studio_directory", _boom)

        rc, lines = _digest(tmp_path)

        assert rc == 0
        assert lines == [f"{cmd.REASON_PROJECT_UNCHECKED} (OSError): nothing to summarise"]


# ------------------------------------------------------------------- registration

class TestRegistrationAndTheAdvisoryContract:

    def test_the_command_is_registered_in_every_dispatch_table(self):
        assert "change-summary" in cli._COMMAND_DESCRIPTIONS
        assert any("change-summary" in names for _, names in cli._COMMAND_SECTIONS)
        assert cli._COMMAND_HANDLERS["change-summary"] == "_cmd_change_summary"
        assert cli._cmd_change_summary in cli._COMMAND_HANDLER_REFERENCES, "dead-code scanners need this"
        assert "change-summary" in cli._ALL_COMMANDS

    def test_the_command_is_wired_into_no_gate(self):
        """An advisory found inside a gate is the exact failure this command promised
        not to ship, so the promise is checked structurally rather than recorded.

        The file set is **discovered, not listed**: everything under `.github`, at any
        depth and whatever the extension, plus the Makefile and any pre-commit config.
        Enumerating `workflows/*.yml` meant a gate added as a composite action, a nested
        workflow, or a `settings.yml` naming required checks would never be scanned and
        this test would stay green while the command was wired — the failure it exists
        to catch, one directory over.

        **Both spellings are rejected.** The CLI name cannot reach a gate without
        `change-summary`, but the module can: `python -m studio.commands.change_summary`
        invokes it just as well, and only the hyphen was checked.

        What this cannot cover, stated rather than implied: GitHub's branch protection
        and rulesets are account-side configuration, not repository text, so no test in
        this repository can assert on the required-status-check list. `pyproject.toml`
        is likewise out of scope by intent — it declares tool configuration rather than
        gate invocations, and its coverage and vulture sections name modules
        legitimately, so scanning it would fail on a benign entry.
        """
        root = Path(__file__).resolve().parents[1]
        github = root / ".github"
        gate_files = [
            *(p for p in [root / "Makefile"] if p.exists()),
            *sorted(p for p in github.rglob("*") if p.is_file()),
            *(p for p in root.glob(".pre-commit-config.y*ml") if p.is_file()),
        ]
        names = {p.name for p in gate_files}
        assert "Makefile" in names, "the Makefile must be scanned"
        assert any(p.parent.name == "workflows" for p in gate_files), "workflows must be scanned"

        for path in gate_files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for spelling in ("change-summary", "change_summary"):
                assert spelling not in text, f"{path} wires {spelling}"

    def test_help_names_the_heuristics_that_shape_the_output(self, capsys):
        """A user who only reads --help would otherwise take an excluded file or a
        capped change set for a bug."""
        with pytest.raises(SystemExit) as exit_info:
            cmd.cmd_change_summary(["--help"])

        assert exit_info.value.code == 0
        text = " ".join(capsys.readouterr().out.split())   # argparse re-wraps the epilog
        for phrase in ("scope policy", "untracked files included", "examined",
                       "references or declares", "decision log", f"{cmd.LINE_CEILING} lines"):
            assert phrase in text, phrase

    @pytest.mark.parametrize("argv", [[], ["--base", "upstream/main"], ["--since", "2026-01-01T00:00:00+00:00"]])
    def test_every_accepted_invocation_exits_zero(self, argv, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)

        rc, _ = _run(["change-summary", "--root", str(repo), *argv])

        assert rc == 0
