"""Tests for the change-summary core — window resolution and event selection.

The module's whole contract is *never raise, never go silent*: every failure path
returns a value carrying a reason. So these tests are weighted toward forcing each
failure rather than confirming the happy path, and several assert on the *reason*
rather than merely on emptiness — an empty result with the wrong explanation is the
defect this feature exists to remove.
"""

from __future__ import annotations

import dataclasses
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from studio.utils import change_summary as cs
from studio.utils import decision_log


# --------------------------------------------------------------------------- helpers

def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _make_repo(repo: Path) -> Path:
    """A minimal repo with one commit and deterministic identity."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


def _commit(repo: Path, name: str, body: str = "x\n") -> str:
    (repo / name).write_text(body, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}")
    return _git(repo, "rev-parse", "HEAD")


def _point_ref(repo: Path, ref: str, sha: str) -> None:
    """Create a remote-tracking ref without needing a real remote."""
    _git(repo, "update-ref", ref, sha)


def _make_studio_project(root: Path) -> Path:
    """A directory the real project/studio resolvers recognise.

    `find_project_root` wants the `@cf:root-agents` marker in AGENTS.md, and
    `find_studio_directory` then reads the `studio` key from its TOML block.
    """
    (root / ".studio" / "rules").mkdir(parents=True)
    (root / "AGENTS.md").write_text(
        '<!-- @cf:root-agents -->\n\n```toml\nstudio = ".studio"\n```\n', encoding="utf-8",
    )
    (root / ".studio" / "AGENTS.md").write_text("# studio\n", encoding="utf-8")
    return root


def _write_log(path: Path, rows: list, extra: str = "") -> Path:
    body = "".join(json.dumps(r) + "\n" for r in rows) + extra
    path.write_text(body, encoding="utf-8")
    return path


def _event(ts: str, run_id: str = "r1", event: str = "validation") -> dict:
    return {"schema": 1, "ts": ts, "run_id": run_id, "decision_id": "d",
            "event": event, "command": "validate", "payload": {}}


# --------------------------------------------------------------------------- window

class TestTheWindowComesFromGit:

    def test_a_repo_with_a_base_ref_yields_a_window(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        base = _git(repo, "rev-parse", "HEAD")
        _point_ref(repo, "refs/remotes/upstream/main", base)
        _commit(repo, "b.txt")

        window = cs.resolve_window(repo)

        assert window.available is True
        assert window.reason == cs.REASON_OK
        assert window.base_ref == "upstream/main"
        assert window.base_sha == base
        assert window.since  # the base commit's own time

    def test_an_explicit_since_short_circuits_git_entirely(self):
        # A path that is not a repo, and does not exist: proof no git call is needed.
        window = cs.resolve_window(Path("/nonexistent-abc"), since="2026-01-01T00:00:00+00:00")

        assert window.available is True
        assert window.since == "2026-01-01T00:00:00+00:00"
        assert window.base_ref == ""

    def test_an_explicit_base_ref_is_honoured(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        base = _git(repo, "rev-parse", "HEAD")
        _git(repo, "branch", "release")
        _commit(repo, "b.txt")

        window = cs.resolve_window(repo, base="release")

        assert window.base_ref == "release"
        assert window.base_sha == base

    def test_an_unknown_explicit_base_ref_is_refused_not_swapped(self, tmp_path):
        """The mutation that matters: a default ref exists, so a fallback would 'work'."""
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))

        window = cs.resolve_window(repo, base="no-such-ref")

        assert window.available is False
        assert window.reason == cs.REASON_BASE_REF_UNKNOWN
        # Must NOT have silently measured against the discoverable default.
        assert window.base_ref == ""

    def test_the_canonical_remote_is_preferred_over_a_lagging_fork(self, tmp_path):
        """In a fork workflow origin is the contributor's fork and lags upstream.

        Preferring origin/HEAD would widen the window to include long-shipped work.
        """
        repo = _make_repo(tmp_path / "r")
        old = _git(repo, "rev-parse", "HEAD")
        newer = _commit(repo, "b.txt")
        _commit(repo, "c.txt")
        _point_ref(repo, "refs/remotes/origin/HEAD", old)       # the stale fork
        _point_ref(repo, "refs/remotes/upstream/main", newer)    # the canonical remote

        window = cs.resolve_window(repo)

        assert window.base_ref == "upstream/main"
        assert window.base_sha == newer

    def test_the_canonical_remotes_own_default_wins_even_when_unnamed(self, tmp_path):
        """A remote whose default is neither main nor master, e.g. trunk.

        Guessing branch names first would skip the symbolic upstream/HEAD and fall
        through to the stale fork ref — the same bug one level deeper.
        """
        repo = _make_repo(tmp_path / "r")
        old = _git(repo, "rev-parse", "HEAD")
        newer = _commit(repo, "b.txt")
        _commit(repo, "c.txt")
        _point_ref(repo, "refs/remotes/origin/HEAD", old)          # stale fork
        _point_ref(repo, "refs/remotes/upstream/trunk", newer)     # unconventional name
        _git(repo, "symbolic-ref", "refs/remotes/upstream/HEAD", "refs/remotes/upstream/trunk")

        window = cs.resolve_window(repo)

        assert window.base_ref == "upstream/HEAD"
        assert window.base_sha == newer, "must not fall through to the stale fork ref"


class TestTheWindowSaysWhyItCouldNotBeBuilt:

    def test_a_non_repo_is_reported_not_crashed(self, tmp_path):
        window = cs.resolve_window(tmp_path)

        assert window.available is False
        assert window.reason == cs.REASON_NOT_A_REPO

    def test_git_unavailable_is_distinguished_from_not_a_repo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cs, "_git_query", lambda *_a, **_k: (None, True))

        window = cs.resolve_window(tmp_path)

        assert window.reason == cs.REASON_GIT_UNAVAILABLE

    def test_no_discoverable_base_ref_is_reported(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        # Rename the only branch to something none of the candidates match.
        _git(repo, "branch", "-m", "wip-nothing-standard")

        window = cs.resolve_window(repo)

        assert window.available is False
        assert window.reason == cs.REASON_NO_BASE_REF

    def test_unrelated_histories_have_no_merge_base(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        monkeypatch.setattr(cs, "_merge_base", lambda *_a, **_k: (None, False))

        window = cs.resolve_window(repo)

        assert window.available is False
        assert window.reason == cs.REASON_NO_MERGE_BASE
        assert window.base_ref == "upstream/main"   # what we did learn is still reported

    def test_a_base_commit_without_a_readable_time_is_reported(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        monkeypatch.setattr(cs, "_commit_time", lambda *_a, **_k: (None, False))

        window = cs.resolve_window(repo)

        assert window.reason == cs.REASON_NO_BASE_TIME
        assert window.base_sha  # still reported

    def test_the_reason_list_has_no_enumerated_ref_names(self):
        """The first version of this string listed the refs it tried and went stale."""
        assert "origin" not in cs.REASON_NO_BASE_REF
        assert "main" not in cs.REASON_NO_BASE_REF


# --------------------------------------------------------------------------- events

class TestEventSelection:

    def test_events_before_the_boundary_are_excluded(self, tmp_path):
        window = cs.ChangeWindow(since="2026-06-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [
            _event("2026-05-31T23:59:59+00:00", "old"),
            _event("2026-06-02T00:00:00+00:00", "new"),
        ])

        selection = cs.select_events(window, path=log)

        assert selection.available is True
        assert [e["run_id"] for e in selection.events] == ["new"]
        assert selection.scanned == 2

    def test_an_event_exactly_at_the_boundary_is_included(self, tmp_path):
        boundary = "2026-06-01T00:00:00+00:00"
        window = cs.ChangeWindow(since=boundary, available=True)
        log = _write_log(tmp_path / "d.jsonl", [_event(boundary, "edge")])

        selection = cs.select_events(window, path=log)

        assert len(selection.events) == 1, "the branch point itself belongs to the window"

    def test_a_z_suffix_and_an_offset_compare_correctly(self, tmp_path):
        window = cs.ChangeWindow(since="2026-06-01T00:00:00Z", available=True)
        log = _write_log(tmp_path / "d.jsonl", [
            _event("2026-06-01T01:00:00+02:00", "before"),   # 23:00 previous day UTC
            _event("2026-06-01T03:00:00+02:00", "after"),    # 01:00 UTC
        ])

        selection = cs.select_events(window, path=log)

        assert [e["run_id"] for e in selection.events] == ["after"]

    def test_unparseable_lines_are_counted_not_hidden(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(
            tmp_path / "d.jsonl",
            [_event("2026-06-01T00:00:00+00:00")],
            extra="{ this is not json\n\n[]\n",
        )

        selection = cs.select_events(window, path=log)

        assert selection.skipped_lines >= 1, "corruption must be reported, not swallowed"

    def test_undated_events_are_excluded_and_counted(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        rows = [
            _event("2026-06-01T00:00:00+00:00", "dated"),
            {"schema": 1, "run_id": "no-ts", "event": "validation", "payload": {}},
            _event("not-a-timestamp", "bad-ts"),
        ]
        log = _write_log(tmp_path / "d.jsonl", rows)

        selection = cs.select_events(window, path=log)

        assert [e["run_id"] for e in selection.events] == ["dated"]
        assert selection.undated == 2, "cannot-tell is counted, never guessed either way"

    def test_a_naive_timestamp_is_refused_rather_than_assumed_utc(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00", "naive")])

        selection = cs.select_events(window, path=log)

        assert selection.events == ()
        assert selection.undated == 1

    def test_runs_preserve_first_seen_order(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [
            _event("2026-06-01T00:00:01+00:00", "second"),
            _event("2026-06-01T00:00:02+00:00", "first"),
            _event("2026-06-01T00:00:03+00:00", "second"),
        ])

        selection = cs.select_events(window, path=log)

        assert selection.runs == ("second", "first"), "first-seen order, not sorted"

    def test_the_scanned_count_is_reported_even_when_nothing_is_selected(self, tmp_path):
        window = cs.ChangeWindow(since="2026-12-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [
            _event("2026-06-01T00:00:00+00:00"), _event("2026-06-02T00:00:00+00:00"),
        ])

        selection = cs.select_events(window, path=log)

        assert selection.events == ()
        assert selection.scanned == 2, "a verdict without its denominator is the defect"


class TestEventSelectionSaysWhyItCouldNotRead:

    def test_an_unavailable_window_propagates_exactly_one_reason(self, tmp_path):
        window = cs.resolve_window(tmp_path)   # not a repo

        selection = cs.select_events(window)

        assert selection.available is False
        assert selection.reason == window.reason, "one cause reported, not two"

    def test_a_disabled_log_is_reported(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CFS_DECISION_LOG", "0")
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=tmp_path / "d.jsonl")

        assert selection.reason == cs.REASON_LOG_DISABLED

    def test_an_absent_log_is_reported(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=tmp_path / "never-written.jsonl")

        assert selection.reason == cs.REASON_LOG_ABSENT

    def test_outside_a_studio_project_is_reported(self, monkeypatch):
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        monkeypatch.setattr(decision_log, "default_log_path", lambda: None)
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window)

        assert selection.reason == cs.REASON_NOT_A_PROJECT

    def test_a_hand_built_window_with_an_unparseable_bound_still_degrades(self, tmp_path):
        """`resolve_window` now rejects a bad `since` up front, so this can only be
        reached by constructing a window directly. The guard stays as the floor beneath
        that, but it is no longer the path a caller passing `since` takes — see
        `TestAnExplicitSinceIsValidatedUpFront`, which is where that case belongs.
        """
        window = cs.ChangeWindow(since="nonsense", available=True)
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])

        selection = cs.select_events(window, path=log)

        assert selection.available is False
        assert selection.reason == cs.REASON_NO_BASE_TIME


# --------------------------------------------------------------------- fail-safe

class TestNothingRaises:

    def test_a_git_timeout_degrades(self, tmp_path, monkeypatch):
        def _boom(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)
        monkeypatch.setattr(cs.subprocess, "run", _boom)

        assert cs._git_query(tmp_path, ["status"]) == (None, True)

    def test_an_oserror_from_git_degrades(self, tmp_path, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("no exec")
        monkeypatch.setattr(cs.subprocess, "run", _boom)

        window = cs.resolve_window(tmp_path)

        assert window.available is False
        assert window.reason == cs.REASON_GIT_UNAVAILABLE

    def test_an_existing_but_unreadable_log_is_never_an_available_empty_selection(self, tmp_path):
        """The false green: is_file() passes on mode 000, and read_events swallows the
        open failure and yields nothing — so this reported "no decisions" having read
        none. Regression for the exact defect class this module exists to prevent."""
        if os.name == "nt":
            pytest.skip("POSIX permission bits do not apply on Windows")
        if os.geteuid() == 0:
            pytest.skip("root bypasses file permissions")
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])
        log.chmod(0o000)
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        try:
            selection = cs.select_events(window, path=log)
        finally:
            log.chmod(0o644)

        assert selection.available is False, "unreadable must not present as an empty window"
        assert selection.reason == cs.REASON_LOG_UNREADABLE
        assert selection.events == ()

    def test_hostile_event_shapes_do_not_raise(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = tmp_path / "d.jsonl"
        log.write_text(
            json.dumps({"ts": 12345, "run_id": None}) + "\n"
            + json.dumps({"ts": ["list"], "run_id": {"d": 1}}) + "\n"
            + json.dumps("a bare string") + "\n",
            encoding="utf-8",
        )

        selection = cs.select_events(window, path=log)

        assert selection.available is True
        assert selection.events == ()


# ---------------------------------------------------------------------- invariants

class TestInvariants:

    @pytest.mark.parametrize("reason_name", [
        n for n in dir(cs) if n.startswith("REASON_") and n != "REASON_OK"
    ])
    def test_every_reason_is_human_readable_prose(self, reason_name):
        value = getattr(cs, reason_name)
        assert isinstance(value, str) and value
        assert value == value.lower() or value[0].islower(), "reason reads as prose, not a code"

    def test_an_unavailable_result_always_carries_a_reason(self, tmp_path):
        for result in (cs.resolve_window(tmp_path), cs.select_events(cs.ChangeWindow())):
            assert result.available is False
            assert result.reason, "unavailable without a reason is the silent failure"

    def test_an_available_window_carries_no_reason(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))

        assert cs.resolve_window(repo).reason == cs.REASON_OK


class TestPrivacy:

    def test_no_reason_string_leaks_a_path_home_or_username(self):
        import os
        home = os.path.expanduser("~")
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
        for name in dir(cs):
            if not name.startswith("REASON_"):
                continue
            value = getattr(cs, name)
            assert os.sep not in value, f"{name} contains a path separator"
            assert home not in value
            if user:
                assert user not in value

    def test_this_process_opens_no_socket(self, tmp_path, monkeypatch):
        """Scope stated honestly: patching `socket` covers **this** process only. It
        says nothing about what the `git` child does, so the companion test below
        checks the git side by a different means."""
        def _no_sockets(*_a, **_k):
            raise AssertionError("change_summary must not open a socket")
        monkeypatch.setattr(socket, "socket", _no_sockets)

        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        window = cs.resolve_window(repo)
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])

        assert window.available is True
        assert cs.select_events(window, path=log).available is True

    def test_no_git_subcommand_can_reach_a_remote(self, tmp_path, monkeypatch):
        """The git side of the no-network claim, which the socket patch above cannot
        observe: a child process has its own sockets. Rather than pretending to watch
        them, this asserts the only thing that actually matters — every subcommand
        issued is a local read, so none of them has a remote to reach."""
        remote_capable = {
            "fetch", "pull", "push", "clone", "remote", "ls-remote",
            "submodule", "archive", "bundle", "daemon", "send-pack", "fetch-pack",
        }
        issued: list = []

        def _capture(args, **_kwargs):
            issued.append(list(args))
            raise OSError("not run")

        # The repo is built first: `subprocess` is shared, so patching it before the
        # fixture would intercept the fixture's own git calls.
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        window = cs.ChangeWindow(
            project_root=str(repo), base_sha=_git(repo, "rev-parse", "HEAD"),
            since="2026-01-01T00:00:00+00:00", available=True,
        )

        monkeypatch.setattr(cs.subprocess, "run", _capture)
        cs.resolve_window(repo)
        # The linkage half lives in a later change; exercise it when present so this
        # test covers every git call site on whichever branch it runs. It takes its
        # root from the window, which is why the window above carries one.
        linker = getattr(cs, "link_changed_files", None)
        if linker is not None:
            linker(window)

        assert issued, "the helper must actually have been exercised"
        for argv in issued:
            subcommand = argv[1] if len(argv) > 1 else ""
            assert subcommand not in remote_capable, f"remote-capable: {subcommand}"


class TestDeterminism:

    def test_the_same_state_yields_identical_results(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        _commit(repo, "b.txt")
        log = _write_log(tmp_path / "d.jsonl", [
            _event("2026-06-01T00:00:00+00:00", "a"), _event("2026-06-02T00:00:00+00:00", "b"),
        ])

        windows, selections = [], []
        for _ in range(5):
            window = cs.resolve_window(repo)
            windows.append(window)
            selections.append(cs.select_events(window, path=log))

        assert len({(w.base_ref, w.base_sha, w.since) for w in windows}) == 1
        assert len({(tuple(s.runs), s.scanned, s.undated) for s in selections}) == 1


class TestTheLogIsBoundToTheWindowsProject:
    """A window and its events must describe the same project.

    `resolve_window` takes an explicit root; `decision_log.default_log_path()` defaults
    to the cwd. Those are independent inputs, so a window for project A resolved while
    the process sat in project B used to select B's decisions — one project's changes
    reported alongside another's history.
    """

    def test_the_default_log_follows_the_window_not_the_cwd(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        window = cs.resolve_window(repo)
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        seen = {}

        def _record(start=None):
            seen["start"] = start
            return tmp_path / "log.jsonl"

        monkeypatch.setattr(decision_log, "default_log_path", _record)
        cs._default_log_for(window)

        assert seen["start"] == Path(window.project_root), "the window's root, not the cwd"

    def test_the_window_records_the_project_it_describes(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))

        assert cs.resolve_window(repo).project_root == str(repo)

    def test_even_an_unavailable_window_records_its_project(self, tmp_path):
        """Provenance must not depend on success, or a failure reason loses its subject."""
        assert cs.resolve_window(tmp_path).project_root == str(tmp_path)

    def test_a_rootless_window_still_falls_back_to_the_cwd_default(self, monkeypatch):
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        monkeypatch.setattr(decision_log, "default_log_path", lambda start=None: None)

        assert cs._default_log_for(cs.ChangeWindow(available=True)) == (None, False)

    def test_the_real_resolver_finds_the_windows_project_from_another_cwd(
        self, tmp_path, monkeypatch,
    ):
        """The earlier test patched `default_log_path`, so it proved the root was
        *passed* — not that passing it works. This drives the real resolver against two
        genuine Studio projects with the process standing in the wrong one."""
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        wanted = _make_studio_project(tmp_path / "wanted")
        other = _make_studio_project(tmp_path / "other")
        monkeypatch.chdir(other)

        resolved, _overridden = cs._default_log_for(
            cs.ChangeWindow(project_root=str(wanted), available=True),
        )

        assert resolved is not None
        assert wanted.resolve() in resolved.parents, "the window's project, not the cwd's"
        assert other.resolve() not in resolved.parents

    def test_a_root_that_is_not_a_studio_project_is_reported(self, tmp_path, monkeypatch):
        """The non-empty-root branch: a root was recorded, but it is not a project."""
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        window = cs.ChangeWindow(
            project_root=str(tmp_path), since="2026-01-01T00:00:00+00:00", available=True,
        )

        selection = cs.select_events(window)

        assert selection.available is False
        assert selection.reason == cs.REASON_NOT_A_PROJECT


class TestTheAnswerDoesNotDependOnWhereTheProcessStands:
    """The window carries its project so the log cannot come from the cwd. That only
    holds if the recorded root is absolute — a relative one reintroduces the exact
    dependence, since both `default_log_path` and `subprocess(cwd=...)` resolve at use
    time rather than at capture time."""

    def test_a_relative_root_is_stored_resolved(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        monkeypatch.chdir(repo)

        window = cs.resolve_window(Path("."))

        assert Path(window.project_root).is_absolute()
        assert Path(window.project_root) == repo.resolve()

    def test_a_window_survives_a_later_chdir(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        monkeypatch.chdir(repo)
        window = cs.resolve_window(Path("."))

        monkeypatch.chdir(tmp_path)          # the process moves after capture

        assert Path(window.project_root) == repo.resolve(), "the recorded root must not move"

    def test_an_ambient_git_dir_cannot_redirect_the_query(self, tmp_path, monkeypatch):
        """`cwd=` alone is not enough: GIT_DIR overrides it, so a query about one
        project could be answered from another's repository."""
        here = _make_repo(tmp_path / "here")
        elsewhere = _make_repo(tmp_path / "elsewhere")
        # The two repositories must be genuinely distinguishable. `_make_repo` writes
        # identical content with a fixed identity, so two repos created in the same
        # second produce the *same* commit sha — which made the first version of this
        # test unfalsifiable: it compared a value against its own twin and passed
        # whether or not the redirect had been neutralised. A distinct commit in the
        # decoy is what gives the assertion something to fail on.
        _commit(elsewhere, "decoy.txt", "different content\n")

        # Both shas are captured *before* the redirect is installed. Reading the
        # expected value afterwards would route the test's own helper through the very
        # mechanism under test, comparing wrong against wrong.
        expected = _git(here, "rev-parse", "HEAD")
        decoy = _git(elsewhere, "rev-parse", "HEAD")
        assert expected != decoy, "fixture precondition: the repositories must differ"
        _point_ref(here, "refs/remotes/upstream/main", expected)
        monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))

        window = cs.resolve_window(here)

        assert window.available is True
        assert window.base_sha == expected, "answered from `here`"
        assert window.base_sha != decoy, "and not from the redirect target"

    def test_the_sanitised_environment_drops_every_redirect_variable(self, monkeypatch):
        for name in cs._GIT_REDIRECT_VARS:
            monkeypatch.setenv(name, "/somewhere/else")

        env = cs._git_env()

        assert not [n for n in cs._GIT_REDIRECT_VARS if n in env]
        assert "PATH" in env, "the rest of the environment is preserved"


