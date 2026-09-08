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
import io
import os
import subprocess
import sys
import threading
import time
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

    @pytest.mark.parametrize(
        "env",
        [
            pytest.param(
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "core.excludesFile",
                    "GIT_CONFIG_VALUE_0": "{excludes}",
                },
                id="indexed-pairs",
            ),
            pytest.param(
                {"GIT_CONFIG_PARAMETERS": "'core.excludesfile'='{excludes}'"},
                id="config-parameters",
            ),
            pytest.param({"GIT_CONFIG_GLOBAL": "{config}"}, id="global-config-file"),
            pytest.param({"GIT_CONFIG_SYSTEM": "{config}"}, id="system-config-file"),
        ],
    )
    def test_ambient_git_config_cannot_hide_a_new_file_from_the_listing(
        self, tmp_path, monkeypatch, env,
    ):
        """Git takes configuration from the environment too, and configuration reaches
        these queries even where it cannot redirect discovery.

        Measured before the fix: with `core.excludesFile` injected through any of these
        four interfaces, `ls-files --others --exclude-standard` returned *nothing* for a
        repository whose untracked file it otherwise lists. So a brand-new file was
        absent from the digest while the report still called itself available and
        complete — the silent omission this module exists to prevent, arriving through
        the environment rather than through the code.

        `core.worktree` is deliberately *not* the case under test: injected this way it
        is set but ignored for discovery, and only redirects once `GIT_DIR` is also set,
        which is cleared and covered by the test above.
        """
        repo = _repo_with_base(tmp_path)
        (repo / "brand-new.py").write_text(_code(), encoding="utf-8")
        excludes = tmp_path / "excludes"
        excludes.write_text("brand-new.py\n", encoding="utf-8")
        config = tmp_path / "gitconfig"
        config.write_text(f"[core]\n\texcludesFile = {excludes}\n", encoding="utf-8")
        for name, value in env.items():
            monkeypatch.setenv(name, value.format(excludes=excludes, config=config))

        report = _report(repo)

        assert report.available is True, report.reason
        assert "brand-new.py" in [f.path for f in report.files], (
            "an ambient config must not decide what the digest can see"
        )

    def test_the_config_interfaces_are_cleared_by_name(self):
        """Names, not just behaviour: git gained the indexed interface after `GIT_DIR`,
        and a future one would pass the behavioural test above only by accident."""
        for name in (
            "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
            "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
            # Reverses the two above rather than adding to them: it decides whether
            # system config participates at all. Measured -- `GIT_CONFIG_SYSTEM` alone
            # emptied the sweep, and adding this brought the file back.
            "GIT_CONFIG_NOSYSTEM",
            # Widens the upward search where `GIT_CEILING_DIRECTORIES` narrows it, so
            # discovery could settle on an ancestor repository across a mount boundary
            # instead of the project's own. Covered by name only: constructing a mount
            # boundary needs privileges a test suite does not have, and clearing the
            # narrowing variable while leaving the widening one is the asymmetry.
            "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        ):
            assert name in cs._GIT_REDIRECT_VARS, name
        # The indexed pairs need no entry of their own: git ignores `GIT_CONFIG_KEY_n`
        # and `GIT_CONFIG_VALUE_n` unless the count says how many to read, verified, so
        # clearing the count clears the family without scanning for indices.
        assert not [n for n in cs._GIT_REDIRECT_VARS if n.startswith("GIT_CONFIG_KEY")]

    def test_every_git_call_site_runs_with_the_sanitised_environment(self):
        """Structural: a new call site that forgets `env=_git_env()` fails here rather
        than in review — which is how the record query slipped through the first time."""
        import inspect
        source = inspect.getsource(cs)
        launches = source.count("subprocess.run(") + source.count("subprocess.Popen(")

        assert launches >= 3
        assert source.count("env=_git_env()") == launches, "every launch, not most of them"
        # And every captured launch decodes with the codec the streamed reader uses, so
        # the two readers of one path cannot disagree about its name.
        assert source.count("encoding=_PATH_ENCODING,") == source.count("subprocess.run(")
        assert "raw.decode(_PATH_ENCODING, _PATH_ERRORS)" in source

    def test_a_failed_untracked_sweep_makes_the_listing_unavailable(self, tmp_path, monkeypatch):
        """`or []` turned a failed `ls-files` into an empty one, so the report came back
        available while silently missing every new file."""
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add")
        monkeypatch.setattr(cs, "_git_records_bounded", lambda *_a, **_k: None)

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


class TestTheCeilingIsSharedAndTheSweepIsStreamed:
    """The untracked sweep is the one unbounded query. It is read as a stream — kept up
    to the ceiling, counted past it — and the ceiling is shared with the diff rather
    than filled from the diff first, so brand-new files are never the first dropped."""

    def test_the_ceiling_is_shared_so_new_files_are_not_the_first_dropped(self, tmp_path, monkeypatch):
        """Filling in order dropped exactly the untracked files whenever the diff alone
        reached the ceiling — the one omission the sweep exists to prevent."""
        repo = _repo_with_base(tmp_path)
        for name in ("t1.py", "t2.py", "t3.py"):
            (repo / name).write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "tracked")
        for name in ("u1.py", "u2.py", "u3.py"):
            (repo / name).write_text("y = 2\n", encoding="utf-8")
        monkeypatch.setattr(cs, "MAX_CHANGED_ENTRIES", 4)

        entries, total = cs._collect_changed_entries(repo, _git(repo, "rev-parse", "upstream/main"))

        assert (len(entries), total) == (4, 6)
        assert sum(1 for status, _ in entries if status == "?") == 2, "shared, not diff-first"

    def test_under_the_ceiling_the_order_is_diff_then_untracked(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "t.py").write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "tracked")
        (repo / "u.py").write_text("y = 2\n", encoding="utf-8")

        entries, total = cs._collect_changed_entries(repo, _git(repo, "rev-parse", "upstream/main"))

        assert entries == [("A", "t.py"), ("?", "u.py")]
        assert total == 2

    @pytest.mark.parametrize("first,second,expected", [
        ([("t1", "A")], [(f"u{i}", "?") for i in range(10)], [("t1", "A"), ("u0", "?"), ("u1", "?")]),
        ([(f"t{i}", "A") for i in range(10)], [("u1", "?")], [("t0", "A"), ("u1", "?"), ("t1", "A")]),
    ], ids=["one-tracked-many-new", "many-tracked-one-new"])
    def test_the_lopsided_case_still_seats_the_minority(self, first, second, expected):
        """One tracked change beside a large new tree, or the reverse — the common shape,
        not the balanced one. The single entry from the smaller side is seated and the
        rest of the cap goes to the other; a fill-in-order implementation seats none
        of the minority when the majority alone reaches the cap."""
        assert cs._interleave(first, second, 3) == expected

    def test_a_lopsided_population_keeps_the_minority_on_the_real_path(self, tmp_path, monkeypatch):
        """The same asymmetry through git: one tracked change beside five new files under a
        cap of 3. The tracked change is seated, the rest of the cap goes to new files, and
        the total is the whole population — statuses and count, not the picker alone."""
        repo = _repo_with_base(tmp_path)
        (repo / "t.py").write_text("x = 1\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "tracked")
        for i in range(5):
            (repo / f"u{i}.py").write_text("y = 2\n", encoding="utf-8")
        monkeypatch.setattr(cs, "MAX_CHANGED_ENTRIES", 3)

        entries, total = cs._collect_changed_entries(repo, _git(repo, "rev-parse", "upstream/main"))

        assert total == 6
        assert [status for status, _ in entries] == ["A", "?", "?"]

    @pytest.mark.parametrize("tracked,keep", [(0, 4), (1, 3), (2, 2), (3, 2), (9, 2)])
    def test_the_sweep_keeps_only_what_the_shared_ceiling_can_still_seat(self, tracked, keep, tmp_path, monkeypatch):
        """The interleave gives tracked entries at most half the ceiling, so once the diff
        is in hand the room left for new files is known. The sweep is asked for that many
        and no more — not the whole ceiling, to be trimmed after the fact."""
        repo = _repo_with_base(tmp_path)
        for i in range(tracked):
            (repo / f"t{i}.py").write_text("x = 1\n", encoding="utf-8")
        if tracked:
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "tracked")
        asked = []
        real = cs._git_records_bounded

        def spy(root, args, keep_arg, **kwargs):
            asked.append(keep_arg)
            return real(root, args, keep_arg, **kwargs)
        monkeypatch.setattr(cs, "_git_records_bounded", spy)
        monkeypatch.setattr(cs, "MAX_CHANGED_ENTRIES", 4)

        cs._collect_changed_entries(repo, _git(repo, "rev-parse", "upstream/main"))

        assert asked == [keep]

    def test_a_skipped_record_takes_no_kept_slot_and_is_not_counted(self, tmp_path):
        """Deduplication happens inside the stream. A record the caller already holds —
        here `a.txt`, in the diff as deleted and first in the sweep — neither occupies one
        of the `keep` slots, which displaced a genuinely new path behind it, nor adds to
        the total."""
        repo = _repo_with_base(tmp_path)
        _git(repo, "rm", "-q", "--cached", "a.txt")
        for name in ("u1.py", "u2.py", "u3.py"):
            (repo / name).write_text("y = 2\n", encoding="utf-8")

        kept, total = cs._git_records_bounded(
            repo, ["ls-files", "--others", "--exclude-standard", "-z"], 2, skip={"a.txt"},
        )

        assert kept == ["u1.py", "u2.py"], "the duplicate sorted first and took no slot"
        assert total == 3

    def test_a_duplicate_past_the_ceiling_is_counted_once(self, tmp_path, monkeypatch):
        """A `git rm --cached` file is in the diff as deleted and in the sweep as new.
        Beyond the kept prefix it could not be checked against the diff afterwards, so
        the total carried it twice; judged as it streams, each distinct path counts once."""
        repo = _make_repo(tmp_path / "r")
        _commit(repo, "zz.txt")
        _point_ref(repo, "refs/remotes/upstream/main", _git(repo, "rev-parse", "HEAD"))
        _git(repo, "rm", "-q", "--cached", "zz.txt")
        for name in ("u1.py", "u2.py", "u3.py"):
            (repo / name).write_text("y = 2\n", encoding="utf-8")
        monkeypatch.setattr(cs, "MAX_CHANGED_ENTRIES", 2)

        entries, total = cs._collect_changed_entries(repo, _git(repo, "rev-parse", "upstream/main"))

        assert total == 4, "zz.txt once, three new files: four distinct paths"
        assert ("D", "zz.txt") in entries
        assert len(entries) == 2

    @pytest.mark.skipif(sys.platform == "win32", reason="byte filenames are a POSIX matter")
    def test_both_readers_decode_one_path_to_one_string(self, tmp_path, monkeypatch):
        """The diff is captured by `subprocess.run`, the sweep streamed from a pipe; both
        must decode the same bytes with the same codec, or the sweep's dedup against the
        diff misses a file under a non-UTF-8 locale and reports it twice. The codec is
        swapped for one that reads the byte differently, so a reader left on a default
        of its own would disagree here."""
        repo = _repo_with_base(tmp_path)
        with open(os.path.join(os.fsencode(repo), b"caf\xe9.py"), "wb") as handle:
            handle.write(b"x = 1\n")
        monkeypatch.setattr(cs, "_PATH_ENCODING", "latin-1")
        monkeypatch.setattr(cs, "_PATH_ERRORS", "strict")
        args = ["ls-files", "--others", "--exclude-standard", "-z"]

        captured = cs._git_records(repo, args)
        streamed, total = cs._git_records_bounded(repo, args, 5)

        assert captured == streamed == ["café.py"]
        assert total == 1

    def test_a_stream_that_fails_part_way_is_a_tool_failure_not_a_shorter_listing(
        self, tmp_path, monkeypatch, caplog,
    ):
        """An exception on the pump thread used to end the thread and be printed nowhere;
        the caller read a stopped pump as a finished one and returned the prefix it had
        as the listing — new files absent, and nothing said."""
        class _Breaking:
            def __init__(self):
                self.calls = 0

            def read(self, _size):
                self.calls += 1
                if self.calls == 1:
                    return b"a.py\0"
                raise OSError("pipe went away")

        class _Proc:
            killed = False

            def __init__(self, *_a, **_k):
                self.stdout = _Breaking()

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def wait(self, timeout=None):
                return 0

            def kill(self):
                _Proc.killed = True

        monkeypatch.setattr(cs.subprocess, "Popen", _Proc)

        with caplog.at_level("WARNING", logger="studio"):
            result = cs._git_records_bounded(tmp_path, ["ls-files", "-z"], 5)

        assert result is None, "a prefix is not the listing"
        assert _Proc.killed
        # The stream template, not the launch one: git started and the pipe then broke,
        # which is a different fact for an operator. Asserted exactly, so the two
        # cannot converge on one wording and lose that distinction.
        assert cs._LOG_GIT_STREAM_FAILED % "OSError" in [
            r.getMessage() for r in caplog.records if r.levelname == "WARNING"
        ], "the shared template, not merely a message naming the type"

    def test_a_record_that_never_ends_is_bounded_not_buffered_forever(self, tmp_path, monkeypatch, caplog):
        """`keep` bounds how many records are stored, not how long one may grow; a child
        that never writes a NUL was buffered chunk after chunk until the deadline."""
        class _Endless:
            reads = 0

            def read(self, _size):
                _Endless.reads += 1
                return b"x" * 64

        class _Proc:
            def __init__(self, *_a, **_k):
                self.stdout = _Endless()

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        monkeypatch.setattr(cs.subprocess, "Popen", _Proc)
        monkeypatch.setattr(cs, "_MAX_RECORD_BYTES", 200)

        with caplog.at_level("WARNING", logger="studio"):
            result = cs._git_records_bounded(tmp_path, ["ls-files", "-z"], 5)

        assert result is None
        assert _Endless.reads == 4, "stopped the read after the bound was crossed, not at the deadline"
        assert any("ValueError" in r.getMessage() for r in caplog.records if r.levelname == "WARNING")

    def test_a_terminated_record_over_the_bound_is_refused_too(self, tmp_path, monkeypatch, caplog):
        """The bound applies to a completed record as much as to the unterminated tail;
        checking the tail alone let a record that ended inside the chunk through."""
        class _Proc:
            def __init__(self, *_a, **_k):
                self.stdout = io.BytesIO(b"x" * 300 + b"\0" + b"a.py\0")

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        monkeypatch.setattr(cs.subprocess, "Popen", _Proc)
        monkeypatch.setattr(cs, "_MAX_RECORD_BYTES", 200)

        with caplog.at_level("WARNING", logger="studio"):
            result = cs._git_records_bounded(tmp_path, ["ls-files", "-z"], 5)

        assert result is None
        assert any("ValueError" in r.getMessage() for r in caplog.records if r.levelname == "WARNING")

    def test_an_oversized_record_makes_the_whole_listing_unavailable(self, tmp_path, monkeypatch):
        """The unit above shows the reader returns no answer; this shows the absence
        reaches the report as unavailable with its reason — not as an empty, available
        untracked list, which an `or ([], 0)` fallback in the collector would produce
        while quietly dropping every new file."""
        repo = _repo_with_base(tmp_path)
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        _git(repo, "add", "m.py")
        _git(repo, "commit", "-q", "-m", "add")

        class _Proc:
            def __init__(self):
                self.stdout = io.BytesIO(b"x" * 300 + b"\0")

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        real_popen = subprocess.Popen

        def only_the_sweep_is_faked(args, *rest, **kwargs):
            # `subprocess.run` launches through the same `Popen`, so the window's and the
            # diff's queries must still reach git; only the untracked sweep is stood in for.
            return _Proc() if "ls-files" in args else real_popen(args, *rest, **kwargs)
        monkeypatch.setattr(cs.subprocess, "Popen", only_the_sweep_is_faked)
        monkeypatch.setattr(cs, "_MAX_RECORD_BYTES", 200)

        report = _report(repo)

        assert report.available is False, "a listing the sweep could not complete is not a listing"
        assert report.reason == cs.REASON_DIFF_UNAVAILABLE
        assert report.files == ()

    def test_the_bounded_reader_keeps_the_cap_and_counts_the_rest(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        for i in range(5):
            (repo / f"u{i}.py").write_text("x = 1\n", encoding="utf-8")

        kept, total = cs._git_records_bounded(
            repo, ["ls-files", "--others", "--exclude-standard", "-z"], 2,
        )

        assert kept == ["u0.py", "u1.py"]
        assert total == 5

    def test_the_bounded_reader_returns_nothing_on_a_non_zero_exit(self, tmp_path):
        repo = _make_repo(tmp_path / "r")

        assert cs._git_records_bounded(repo, ["rev-parse", "--verify", "refs/heads/no-such"], 5) is None

    def test_a_launch_failure_and_a_broken_stream_do_not_share_one_message(self):
        """Two different facts for an operator: git never started, versus git started
        and the pipe broke part-way.

        Pinned here rather than left to the two tests that assert each message, because
        those compare against the templates themselves — so if the two names ever became
        one value, both would still pass while the log lost the distinction. Verified: a
        mutation aliasing one to the other passed the whole streaming suite until this
        existed.
        """
        assert cs._LOG_GIT_FAILED != cs._LOG_GIT_STREAM_FAILED
        assert "could not run" in cs._LOG_GIT_FAILED
        assert "stream failed" in cs._LOG_GIT_STREAM_FAILED

    def test_the_bounded_reader_degrades_when_git_cannot_launch(self, tmp_path, monkeypatch, caplog):
        def _no_git(*_a, **_k):
            raise OSError("git: not found")
        monkeypatch.setattr(cs.subprocess, "Popen", _no_git)

        with caplog.at_level("WARNING", logger="studio"):
            result = cs._git_records_bounded(tmp_path, ["ls-files", "-z"], 5)

        assert result is None
        assert any(r.levelname == "WARNING" and "could not run" in r.getMessage() for r in caplog.records)

    def test_a_git_that_closes_its_pipe_but_never_exits_is_killed(self, tmp_path, monkeypatch, caplog):
        """The stream reaches EOF but git never exits: the wait carries the module's
        timeout, so the process is killed rather than left running, and reported like
        any other tool failure. The pipe held open in silence is the next test."""
        class _Hung:
            killed = False

            def __init__(self, *_a, **_k):
                self.stdout = io.BytesIO(b"a.py\0")

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired(cmd="git", timeout=timeout)

            def kill(self):
                _Hung.killed = True

        monkeypatch.setattr(cs.subprocess, "Popen", _Hung)

        with caplog.at_level("WARNING", logger="studio"):
            result = cs._git_records_bounded(tmp_path, ["ls-files", "-z"], 5)

        assert result is None
        assert _Hung.killed, "a hung git is not left running"
        assert any("TimeoutExpired" in r.getMessage() for r in caplog.records if r.levelname == "WARNING")

    def test_a_sweep_that_holds_the_pipe_open_is_killed_at_the_deadline(self, tmp_path, monkeypatch, caplog):
        """A `read()` on a pipe git keeps open without writing never returns, so a
        `wait(timeout)` placed after it could never run. The reader now pumps on a
        helper thread against the module's deadline, and a silent git is killed."""
        class _StalledPipe:
            def __init__(self, gate):
                self.gate = gate

            def read(self, _size):
                self.gate.wait()
                return b""

        class _Stalled:
            killed = False

            def __init__(self, *_a, **_k):
                self.gate = threading.Event()
                self.stdout = _StalledPipe(self.gate)

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def wait(self, timeout=None):
                return 0

            def kill(self):
                _Stalled.killed = True
                self.gate.set()

        monkeypatch.setattr(cs.subprocess, "Popen", _Stalled)
        monkeypatch.setattr(cs, "_GIT_TIMEOUT", 0.2)
        started = time.monotonic()

        with caplog.at_level("WARNING", logger="studio"):
            result = cs._git_records_bounded(tmp_path, ["ls-files", "-z"], 5)

        assert result is None
        assert _Stalled.killed, "a silent git is not left holding the pipe"
        assert time.monotonic() - started < 5, "returned at the deadline, not never"
        assert any("TimeoutExpired" in r.getMessage() for r in caplog.records if r.levelname == "WARNING")

    def test_an_unterminated_final_record_is_kept_and_counted(self, tmp_path, monkeypatch):
        """`_git_records` keeps a trailing record with no NUL after it; the streamed
        reader must agree, or the two would disagree about the same output."""
        class _Short:
            def __init__(self, *_a, **_k):
                self.stdout = io.BytesIO(b"a.py\0b.py")

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        monkeypatch.setattr(cs.subprocess, "Popen", _Short)

        assert cs._git_records_bounded(tmp_path, ["ls-files", "-z"], 5) == (["a.py", "b.py"], 2)
        assert cs._git_records_bounded(tmp_path, ["ls-files", "-z"], 1) == (["a.py"], 2)

    def test_a_launch_failure_is_a_warning_and_a_miss_is_not(self, tmp_path, monkeypatch, caplog):
        """The tool failing and git answering "no" must not look alike in a log."""
        repo = _make_repo(tmp_path / "r")
        with caplog.at_level("DEBUG", logger="studio"):
            cs._git_records(repo, ["rev-parse", "--verify", "refs/heads/no-such"])
        assert not [r for r in caplog.records if r.levelname == "WARNING"], "a miss is routine"

        def _no_git(*_a, **_k):
            raise OSError("git: not found at /secret/path")
        monkeypatch.setattr(cs.subprocess, "run", _no_git)
        caplog.clear()
        with caplog.at_level("WARNING", logger="studio"):
            assert cs._git_records(repo, ["diff"]) is None
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert warnings and warnings[0] == cs._LOG_GIT_FAILED % "OSError"
        assert "/secret/path" not in warnings[0], "the type, not the message"


class TestNoExtensionFilterApplies:
    """Pinned as a design decision: the digest reads both directions, and a changed
    feature artifact declares requirements without carrying a code extension, so the
    registry's extension list would report a changed specification as tracing to
    nothing. What a file does with IDs is decided by reading it, not by its suffix."""

    def test_a_non_source_extension_is_read_not_excluded(self, tmp_path):
        repo = _repo_with_base(tmp_path)
        (repo / "deps.lock").write_text("nothing to see\n", encoding="utf-8")
        _git(repo, "add", "deps.lock")
        _git(repo, "commit", "-q", "-m", "lock")

        report = _report(repo)

        assert report.excluded == 0
        assert [(f.path, f.reason) for f in report.files] == [("deps.lock", cs.REASON_OK)]

    def test_the_resolver_is_asked_about_containment_with_no_fabricated_filter(self, tmp_path, monkeypatch):
        repo = _make_repo(tmp_path / "r")
        (repo / "m.py").write_text(_code(), encoding="utf-8")
        asked = {}
        real = cs.codebase.resolve_entry_code_files

        def _spy(candidate, extensions, **kwargs):
            asked["extensions"] = extensions
            return real(candidate, extensions, **kwargs)
        monkeypatch.setattr(cs.codebase, "resolve_entry_code_files", _spy)

        assert cs._in_project_scope(repo / "m.py", repo) is True
        assert asked["extensions"] == [], "no filter is in force, so none is pretended"


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
