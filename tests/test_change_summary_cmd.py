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
            f"window: since upstream/main @ {base} ({since})",
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

    def test_the_ceiling_is_enforced_on_the_real_path(self, tmp_path, monkeypatch):
        """Lowered, so the real digest overflows; the arithmetic is tested above."""
        repo = _project_repo(tmp_path, monkeypatch)
        monkeypatch.setattr(cmd, "LINE_CEILING", 3)

        rc, data = _payload(repo)

        assert rc == 0
        assert len(data["lines"]) == 3
        assert data["omitted"] == 4
        assert data["lines"][-1] == "(+4 more line(s) omitted; --json carries everything)"

    def test_no_line_is_emitted_without_data_behind_it(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)

        _, lines = _digest(repo)

        assert not any(line.startswith("decision log:") for line in lines), "nothing was skipped or undated"
        assert not any(line.startswith("changes: scan capped") for line in lines)
        assert all(lines), "no blank lines"

    def test_requirements_are_capped_and_counted_not_truncated_silently(self):
        ids = [f"cpt-x-{i}" for i in range(7)]

        line = cmd._requirements_line(ids)

        assert line == "requirements: cpt-x-0, cpt-x-1, cpt-x-2, cpt-x-3, cpt-x-4 (+2 more)"
        assert cmd._requirements_line([]) is None


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

    def test_telemetry_and_own_invocations_are_not_decisions(self):
        selection = core.EventSelection(
            events=(
                _event("2026-06-01T00:00:00+00:00", "r1", "validation"),
                _event("2026-06-01T00:00:01+00:00", "r1", "read"),
                {**_event("2026-06-01T00:00:02+00:00", "r9", "invocation"), "command": "change-summary"},
            ),
            runs=("r1", "r9"), available=True, reason=core.REASON_OK,
        )

        lines = cmd._decision_lines(selection)
        payload = cmd._decisions_payload(selection)

        assert lines == ["why: 1 decision(s) in 1 run(s): validation ×1", "runs: r1 ×1"]
        assert payload["events"] == 2, "the read stays; the digest's own invocation is gone"
        assert payload["decisions"] == 1
        assert payload["runs"] == [{"run_id": "r1", "decisions": 1}]

    def test_a_window_with_only_telemetry_says_so_with_its_denominator(self):
        selection = core.EventSelection(
            events=(_event("2026-06-01T00:00:00+00:00", "r1", "invocation"),),
            runs=("r1",), available=True, reason=core.REASON_OK,
        )

        assert cmd._decision_lines(selection) == [
            "why: no decisions recorded in this window (1 event(s) scanned)",
        ]


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
            "3 excluded by the project's scope policy; 1 deleted; 1 could not be read or parsed; "
            "1 not regular files",
            "markers: 0 of 9 changed files carry requirement markers",
        ]

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
            events=(), runs=(), undated=2, skipped_lines=1, log_overridden=True,
            available=True, reason=core.REASON_OK,
        )

        assert cmd._decision_lines(selection) == [
            "why: no decisions recorded in this window (0 event(s) scanned)",
            "decision log: 1 unparseable line(s) skipped",
            "decision log: 2 undated event(s) excluded",
            "decision log: shared via CFS_DECISION_LOG; decisions are not attributable to this project",
        ]

    def test_the_window_line_names_its_source(self):
        assert cmd._window_line(core.ChangeWindow(
            base_ref="upstream/main", base_sha="0123456789ab", since="2026-01-01T00:00:00+00:00",
            available=True, reason=core.REASON_OK,
        )) == "window: since upstream/main @ 01234567 (2026-01-01T00:00:00+00:00)"
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

    def test_no_output_carries_a_path_home_user_or_author(self, tmp_path, monkeypatch):
        repo = _project_repo(tmp_path, monkeypatch)
        home = os.path.expanduser("~")
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""

        _, human = _run(["change-summary", "--root", str(repo)])
        _, as_json = _run(["change-summary", "--json", "--root", str(repo)])

        for text in (human, as_json):
            assert str(tmp_path) not in text, "no absolute path, in either rendering"
            assert home not in text
            if user and user not in MARKER:
                assert not re.search(rf"\b{re.escape(user)}\b", text)
            assert "Test User" not in text and "test@example.com" not in text, "no commit author"


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
        not to ship, so the promise is checked structurally rather than recorded: the
        Makefile, every workflow file, and any pre-commit configuration."""
        root = Path(__file__).resolve().parents[1]
        workflows = root / ".github" / "workflows"
        gate_files = [
            root / "Makefile",
            *sorted(workflows.glob("*.yml")), *sorted(workflows.glob("*.yaml")),
            *(p for p in (root / ".pre-commit-config.yaml", root / ".pre-commit-config.yml") if p.exists()),
        ]
        assert len(gate_files) >= 2, "the Makefile and at least one workflow must be scanned"
        for path in gate_files:
            assert "change-summary" not in path.read_text(encoding="utf-8"), path

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