class TestCallerValuesCannotBecomeGitOptions:

    def test_a_ref_beginning_with_a_dash_is_treated_as_a_ref(self, tmp_path):
        """Without `--end-of-options` git reads this as an option, so the failure is
        an argument error rather than an honest "no such ref"."""
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))

        window = cs.resolve_window(repo, base="--upload-pack=touch /tmp/pwned")

        assert window.available is False
        assert window.reason == cs.REASON_BASE_REF_UNKNOWN, "refused as a ref, not as an option"

    def test_a_ref_containing_nul_is_refused_not_raised(self, tmp_path):
        """`subprocess` raises ValueError for an embedded NUL before git starts —
        outside the git helper's handler, so this escaped the never-raises contract."""
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))

        window = cs.resolve_window(repo, base="main\x00")

        assert window.available is False
        assert window.reason == cs.REASON_BASE_REF_UNKNOWN, "a ref that cannot exist"

    def test_every_option_bearing_call_separates_its_operands(self):
        """A structural check, so a new call site that interpolates a caller value
        without the separator is caught here rather than in review."""
        import inspect
        source = inspect.getsource(cs)
        required = ['"--verify", "--quiet", "--end-of-options"',
                    '["merge-base", "--end-of-options"',
                    '"--format=%cI", "--end-of-options"']
        if "_git_records" in source:
            # Only present once the linkage half lands.
            required.append('"--name-status", "-z", "--end-of-options"')
        for fragment in required:
            assert fragment in source, f"missing separator: {fragment}"


