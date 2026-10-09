"""The sub-agent work check: does the tree back the claim?

Every test drives a real git repository rather than a stubbed one, because the whole point
of this check is that it reads something the agent cannot narrate -- a fake tree would be
exactly the report we refuse to trust.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio.utils import git_read, subagent_work as sw  # noqa: E402
from studio.commands.verify_subagent_work import cmd_verify_subagent_work  # noqa: E402
from studio import cli  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _run(repo: Path, *args: str) -> None:
    # `env=git_read.env()` for the same reason the production reader uses it: an inherited
    # GIT_DIR or GIT_WORK_TREE sends git at a different repository despite `cwd=repo`, which
    # would make every fixture here quietly unreliable in a git-controlled environment.
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   env=git_read.env())


@pytest.fixture(name="repo")
def _repo(tmp_path: Path) -> Path:
    """A real repository with one commit."""
    _run(tmp_path, "init", "-q", ".")
    _run(tmp_path, "config", "user.email", "t@example.invalid")
    _run(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    _run(tmp_path, "add", "-A")
    _run(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_an_untouched_tree_is_reported_unchanged(repo: Path) -> None:
    before = sw.mark(repo)
    assert before is not None
    result = sw.compare(repo, before)
    assert result.verdict is sw.Verdict.UNCHANGED
    assert result.blocks is True


def test_an_edit_left_uncommitted_is_a_change(repo: Path) -> None:
    # A run may be configured not to commit, so reading HEAD alone would call this
    # "nothing happened" -- the exact false accusation this check must not make.
    before = sw.mark(repo)
    (repo / "a.txt").write_text("hello\nmore\n", encoding="utf-8")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_a_committed_change_is_a_change(repo: Path) -> None:
    before = sw.mark(repo)
    (repo / "a.txt").write_text("hello\nmore\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "work")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_a_brand_new_untracked_file_is_a_change(repo: Path) -> None:
    before = sw.mark(repo)
    (repo / "nested").mkdir()
    (repo / "nested" / "new.txt").write_text("brand new\n", encoding="utf-8")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_a_second_file_in_an_already_untracked_directory_is_a_change(repo: Path) -> None:
    # The case that forces `--untracked-files=all`. git's DEFAULT status collapses an
    # untracked directory to one entry (`?? nested/`), so adding a second file inside it
    # leaves the status text byte-identical -- and the whole contribution would read as
    # "nothing happened". Marking before the directory exists would not catch this,
    # because the directory itself is the change.
    (repo / "nested").mkdir()
    (repo / "nested" / "first.txt").write_text("one\n", encoding="utf-8")
    before = sw.mark(repo)                      # `nested/` is already untracked here
    (repo / "nested" / "second.txt").write_text("two\n", encoding="utf-8")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_an_edit_to_an_already_dirty_tracked_file_is_a_change(repo: Path) -> None:
    # The case every other test here misses, because they all start from a clean tree.
    # `git status` names WHICH paths are dirty, never WHAT is in them: a file already
    # modified before dispatch keeps the same path and the same status code when the agent
    # edits it again, and HEAD has not moved either. Measured before the fix, both marks were
    # byte-identical and real work reported UNCHANGED — a false accusation, which is the one
    # thing this check must never make.
    (repo / "a.txt").write_text("hello\npre-existing edit\n", encoding="utf-8")
    before = sw.mark(repo)                       # already dirty at dispatch time
    (repo / "a.txt").write_text("hello\npre-existing edit\nTHE AGENT WROTE THIS\n",
                                encoding="utf-8")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_rewriting_an_already_untracked_file_is_a_change(repo: Path) -> None:
    # Same defect, untracked half: the status line `?? new.txt` is identical before and after.
    (repo / "new.txt").write_text("first draft\n", encoding="utf-8")
    before = sw.mark(repo)
    (repo / "new.txt").write_text("the agent rewrote this entirely\n", encoding="utf-8")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_a_change_is_seen_when_the_root_is_a_subdirectory(repo: Path) -> None:
    # `--porcelain` paths are relative to the REPOSITORY root, not to the directory git ran
    # in. Joining them to the caller's --root only works when the two coincide; from a
    # subdirectory the built path does not exist, every dirty file reads as unreadable, and
    # the content fingerprint degrades back to status-only — silently undoing the fix above.
    nested = repo / "nested" / "deep"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("base\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "nested")
    (nested / "file.txt").write_text("base\nalready dirty\n", encoding="utf-8")

    sub = repo / "nested"
    before = sw.mark(sub)                       # marked FROM the subdirectory
    assert before is not None
    (nested / "file.txt").write_text("base\nalready dirty\nAGENT WROTE THIS\n",
                                     encoding="utf-8")
    assert sw.compare(sub, before).verdict is sw.Verdict.CHANGED


def test_a_path_resolving_outside_the_tree_is_refused(repo: Path, tmp_path: Path) -> None:
    # The names come from git, not from a user, but `--root` arrives on the command line.
    # A name resolving outside the tree is not part of what this check measures, so it is
    # refused rather than read. Compared with the SAME name whose target does not exist:
    # if the contents were being read, the two would differ. The path name itself is hashed
    # either way (it is the delimiter), so only the refusal can make them equal.
    outside = repo.parent / "outside.txt"
    escaping = ["../outside.txt"]

    outside.write_text("not part of this tree\n", encoding="utf-8")
    with_target = sw._content_digest(repo, escaping)
    outside.unlink()
    without_target = sw._content_digest(repo, escaping)

    assert with_target == without_target, (
        "the escaping path's contents reached the fingerprint; a file outside the tree being "
        "checked must be refused exactly as an unreadable one is")


@pytest.mark.parametrize("answer", [(None, True), (None, False), ("", False), ("   \n", False)],
                         ids=["tool-failed", "non-zero-exit", "empty", "blank"])
def test_the_top_level_is_none_when_git_cannot_name_it(repo: Path, answer,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    # Each way `rev-parse --show-toplevel` can decline to answer: the tool failing, a non-zero
    # exit (outside a repository), and an answer that is empty or only whitespace. All must
    # return None so `mark` falls back to the caller's root rather than building `Path("")`,
    # which resolves to the process's cwd — a different tree entirely.
    monkeypatch.setattr(sw.git_read, "query", lambda *_a, **_k: answer)
    assert sw._repo_root(repo) is None


def test_no_repository_top_level_means_no_mark_at_all(repo: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    # Review finding: the earlier version fell back to the caller's root when
    # `rev-parse --show-toplevel` could not answer. Status paths are relative to the
    # repository root, so a different base reads the wrong files — and a mark that is wrong
    # in a *stable* way compares equal to itself, which reads as UNCHANGED. Degrading to no
    # mark instead reaches "could not be asked", which is the documented direction.
    monkeypatch.setattr(sw, "_repo_root", lambda _root: None)
    assert sw.mark(repo) is None
    assert sw.compare(repo, "tree1:" + "0" * 32).verdict is sw.Verdict.UNKNOWN


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_a_symlink_loop_does_not_raise_through_mark(repo: Path) -> None:
    # `Path.resolve()` raises **RuntimeError**, not OSError, on a symlink loop. Catching only
    # OSError let it escape `mark()` and break the caller's run, against this module's stated
    # never-raises contract — the same trap as `Path.home()` raising RuntimeError where a
    # guard expected OSError. Reproduced before the fix.
    (repo / "loop").symlink_to("loop")
    marked = sw.mark(repo)                       # must not raise
    assert marked is None or marked.startswith("tree1:")
    result = sw.compare(repo, "tree1:" + "0" * 32)   # must not raise either
    assert result.verdict in (sw.Verdict.UNKNOWN, sw.Verdict.CHANGED)


def test_an_unresolvable_root_degrades_instead_of_raising(repo: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    # `Path.resolve()` can raise on a path the filesystem will not answer for. The digest then
    # has nothing to add, which is a degraded answer rather than an exception escaping into a
    # caller's run — the same fail direction every other unreadable case takes here.
    class _Unresolvable(type(repo)):  # type: ignore[misc]
        def resolve(self, strict: bool = False):  # noqa: ARG002
            raise OSError("this path cannot be resolved")
    assert sw._content_digest(_Unresolvable(repo), ["a.txt"]) == hashlib.sha256().digest()


def test_a_rename_includes_its_source_path(repo: Path) -> None:
    # Review finding: `R  new\0old\0` spans two records and the second carries no `XY ` status
    # prefix. Slicing three characters off it corrupts the source into a path that does not
    # exist — or drops it entirely when it is three characters or shorter, which `abc` is.
    (repo / "abc").write_text("content here\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "add abc")
    _run(repo, "mv", "abc", "xyz")

    status, _failed = git_read.query(
        repo, ["status", "--porcelain=v2", "-z", "--untracked-files=all"])
    assert status is not None
    paths = sw._dirty_paths(status)
    assert "xyz" in paths, "the rename destination must be named"
    assert "abc" in paths, (
        "the rename SOURCE is missing: its record carries no status prefix, so slicing three "
        "characters off it loses the path entirely for a short name")


#: A real `--porcelain=v2 -z` rename record, copied from git output rather than hand-shaped.
_V2_RENAME = ("2 R. N... 100644 100644 100644 d95f3ad14dee633a758d2e331151e950dd13e4ed "
              "d95f3ad14dee633a758d2e331151e950dd13e4ed R100 destination")
_V2_ORDINARY = ("1 .M N... 100644 100644 100644 587be6b4c3f93f93c489c0111bba5596147a26cb "
                "587be6b4c3f93f93c489c0111bba5596147a26cb other")


@pytest.mark.parametrize("score", ["R100", "C75"], ids=["rename", "copy"])
def test_both_rename_and_copy_records_consume_their_source(score: str) -> None:
    # A direct parser test, because git emits a copy record only when copy detection is
    # configured, so a repository fixture cannot reach that branch by default. `_dirty_paths`
    # is a pure function over the status text, which is where a parser test belongs.
    status = f"{_V2_RENAME.replace('R100', score)}\0source\0{_V2_ORDINARY}\0"
    assert sw._dirty_paths(status) == ["destination", "source", "other"]


def test_a_two_record_status_does_not_run_past_its_end() -> None:
    # A rename record with no following source — truncated output, or a shape this does not
    # model. It must not raise and must not invent a path.
    assert sw._dirty_paths(f"{_V2_RENAME}\0") == ["destination"]
    assert sw._dirty_paths(f"{_V2_RENAME}\0\0") == ["destination"]


def test_an_unmerged_record_names_its_path() -> None:
    # A conflicted file during a merge. Taken verbatim from real git output: the `u` shape
    # carries three stage hashes and four modes, so it has 10 fields before the path rather
    # than the 8 an ordinary change has. Parsing it as an ordinary record would slice the
    # path apart — and a conflicted tree is exactly when a verifier should still work.
    status = ("u UU N... 100644 100644 100644 100644 "
              "df967b96a579e45a18b8251732d16804b2e56a55 "
              "b19a1e93bec1317dc6097229e12afaffbfa74dc2 "
              "950b81b7eee953d050aa05a641f8e056c85dd1bd f.txt\0")
    assert sw._dirty_paths(status) == ["f.txt"]


def test_a_malformed_record_is_skipped_not_guessed() -> None:
    # A record whose field count does not match its shape is not something this models. It is
    # skipped rather than half-parsed into a path that does not exist.
    assert sw._dirty_paths("1 .M N... 100644 truncated\0") == []
    assert sw._dirty_paths("u UU N... 100644\0") == []
    assert sw._dirty_paths("2 R. N... 100644 short\0") == []


def test_a_path_containing_spaces_survives_the_parser() -> None:
    # v2 fields are space-separated and a path may contain spaces, so each shape splits on a
    # fixed field count and takes the remainder — never on the last space.
    spaced = _V2_ORDINARY.rsplit(" ", 1)[0] + " a file with spaces.txt"
    assert sw._dirty_paths(f"{spaced}\0") == ["a file with spaces.txt"]


def test_a_mangled_rename_source_cannot_pull_in_an_unrelated_file(repo: Path) -> None:
    """The real harm the rename fix prevents — and it is not a missing contribution.

    A renamed source does not exist on disk after the rename, so its bytes were never going to
    be read. The danger is the **mangled** name: slicing three characters off `oldname.txt`
    yields `name.txt`, which may be a different, real file. Its contents would then be hashed
    as though it were part of this change, making the fingerprint depend on a file the agent
    never touched.

    (An earlier regression here was vacuous: it renamed and then edited, so the porcelain
    status changed from `R ` to `RM` and the mark differed through the status component alone.
    Removing the content digest entirely left it passing. Review flagged exactly that risk.)
    """
    (repo / "oldname.txt").write_text("the real source\n", encoding="utf-8")
    (repo / "name.txt").write_text("AN UNRELATED FILE\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "two files")
    _run(repo, "mv", "oldname.txt", "brandnew.txt")

    status, _failed = git_read.query(
        repo, ["status", "--porcelain=v2", "-z", "--untracked-files=all"])
    assert status is not None
    paths = sw._dirty_paths(status)
    assert "oldname.txt" in paths, "the rename source must be named in full"
    assert "name.txt" not in paths, (
        "the mangled source name reached the path list; `name.txt` is a different, clean file "
        "and hashing it would make the mark depend on content the agent never touched")


def test_an_edit_far_beyond_the_old_sampling_bound_is_a_change(repo: Path) -> None:
    # Review finding, reproduced: the content digest used to stop after the first 64 KiB, so an
    # agent editing past that point in an ALREADY-dirty file produced a byte-identical mark —
    # the very case content hashing was added to catch. Files are now read in full, chunked for
    # memory rather than truncated for speed.
    big = repo / "big.txt"
    big.write_text("A" * 200_000 + "\nEND\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "big")
    big.write_text("A" * 200_000 + "\nEND\npre-existing edit\n", encoding="utf-8")

    before = sw.mark(repo)                       # already dirty at dispatch time
    assert before is not None
    with big.open("a", encoding="utf-8") as handle:
        handle.write("THE AGENT WROTE THIS AT THE VERY END\n")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def _dirty_beyond_the_path_cap(repo: Path) -> Path:
    """Leave more paths dirty than the content cap, and hand back one sorted past the cut."""
    for i in range(sw._CONTENT_PATHS + 1):
        (repo / f"f{i:05d}.txt").write_text("pre-existing\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "many")
    for i in range(sw._CONTENT_PATHS + 1):
        (repo / f"f{i:05d}.txt").write_text("pre-existing edit\n", encoding="utf-8")
    return repo / f"f{sw._CONTENT_PATHS:05d}.txt"   # last by sort, so first to be dropped


def test_an_unrecognised_record_kind_contributes_no_path() -> None:
    # porcelain v2 defines `1`, `2`, `u`, `?` and `!`; a future git could add another. An
    # unknown kind yields no path rather than a guessed one -- a record this cannot read must
    # not put an invented name into the fingerprint. It also must not swallow the records
    # around it, so a known record either side is still read.
    # The unknown record is shaped EXACTLY like an ordinary `1` record apart from its kind,
    # so a parser that fell back to a default field count would happily yield `future.txt`.
    # A record whose shape cannot parse either way would not tell the two apart.
    future = "x" + _V2_ORDINARY[1:].replace("other", "future.txt")
    status = _V2_ORDINARY + "\0" + future + "\0" + "? new.txt\0"
    assert sw._dirty_paths(status) == ["other", "new.txt"], (
        "a record kind this parser does not define contributed a path")
    assert sw._record_path(future) is None


def test_more_dirty_paths_than_the_cap_yields_no_mark(repo: Path) -> None:
    # Review finding, reproduced: the digest used to take `sorted(paths)[:512]` while its own
    # comment claimed the ceiling was "stated rather than silently truncated". Declining to
    # answer is the only honest option -- a partial digest cannot tell the two cases apart.
    _dirty_beyond_the_path_cap(repo)
    assert sw.mark(repo) is None


def test_an_edit_past_the_path_cap_is_never_reported_unchanged(repo: Path) -> None:
    # The defect the cap caused: with the tail of the sorted path list unhashed, an agent
    # editing an already-dirty path beyond the cut moved neither HEAD nor the status records,
    # so the mark was byte-identical and real work read as UNCHANGED. UNKNOWN is correct here;
    # UNCHANGED is the false accusation this module exists to prevent.
    beyond_the_cut = _dirty_beyond_the_path_cap(repo)
    before = sw.mark(repo)
    beyond_the_cut.write_text("THE AGENT WROTE THIS\n", encoding="utf-8")

    result = sw.compare(repo, before)
    assert result.verdict is not sw.Verdict.UNCHANGED, (
        "an edit the mark could not cover was reported as no work at all")
    assert result.verdict is sw.Verdict.UNKNOWN
    assert result.blocks is False, "an unanswerable check must not block the run"


def test_dirty_paths_up_to_the_cap_are_still_fingerprinted(repo: Path) -> None:
    # The cap must not be so eager that the ordinary case degrades: at exactly the cap the
    # check still answers, and still catches an edit to the last path by sort order.
    for i in range(sw._CONTENT_PATHS):
        (repo / f"f{i:05d}.txt").write_text("pre-existing\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "exactly the cap")
    for i in range(sw._CONTENT_PATHS):
        (repo / f"f{i:05d}.txt").write_text("pre-existing edit\n", encoding="utf-8")

    before = sw.mark(repo)
    assert before is not None, "at the cap the check must still answer"
    (repo / f"f{sw._CONTENT_PATHS - 1:05d}.txt").write_text("agent\n", encoding="utf-8")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_a_mode_change_alone_is_a_change(repo: Path) -> None:
    # Review finding: the fingerprint carried no mode information. `git status --porcelain=v1`
    # renders `chmod +x` as the same two characters as a content edit, so a mode-only change
    # was invisible. v2 reports HEAD, index and worktree modes separately.
    script = repo / "run.sh"
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", "script")

    before = sw.mark(repo)
    assert before is not None
    script.chmod(0o755)                          # content untouched; only the mode moves
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_a_staged_edit_is_a_change(repo: Path) -> None:
    # v2 carries the object ids for HEAD and index, so staged content is visible in the status
    # text itself rather than depending on reading the worktree file.
    (repo / "a.txt").write_text("hello\nstaged edit\n", encoding="utf-8")
    _run(repo, "add", "-A")
    before = sw.mark(repo)
    assert before is not None
    (repo / "a.txt").write_text("hello\nstaged edit\nand another\n", encoding="utf-8")
    _run(repo, "add", "-A")
    assert sw.compare(repo, before).verdict is sw.Verdict.CHANGED


def test_contents_cannot_slide_between_two_dirty_files(repo: Path) -> None:
    # The path name is not decoration in the content digest: it is the delimiter. Hashing the
    # bytes of each dirty file with nothing between them makes "ab" + "c" and "a" + "bc"
    # identical, so an agent moving a character from one file to another would fingerprint as
    # no change at all. The status line cannot save this — it names the same two paths with
    # the same codes in both trees.
    (repo / "x.txt").write_text("ab", encoding="utf-8")
    (repo / "y.txt").write_text("c", encoding="utf-8")
    split_one = sw.mark(repo)

    (repo / "x.txt").write_text("a", encoding="utf-8")
    (repo / "y.txt").write_text("bc", encoding="utf-8")
    split_two = sw.mark(repo)

    assert split_one is not None
    assert split_one != split_two, (
        "the same bytes divided differently between two dirty files produced one mark, so "
        "moving content between files would report UNCHANGED")


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode-000 file")
def test_an_unreadable_dirty_file_is_distinguishable_from_an_empty_one(repo: Path) -> None:
    # The invariant the unreadable marker exists for. If a file whose bytes cannot be read
    # contributed *nothing*, it would fingerprint identically to an empty file at the same
    # path — two different trees with one mark, which is the false-unchanged this whole
    # change exists to prevent, reintroduced by another route.
    empty = repo / "secret.txt"
    empty.write_text("", encoding="utf-8")
    mark_empty = sw.mark(repo)

    empty.write_text("content that cannot be read\n", encoding="utf-8")
    empty.chmod(0o000)
    try:
        mark_unreadable = sw.mark(repo)
    finally:
        empty.chmod(0o644)

    assert mark_empty is not None
    assert mark_unreadable is not None
    assert mark_unreadable != mark_empty, (
        "an unreadable dirty file fingerprints the same as an empty one, so a tree that "
        "changed would report UNCHANGED")


@pytest.mark.parametrize("bad", [
    "tree1:not-a-digest",                        # prefixed, but not a digest
    "tree1:" + "0" * 31,                         # one character short
    "tree1:" + "0" * 33,                         # one character long
    "tree1:" + "G" * 32,                         # not hexadecimal
    "tree1:",                                    # prefix alone
])
def test_a_malformed_mark_is_unknown_not_changed(repo: Path, bad: str) -> None:
    # A prefix check alone passes these, and they then compare unequal to every real mark —
    # so the answer would be a confident CHANGED from an input this cannot read. The
    # documented outcome for an unusable mark is "could not be asked".
    result = sw.compare(repo, bad)
    assert result.verdict is sw.Verdict.UNKNOWN, bad
    assert result.blocks is False


def test_a_change_undone_is_honestly_reported_unchanged(repo: Path) -> None:
    # Edited then reverted really is no contribution, and saying so is correct.
    before = sw.mark(repo)
    (repo / "a.txt").write_text("temporary\n", encoding="utf-8")
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    assert sw.compare(repo, before).verdict is sw.Verdict.UNCHANGED


@pytest.mark.parametrize("earlier, why", [
    (None, "no mark at all"),
    ("", "an empty mark"),
    ("deadbeef", "a mark this check did not write"),
])
def test_an_unusable_mark_is_unknown_and_never_unchanged(repo: Path, earlier, why: str) -> None:
    # The one error that would make this worse than no check: reporting "nothing changed"
    # when the question was never answered would hold a run on a false accusation.
    result = sw.compare(repo, earlier)
    assert result.verdict is sw.Verdict.UNKNOWN, why
    assert result.blocks is False


def test_a_directory_that_is_not_a_repository_is_unknown(tmp_path: Path) -> None:
    assert sw.mark(tmp_path) is None
    result = sw.compare(tmp_path, "tree1:" + "0" * 32)
    assert result.verdict is sw.Verdict.UNKNOWN
    assert result.blocks is False


def test_a_repository_before_its_first_commit_can_still_be_marked(tmp_path: Path) -> None:
    # No HEAD is not an error: there is still a working tree, and a sub-agent's first
    # contribution to a fresh repository is exactly when this must work.
    _run(tmp_path, "init", "-q", ".")
    before = sw.mark(tmp_path)
    assert before is not None
    (tmp_path / "first.txt").write_text("x\n", encoding="utf-8")
    assert sw.compare(tmp_path, before).verdict is sw.Verdict.CHANGED


def test_git_failing_to_launch_is_unknown_not_a_crash(repo: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    # The launch lives in the shared reader, so that is where it must be intercepted.
    def _boom(*_args, **_kwargs):
        raise OSError("git is not here")
    monkeypatch.setattr(git_read.subprocess, "run", _boom)
    assert sw.mark(repo) is None
    assert sw.compare(repo, "tree1:" + "0" * 32).verdict is sw.Verdict.UNKNOWN


def test_the_mark_never_carries_the_status_text(repo: Path) -> None:
    # The status names every dirty path in the project; the mark is passed on a command
    # line and may be logged, so it must be a digest and nothing else.
    (repo / "secret-plan.txt").write_text("x\n", encoding="utf-8")
    taken = sw.mark(repo)
    assert taken is not None
    assert "secret-plan" not in taken
    assert taken.startswith("tree1:")


class TestTheCommandsExitCodes:
    """0 when the tree moved or the question could not be asked; 2 only when it did not."""

    def test_an_unchanged_tree_exits_two(self, repo: Path, capsys: pytest.CaptureFixture) -> None:
        before = sw.mark(repo)
        assert cmd_verify_subagent_work(["--since", str(before), "--root", str(repo)]) == 2

    def test_a_changed_tree_exits_zero(self, repo: Path, capsys: pytest.CaptureFixture) -> None:
        before = sw.mark(repo)
        (repo / "a.txt").write_text("changed\n", encoding="utf-8")
        assert cmd_verify_subagent_work(["--since", str(before), "--root", str(repo)]) == 0

    def test_an_unknown_verdict_exits_zero(self, tmp_path: Path,
                                           capsys: pytest.CaptureFixture) -> None:
        # Not every project is a git checkout; refusing to proceed there would make the
        # common case unusable, and the trust this replaces was worth nothing anyway.
        assert cmd_verify_subagent_work(["--since", "tree1:" + "0" * 32,
                                         "--root", str(tmp_path)]) == 0

    def test_marking_exits_zero_and_prints_a_mark(self, repo: Path,
                                                  capsys: pytest.CaptureFixture) -> None:
        assert cmd_verify_subagent_work(["--mark", "--root", str(repo)]) == 0
        assert "tree1:" in capsys.readouterr().out

    def test_requiring_one_mode_rejects_neither(self, repo: Path,
                                                capsys: pytest.CaptureFixture) -> None:
        assert cmd_verify_subagent_work(["--root", str(repo)]) == 2


class TestRegistration:
    """verify-subagent-work is reachable through every dispatch table (B7)."""

    def test_handler_is_mapped(self) -> None:
        assert cli._COMMAND_HANDLERS["verify-subagent-work"] == "_cmd_verify_subagent_work"

    def test_handler_reference_is_kept_for_dead_code_scanners(self) -> None:
        assert cli._cmd_verify_subagent_work in cli._COMMAND_HANDLER_REFERENCES

    def test_command_has_a_description(self) -> None:
        assert "verify-subagent-work" in cli._COMMAND_DESCRIPTIONS

    def test_the_command_is_listed_in_a_section(self) -> None:
        listed = {name for _title, names in cli._COMMAND_SECTIONS for name in names}
        assert "verify-subagent-work" in listed, (
            "a command absent from every section is unreachable from `cfs --help`")

    def test_dispatch_actually_runs_the_command(self, repo: Path) -> None:
        # B7: assert the wiring, do not assume it. A mapped name that dispatches nowhere
        # looks identical in the table above.
        assert cli._cmd_verify_subagent_work(["--mark", "--root", str(repo)]) == 0


REPO_ROOT = Path(__file__).resolve().parents[1]
DISPATCH = REPO_ROOT / "skills/studio/modules/coding-author-dispatch.md"


def _dispatch_do_block() -> list[str]:
    """The `DO:` lines of `UNIT CodingAuthorDispatch`, in written order."""
    lines, unit, collecting, body = DISPATCH.read_text(encoding="utf-8").splitlines(), False, False, []
    for line in lines:
        s = line.strip()
        if s.startswith("UNIT "):
            unit = s == "UNIT CodingAuthorDispatch"
            collecting = False
        elif unit and s == "DO:":
            collecting = True
        elif collecting:
            if s in ("RULES:", "INVARIANTS:", "NOTES:", "```") or s.startswith("UNIT "):
                break
            if s:
                body.append(s)
    return body


class TestTheDispatchWiring:
    """The check only works if both halves run, and *where* they sit decides that.

    A sibling change in this series shipped four instructions that sat after a `CONTINUE` or a
    `WAIT`/`STOP_TURN` and could never execute, while a test asserting they merely *existed in
    the file* stayed green throughout. These assert position, not presence.
    """

    def test_the_mark_is_taken_before_the_agent_is_dispatched(self) -> None:
        body = _dispatch_do_block()
        mark = next(i for i, text in enumerate(body) if "verify-subagent-work --mark" in text)
        dispatch = next(i for i, text in enumerate(body) if text.startswith("DISPATCH "))
        assert mark < dispatch, (
            "the mark must be taken while the tree is still untouched; taken after dispatch it "
            "would fingerprint the agent's own work and every run would look unchanged")

    def test_the_comparison_runs_after_the_agent_returns(self) -> None:
        body = _dispatch_do_block()
        dispatch = next(i for i, text in enumerate(body) if text.startswith("DISPATCH "))
        since = next(i for i, text in enumerate(body) if "verify-subagent-work --since" in text)
        assert dispatch < since, "comparing before the agent runs can only ever report unchanged"

    def test_the_comparison_shares_the_reachability_of_a_known_live_line(self) -> None:
        # This is the honest reachability argument, pinned rather than left in a PR description.
        # `RUN SubAgentDispatch` can stop the turn for its approval gate, so whether this DO block
        # resumes is not something this test can prove. What it CAN do is bind the new line to
        # `CONTINUE CodingValidate` -- the only route from dispatch into validation, long shipped.
        # If the comparison is reachable at all, so is that; if it is not, the workflow was already
        # broken. Separating them would quietly break that argument.
        body = _dispatch_do_block()
        since = next(i for i, text in enumerate(body) if "verify-subagent-work --since" in text)
        cont = next(i for i, text in enumerate(body) if text.startswith("CONTINUE CodingValidate"))
        assert cont == since + 1, (
            "the comparison must sit immediately before `CONTINUE CodingValidate`. Its "
            "reachability is argued from that line's: anything between them breaks the argument.")

    def test_the_mark_is_captured_from_the_machine_readable_field(self) -> None:
        # Review finding: the instruction used to say "SET to the mark it prints", and the
        # default output is a human sentence — `tree mark taken (tree1:…)`. Every near-miss at
        # pulling the token out of that sentence (the whole line, the brackets, a trailing
        # bracket) compares as an unusable mark and reports UNKNOWN, which exits 0 and blocks
        # nothing. Measured. The wiring now reads a named JSON field instead of parsing prose.
        text = DISPATCH.read_text(encoding="utf-8")
        mark_line = next(line for line in text.splitlines()
                         if "verify-subagent-work --mark" in line)
        assert "--json" in mark_line, (
            "the mark is captured from human output; a near-miss on the token reports UNKNOWN "
            "and the check silently passes everything")
        assert "`mark` field" in mark_line, (
            "the instruction must name the field to read, not 'the mark it prints'")

    def test_the_comparison_also_runs_machine_readably(self) -> None:
        text = DISPATCH.read_text(encoding="utf-8")
        since_line = next(line for line in text.splitlines()
                          if "verify-subagent-work --since" in line)
        assert "--json" in since_line, "the comparison's result should be read as data too"

    def test_the_agents_own_report_is_refused_as_evidence(self) -> None:
        text = DISPATCH.read_text(encoding="utf-8")
        assert "NEVER treat a coding agent's own success report as evidence" in text, (
            "removing this rule restores the trust the check exists to replace")


def test_every_git_read_disables_repository_supplied_helpers() -> None:
    """Structural: a repository can name a program for git to launch.

    `git status` honours `core.fsmonitor`, which is repository-supplied — so inspecting an
    untrusted checkout could make this read-only check execute that project's chosen binary.
    Asserted on the command this builds rather than on behaviour, because reproducing it would
    mean running an actual helper.
    """
    captured: dict = {}

    def _capture(cmd, **kwargs):
        captured["cmd"] = cmd
        raise OSError("not actually running git")

    import unittest.mock as _mock
    with _mock.patch.object(git_read.subprocess, "run", _capture):
        git_read.query(Path("."), ["status", "--porcelain=v1"])

    cmd = captured["cmd"]
    assert "core.fsmonitor=false" in cmd, (
        f"git is launched without disabling repository-supplied fsmonitor helpers: {cmd}")
    assert cmd.index("core.fsmonitor=false") < cmd.index("status"), (
        "the -c overrides must precede the subcommand or git ignores them")
