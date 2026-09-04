"""Tests for change-summary requirement linkage — changed files to the IDs they carry.

The contract is the same as the window's: never raise, never go silent, and always
report the denominator. So most of these force a failure or an awkward file shape
rather than confirming the happy path.

Git setup helpers are imported from the window suite rather than copied — `tests/` is
on `sys.path` via conftest, and a second copy of the same four git calls is duplication
a reviewer would rightly flag.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
from pathlib import Path

import pytest

from studio.utils import change_summary as cs
from test_change_summary_core import _commit, _git, _make_repo, _point_ref


# --------------------------------------------------------------------------- helpers

MARKER = "cpt-studio-algo-developer-experience-change-summary"


def _repo_with_base(tmp_path: Path) -> Path:
    """A repo whose branch point is one commit behind HEAD."""
    repo = _make_repo(tmp_path / "r")
    _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
    return repo


def _code(body: str = "") -> str:
    return (
        f'"""Module.\n\n@cpt-algo:{MARKER}:p1\n"""\n\n'
        f"# @cpt-begin:{MARKER}:p1:inst-x\n"
        f"def f():\n    return 1\n{body}"
        f"# @cpt-end:{MARKER}:p1:inst-x\n"
    )


def _artifact() -> str:
    return f"# Feature\n\n- [x] `p1` - **ID**: `{MARKER}`\n\n1. [x] - `p1` - step - `inst-x`\n"


def _report(repo: Path) -> cs.LinkReport:
    return cs.link_changed_files(cs.resolve_window(repo))


# ----------------------------------------------------------------- name-status parsing

class TestNameStatusWalking:

    @pytest.mark.parametrize("records,expected", [
        (["M", "src/a.py"], [("M", "src/a.py")]),
        (["A", "new.py"], [("A", "new.py")]),
        (["D", "gone.py"], [("D", "gone.py")]),
        (["R100", "old.py", "new.py"], [("R", "new.py")]),
        (["C075", "src.py", "copy.py"], [("C", "copy.py")]),
        (["T", "mode.py"], [("T", "mode.py")]),
    ])
    def test_each_status_shape_walks(self, records, expected):
        assert cs._walk_name_status(records) == expected

    def test_a_rename_yields_the_new_path_not_the_old(self):
        assert cs._walk_name_status(["R100", "old.py", "new.py"]) == [("R", "new.py")]

    def test_a_rename_does_not_desynchronise_what_follows(self):
        """Under -z a rename consumes three records, not two. Mis-counting shifts
        every later entry, so this is the assertion that matters most."""
        records = ["R100", "old.py", "new.py", "M", "after.py", "A", "last.py"]

        assert cs._walk_name_status(records) == [
            ("R", "new.py"), ("M", "after.py"), ("A", "last.py"),
        ]

    def test_a_path_containing_a_tab_survives(self):
        """Line/tab splitting cannot do this; NUL records can."""
        assert cs._walk_name_status(["A", "we\tird.py"]) == [("A", "we\tird.py")]

    def test_a_path_containing_a_quote_survives(self):
        assert cs._walk_name_status(["M", 'qu"ote.py']) == [("M", 'qu"ote.py')]

    @pytest.mark.parametrize("records", [
        [], [""], ["M"], ["R100", "only-old.py"], ["A", ""],
    ])
    def test_truncated_or_empty_records_are_dropped_not_raised(self, records):
        assert cs._walk_name_status(records) == []


# ------------------------------------------------------------------ per-file traceability

class TestWhatAFileDoesWithIds:

    def test_code_reports_references_and_no_definitions(self, tmp_path):
        path = tmp_path / "m.py"
        path.write_text(_code(), encoding="utf-8")

        references, defines, reason = cs._file_traceability(path)

        assert references == [MARKER]
        assert defines == []
        assert reason == cs.REASON_OK

    def test_an_artifact_reports_definitions_and_no_references(self, tmp_path):
        path = tmp_path / "f.md"
        path.write_text(_artifact(), encoding="utf-8")

        references, defines, reason = cs._file_traceability(path)

        assert defines == [MARKER], "a changed spec declares requirements"
        assert references == [], "and does not reference them as code"

    def test_a_document_that_cites_an_id_it_does_not_declare_references_it(self, tmp_path):
        """A design note pointing at a requirement is a link to it. Only definitions
        used to be read from documents, so a changed artifact that referenced an ID
        without declaring it came back with no references at all."""
        path = tmp_path / "design.md"
        path.write_text(f"# Note\n\nThis change serves `{MARKER}` and nothing else.\n", encoding="utf-8")

        references, defines, reason = cs._file_traceability(path)

        assert references == [MARKER]
        assert defines == []
        assert reason == cs.REASON_OK

    def test_a_documents_mention_of_its_own_id_is_not_a_reference(self, tmp_path):
        """Feature artifacts routinely cite the IDs they declare. That points at nothing
        else, so it is a declaration, not also a link."""
        path = tmp_path / "f.md"
        path.write_text(_artifact() + f"\nSee `{MARKER}` above.\n", encoding="utf-8")

        references, defines, _reason = cs._file_traceability(path)

        assert defines == [MARKER]
        assert references == []

    def test_a_file_with_no_markers_reports_neither_and_no_failure(self, tmp_path):
        path = tmp_path / "plain.py"
        path.write_text("x = 1\n", encoding="utf-8")

        references, defines, reason = cs._file_traceability(path)

        assert (references, defines, reason) == ([], [], cs.REASON_OK)

    def test_a_binary_file_is_unreadable_not_marker_free(self, tmp_path):
        """"Carries no markers" and "could not be read" are different claims."""
        path = tmp_path / "blob.py"
        path.write_bytes(b"\xff\xfe\x00\x01binary\x00")

        references, defines, reason = cs._file_traceability(path)

        assert reason == cs.REASON_FILE_UNREADABLE
        assert (references, defines) == ([], [])

    def test_ids_are_sorted_and_deduplicated(self, tmp_path):
        path = tmp_path / "m.py"
        path.write_text(_code() + _code().replace("inst-x", "inst-y"), encoding="utf-8")

        references, _defines, _reason = cs._file_traceability(path)

        assert references == sorted(set(references))


# ------------------------------------------------------------------------- scope

class TestProjectScope:

    def test_a_file_inside_the_project_is_in_scope(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        (repo / "a.py").write_text("x = 1\n", encoding="utf-8")

        assert cs._in_project_scope(repo / "a.py", repo) is True

    def test_a_file_outside_the_project_is_not(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        outside = tmp_path / "elsewhere.py"
        outside.write_text("x = 1\n", encoding="utf-8")

        assert cs._in_project_scope(outside, repo) is False

    def test_a_missing_file_is_not_in_scope(self, tmp_path):
        repo = _make_repo(tmp_path / "r")

        assert cs._in_project_scope(repo / "never.py", repo) is False


# ------------------------------------------------------------------- the whole report

class TestTheReport:

    def test_a_changed_code_file_links_to_its_requirement(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add module")

        report = _report(repo)

        assert report.available is True
        assert report.changed == 1
        assert report.linked == 1
        assert [f.references for f in report.files] == [(MARKER,)]

    def test_a_changed_artifact_counts_as_declaring_not_unlinked(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "f.md").write_text(_artifact(), encoding="utf-8")
        _git(repo, "add", "f.md")
        _git(repo, "commit", "-q", "-m", "add spec")

        report = _report(repo)

        assert report.declaring == 1
        assert report.linked == 0, "a spec is a requirement source, not code serving one"

    def test_an_untracked_file_is_reported_not_omitted(self, tmp_path):
        """git diff cannot see it, so omitting it would hide a brand-new module."""
        repo = _repo_with_base(tmp_path)
        (repo / "fresh.py").write_text(_code(), encoding="utf-8")

        report = _report(repo)

        statuses = {f.status for f in report.files}
        assert "?" in statuses
        assert report.linked == 1

    def test_a_deleted_file_is_reported_as_gone_not_excluded(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "a.txt").unlink()
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "delete")

        report = _report(repo)

        gone = [f for f in report.files if f.reason == cs.REASON_FILE_GONE]
        assert len(gone) == 1
        assert report.deleted == 1, "the count must be readable without reparsing files"
        assert report.excluded == 0, "a deletion is not a policy exclusion"

    def test_an_undecodable_path_does_not_raise_out_of_the_report(self, tmp_path):
        """POSIX paths are bytes and need not be UTF-8. `subprocess(text=True)` decodes
        strictly, so a legal but undecodable filename raised UnicodeDecodeError out of
        the git helper — past its handler and out of `link_changed_files`, breaking the
        never-raises contract. Skipped where the filesystem refuses such a name."""
        repo = _repo_with_base(tmp_path)
        try:
            (repo / os.fsdecode(b"bad\xff.py")).write_text(_code(), encoding="utf-8")
        except (OSError, UnicodeError):
            pytest.skip("this filesystem rejects non-UTF-8 file names")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "undecodable name")

        report = _report(repo)          # must not raise

        assert report.available is True
        assert report.changed == 1
        assert report.deleted == 0, "the file exists; surrogates must round-trip to it"
        assert report.linked == 1, "and it must still resolve its requirement"

    def test_a_path_with_a_tab_is_linked_not_reported_gone(self, tmp_path):
        """End-to-end for the quoting bug: without -z, git emits this path as the
        literal characters `"we\\tird.py"`, which matches nothing on disk, so the file
        was reported as deleted while sitting right there."""
        if os.name == "nt":
            pytest.skip("a tab is not a legal file-name character on Windows")
        repo = _repo_with_base(tmp_path)
        odd = repo / "we\tird.py"
        odd.write_text(_code(), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "odd name")

        report = _report(repo)

        assert report.changed == 1
        assert report.deleted == 0, "the file exists; it must not be reported gone"
        assert report.linked == 1
        assert report.files[0].path == "we\tird.py"
        assert report.files[0].references == (MARKER,)

    def test_a_renamed_file_keeps_its_requirement_link(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add")
        _git(repo, "mv", "m.py", "renamed.py")
        _git(repo, "commit", "-q", "-m", "rename")

        report = _report(repo)

        linked = [f for f in report.files if f.references]
        assert linked, "a rename must not lose the link"
        assert all(f.path.endswith("renamed.py") for f in linked)

    def test_a_binary_change_is_counted_unreadable(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "blob.py").write_bytes(b"\xff\xfe\x00binary")
        _git(repo, "add", "blob.py")
        _git(repo, "commit", "-q", "-m", "add blob")

        report = _report(repo)

        assert report.unreadable == 1
        assert report.linked == 0

    def test_no_changes_is_available_with_a_zero_denominator(self, tmp_path):
        repo = _repo_with_base(tmp_path)

        report = _report(repo)

        assert report.available is True
        assert (report.changed, report.linked) == (0, 0)
        assert report.reason == cs.REASON_OK


class TestOnePhysicalFileIsReportedOnce:
    """The diff stream and the untracked sweep overlap, and concatenating them produced
    two contradictory rows for one file plus inflated counters."""

    def test_an_unstaged_but_kept_file_appears_exactly_once(self, tmp_path):
        """`git rm --cached` on a file present in the base leaves it deleted in the
        index and untracked on disk, so both streams report it."""
        repo = _make_repo(tmp_path / "r")
        (repo / "foo.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "add foo")
        base = _git(repo, "rev-parse", "HEAD")
        _point_ref(repo, "refs/remotes/upstream/main", base)
        _git(repo, "rm", "--cached", "-q", "foo.py")     # unstaged, still on disk

        report = _report(repo)

        paths = [f.path for f in report.files]
        assert paths.count("foo.py") == 1, "one physical file, one row"
        assert report.changed == len(set(paths)), "counters must not double-count"

    def test_the_diff_status_wins_over_the_untracked_status(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        (repo / "foo.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "add foo")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        _git(repo, "rm", "--cached", "-q", "foo.py")

        report = _report(repo)

        assert [f.status for f in report.files] == ["D"], "not the untracked '?'"

    def test_entries_beyond_the_ceiling_are_counted_not_dropped(self, tmp_path, monkeypatch):
        repo = _repo_with_base(tmp_path)
        for index in range(4):
            (repo / f"m{index}.py").write_text(_code(), encoding="utf-8")
        monkeypatch.setattr(cs, "MAX_CHANGED_ENTRIES", 2)

        report = _report(repo)

        assert len(report.files) == 2
        assert report.truncated == 2, "the unexamined remainder must be visible"
        assert report.changed == 4, "the denominator is what was found, not what was read"


class TestUnscannableEntries:

    def test_a_file_over_the_shared_size_cap_says_so(self, tmp_path, monkeypatch):
        """Reported as over-cap rather than as unreadable or marker-free — the file is
        fine, the reader declined it."""
        repo = _repo_with_base(tmp_path)
        (repo / "big.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "add big")
        monkeypatch.setattr(cs.codebase, "_MAX_CODE_FILE_BYTES", 1)

        report = _report(repo)

        assert [f.reason for f in report.files] == [cs.REASON_FILE_TOO_LARGE]
        assert report.linked == 0

    def test_a_directory_shaped_entry_is_refused_without_being_walked(self, tmp_path, monkeypatch):
        """A changed submodule is a gitlink — a directory on disk. The shared resolver
        would rglob the entire nested tree just to answer a boolean, so the directory
        must be refused before it is reached."""
        repo = _make_repo(tmp_path / "r")
        (repo / "sub").mkdir()

        def _must_not_walk(*_a, **_k):
            raise AssertionError("a directory entry must not reach the shared resolver")

        monkeypatch.setattr(cs.codebase, "resolve_entry_code_files", _must_not_walk)

        assert cs._in_project_scope(repo / "sub", repo) is False

    def test_a_changed_submodule_is_reported_as_not_a_regular_file(self, tmp_path):
        """End-to-end for the gitlink case: a real submodule, so the entry genuinely
        arrives from git as a directory rather than being injected."""
        other = _make_repo(tmp_path / "other")
        repo = _repo_with_base(tmp_path)
        added = subprocess.run(
            ["git", "-c", "protocol.file.allow=always", "submodule", "add",
             "-q", str(other), "sub"],
            cwd=str(repo), capture_output=True, text=True, check=False,
        )
        if added.returncode:
            pytest.skip(f"submodule add unavailable here: {added.stderr.strip()[:80]}")
        _git(repo, "commit", "-q", "-m", "add submodule")

        report = _report(repo)

        gitlink = [f for f in report.files if f.path == "sub"]
        assert gitlink, "the gitlink entry must be reported, not dropped"
        assert gitlink[0].reason == cs.REASON_NOT_A_FILE
        assert report.excluded == 0, "not a policy exclusion — it is not a file at all"
        assert report.not_a_file == 1, "and it lands in a tally a reader can count"

    def test_an_unopenable_file_is_unreadable_not_oversized(self, tmp_path, monkeypatch):
        """If the file cannot be opened, "too large" is a claim we cannot make."""
        path = tmp_path / "blob.py"
        path.write_bytes(b"\xff\xfebinary")
        real_open = Path.open

        def _open_fails(self, *a, **k):
            if self == path:
                raise OSError("open refused")
            return real_open(self, *a, **k)

        monkeypatch.setattr(Path, "open", _open_fails)

        assert cs._file_traceability(path)[2] == cs.REASON_FILE_UNREADABLE

    def test_the_size_ceiling_bounds_what_is_read_not_what_a_stat_said(self, tmp_path, monkeypatch):
        """The first version measured the file and then read it whole, so a file growing
        in between slipped past the limit it had just been checked against. Nothing is
        measured now: with `stat` refusing outright, the ceiling still holds."""
        path = tmp_path / "big.py"
        path.write_text(_code() * 50, encoding="utf-8")
        real_stat = Path.stat

        def _stat_fails(self, *a, **k):
            if self == path:
                raise OSError("stat refused")
            return real_stat(self, *a, **k)

        monkeypatch.setattr(Path, "stat", _stat_fails)
        monkeypatch.setattr(cs.codebase, "_MAX_CODE_FILE_BYTES", 64)

        assert cs._file_traceability(path)[2] == cs.REASON_FILE_TOO_LARGE

    def test_both_marker_directions_come_from_one_read(self, tmp_path, monkeypatch):
        """Two independent reads let a file edited mid-scan report `references` from
        one version and `defines` from another. The document scan now parses the text
        the code scan just read, so a rewrite after that read is invisible to both."""
        path = tmp_path / "f.md"
        path.write_text(_artifact(), encoding="utf-8")
        real_read = cs.codebase.read_code_text

        def _read_then_rewrite(p, **kw):
            result = real_read(p, **kw)
            path.write_text("# nothing here now\n", encoding="utf-8")
            return result

        monkeypatch.setattr(cs.codebase, "read_code_text", _read_then_rewrite)

        references, defines, reason = cs._file_traceability(path)

        assert reason == cs.REASON_OK
        assert defines == [MARKER], "the snapshot, not the file as it is now"
        assert references == []

    def test_structurally_broken_markers_have_their_own_reason(self, tmp_path):
        """A dangling `@cpt-end` is a parse error: not "carries no markers" (the file
        may well carry some) and not "could not be read" (it was read fine — a test
        file full of deliberately malformed fixtures is the everyday case)."""
        path = tmp_path / "broken.py"
        path.write_text(f"# @cpt-end:{MARKER}:p1:inst-never-opened\n", encoding="utf-8")

        assert cs._file_traceability(path)[2] == cs.REASON_MARKERS_INVALID

    def test_a_scope_check_that_errors_is_unknown_not_excluded(self, tmp_path, monkeypatch):
        """Folding a filesystem error into `excluded` reports a policy judgement that
        was never made."""
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "add")

        def _boom(*_a, **_k):
            raise OSError("stat failed")

        monkeypatch.setattr(cs.codebase, "resolve_entry_code_files", _boom)
        report = _report(repo)

        assert [f.reason for f in report.files] == [cs.REASON_SCOPE_UNKNOWN]
        assert report.excluded == 0, "not a policy exclusion"
        assert report.unreadable == 1

    def test_a_tracked_change_under_a_vendored_path_is_reported(self, tmp_path):
        """Pins the documented judgement call: the shared policy does not apply
        conventional non-source directory names to an explicitly named file, and this
        module deliberately keeps that — over-reporting costs a reader a moment,
        under-reporting hides work that changed."""
        repo = _repo_with_base(tmp_path)
        vendored = repo / "vendor" / "dep.py"
        vendored.parent.mkdir()
        vendored.write_text(_code(), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "vendor change")

        report = _report(repo)

        assert [f.path for f in report.files] == ["vendor/dep.py"]
        assert report.excluded == 0
        assert report.linked == 1, "reported, not hidden"


class TestTheReportSaysWhyItCouldNot:

    def test_an_unavailable_window_propagates_exactly_one_reason(self, tmp_path):
        window = cs.resolve_window(tmp_path)   # not a repo

        report = cs.link_changed_files(window)

        assert report.available is False
        assert report.reason == window.reason

    def test_a_since_only_window_has_no_base_commit_to_diff(self, tmp_path):
        window = cs.ChangeWindow(since="2026-01-01T00:00:00+00:00", available=True)

        report = cs.link_changed_files(window)

        assert report.available is False
        assert report.reason == cs.REASON_NO_BASE_COMMIT

    def test_a_failing_diff_is_reported(self, tmp_path, monkeypatch):
        repo = _repo_with_base(tmp_path)
        window = cs.resolve_window(repo)
        monkeypatch.setattr(cs, "_git_records", lambda *_a, **_k: None)

        report = cs.link_changed_files(window)

        assert report.available is False
        assert report.reason == cs.REASON_DIFF_UNAVAILABLE


class TestTheListingIsAboutTheProjectNamedAndNothingElse:
    """Two ways the changed-file listing could describe something other than the
    project it was asked about: an ambient redirect pointing git elsewhere, and a
    failed untracked sweep presented as an empty one."""

    def test_an_ambient_git_dir_cannot_redirect_the_record_query(self, tmp_path, monkeypatch):
        """The window is resolved with git's redirect variables cleared; the record
        query used to run without that clearing, so `GIT_DIR` pointing at a second
        repository listed that repository's files under the first one's window."""
        repo = _repo_with_base(tmp_path)
        (repo / "mine.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "mine.py")
        _git(repo, "commit", "-q", "-m", "mine")
        decoy = _make_repo(tmp_path / "decoy")
        (decoy / "theirs.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
        monkeypatch.setenv("GIT_WORK_TREE", str(decoy))

        report = _report(repo)

        assert report.available is True, report.reason
        assert [f.path for f in report.files] == ["mine.py"], "this project's files, not the decoy's"

    def test_every_git_call_site_runs_with_the_sanitised_environment(self):
        """Structural: a new call site that forgets `env=_git_env()` fails here rather
        than in review — which is how the record query slipped through the first time."""
        import inspect
        source = inspect.getsource(cs)
        launches = source.count("subprocess.run(")

        assert launches >= 2
        assert source.count("env=_git_env()") == launches, "every launch, not most of them"

    def test_a_failed_untracked_sweep_makes_the_listing_unavailable(self, tmp_path, monkeypatch):
        """`or []` turned a failed `ls-files` into an empty one, so the report came back
        available while silently missing every new file."""
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add")
        real_records = cs._git_records

        def _diff_only(root, args):
            return None if args[0] == "ls-files" else real_records(root, args)
        monkeypatch.setattr(cs, "_git_records", _diff_only)

        report = _report(repo)

        assert report.available is False, "a partial listing must not present as complete"
        assert report.reason == cs.REASON_DIFF_UNAVAILABLE
        assert report.files == ()


class TestTheReportAccountsForEveryEntry:
    """Every changed entry is in exactly one place a reader can count, over the entries
    the report actually examined — and one entry cannot take the others down with it."""

    def test_the_root_comes_from_the_window_not_from_where_the_process_stands(
        self, tmp_path, monkeypatch,
    ):
        """`resolve_window` resolves its root and carries it. The linkage used to take
        a second, unresolved root, so a later `chdir` diffed a different directory from
        the one the window's base commit described."""
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add")
        monkeypatch.chdir(repo)
        window = cs.resolve_window(Path("."))
        elsewhere = _make_repo(tmp_path / "elsewhere")
        (elsewhere / "theirs.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.chdir(elsewhere)

        report = cs.link_changed_files(window)

        assert [f.path for f in report.files] == ["m.py"], "the window's project, not the cwd"

    def test_a_window_without_a_root_is_refused_with_its_own_reason(self):
        window = cs.ChangeWindow(
            base_sha="0" * 40, since="2026-01-01T00:00:00+00:00", available=True,
        )

        report = cs.link_changed_files(window)

        assert report.available is False
        assert report.reason == cs.REASON_NO_PROJECT_ROOT

    def test_rename_detection_does_not_depend_on_ambient_git_config(self, tmp_path):
        """With `diff.renames` off, an unpinned diff reports a rename as a delete plus
        an add — so "a rename keeps its link" held on one machine and not on another."""
        repo = _make_repo(tmp_path / "r")
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        _git(repo, "config", "diff.renames", "false")
        _git(repo, "mv", "m.py", "renamed.py")
        _git(repo, "commit", "-q", "-m", "rename")

        report = _report(repo)

        assert [(f.status, f.path) for f in report.files] == [("R", "renamed.py")]
        assert report.deleted == 0

    def test_one_entry_that_raises_unexpectedly_is_its_own_row_not_the_whole_report(
        self, tmp_path, monkeypatch,
    ):
        """Everything an entry can legitimately fail with is handled inside the
        classifier; this is what was not foreseen. It used to propagate out of the
        loop, and the command's last-resort guard then replaced the whole digest."""
        repo = _repo_with_base(tmp_path)
        (repo / "good.py").write_text(_code(), encoding="utf-8")
        (repo / "bad.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "two")
        real = cs._file_traceability

        def _boom_on_bad(path):
            if path.name == "bad.py":
                raise TypeError("unforeseen")
            return real(path)
        monkeypatch.setattr(cs, "_file_traceability", _boom_on_bad)

        report = _report(repo)

        assert report.available is True
        assert {f.path: f.reason for f in report.files} == {
            "good.py": cs.REASON_OK, "bad.py": cs.REASON_SCAN_FAILED,
        }
        assert (report.linked, report.unreadable) == (1, 1)

    def test_a_not_a_file_entry_has_its_own_tally(self, tmp_path):
        repo = _make_repo(tmp_path / "r")
        (repo / "sub").mkdir()

        link, counter = cs._classify_entry("A", "sub", repo)

        assert link is not None and link.reason == cs.REASON_NOT_A_FILE
        assert counter == "not_a_file"

    def test_the_ceiling_counts_everything_and_examines_the_cap(self, tmp_path, monkeypatch):
        """`changed` is the whole population, the tallies are over `examined`, and the
        difference is stated — so the arithmetic a reader checks is over one population."""
        repo = _repo_with_base(tmp_path)
        for name in ("a.py", "b.py", "c.py"):
            (repo / name).write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(cs, "MAX_CHANGED_ENTRIES", 2)

        report = _report(repo)

        assert (report.changed, report.examined, report.truncated) == (3, 2, 1)
        assert report.examined == len(report.files) + report.excluded

    def test_untracked_paths_beyond_the_cap_are_counted_but_not_materialised(
        self, tmp_path, monkeypatch,
    ):
        repo = _repo_with_base(tmp_path)
        for i in range(5):
            (repo / f"u{i}.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(cs, "MAX_CHANGED_ENTRIES", 2)

        entries, total = cs._collect_changed_entries(repo, _git(repo, "rev-parse", "upstream/main"))

        assert len(entries) == 2, "no more stored than will be examined"
        assert total == 5, "but every one of them counted"


class TestInvariants:

    def test_git_records_degrades_rather_than_raising(self, tmp_path, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("no exec")
        monkeypatch.setattr(cs.subprocess, "run", _boom)

        assert cs._git_records(tmp_path, ["diff"]) is None

    def test_git_records_handles_a_decode_error_from_the_subprocess(self, tmp_path, monkeypatch):
        """The `UnicodeDecodeError` arm of the helper's except tuple. Line coverage
        marks the `except (A, B, C)` line covered once *any* member fires, so this arm
        was reported as covered while never being exercised."""
        def _raise_decode(*_a, **_k):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        monkeypatch.setattr(cs.subprocess, "run", _raise_decode)

        assert cs._git_records(tmp_path, ["diff"]) is None

    def test_git_records_returns_nothing_on_a_non_zero_exit(self, tmp_path):
        repo = _make_repo(tmp_path / "r")

        assert cs._git_records(repo, ["rev-parse", "--verify", "refs/heads/no-such"]) is None

    def test_git_records_drops_only_the_trailing_empty_record(self, tmp_path):
        repo = _make_repo(tmp_path / "r")

        records = cs._git_records(repo, ["ls-files", "-z"])

        assert records == ["a.txt"], "a trailing NUL must not leave an empty tail record"

    def test_a_scope_check_that_errors_refuses_rather_than_admits(self, tmp_path, monkeypatch):
        def _boom(*_a, **_k):
            raise OSError("stat failed")
        monkeypatch.setattr(cs.codebase, "resolve_entry_code_files", _boom)

        assert cs._in_project_scope(tmp_path / "a.py", tmp_path) is False

    def test_an_out_of_scope_change_is_counted_excluded_not_dropped(self, tmp_path):
        """A tracked symlink is refused by the shared policy but still appears in the
        diff, so it must land in `excluded` — a published counter that would otherwise
        never be exercised."""
        if os.name == "nt":
            pytest.skip("symlink creation needs privileges on Windows")
        repo = _repo_with_base(tmp_path)
        outside = tmp_path / "outside.py"
        outside.write_text(_code(), encoding="utf-8")
        (repo / "link.py").symlink_to(outside)
        _git(repo, "add", "link.py")
        _git(repo, "commit", "-q", "-m", "add symlink")

        report = _report(repo)

        assert report.excluded == 1, "refused by policy, but still counted"
        assert report.changed == 1
        assert all(not f.path.endswith("link.py") for f in report.files)

    def test_every_new_reason_is_path_free(self):
        home = os.path.expanduser("~")
        for name in ("REASON_NO_BASE_COMMIT", "REASON_DIFF_UNAVAILABLE",
                     "REASON_FILE_GONE", "REASON_FILE_UNREADABLE"):
            value = getattr(cs, name)
            assert value and os.sep not in value and home not in value

    def test_the_counters_partition_what_was_seen(self, tmp_path):
        """linked/declaring overlap by design, but neither may exceed what was seen."""
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        (repo / "f.md").write_text(_artifact(), encoding="utf-8")
        (repo / "blob.py").write_bytes(b"\xff\xfebinary")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "mixed")

        report = _report(repo)

        assert report.changed == len(report.files) + report.excluded
        assert report.examined == report.changed, "nothing was truncated"
        for counter in (report.linked, report.declaring, report.deleted,
                        report.excluded, report.unreadable, report.not_a_file):
            assert counter <= report.changed
        # Every row is in exactly one bucket: it carries a marker, it was read and
        # carries none, or it is in one of the three could-not tallies.
        marked = sum(1 for f in report.files if f.references or f.defines)
        plain = sum(1 for f in report.files
                    if not f.references and not f.defines and f.reason == cs.REASON_OK)
        assert len(report.files) == (
            marked + plain + report.deleted + report.unreadable + report.not_a_file
        )
        assert (marked, plain, report.unreadable) == (2, 0, 1)

    def test_the_same_state_yields_identical_reports(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add")

        shapes = set()
        for _ in range(5):
            report = _report(repo)
            shapes.add((
                report.changed, report.linked, report.declaring,
                tuple((f.path, f.status, tuple(f.references)) for f in report.files),
            ))

        assert len(shapes) == 1


class TestGoldenShape:

    def test_a_mixed_change_set_renders_a_stable_report(self, tmp_path):
        """Regression fixture: a later change that degrades the output is caught."""
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        (repo / "f.md").write_text(_artifact(), encoding="utf-8")
        (repo / "plain.py").write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "mixed")

        report = _report(repo)
        actual = sorted(
            (f.path, f.status, len(f.references), len(f.defines), f.reason)
            for f in report.files
        )

        assert actual == [
            ("f.md", "A", 0, 1, ""),
            ("m.py", "A", 1, 0, ""),
            ("plain.py", "A", 0, 0, ""),
        ]
        assert (report.changed, report.linked, report.declaring) == (3, 1, 1)
        assert (report.excluded, report.unreadable) == (0, 0)


class TestLinkRecordsAreImmutable:
    """Same discipline as the window and selection records: the counters describe
    `files`, so `files` must not be growable or reassignable underneath them, and a
    link is what one read of one file found."""

    def test_a_report_and_its_links_refuse_reassignment(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add")

        report = _report(repo)

        with pytest.raises(dataclasses.FrozenInstanceError):
            report.linked = 0
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.files[0].reason = "edited"
        assert isinstance(report.files, tuple)
        assert isinstance(report.files[0].references, tuple)
        assert isinstance(report.files[0].defines, tuple)