class TestGitFailureIsNotAConclusionAboutHistory:
    """After the repo probe succeeds, a later git failure must not be reported as a
    finding about the branch. "No merge base" and "git timed out" are different facts."""

    def test_a_tool_failure_during_merge_base_reports_git_not_history(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        monkeypatch.setattr(cs, "_merge_base", lambda *_a, **_k: (None, True))

        window = cs.resolve_window(repo)

        assert window.reason == cs.REASON_GIT_UNAVAILABLE
        assert window.reason != cs.REASON_NO_MERGE_BASE

    def test_a_genuine_absence_of_a_merge_base_still_says_so(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        monkeypatch.setattr(cs, "_merge_base", lambda *_a, **_k: (None, False))

        assert cs.resolve_window(repo).reason == cs.REASON_NO_MERGE_BASE

    def test_a_tool_failure_reading_the_base_time_reports_git(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        monkeypatch.setattr(cs, "_commit_time", lambda *_a, **_k: (None, True))
        window = cs.resolve_window(repo)

        assert window.reason == cs.REASON_GIT_UNAVAILABLE
        assert window.base_sha, "what was already learned is still reported"

    def test_a_non_zero_exit_is_a_valid_negative_not_a_tool_failure(self, tmp_path):
        """`merge-base` and `rev-parse --verify` exit non-zero to mean "no" — treating
        that as breakage would mislead in the opposite direction."""
        repo = _make_repo(tmp_path / "r")

        value, failed = cs._git_query(repo, ["rev-parse", "--verify", "--quiet", "nope"])

        assert value is None
        assert failed is False

    def test_git_not_launching_is_a_tool_failure(self, tmp_path, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("no git")
        monkeypatch.setattr(cs.subprocess, "run", _boom)

        assert cs._git_query(tmp_path, ["status"]) == (None, True)


class TestAnExplicitSinceIsValidatedUpFront:
    """A caller-supplied bound is the caller's input, so a complaint about it must name
    that input. Accepting it and failing later produced a reason about a base commit
    that was never consulted."""

    @pytest.mark.parametrize("bad", [
        "nonsense", "", "2026-13-99T00:00:00+00:00", "not-a-time",
    ])
    def test_an_unparseable_bound_never_yields_an_available_window(self, bad, tmp_path):
        window = cs.resolve_window(tmp_path, since=bad)

        assert window.available is False
        if bad:
            assert window.reason == cs.REASON_INVALID_SINCE

    def test_a_naive_bound_is_refused_rather_than_assumed_utc(self, tmp_path):
        """Guessing an offset would silently shift the window boundary."""
        window = cs.resolve_window(tmp_path, since="2026-06-01T00:00:00")

        assert window.available is False
        assert window.reason == cs.REASON_INVALID_SINCE

    def test_a_valid_bound_still_short_circuits_git(self):
        window = cs.resolve_window(Path("/nonexistent-abc"), since="2026-01-01T00:00:00+00:00")

        assert window.available is True
        assert window.reason == cs.REASON_OK


class TestBaseRefLookupPreservesTheGitDiagnosis:
    """The previous round fixed this for merge-base and commit-time but left base-ref
    lookup on the value-only helper, so two of three stages were covered."""

    def test_a_tool_failure_on_an_explicit_ref_reports_git(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        monkeypatch.setattr(cs, "_git_query", lambda *_a, **_k: (None, True))
        monkeypatch.setattr(cs, "_detect_repo", lambda *_a, **_k: cs.REASON_OK)

        window = cs.resolve_window(repo, base="release")

        assert window.reason == cs.REASON_GIT_UNAVAILABLE
        assert window.reason != cs.REASON_BASE_REF_UNKNOWN

    def test_a_tool_failure_on_the_default_ref_reports_git(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        monkeypatch.setattr(cs, "_git_query", lambda *_a, **_k: (None, True))
        monkeypatch.setattr(cs, "_detect_repo", lambda *_a, **_k: cs.REASON_OK)

        window = cs.resolve_window(repo)

        assert window.reason == cs.REASON_GIT_UNAVAILABLE
        assert window.reason != cs.REASON_NO_BASE_REF

    def test_a_genuinely_missing_explicit_ref_still_says_so(self, tmp_path):
        repo = _make_repo(tmp_path / "r")

        assert cs.resolve_window(repo, base="no-such").reason == cs.REASON_BASE_REF_UNKNOWN

    def test_the_default_walk_stops_at_the_first_tool_failure(self, tmp_path, monkeypatch):
        """Walking the remaining candidates after a launch failure would report a fact
        about the repository that was never established."""
        repo = _make_repo(tmp_path / "r")
        calls = []

        def _fail(_root, args):
            calls.append(args)
            return None, True

        monkeypatch.setattr(cs, "_git_query", _fail)
        monkeypatch.setattr(cs, "_detect_repo", lambda *_a, **_k: cs.REASON_OK)
        cs.resolve_window(repo)

        assert len(calls) == 1, "one attempt, not one per candidate ref"


class TestTheLogIsReadExactlyOnce:
    """Readability, the events and the line count come from one read of the file.

    Separate reads let two things go wrong. A valid line appended between the event
    read and the line count made the count exceed the events, so ordinary concurrent
    logging was reported as corruption. A rotation between the readability probe and
    the event read swapped the verified file for a fresh near-empty one, and the
    selection came back clean and almost empty with no sign anything had moved.
    """

    def test_the_log_is_opened_exactly_once(self, tmp_path, monkeypatch):
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])
        real_open = Path.open
        opens = []

        def _counting(self, *args, **kwargs):
            if self == log:
                opens.append(args)
            return real_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", _counting)
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=log)

        assert selection.available is True
        assert len(opens) == 1, "a second open is a gap for the file to change in"

    def test_a_line_appended_during_selection_is_not_reported_as_corruption(
        self, tmp_path, monkeypatch,
    ):
        """With separate reads the line count saw the new line and the events did not,
        so `skipped_lines` reported normal concurrent activity as corruption."""
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])
        real_parse = decision_log.parse_events

        def _append_then_parse(lines):
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(_event("2026-06-01T00:00:01+00:00", "late")) + "\n")
            return real_parse(lines)

        monkeypatch.setattr(decision_log, "parse_events", _append_then_parse)
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=log)

        assert selection.skipped_lines == 0
        assert selection.scanned == 1, "the snapshot, not the file as it is now"

    def test_a_rotation_during_selection_cannot_swap_the_file_under_the_read(
        self, tmp_path, monkeypatch,
    ):
        """The writer rotates by renaming the log aside and starting a fresh one. A
        selection that verified the old file and then read the new one reported a
        clean, near-empty window; now what was verified is what is read."""
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])
        real_parse = decision_log.parse_events

        def _rotate_then_parse(lines):
            os.replace(log, log.with_name(log.name + ".1"))
            log.write_text("", encoding="utf-8")
            return real_parse(lines)

        monkeypatch.setattr(decision_log, "parse_events", _rotate_then_parse)
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=log)

        assert len(selection.events) == 1, "the file that was read, not its replacement"
        assert selection.skipped_lines == 0

    def test_a_read_error_is_unreadable_not_absent(self, tmp_path, monkeypatch):
        """The plain `OSError` arm — neither a missing file nor a permission bit — so a
        regression confined to it fails here rather than hiding behind the arms other
        tests drive. Line coverage marks a whole `except (A, B)` covered once either
        fires, which is how this arm went untested before."""
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])

        def _io_error(self, *_a, **_k):
            raise OSError(5, "Input/output error")

        monkeypatch.setattr(Path, "read_text", _io_error)
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=log)

        assert selection.available is False
        assert selection.reason == cs.REASON_LOG_UNREADABLE, "a failed read is not proof of absence"

    def test_a_log_path_under_a_file_is_absent_not_unreadable(self, tmp_path):
        """`NotADirectoryError`: a parent component is a regular file, so no log can
        exist there. That is absence — the writer's own mkdir fails the same way."""
        (tmp_path / "cache").write_text("", encoding="utf-8")
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=tmp_path / "cache" / "d.jsonl")

        assert selection.reason == cs.REASON_LOG_ABSENT

    def test_an_empty_log_is_a_count_not_a_failure(self, tmp_path):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("", encoding="utf-8")

        assert cs._read_log(empty) == ([], cs.REASON_OK)
        assert cs._read_log(tmp_path / "gone.jsonl") == (None, cs.REASON_LOG_ABSENT)

    def test_skipped_lines_is_exact_for_the_snapshot(self, tmp_path):
        """Two non-empty lines that yield no event — one not JSON, one JSON that is not
        an object — and a blank line, which is not a line at all for this purpose."""
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(
            tmp_path / "d.jsonl",
            [_event("2026-06-01T00:00:00+00:00")],
            extra="{ this is not json\n\n[]\n",
        )

        selection = cs.select_events(window, path=log)

        assert selection.skipped_lines == 2


