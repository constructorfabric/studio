"""Did a dispatched sub-agent actually change the tree, or only say so?

Ungating sub-agent dispatch removes the human who used to look. Removing the gate and
keeping the trust deletes a check rather than moving it, and "trusting agent success
reports" is the failure this module exists to stop believing. So the claim is checked
against the **working tree**, which the agent cannot narrate.

**What it answers, and what it does not.** One question only: *has anything changed since
the mark taken before dispatch?* It does not attribute hunks to plan items -- that would be
a second judgement engine, which verification before completion explicitly must not become.
A richer answer needs its own design, not a wider regex here.

**Both halves of "changed" matter.** A run may be configured to commit or to leave work in
place, so a mark that only read ``HEAD`` would call an uncommitted change "nothing happened".
The fingerprint covers the commit *and* the porcelain status, so either moving is a change.

**One git reader.** The invocation lives in ``git_read`` because `change_summary` needs the
same hardening, and a second copy is a second place for it to drift.

**Fail direction.** Unlike the completion check, an unanswerable question here degrades
rather than blocks: not every project is a git checkout, and refusing to proceed because
there is no repository to read would make the common case unusable. ``UNKNOWN`` is reported
with its reason and never reported as ``UNCHANGED`` -- conflating "nothing changed" with
"could not look" is the one error that would make this check worse than no check at all.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence

from . import git_read

logger = logging.getLogger(__name__)

# @cpt-begin:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-limits
#: The mark is a digest, never the status text itself: the text names every dirty path in
#: the project, and the mark is passed on a command line and may be logged.
#: Names this check in the operator-facing warning, so a degraded run says which
#: command could not read the tree rather than only that some git read failed.
_LOG_GIT_FAILED = "sub-agent work check: git could not be read: %s"

_MARK_PREFIX = "tree1:"
_DIGEST_CHARS = 32

#: A well-formed mark, checked in full rather than by prefix alone. A value like
#: ``tree1:not-a-digest`` passes a prefix test and then compares unequal to every real mark,
#: which would report CHANGED -- a confident answer from an input this cannot read. The
#: documented outcome for an unusable mark is "could not be asked", so it is matched exactly.
_MARK_RE = re.compile(rf"^{re.escape(_MARK_PREFIX)}[0-9a-f]{{{_DIGEST_CHARS}}}$")

#: How much of a file is read at a time. This bounds **memory**, never coverage: an earlier
#: version stopped after the first 64 KiB, and an agent editing past that point in an
#: already-dirty file produced a byte-identical mark -- measured, and exactly the case content
#: hashing was added to catch. A verifier that skims is worse than one that is slow.
_CHUNK_BYTES = 64 * 1024

#: The most dirty paths this will fingerprint by content. Past it the check **declines to
#: answer** rather than sampling a subset: with more than this many dirty paths, an agent
#: editing an already-dirty path beyond the cut leaves HEAD and the status records untouched,
#: so a truncated digest reports UNCHANGED for real work. An earlier version truncated here
#: silently while its own comment claimed otherwise. Degrading to no mark reaches "could not
#: be asked", which is the direction this module takes everywhere else.
_CONTENT_PATHS = 512

#: Stands in for a dirty file whose bytes cannot be read. It must be a **stable** marker and
#: never an empty string: "unreadable" collapsing to "no content" would make two different
#: trees fingerprint alike, which is the false-unchanged this whole change exists to avoid.
_UNREADABLE = b"\0<unreadable>\0"
# @cpt-end:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-limits


# @cpt-begin:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-verdict
class Verdict(Enum):
    """What the tree says about a dispatch."""

    CHANGED = "changed"      # the tree moved: the work left evidence
    UNCHANGED = "unchanged"  # the tree is identical: the report and the tree disagree
    UNKNOWN = "unknown"      # the question could not be asked; never read as UNCHANGED


@dataclass(frozen=True)
class Result:
    """A verdict and the reason behind it, so a caller never has to infer why."""

    verdict: Verdict
    reason: str

    @property
    def blocks(self) -> bool:
        """Only a tree that demonstrably did not move blocks; not knowing never does."""
        return self.verdict is Verdict.UNCHANGED
# @cpt-end:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-verdict


# @cpt-begin:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-mark
#: Fields before the path in each porcelain v2 record kind, for the fixed-count split. A path
#: may contain spaces, so splitting on the last space would truncate it.
_RECORD_FIELDS = {"1": 8, "2": 9, "u": 10}

#: Untracked and ignored records are `<code><space><path>`, with no counted fields.
_BARE_KINDS = ("?", "!")

#: The record kind for a rename or copy. Its source path follows as a second, bare record
#: carrying no field prefix at all, so the source is taken whole rather than sliced. (An
#: earlier draft keyed this off the ``R``/``C`` status codes, which is the v1 spelling; in v2
#: the kind is the record's first field.)
_RENAME_KIND = "2"


def _record_path(record: str) -> Optional[str]:
    """The path out of one v2 record, or ``None`` when the record is too short to hold one.

    A malformed record yields no path rather than a guess: a truncated line is something this
    could not read, and inventing a path from it would put a name that is not a path into the
    fingerprint.
    """
    kind = record[0]
    if kind in _BARE_KINDS:
        return record[2:]
    fields = _RECORD_FIELDS.get(kind)
    if fields is None:
        return None
    parts = record.split(" ", fields)
    return parts[fields] if len(parts) == fields + 1 else None


def _dirty_paths(status: str) -> List[str]:
    """The paths named by ``--porcelain=v2 -z``.

    v2 is used rather than v1 because v1 reports only *that* a path is dirty. v2 carries the
    file modes for HEAD, index and worktree, and the object ids for HEAD and index -- so a
    `chmod +x`, a staged edit, and a submodule's commit move are all visible in the status
    text itself, where v1 renders every one of them as the same two characters. The whole
    record goes into the fingerprint for that reason; only the **paths** come back here, for
    reading worktree content.

    Record shapes, each NUL-terminated:

    * ``1 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <path>`` -- ordinary change, 8 fields then path
    * ``2 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <X><score> <path>`` + a second record holding the
      rename/copy **source**, which carries no field prefix at all
    * ``u <XY> <sub> <m1> <m2> <m3> <mW> <h1> <h2> <h3> <path>`` -- unmerged, 10 fields
    * ``? <path>`` / ``! <path>`` -- untracked and ignored

    A path may contain spaces, so each shape splits on a **fixed field count** and takes the
    remainder, never on the last space.
    """
    out: List[str] = []
    records = status.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        path = _record_path(record)
        if path is not None:
            out.append(path)
        if record[0] == _RENAME_KIND and index < len(records) and records[index]:
            # The rename/copy SOURCE is its own record and carries no field prefix, so it is
            # taken whole. It is consumed even when the record above it was malformed: it
            # belongs to that record, and leaving it to be read as a record in its own right
            # would make one unparsable line corrupt every path after it.
            out.append(records[index])
            index += 1
    return out


def _repo_root(root: Path) -> Optional[Path]:
    """The repository's own top level, or ``None``.

    ``--porcelain`` paths are relative to the **repository root**, not to the directory git
    was run from. Joining them to the caller's ``--root`` is only correct when the two are the
    same: from a subdirectory it builds a path that does not exist, every dirty file reads as
    unreadable, and the content fingerprint silently degrades to the status-only behaviour
    this module exists to replace.
    """
    out, failed = git_read.query(root, ["rev-parse", "--show-toplevel"], failed_log=_LOG_GIT_FAILED)
    if failed or not out or not out.strip():
        return None
    return Path(out.strip())


def _content_digest(root: Path, paths: Sequence[str]) -> Optional[bytes]:
    """A digest over the first bytes of each dirty path, bounded in size and in count.

    The status line says *which* paths are dirty, never *what is in them*. A file already
    modified before dispatch keeps the same path and the same status code when an agent edits
    it again, so a status-only fingerprint is identical across real work -- measured, and the
    reason this exists. An unreadable file contributes a stable marker rather than nothing.
    """
    if len(paths) > _CONTENT_PATHS:
        # Sampling a subset would under-report: an agent editing an already-dirty path beyond
        # the cut changes neither HEAD nor the status records, so the mark would be identical
        # and real work would read as UNCHANGED.
        logger.debug("sub-agent work check: %d dirty paths exceeds the %d-path cap, so no mark",
                     len(paths), _CONTENT_PATHS)
        return None
    digest = hashlib.sha256()
    try:
        base = root.resolve()
    except (OSError, RuntimeError):
        # `Path.resolve()` raises **RuntimeError**, not OSError, on a symlink loop. Catching
        # only OSError let that escape `mark()` and break the caller's run, against this
        # module's documented never-raises contract -- the same trap as `Path.home()`
        # raising RuntimeError where a guard expected OSError.
        return digest.digest()
    for name in sorted(paths):
        digest.update(name.encode(git_read.PATH_ENCODING, git_read.PATH_ERRORS))
        try:
            # Confined to the tree being fingerprinted. These names come from git rather than
            # from a user, but `root` arrives from the command line, and a name that resolves
            # outside the tree is not part of what this check measures -- so it is refused
            # rather than read, and contributes the same marker as any other unreadable path.
            target = (base / name).resolve()
            if not target.is_relative_to(base):
                raise OSError(f"{name} resolves outside the tree being checked")
            with open(target, "rb") as handle:
                while True:
                    chunk = handle.read(_CHUNK_BYTES)
                    if not chunk:
                        break
                    digest.update(chunk)
        except (OSError, RuntimeError):
            # A directory, a dangling symlink, a permission error, a file deleted between the
            # status and this read. None of them is a reason to fail the run, and none may be
            # confused with an empty file.
            digest.update(_UNREADABLE)
    return digest.digest()


def mark(root: Path) -> Optional[str]:
    """A fingerprint of the tree right now, or ``None`` when it cannot be taken honestly.

    ``None`` means the tree could not be read at all, or that more than ``_CONTENT_PATHS``
    paths are dirty -- a mark that skipped some of them would read as UNCHANGED across real
    work. Either way the caller reports UNKNOWN, never UNCHANGED.

    Three parts, because any two of them alone miss real work:

    * ``HEAD`` -- moves when the work is committed;
    * the porcelain status -- moves when the work is left in place, and names new files
      individually (``--untracked-files=all``), since the default summarises them per
      directory and would hide a second file added inside an already-untracked one;
    * the **contents** of the dirty paths -- because the status names which paths are dirty,
      never what is in them. A file already modified before dispatch keeps the same path and
      status code when an agent edits it further, so the first two are byte-identical across
      genuine work. That reported real work as "unchanged", which is a false accusation of
      exactly the kind this check must not make.
    """
    head, failed = git_read.query(root, ["rev-parse", "HEAD"], failed_log=_LOG_GIT_FAILED)
    if failed:
        return None
    # No `HEAD` is not an error: a repository before its first commit still has a status.
    status, failed = git_read.query(root, ["status", "--porcelain=v2", "-z", "--untracked-files=all"],
                                    failed_log=_LOG_GIT_FAILED)
    if failed or status is None:
        return None
    base = _repo_root(root)
    if base is None:
        # The status paths are relative to the repository root, so without it there is no
        # correct base to read them from. Guessing the caller's root produces a syntactically
        # valid mark computed from the wrong directory -- and a mark that is wrong in a
        # *stable* way compares equal to itself, which reads as UNCHANGED. No mark at all
        # degrades to "could not be asked", which is the documented direction.
        logger.debug("sub-agent work check: no repository top level, so no mark")
        return None
    contents = _content_digest(base, _dirty_paths(status))
    if contents is None:
        return None     # too many dirty paths to fingerprint honestly; see `_CONTENT_PATHS`
    payload = (f"{(head or '').strip()}\0{status}".encode(git_read.PATH_ENCODING,
                                                          git_read.PATH_ERRORS)
               + contents)
    return _MARK_PREFIX + hashlib.sha256(payload).hexdigest()[:_DIGEST_CHARS]
# @cpt-end:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-mark


# @cpt-begin:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-compare
def compare(root: Path, earlier: Optional[str]) -> Result:
    """Whether the tree moved since ``earlier``, the mark taken before dispatch.

    Every way of not knowing returns ``UNKNOWN`` with its own reason -- no mark was taken,
    the mark is not one this module wrote, or the tree cannot be read now. None of them is
    ``UNCHANGED``: reporting "nothing changed" when the question was never answered would
    turn a missing check into a false accusation, and a run would be held on it.
    """
    if not earlier:
        return Result(Verdict.UNKNOWN, "no mark was taken before dispatch")
    if not _MARK_RE.match(earlier):
        return Result(Verdict.UNKNOWN, "the mark was not written by this check")
    now = mark(root)
    if now is None:
        return Result(Verdict.UNKNOWN, "the working tree could not be read")
    if now == earlier:
        return Result(Verdict.UNCHANGED,
                      "the tree is byte-for-byte what it was before the sub-agent ran")
    return Result(Verdict.CHANGED, "the tree moved while the sub-agent ran")
# @cpt-end:cpt-studio-algo-execution-plans-subagent-work:p1:inst-subagent-work-compare