class TestRunIdsAreCanonicalised:

    @pytest.mark.parametrize("raw,expected", [
        ("abcdef012345", "abcdef012345"),
        ("ABCDEF012345", "abcdef012345"),   # case variants are one run, not two
        (" ab12 ", "ab12"),                 # surrounding whitespace is not identity
        ("   ", ""),                        # whitespace is not a run
        ("", ""),
        (None, ""),
        (1, ""),                            # a non-string must not join its own text
        ("not-hex!", "not-hex!"),           # unrecognised, but a real identifier
        ("Custom-Run-7", "custom-run-7"),   # a future writer's shape is not rejected
        ("STRASSE", "strasse"),
        ("Straße", "strasse"),              # casefold, not lower: ß folds to ss
    ])
    def test_the_canonical_form(self, raw, expected):
        assert cs._canonical_run_id(raw) == expected

    def test_unicode_case_variants_form_one_group(self, tmp_path):
        """`lower()` left these as two runs while the docstring promised casefolding."""
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [
            _event("2026-06-01T00:00:00+00:00", "Straße"),
            _event("2026-06-01T00:00:01+00:00", "STRASSE"),
        ])

        selection = cs.select_events(window, path=log)

        assert selection.runs == ("strasse",), "one logical run, not two"

    def test_case_variants_form_one_group(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [
            _event("2026-06-01T00:00:00+00:00", "ABCDEF012345"),
            _event("2026-06-01T00:00:01+00:00", "abcdef012345"),
        ])

        selection = cs.select_events(window, path=log)

        assert selection.runs == ("abcdef012345",), "one logical run, not two"
        assert len(cs.group_by_run(selection)["abcdef012345"]) == 2

    def test_a_numeric_id_does_not_merge_with_its_own_text(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = tmp_path / "d.jsonl"
        log.write_text(
            json.dumps({"schema": 1, "ts": "2026-06-01T00:00:00+00:00", "run_id": 1}) + "\n"
            + json.dumps({"schema": 1, "ts": "2026-06-01T00:00:01+00:00", "run_id": "1"}) + "\n",
            encoding="utf-8",
        )

        grouped = cs.group_by_run(cs.select_events(window, path=log))

        assert set(grouped) == {cs.RUN_UNATTRIBUTED, "1"}
        assert len(grouped[cs.RUN_UNATTRIBUTED]) == 1
        assert len(grouped["1"]) == 1

    def test_a_whitespace_id_is_unattributed_not_a_named_run(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00", "   ")])

        selection = cs.select_events(window, path=log)

        assert selection.runless == 1
        assert selection.runs == (cs.RUN_UNATTRIBUTED,)


class TestUndecodableLogs:

    def test_invalid_utf8_returns_unavailable_rather_than_raising(self, tmp_path):
        """The probe opened the file but did not decode it, so `read_events` performed
        the first strict read and UnicodeDecodeError escaped `select_events`."""
        log = tmp_path / "bad.jsonl"
        log.write_bytes(b'{"schema":1,"ts":"2026-06-01T00:00:00+00:00"}\n\xff\xfe bad\n')
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=log)

        assert selection.available is False
        assert selection.reason == cs.REASON_LOG_UNREADABLE


class TestEveryEventIsGrouped:

    def test_events_without_a_run_id_are_bucketed_and_counted(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = tmp_path / "d.jsonl"
        rows = [
            _event("2026-06-01T00:00:00+00:00", "r1"),
            _event("2026-06-01T00:00:01+00:00", ""),
            {"schema": 1, "ts": "2026-06-01T00:00:02+00:00", "event": "x", "payload": {}},
            {"schema": 1, "ts": "2026-06-01T00:00:03+00:00", "run_id": None,
             "event": "x", "payload": {}},
        ]
        log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

        selection = cs.select_events(window, path=log)
        grouped = cs.group_by_run(selection)

        assert selection.runless == 3
        assert sum(len(v) for v in grouped.values()) == len(selection.events), \
            "every selected event lands in exactly one bucket"
        assert grouped[cs.RUN_UNATTRIBUTED] and len(grouped[cs.RUN_UNATTRIBUTED]) == 3

    def test_a_collision_with_the_unattributed_label_merges_rather_than_loses(self):
        """This assertion used to rest on run ids being hexadecimal. That is no longer
        enforced — an unrecognised id is kept rather than discarded — so a writer
        emitting this exact parenthesised string would land in the same bucket. The
        property worth pinning is therefore the *consequence*: such events merge into
        one bucket, and none is dropped. Losing an event would be the real defect;
        sharing a label with an anonymous one is cosmetic."""
        selection = cs.EventSelection(
            events=({"run_id": cs.RUN_UNATTRIBUTED}, {"run_id": None}),
            runs=(cs.RUN_UNATTRIBUTED,),
            available=True,
        )

        grouped = cs.group_by_run(selection)

        assert sum(len(v) for v in grouped.values()) == 2


class TestGrouping:

    def test_grouping_preserves_run_order(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [
            _event("2026-06-01T00:00:01+00:00", "z"),
            _event("2026-06-01T00:00:02+00:00", "a"),
            _event("2026-06-01T00:00:03+00:00", "z"),
        ])
        selection = cs.select_events(window, path=log)

        grouped = cs.group_by_run(selection)

        assert list(grouped) == ["z", "a"], "run order follows the log, not the alphabet"
        assert [len(v) for v in grouped.values()] == [2, 1]

    def test_grouping_an_empty_selection_is_empty_not_an_error(self):
        assert cs.group_by_run(cs.EventSelection()) == {}


class TestRepoDetectionKeepsItsAnswersApart:
    """`rev-parse --is-inside-work-tree` has three outcomes — true, false, and a
    non-zero exit — plus the tool not answering at all. Each is a different fact."""

    def test_a_tool_failure_during_detection_is_not_a_verdict_about_the_directory(
        self, tmp_path, monkeypatch,
    ):
        """Before: the flag was dropped and `git --version` was asked separately, so a
        timeout on the real question plus a healthy second launch came back as "not a
        git repository" — a claim nothing had established."""
        repo = _make_repo(tmp_path / "r")
        real_run = subprocess.run

        def _flaky(cmd, *args, **kwargs):
            if "--is-inside-work-tree" in cmd:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(cs.subprocess, "run", _flaky)

        window = cs.resolve_window(repo)

        assert window.available is False
        assert window.reason == cs.REASON_GIT_UNAVAILABLE, "nothing learned, nothing claimed"

    def test_a_bare_repository_is_a_repository_without_a_working_tree(self, tmp_path):
        bare = tmp_path / "bare.git"
        bare.mkdir()
        _git(bare, "init", "-q", "--bare")

        window = cs.resolve_window(bare)

        assert window.available is False
        assert window.reason == cs.REASON_NO_WORK_TREE, "a bare repository is a repository"

    def test_the_git_directory_itself_is_outside_the_working_tree(self, tmp_path):
        repo = _make_repo(tmp_path / "r")

        assert cs.resolve_window(repo / ".git").reason == cs.REASON_NO_WORK_TREE

    def test_detection_launches_git_exactly_once(self, tmp_path, monkeypatch):
        """The second launch was the `--version` guess. It is gone, and with it the
        doubled cost on every non-repo path."""
        real_run = subprocess.run
        launches = []

        def _counting(cmd, *args, **kwargs):
            launches.append(cmd)
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(cs.subprocess, "run", _counting)

        assert cs.resolve_window(tmp_path).reason == cs.REASON_NOT_A_REPO
        assert len(launches) == 1


class TestResultsAreImmutableRecords:
    """A selection's counts describe its collections. If a caller could grow, shrink or
    reassign them, `scanned`, `undated` and `runless` would silently stop being true."""

    def test_a_window_refuses_reassignment(self, tmp_path):
        window = cs.resolve_window(tmp_path)

        with pytest.raises(dataclasses.FrozenInstanceError):
            window.since = "2026-01-01T00:00:00+00:00"

    def test_a_selection_refuses_reassignment_and_its_collections_cannot_grow(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])
        selection = cs.select_events(window, path=log)

        with pytest.raises(dataclasses.FrozenInstanceError):
            selection.scanned = 0
        assert isinstance(selection.events, tuple)
        assert isinstance(selection.runs, tuple)

    def test_grouping_shares_the_selections_event_objects_deliberately(self, tmp_path):
        """Not a copy: one event, one identity. A copy would let a renderer annotate a
        group and then read a different value back from `events`."""
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00", "r1")])
        selection = cs.select_events(window, path=log)

        grouped = cs.group_by_run(selection)

        assert grouped["r1"][0] is selection.events[0]


class TestAnEnvironmentOverrideIsFollowedAndReported:
    """`$CFS_DECISION_LOG` is process-wide: the writer honours it in every project the
    process runs in. The reader follows it — that is where the events are — and says
    so, because one shared log cannot be attributed to the window's project."""

    def test_the_override_is_read_because_that_is_where_the_writer_wrote(
        self, tmp_path, monkeypatch,
    ):
        """Reading the project-local path instead would report "no decision log yet"
        about a log that exists and is being written to."""
        project = _make_studio_project(tmp_path / "project")
        shared = _write_log(tmp_path / "shared.jsonl", [_event("2026-06-01T00:00:00+00:00")])
        monkeypatch.setenv("CFS_DECISION_LOG", str(shared))
        window = cs.ChangeWindow(
            project_root=str(project), since="2026-01-01T00:00:00+00:00", available=True,
        )

        selection = cs.select_events(window)

        assert selection.available is True
        assert len(selection.events) == 1
        assert selection.log_overridden is True, "a shared log is reported as shared"

    def test_the_writer_and_the_reader_agree_on_where_the_log_is(self, tmp_path, monkeypatch):
        """End to end: the writer records from inside project B with the override set,
        and a window for project A reads that event. Had the reader ignored the
        override, it would have found nothing at all."""
        project_a = _make_studio_project(tmp_path / "a")
        project_b = _make_studio_project(tmp_path / "b")
        shared = tmp_path / "shared.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(shared))
        monkeypatch.setattr(decision_log, "opt_out_sentinel_path", lambda: tmp_path / "absent")
        monkeypatch.setattr(decision_log, "_FAILURE_WARNED", False)
        monkeypatch.chdir(project_b)
        assert decision_log.record("validation", {"check": "x"}, command="validate") is True
        window = cs.ChangeWindow(
            project_root=str(project_a), since="2000-01-01T00:00:00+00:00", available=True,
        )

        selection = cs.select_events(window)

        assert selection.scanned == 1
        assert selection.log_overridden is True

    def test_a_project_resolved_log_is_not_reported_as_overridden(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        project = _make_studio_project(tmp_path / "project")
        log = decision_log.default_log_path(project)
        assert log is not None
        log.parent.mkdir(parents=True, exist_ok=True)
        _write_log(log, [_event("2026-06-01T00:00:00+00:00")])
        window = cs.ChangeWindow(
            project_root=str(project), since="2026-01-01T00:00:00+00:00", available=True,
        )

        selection = cs.select_events(window)

        assert len(selection.events) == 1
        assert selection.log_overridden is False

    def test_an_explicit_path_is_never_reported_as_overridden(self, tmp_path, monkeypatch):
        """A caller that names the log chose it; the environment did not."""
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "elsewhere.jsonl"))
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-06-01T00:00:00+00:00")])
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        selection = cs.select_events(window, path=log)

        assert len(selection.events) == 1, "the named log, not the override"
        assert selection.log_overridden is False


class TestTheBoundaryFollowsTheMergeBase:
    """The lower bound is the merge-base's commit time, so it moves when the merge-base
    does. This pins that documented behaviour — and its remedy — so a change to the
    window's meaning is a deliberate edit here rather than a silent drift."""

    def test_a_rebase_advances_the_boundary_and_an_explicit_since_restores_it(
        self, tmp_path, monkeypatch,
    ):
        def _at(stamp):
            monkeypatch.setenv("GIT_AUTHOR_DATE", stamp)
            monkeypatch.setenv("GIT_COMMITTER_DATE", stamp)

        _at("2026-01-01T00:00:00+00:00")
        repo = _make_repo(tmp_path / "r")
        trunk = _git(repo, "branch", "--show-current")
        old_base = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "-q", "-b", "feature")
        _at("2026-01-02T00:00:00+00:00")
        _commit(repo, "feature.txt")
        _git(repo, "checkout", "-q", trunk)
        _at("2026-01-05T00:00:00+00:00")
        new_base = _commit(repo, "upstream.txt")
        _point_ref(repo, "refs/remotes/upstream/main", new_base)
        _git(repo, "checkout", "-q", "feature")
        log = _write_log(tmp_path / "d.jsonl", [_event("2026-01-03T00:00:00+00:00")])

        before = cs.resolve_window(repo)
        assert before.base_sha == old_base
        assert len(cs.select_events(before, path=log).events) == 1

        _git(repo, "rebase", "-q", "upstream/main")

        after = cs.resolve_window(repo)
        assert after.base_sha == new_base, "the merge-base moved, so the boundary moved"
        assert after.since > before.since
        assert cs.select_events(after, path=log).events == (), \
            "the documented loss: a decision logged before the new base commit"

        pinned = cs.resolve_window(repo, since=before.since)
        assert len(cs.select_events(pinned, path=log).events) == 1, "since= is the remedy"
