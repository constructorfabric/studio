"""Change-summary core — resolve the window a digest covers, the decision-log events
recorded inside it, and the requirements the changed files declare.

The digest answers "what changed on this branch, and why". This module owns the three
halves that have no output format: **which span of work counts as "the run"**, **which
recorded decisions fall inside it**, and **which requirement each changed file serves**.
Rendering belongs to the command wrapper.

Three deliberate choices:

* **The window comes from git, not from a decision-log ``run_id``.** A ``run_id`` is
  one CLI invocation, but a reviewer's "run" is a branch's worth of work. The window
  is the span since the merge-base with the default branch, so ``run_id`` becomes a
  grouping key *inside* that span rather than the span itself. The boundary is the
  merge-base's own commit time, so it moves when the merge-base does — a rebase onto
  newer upstream commits advances it, and decisions logged before the new base commit
  fall outside the window. Git keeps no record of where a branch *used* to start, so
  that is documented (see :func:`resolve_window`) rather than guessed around, and an
  explicit ``since`` pins the boundary where the caller says.
* **Nothing here raises, and nothing here is silent.** Every path returns a value
  carrying an explicit ``reason`` when a dimension is unavailable. A digest that
  quietly shows less is the defect this effort exists to remove, so "cannot tell" is
  always reported rather than rounded down to "nothing to say".
* **Reason strings carry no filesystem paths**, so no ``$HOME`` or username can
  reach a rendered digest through them.

Git access is a narrow read-only query helper, not a general runner. The two existing
private ``_run_git`` helpers in this package have incompatible contracts — one returns
``(code, stdout, stderr)``, the other returns a string and raises — so a third generic
copy would duplicate both. ``_git_query`` answers only "one line of stdout, or nothing —
and whether git itself failed to answer".

Requirement linkage reads markers through :func:`codebase.load_code_file`, the parser
``validate`` uses and the only one that yields identifiers. ``coverage.py`` measures
marker *density* — counts and line ranges, no IDs — so it cannot answer "which
requirement does this file serve" at all. A referenced ID is reported as-is rather than
resolved back to its declaring artifact: ``cfs validate`` already fails when a code
marker names an ID no artifact defines, so in a green tree every reported ID is known
to be declared, and re-resolving it here would duplicate that gate for cosmetic gain.

@cpt-algo:cpt-studio-algo-developer-experience-change-summary:p1
"""

# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-reader-bounds
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Container, Dict, List, Optional, Tuple

from . import codebase
from . import decision_log
from . import document
from . import error_codes as EC

logger = logging.getLogger(__name__)

#: Seconds any single git query may take before it is treated as unavailable.
_GIT_TIMEOUT = 10

#: The codec every git reader here decodes with — the one Python uses for filesystem
#: paths, so a path read from git is the string ``open`` encodes back to the same bytes.
#: Git emits paths as raw bytes. ``text=True`` without an ``encoding`` decodes them with
#: the locale's codec instead, and the two readers of the changed-file listing — the
#: captured diff and the streamed sweep — then disagreed about one file's name under a
#: non-UTF-8 locale, so the sweep's deduplication against the diff missed it and one
#: file was reported twice.
_PATH_ENCODING = sys.getfilesystemencoding()
_PATH_ERRORS = sys.getfilesystemencodeerrors()

#: Longest single record the streamed reader buffers before calling the stream
#: malformed. The ceiling on records bounds how many are kept, not how long one may
#: grow: a child that never writes a NUL was otherwise buffered without limit. Far above
#: any path a repository holds, and far below the point where it would matter.
_MAX_RECORD_BYTES = 1 << 20

#: What the three readers below say when git could not be launched at all, and when it
#: ran and refused. One template each, because an operator greps a log for a fixed
#: phrase: three readers wording the same outcome three ways is three things to search
#: for. Both carry the exception *type* or the exit code, never the message — an
#: ``OSError``'s text can carry a path.
_LOG_GIT_FAILED = "change-summary git query could not run: %s"
_LOG_GIT_EXITED = "change-summary git query exited %d"
#: Distinct from :data:`_LOG_GIT_FAILED` on purpose: git launched and then the stream
#: broke part-way, which is a different fact for an operator than git never starting.
#: Named for the same reason as the other two, and because a test asserting the exact
#: message needs the template rather than a substring of it.
_LOG_GIT_STREAM_FAILED = "change-summary git query stream failed: %s"
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-reader-bounds

# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-git-environment
#: Environment variables that let the ambient environment change what these queries
#: answer. Two mechanisms, both cleared, because naming the directory is not enough on
#: either count.
#:
#: The first **redirects which repository git reads**: an ambient ``GIT_DIR`` overrides
#: ``cwd=``, so a query about project A was answered from project B's repository.
#: Verified — ``GIT_DIR=b/.git git -C a log`` reports b's commit, not a's.
#:
#: The second **changes what git reports about the right repository**, and is described
#: at the group below. Every variable here is cleared, so the answer describes the
#: project the caller named, in the state that project is actually in.
_GIT_REDIRECT_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CEILING_DIRECTORIES",
    # Widens the upward search instead of narrowing it: with this set, discovery crosses
    # a mount boundary and can settle on an ancestor repository on another filesystem
    # rather than stopping at the requested project's own. Cleared for symmetry with
    # ``GIT_CEILING_DIRECTORIES`` above — leaving the variable that widens the walk while
    # clearing the one that restricts it would make the search depend on the ambient
    # environment in exactly the direction that hurts.
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    # The second mechanism: git also takes *configuration* from the environment, and
    # config reaches these queries even though it cannot redirect discovery. Measured —
    # with `core.excludesFile` injected through any of the three below,
    # `ls-files --others --exclude-standard` returned **nothing** for a repository whose
    # untracked file it otherwise lists. That is the silent omission this module exists
    # to prevent, arriving through the environment rather than through the code, so the
    # digest would have called a brand-new file absent while reporting itself complete.
    #
    # `core.worktree` is *not* the vector it first appears to be: injected this way it
    # is set (``git config core.worktree`` echoes it back) but ignored for discovery, so
    # `--show-toplevel` and the listings stay with the directory git was pointed at. It
    # only redirects once `GIT_DIR` is also set — verified, and that is cleared above,
    # which is what makes the two groups here complementary rather than overlapping.
    "GIT_CONFIG_PARAMETERS",
    # Gates the indexed `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` pairs: verified that
    # without a count git ignores them entirely, so clearing the count clears the family
    # and no unbounded scan for indices is needed.
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    # Toggles whether system config participates at all, so it changes the answer in the
    # opposite direction to the two above — and directly reverses them. Measured:
    # `GIT_CONFIG_SYSTEM=<file setting core.excludesFile>` emptied the untracked sweep,
    # and adding `GIT_CONFIG_NOSYSTEM=1` brought the file back. Left inherited, an
    # ambient value would decide whether the machine's real ``/etc/gitconfig`` is
    # consulted, which is the same ambient dependence as the rest of this tuple.
    #
    # With this, the set is the whole documented config surface — `git help config`
    # lists exactly ``GIT_CONFIG_COUNT``, ``GIT_CONFIG_KEY_n``, ``GIT_CONFIG_VALUE_n``,
    # ``GIT_CONFIG_GLOBAL``, ``GIT_CONFIG_SYSTEM`` and ``GIT_CONFIG_NOSYSTEM``, plus the
    # undocumented ``GIT_CONFIG_PARAMETERS`` above, which was verified by measurement.
    "GIT_CONFIG_NOSYSTEM",
)

#: Refs tried in order when the caller names no base.
#:
#: ``upstream/*`` comes first deliberately. In a fork-based workflow — which this
#: project mandates, with ``origin`` pointing at the contributor's fork — ``origin/HEAD``
#: tracks the *fork's* default branch, which lags the canonical one. Measured on this
#: checkout, ``origin/HEAD`` was five weeks behind ``upstream/main``, so preferring it
#: would silently widen every window to include work that shipped long ago.
#: A fresh clone of the canonical repo has no ``upstream`` remote, so it falls through
#: to ``origin/HEAD`` and is still correct.
#: ``upstream/HEAD`` leads because it is the canonical remote's *own* symbolic default
#: — right even when that default is neither ``main`` nor ``master``. Guessing branch
#: names first would skip it and fall through to a stale fork ref, which is the same
#: failure this ordering exists to prevent, one level deeper.
_DEFAULT_BASE_REFS = (
    "upstream/HEAD",
    "upstream/main",
    "upstream/master",
    "origin/HEAD",
    "origin/main",
    "main",
    "origin/master",
    "master",
)
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-git-environment

# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-reason-vocabulary
# Reasons are module constants so the renderer and the tests share one vocabulary
# instead of matching on prose that can drift.
REASON_OK = ""
REASON_NOT_A_REPO = "not a git repository"
#: A bare repository, or a path inside the ``.git`` directory itself. Both *are*
#: repositories, so reporting them as :data:`REASON_NOT_A_REPO` was a false statement.
REASON_NO_WORK_TREE = "in a git repository but outside any working tree"
REASON_GIT_UNAVAILABLE = "git unavailable"
#: Kept free of an enumerated candidate list on purpose: the first version of this
#: string named the refs it tried, and went stale the moment the list changed.
REASON_NO_BASE_REF = "no default base ref found"
REASON_BASE_REF_UNKNOWN = "requested base ref not found"
REASON_NO_MERGE_BASE = "no merge base with the base ref"
#: A merge-base miss in a shallow clone decides nothing: the branch point may lie beyond
#: the fetched depth, or the histories may be unrelated, and a truncated history cannot
#: tell which. The reason says so rather than pick one. CI checkouts default to depth 1.
REASON_SHALLOW_HISTORY = "no merge base in a shallow history; the branch point may lie beyond the fetched depth"
REASON_NO_BASE_TIME = "base commit has no readable timestamp"
REASON_NOT_A_PROJECT = "not inside a Studio project"
REASON_LOG_DISABLED = "decision log disabled"
REASON_LOG_ABSENT = "no decision log yet"
REASON_LOG_UNREADABLE = "decision log unreadable"
REASON_NO_BASE_COMMIT = "window has no base commit to compare against"
REASON_DIFF_UNAVAILABLE = "git could not list changed files"
REASON_FILE_GONE = "file no longer present"
REASON_FILE_UNREADABLE = "file could not be read"
REASON_INVALID_SINCE = "the supplied lower bound is not an absolute timestamp"
REASON_FILE_TOO_LARGE = "file exceeds the shared scan size limit"
REASON_NOT_A_FILE = "not a regular file"
REASON_SCOPE_UNKNOWN = "scope could not be determined"
#: One entry's classification raised something no arm anticipated. The row says so and
#: the rest of the report stands; the alternative was one bad file discarding everything.
REASON_SCAN_FAILED = "marker scan failed unexpectedly"
#: The file was read fine; its markers do not parse — a dangling ``@cpt-end``, a
#: mismatched id. Reporting that as "could not be read" named the wrong failure.
REASON_MARKERS_INVALID = "requirement markers could not be parsed"
#: A hand-built window with a base commit but no root: there is nothing to diff *in*.
REASON_NO_PROJECT_ROOT = "window carries no project root"

#: Most changed entries examined in one report.
#:
#: A bound is needed because the entry list is not bounded by the diff: the untracked
#: sweep can return an arbitrary number of paths (an unignored dependency tree), and
#: each entry costs a stat plus two full reads. The number is chosen from the feature's
#: own premise rather than picked arbitrarily — a change set larger than this is not
#: summarisable in ten lines, so examining more of it buys nothing a reader can use.
#: Entries beyond the ceiling are counted in ``truncated`` rather than dropped quietly.
MAX_CHANGED_ENTRIES = 1000

#: Bucket name for selected events whose ``run_id`` is missing or unusable. Grouping
#: used to build buckets only for truthy ids, so such events sat in ``events`` and in no
#: group, and a renderer summing the groups under-reported without saying so.
#:
#: The parentheses make it read as a label rather than an identifier, but nothing
#: *enforces* uniqueness: a writer emitting this exact string would share the bucket.
#: That is a deliberate trade — the alternative is rejecting unrecognised ids, which
#: discards real information (see :func:`_canonical_run_id`). Sharing a label is
#: cosmetic; dropping an event is not.
RUN_UNATTRIBUTED = "(unattributed)"
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-reason-vocabulary


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-datamodel
@dataclass(frozen=True)
class ChangeWindow:
    """The span of work a digest covers.

    ``available`` false means no git-derived window could be established; ``reason``
    then says which of the failure modes applied. ``since`` is the base commit's own
    commit time, which is what makes the window "everything after the branch point".

    Frozen: a window records what git said at one moment, and nothing here mutates one
    after construction, so nothing may.
    """

    project_root: str = ""
    base_ref: str = ""
    base_sha: str = ""
    since: str = ""
    available: bool = False
    reason: str = REASON_NOT_A_REPO


@dataclass(frozen=True)
class EventSelection:
    """Decision-log events falling inside a window.

    ``skipped_lines`` is the number of non-empty log lines that yielded no event — not
    JSON, or JSON that is not an object. It is exact for the snapshot the selection was
    read from, because the events and the line count come from one read of the file
    (see :func:`_read_log`), and it is reported rather than hidden.

    ``log_overridden`` says the environment named the log (``$CFS_DECISION_LOG``) rather
    than the window's project. That log is shared by every project the process ran in,
    so its events cannot be attributed to this window's project, and a digest should
    say so instead of presenting them as the project's own.

    Frozen, with ``events`` and ``runs`` as tuples: the counts describe those
    collections, and a caller able to grow or shrink them would silently make the
    counts wrong.
    """

    events: Tuple[Dict[str, Any], ...] = ()
    runs: Tuple[str, ...] = ()
    scanned: int = 0
    undated: int = 0
    runless: int = 0
    skipped_lines: int = 0
    log_overridden: bool = False
    available: bool = False
    reason: str = REASON_NOT_A_PROJECT
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-datamodel


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-git-query
def _git_env() -> Dict[str, str]:
    """The ambient environment with git's repository-redirecting variables removed."""
    env = dict(os.environ)
    for name in _GIT_REDIRECT_VARS:
        env.pop(name, None)
    return env


def _git_query(project_root: Path, args: List[str]) -> Tuple[Optional[str], bool]:
    """Run a read-only git query, returning ``(first line or None, tool_failed)``.

    The two halves of "no answer" are kept apart, because conflating them lets a
    transient tool failure be reported as a conclusion about history — "no merge base"
    when git simply timed out.

    * **Tool failure** is git not launching, or timing out. Nothing was learned.
    * **A non-zero exit is a valid negative**, not a failure: ``merge-base`` exits 1
      when two histories genuinely have no common ancestor, and
      ``rev-parse --verify --quiet`` exits 1 when a ref genuinely does not exist. Those
      are answers, and treating them as breakage would be just as misleading in the
      other direction.

    Never raises.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(project_root),
            env=_git_env(),
            capture_output=True,
            text=True,
            # Git refs and paths are bytes and need not be UTF-8, so `text=True`'s
            # strict default would raise UnicodeDecodeError past the handler below and
            # break the never-raises contract. The filesystem codec is the one Python
            # uses for paths, so a value round-trips to the same bytes -- and every
            # reader in this module decodes with it, so one path is one string.
            encoding=_PATH_ENCODING,
            errors=_PATH_ERRORS,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as exc:
        # Warning, not debug: git not launching is an environment fault an operator
        # should see, unlike the routine non-zero exit below.
        logger.warning(_LOG_GIT_FAILED, type(exc).__name__)
        return None, True
    if result.returncode:
        logger.debug(_LOG_GIT_EXITED, result.returncode)
        return None, False
    line = result.stdout.strip().splitlines()
    return (line[0].strip() if line else None), False
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-git-query


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-detect-repo
def _detect_repo(project_root: Path) -> str:
    """Return :data:`REASON_OK` when ``project_root`` is inside a git work tree, else why not.

    One query, three answers, kept apart:

    * a **tool failure** is :data:`REASON_GIT_UNAVAILABLE`. Nothing was learned, so
      nothing is claimed about the directory. An earlier version dropped this flag and
      asked ``git --version`` separately to guess between "not a repo" and "git broken"
      — so a timeout here followed by a healthy second launch was reported as a fact
      about the directory that was never established, and every non-repo path cost two
      launches instead of one;
    * a **non-zero exit** is :data:`REASON_NOT_A_REPO`: git looked, and there is none;
    * ``false`` is :data:`REASON_NO_WORK_TREE`: a bare repository, or the ``.git``
      directory itself. Both are repositories, and a digest of working-tree changes
      needs a working tree, so the reason names the thing that is actually missing.
    """
    answer, failed = _git_query(project_root, ["rev-parse", "--is-inside-work-tree"])
    if failed:
        return REASON_GIT_UNAVAILABLE
    if answer is None:
        return REASON_NOT_A_REPO
    return REASON_OK if answer == "true" else REASON_NO_WORK_TREE
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-detect-repo


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-default-base
def _resolve_base_ref(project_root: Path, requested: str = "") -> Tuple[Optional[str], bool]:
    """Pick the ref the window is measured from.

    An explicitly requested ref is honoured or refused — never silently swapped for a
    fallback, because a digest measured against a different ref than the caller asked
    for is worse than one that says it could not comply.
    """
    if requested:
        if "\0" in requested:
            # No ref can contain NUL, and `subprocess` refuses to pass one — raising
            # ValueError before git starts, outside `_git_query`'s handler. Refuse it
            # here as what it is: a ref that cannot exist.
            return None, False
        resolved, failed = _git_query(
            project_root,
            # `--end-of-options` so a caller-supplied ref beginning with a dash is read
            # as a ref rather than as a git option.
            ["rev-parse", "--verify", "--quiet", "--end-of-options", requested],
        )
        return (requested if resolved else None), failed
    for candidate in _DEFAULT_BASE_REFS:
        resolved, failed = _git_query(
            project_root, ["rev-parse", "--verify", "--quiet", "--end-of-options", candidate],
        )
        if failed:
            # Stop at the first tool failure rather than walking the remaining
            # candidates: each would fail the same way, and reporting "no default base
            # ref" after eight failed launches states a fact about the repository that
            # was never established.
            return None, True
        if resolved:
            return candidate, False
    return None, False
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-default-base


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-merge-base
def _merge_base(project_root: Path, base_ref: str) -> Tuple[Optional[str], bool]:
    """Return the merge-base sha between ``HEAD`` and ``base_ref``.

    Returns ``(sha, tool_failed)``. A ``None`` sha with ``tool_failed`` false means git
    found no common ancestor *in the history it has*: genuinely unrelated branches, a
    missing ref — or a shallow clone whose branch point was never fetched, which
    :func:`_is_shallow` tells apart. A ``True`` flag means git never answered, which is
    a different fact and must not be reported as a finding about history.
    """
    return _git_query(project_root, ["merge-base", "--end-of-options", "HEAD", base_ref])
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-merge-base


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-shallow-check
def _is_shallow(project_root: Path) -> Tuple[bool, bool]:
    """Whether the repository's history is truncated — a shallow clone.

    Returns ``(shallow, tool_failed)``, like every other probe here. Asked only after a
    merge-base miss, so it costs nothing on the common path, and only to choose between
    two reasons: a miss in full history is a fact about the branches; a miss in a shallow
    one is undecidable — the branch point may lie beyond the fetched depth, or the
    histories may be unrelated, and a truncated history cannot tell the two apart — so it
    is reported as exactly that. The failure flag is kept rather than dropped: a probe
    that never ran answered neither way, and an earlier version read that as "not
    shallow" and reported unrelated history on the strength of a timeout.
    """
    answer, failed = _git_query(project_root, ["rev-parse", "--is-shallow-repository"])
    return answer == "true", failed
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-shallow-check


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-base-time
def _commit_time(project_root: Path, sha: str) -> Tuple[Optional[str], bool]:
    """Commit time in strict ISO 8601, plus whether git itself failed."""
    return _git_query(project_root, ["show", "-s", "--format=%cI", "--end-of-options", sha])
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-base-time


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-resolve-window
def resolve_window(
    project_root: Path,
    *,
    base: str = "",
    since: str = "",
) -> ChangeWindow:
    """Resolve the span of work a digest should cover.

    ``since`` on its own short-circuits git entirely — an explicit lower bound is the
    caller's assertion and needs no branch point. Otherwise the window starts at the
    merge-base with ``base`` (or the first of :data:`_DEFAULT_BASE_REFS` that exists).
    Given both, the base still anchors the changed-file diff and ``since`` replaces only
    the decision boundary; a base the caller named is never silently ignored.

    **The boundary moves with the merge-base.** It is the base commit's *commit* time,
    so rebasing onto newer upstream commits advances it, and decisions logged before
    the new base commit was committed then fall outside the window — while the files
    they concern still show as changed, because file changes are measured by tree
    content, not by time. Git keeps no record of where the branch used to start, so
    the old boundary cannot be recovered from history. The sha and time that *were*
    used are carried on the window so a digest can print them, and ``since`` pins the
    boundary where the caller says. Widening automatically to the branch's earliest
    author date was considered and rejected: author dates are arbitrary (cherry-picks,
    ``--date``), so one old commit would silently pull years of unrelated decisions
    into the window — the opposite failure, and harder to notice.

    Every failure returns an unavailable window carrying its reason. Never raises.
    """
    # Resolved, not merely stored. A relative root left as-is puts the cwd dependence
    # straight back: `resolve_window(Path("."))` recorded "." and a later chdir then
    # redirected log resolution to a different project — the exact failure carrying the
    # root on the window was added to prevent. Resolving also fixes the git cwd, since
    # `subprocess(cwd=...)` resolves a relative path at call time, not at capture time.
    project_root = Path(project_root).resolve()
    root = str(project_root)
    if since and (not base or _parse_ts(since) is None):
        # A bad bound is refused up front, whether or not a base was named, rather than
        # surfacing later as a complaint about a base commit that was never consulted. A
        # good bound with no base *is* the window, and needs no git. With a base as
        # well, the base still anchors the changed-file diff below and `since` replaces
        # only the decision boundary once the window is built — ignoring the base
        # silently left a caller who named one with no file changes and no hint why.
        return _since_only_window(root, since)

    repo_state = _detect_repo(project_root)
    if repo_state:
        return ChangeWindow(project_root=root, reason=repo_state)

    base_ref, failed = _resolve_base_ref(project_root, base)
    if failed:
        return ChangeWindow(project_root=root, reason=REASON_GIT_UNAVAILABLE)
    if base_ref is None:
        # Two different failures, two different reasons: a ref the caller named and
        # git does not have, versus no discoverable default at all.
        return ChangeWindow(
            project_root=root,
            reason=REASON_BASE_REF_UNKNOWN if base else REASON_NO_BASE_REF,
        )
    window = _window_from_base_ref(project_root, base_ref)
    return replace(window, since=since) if since and window.available else window


def _since_only_window(root: str, since: str) -> ChangeWindow:
    """The window an explicit bound makes on its own, or the reason the bound is unusable."""
    if _parse_ts(since) is None:
        return ChangeWindow(project_root=root, reason=REASON_INVALID_SINCE)
    return ChangeWindow(project_root=root, since=since, available=True, reason=REASON_OK)
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-resolve-window


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-window-from-base
def _window_from_base_ref(project_root: Path, base_ref: str) -> ChangeWindow:
    """Walk a known-good base ref down to a window, or the reason it could not.

    Split out of :func:`resolve_window` to keep each function's guard clauses legible;
    the whole point of this stage is that there are several distinct ways to fail and
    each gets its own reported reason rather than a shared shrug.

    Past this point git has already answered once, so a further non-answer is
    ambiguous: it may be a genuine negative about history, or the tool falling over.
    Reporting "no merge base" for a timeout would be a false conclusion, so the failure
    flag takes precedence over the historical reading. Whatever *was* learned — the ref,
    then the sha — stays on the returned window so a reason keeps its subject.
    """
    root = str(project_root)
    base_sha, failed = _merge_base(project_root, base_ref)
    if failed:
        return ChangeWindow(project_root=root, base_ref=base_ref, reason=REASON_GIT_UNAVAILABLE)
    if base_sha is None:
        # A miss in a shallow clone is not a fact about history: the branch point may lie
        # beyond the fetched depth. "No merge base" would send someone looking for
        # unrelated branches that are related, and CI checkouts default to depth 1.
        shallow, failed = _is_shallow(project_root)
        if failed:
            return ChangeWindow(project_root=root, base_ref=base_ref, reason=REASON_GIT_UNAVAILABLE)
        reason = REASON_SHALLOW_HISTORY if shallow else REASON_NO_MERGE_BASE
        return ChangeWindow(project_root=root, base_ref=base_ref, reason=reason)

    base_time, failed = _commit_time(project_root, base_sha)
    if failed or base_time is None:
        return ChangeWindow(
            project_root=root, base_ref=base_ref, base_sha=base_sha,
            reason=REASON_GIT_UNAVAILABLE if failed else REASON_NO_BASE_TIME,
        )

    return ChangeWindow(
        project_root=root,
        base_ref=base_ref,
        base_sha=base_sha,
        since=base_time,
        available=True,
        reason=REASON_OK,
    )
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-window-from-base


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-parse-ts
def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to an aware ``datetime``, or ``None``.

    A trailing ``Z`` is normalised because git and the log writer disagree about it.
    A naive timestamp is refused rather than assumed to be UTC: guessing an offset
    would silently move events across the window boundary.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        logger.debug("change-summary could not parse timestamp %r: %s", value, exc)
        return None
    return parsed if parsed.tzinfo is not None else None
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-parse-ts


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-log-state
def _read_log(path: Path) -> Tuple[Optional[List[str]], str]:
    """Read the whole log once, returning ``(non-empty lines, reason)``.

    One open, one decode, one snapshot. Readability, the events and the line count the
    corruption figure is derived from all come out of this single read, so nothing can
    change underneath the selection:

    * an earlier design probed readability, let :func:`decision_log.read_events` open
      the file again, then opened it a third time to count lines. A writer appending a
      valid line between the last two opens made the count exceed the events, so normal
      concurrent activity was reported as corruption; a rotation between the first two
      swapped the verified file for a fresh near-empty one, and the selection came back
      clean and almost empty with no sign that anything had moved;
    * readability is proved by reading, not inferred from ``stat``: ``is_file`` passes
      a mode-000 file, and only a strict decode catches bytes that are not UTF-8.

    Absent and unreadable stay distinct — "no decision log yet" and "the log could not
    be read" call for different actions. Never raises.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError) as exc:
        logger.debug("change-summary found no decision log: %s", exc)
        return None, REASON_LOG_ABSENT
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("change-summary log is unreadable: %s", exc)
        return None, REASON_LOG_UNREADABLE
    return [line for line in text.splitlines() if line.strip()], REASON_OK
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-log-state


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-default-log
def _default_log_for(window: ChangeWindow) -> Tuple[Optional[Path], bool]:
    """Resolve the decision log for *the window's* project, and whether the environment chose it.

    ``decision_log.default_log_path()`` defaults to the cwd, which is correct for the
    writer — it logs whichever project the command runs in. A reader reporting on an
    explicitly named project must not inherit that default, or the digest describes one
    project's changes alongside another project's decisions.

    ``$CFS_DECISION_LOG`` names one log for the whole process, and the writer honours it
    in every project the process runs in — so the reader follows it too, because that
    is where the events *are*. Reading the project-local path instead would report "no
    decision log yet" about a log that exists and is being written to. What the reader
    cannot do is attribute a shared log's events to this window's project, so the
    second value says the environment chose the log, and the selection carries that
    rather than presenting a shared log as the project's own.
    """
    overridden = decision_log.override_log_path() is not None
    if not window.project_root:
        return decision_log.default_log_path(), overridden
    return decision_log.default_log_path(Path(window.project_root)), overridden
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-default-log


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-resolve-log
def _resolve_log_for(
    window: ChangeWindow, path: Optional[Path],
) -> Tuple[Optional[Path], str, bool]:
    """Return ``(log path, reason, overridden)`` — the path and the reason are exclusive.

    Split out of :func:`select_events` so each function's guard clauses stay within the
    project's return-count budget, and so "which log, and is it this project's own" is
    answerable on its own. Whether the log can be *read* is answered by reading it —
    :func:`_read_log` — not by a separate probe the file could change after.
    """
    if not decision_log.is_enabled():
        return None, REASON_LOG_DISABLED, False
    if path is not None:
        return path, REASON_OK, False
    target, overridden = _default_log_for(window)
    if target is None:
        return None, REASON_NOT_A_PROJECT, False
    return target, REASON_OK, overridden
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-resolve-log


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-select-events
def select_events(
    window: ChangeWindow,
    *,
    path: Optional[Path] = None,
) -> EventSelection:
    """Select the decision-log events recorded inside ``window``.

    An event whose timestamp cannot be parsed is **excluded and counted** in
    ``undated`` rather than guessed into or out of the window — the caller can then
    say so instead of presenting a quietly incomplete list.

    An unavailable window yields an unavailable selection carrying the window's own
    reason, so the caller reports one cause rather than two.

    The default log is resolved from **the window's own project**, not from the current
    working directory. Those are independent inputs, so a window built for project A
    while the process sits in project B used to select B's decisions — a digest about
    one project carrying another's history.

    The log is read **once**, and everything reported comes from that one snapshot —
    see :func:`_read_log` for the two races that separate reads allowed. Never raises.
    """
    if not window.available:
        return EventSelection(reason=window.reason)

    target, reason, overridden = _resolve_log_for(window, path)
    if target is None:
        return EventSelection(reason=reason)

    boundary = _parse_ts(window.since)
    if boundary is None:
        return EventSelection(reason=REASON_NO_BASE_TIME)

    lines, reason = _read_log(target)
    if lines is None:
        return EventSelection(reason=reason)

    selected, runs, scanned, undated, runless = [], [], 0, 0, 0
    for event in decision_log.parse_events(lines):
        scanned += 1
        stamp = _parse_ts(event.get("ts"))
        if stamp is None:
            undated += 1
            continue
        if stamp < boundary:
            continue
        selected.append(event)
        run_id = _canonical_run_id(event.get("run_id"))
        if not run_id:
            runless += 1
            run_id = RUN_UNATTRIBUTED
        if run_id not in runs:
            runs.append(run_id)

    return EventSelection(
        events=tuple(selected),
        runs=tuple(runs),
        scanned=scanned,
        undated=undated,
        runless=runless,
        # Exact, not a bound: the lines and the events came from the same snapshot.
        skipped_lines=len(lines) - scanned,
        log_overridden=overridden,
        available=True,
        reason=REASON_OK,
    )
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-select-events


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-canonical-run
def _canonical_run_id(value: Any) -> str:
    """Return the canonical form of a ``run_id``, or ``""`` when it is not usable.

    Raw values were used directly as grouping keys, which fragmented and merged history
    in three ways:

    * **case variants split one run** — ``"AB12"`` and ``"ab12"`` became two groups for
      something the writer would only ever have emitted once, so casefolding merges them;
    * **a non-string merged with its own text** — ``1`` and ``"1"`` both stringified to
      ``"1"``, so a numeric field silently joined an unrelated run. Only ``str`` is
      accepted, which keeps them apart;
    * **whitespace formed an attributed group** — ``"   "`` is truthy, so it looked like
      a real run. Stripping sends it to :data:`RUN_UNATTRIBUTED` where it belongs.

    What this deliberately does **not** do is require the writer's current shape
    (``uuid4().hex[:12]``). Rejecting anything non-hexadecimal would discard a real,
    distinguishing identifier by folding it into the anonymous bucket, and
    ``decision_log``'s own schema is explicit that "readers must ignore unknown event
    names and unknown payload keys so that newer instrumentation never breaks an older
    reader". A reader that refuses a run id it does not recognise breaks exactly that.
    An unrecognised-but-present id is more honestly reported under its own name than
    merged into "unattributed", which is a claim that no id was recorded at all.

    ``casefold`` rather than ``lower``: the writer's own ids are ASCII hex, where the
    two agree, but the contract is casefolding — and ``lower`` leaves ``"Straße"`` and
    ``"STRASSE"`` as two runs.
    """
    if not isinstance(value, str):
        return ""
    return value.strip().casefold()
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-canonical-run


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-group-runs
def group_by_run(selection: EventSelection) -> Dict[str, List[Dict[str, Any]]]:
    """Group a selection's events by ``run_id``, preserving first-seen run order.

    This is the role ``run_id`` keeps once the window stops being derived from it: a
    subdivision *within* the branch's span, so a digest can say "three invocations"
    without treating the last one as the whole story.

    **Every selected event lands in exactly one bucket.** Events carrying a blank or
    missing ``run_id`` go to :data:`RUN_UNATTRIBUTED`; previously buckets were built
    only for truthy ids, so such an event sat in ``events`` and in no group at all and
    a renderer summing the groups under-reported without saying so.

    The buckets hold the selection's own event objects, not copies. One event has one
    identity: a copy would let a renderer annotate a group and then read a different
    value back from ``events`` — two truths where there was one. The selection itself is
    frozen and its collections are tuples, so this view cannot make its counts wrong.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {run: [] for run in selection.runs}
    for event in selection.events:
        run_id = _canonical_run_id(event.get("run_id")) or RUN_UNATTRIBUTED
        grouped.setdefault(run_id, []).append(event)
    return grouped
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-group-runs


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-link-datamodel
@dataclass(frozen=True)
class FileLink:
    """One changed file and what it does with requirement IDs.

    Two directions, deliberately separate. ``references`` are IDs the file *points at*
    — code serving a requirement. ``defines`` are IDs the file *declares* — an artifact
    that **is** a requirement. Code can only reference and artifacts normally only
    define, so collapsing them into one list would report a changed specification as
    "traces to nothing", which is precisely backwards.

    ``reason`` separates *"checked, and it carries no markers"* (empty) from *"could
    not check"* — deleted or unreadable. A digest that merges those implies a file
    serves no requirement when in truth it was never read.

    Frozen, with tuple fields, like the window and selection records: a link is what
    one read of one file found, and nothing may edit that after the fact.
    """

    path: str = ""
    status: str = ""
    references: Tuple[str, ...] = ()
    defines: Tuple[str, ...] = ()
    reason: str = REASON_OK


@dataclass(frozen=True)
class LinkReport:
    """What every file changed inside a window does with requirement IDs.

    The counters exist so a renderer can print its denominator. ``linked`` alone is a
    number without a scope; ``linked`` of ``changed``, with ``declaring``, ``excluded``
    and ``unreadable`` broken out, is checkable — which is only true while ``files``
    cannot be grown or shrunk underneath them, hence frozen and a tuple.

    ``changed`` counts every entry git reported; ``examined`` counts the ones this
    report classified, which is fewer when the ceiling bit (``truncated`` is the
    difference). Every tally and every row is over ``examined``, so the arithmetic a
    renderer checks is ``examined == len(files) + excluded``, and every row that carries
    no marker is in exactly one of ``deleted``, ``unreadable`` or ``not_a_file`` — or is
    a regular file that was read and simply carries none.

    ``unreadable`` is **the aggregate of every reason no marker could be established**,
    not only a failed read: a file whose scope could not be determined
    (:data:`REASON_SCOPE_UNKNOWN`), one whose markers would not parse
    (:data:`REASON_MARKERS_INVALID`) and one whose scan failed unexpectedly
    (:data:`REASON_SCAN_FAILED`) all land here alongside
    :data:`REASON_FILE_UNREADABLE`. Splitting it would put a counter on each cause and
    an invariant on none of them — the exactly-one property above is what a renderer
    checks its arithmetic against. The distinction is not lost: each row keeps its own
    ``reason``, so the per-file detail says which cause applied while the counter says
    only how many rows yielded nothing. A renderer naming this count must therefore name
    the aggregate rather than one of its causes.
    """

    files: Tuple[FileLink, ...] = ()
    changed: int = 0
    examined: int = 0
    linked: int = 0
    declaring: int = 0
    deleted: int = 0
    excluded: int = 0
    unreadable: int = 0
    not_a_file: int = 0
    truncated: int = 0
    available: bool = False
    reason: str = REASON_NOT_A_REPO
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-link-datamodel


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-git-lines
def _git_records(project_root: Path, args: List[str]) -> Optional[List[str]]:
    """Run a read-only git query with ``-z`` output and split it on NUL.

    The multi-record sibling of :func:`_git_query`. ``None`` here means "no answer" for
    every failure mode, so callers report rather than diagnose. Never raises.

    Line-splitting is not usable here. Without ``-z``, git *quotes and escapes* any
    path containing a control character, a quote or a non-ASCII byte — a file legally
    named ``we<TAB>ird.py`` arrives as the literal 12 characters ``"we\\tird.py"``.
    Splitting that on tab yields fragments that match nothing on disk, so the file
    would be reported as deleted while sitting right there. NUL records are the only
    unambiguous form, since NUL is the one byte a path cannot contain.

    Runs with the same sanitised environment as :func:`_git_query`. This helper was
    written before that sanitising existed and did not pick it up, so an ambient
    ``GIT_DIR`` could resolve the window against one repository and then list the
    changed files of another — half a digest about the wrong project.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(project_root),
            env=_git_env(),
            capture_output=True,
            # Bytes, decoded per record below rather than by `text=True`.
            #
            # Sharing the codec with the streamed sweep was not enough to make the two
            # readers name one file alike: `text=True` also turns on *universal
            # newlines*, and `subprocess` exposes no way to switch that off. So a path
            # containing CR came back translated -- measured, `sweep\rname.txt` decoded
            # here as `sweep\nname.txt` -- while the sweep, decoding raw slices, kept
            # the CR. Two consequences, and the second is the worse one: deduplication
            # against this listing missed the file, so it was reported twice; and the
            # translated name opens nothing, so a *tracked* file present on disk was
            # reported as "file no longer present".
            #
            # A path may contain any byte but NUL and `/`, CR included, and only NUL is
            # the record separator -- so nothing in the output needs translating and
            # anything translated is corruption.
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as exc:
        # Warning, not debug, for the same reason as `_git_query`: this is the tool
        # failing, not git answering "no", and the two must not look alike in a log.
        logger.warning(_LOG_GIT_FAILED, type(exc).__name__)
        return None
    if result.returncode:
        logger.debug(_LOG_GIT_EXITED, result.returncode)
        return None
    # A trailing NUL leaves one empty tail record; drop it without dropping
    # legitimately empty interior records, which would desynchronise the walk.
    raw = result.stdout.split(b"\0")
    if raw and not raw[-1]:
        raw.pop()
    # The same decode call the pump makes, on the same slices, so one path is one
    # string whichever reader saw it.
    return [record.decode(_PATH_ENCODING, _PATH_ERRORS) for record in raw]
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-git-lines


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-git-stream
def _git_records_bounded(
    project_root: Path, args: List[str], keep: int, skip: Container[str] = frozenset(),
) -> Optional[Tuple[List[str], int]]:
    """Stream a ``-z`` query, storing at most ``keep`` records and counting them all.

    For the one query whose output is not bounded by the repository — the untracked
    sweep, which an unignored dependency tree can turn into hundreds of thousands of
    paths. :func:`_git_records` captures the whole output and splits it into one Python
    string per record before any ceiling applies; this reads git's pipe in chunks, keeps
    the first ``keep`` records, and counts the rest as they stream past, so the cost
    bounded is the cost that was actually accruing. Records in ``skip`` are neither kept
    nor counted, and are judged before the ceiling: a caller deduplicating this stream
    against another listing cannot do so afterwards for records that were only counted,
    and a duplicate that took a kept slot displaced a record that was genuinely new.
    Returns ``(kept, total)``, or ``None`` for any non-answer, like its sibling — a
    stream that failed part-way is a non-answer too, not a shorter listing.
    """
    kept: List[str] = []
    counts = [0]
    failure: List[BaseException] = []
    deadline = time.monotonic() + _GIT_TIMEOUT
    try:
        with subprocess.Popen(
            ["git"] + args,
            cwd=str(project_root),
            env=_git_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as proc:
            assert proc.stdout is not None
            # The pipe is read on a helper thread against the module's deadline. A
            # blocking read on the main thread was bounded by nothing: a git that holds
            # stdout open without writing never returns from `read`, so the `wait`
            # with its timeout behind it could never run. Threads are how `subprocess`
            # itself does this portably (`communicate`), and pipes are not selectable
            # everywhere this runs.
            pump = threading.Thread(
                target=_pump_records,
                args=(proc.stdout, keep, skip, kept, counts, failure),
                daemon=True,
            )
            pump.start()
            pump.join(timeout=max(0.0, deadline - time.monotonic()))
            if pump.is_alive():
                proc.kill()
                pump.join(timeout=1.0)
                raise subprocess.TimeoutExpired(cmd="git", timeout=_GIT_TIMEOUT)
            if failure:
                # The pump stopped early. What it kept is a prefix of the truth, and a
                # prefix presented as the listing is the silent omission this module
                # exists to prevent — so nothing is returned rather than part of it.
                proc.kill()
                logger.warning(_LOG_GIT_STREAM_FAILED, type(failure[0]).__name__)
                return None
            try:
                returncode = proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                proc.kill()
                raise
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(_LOG_GIT_FAILED, type(exc).__name__)
        return None
    if returncode:
        logger.debug(_LOG_GIT_EXITED, returncode)
        return None
    return kept, counts[0]
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-git-stream


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-pump-records
def _pump_records(
    stream: Any, keep: int, skip: Container[str],
    kept: List[str], counts: List[int], failure: List[BaseException],
) -> None:
    """Split a NUL-delimited byte stream as it arrives: keep up to ``keep``, count all.

    ``counts`` and ``failure`` are lists so the total and any exception cross the thread
    boundary without a lock — the caller reads them only after joining. An unterminated
    final record is a record too, as :func:`_git_records` treats it; an empty record is
    not, since this reader lists paths and there is no empty path. Whatever is raised in
    here is recorded rather than lost: an exception ends a thread and is printed nowhere,
    and the caller would have read a stopped pump as a finished one — a partial listing
    as the whole. A record longer than :data:`_MAX_RECORD_BYTES` is such a failure,
    whether it has been terminated or is still accruing in the tail.
    """
    def take(raw: bytes) -> None:
        if len(raw) > _MAX_RECORD_BYTES:
            raise ValueError("record exceeds the streamed reader's size bound")
        record = raw.decode(_PATH_ENCODING, _PATH_ERRORS)
        if not record or record in skip:
            return
        counts[0] += 1
        if len(kept) < keep:
            kept.append(record)

    try:
        tail = b""
        for chunk in iter(lambda: stream.read(65536), b""):
            parts = (tail + chunk).split(b"\0")
            tail = parts.pop()
            if len(tail) > _MAX_RECORD_BYTES:
                raise ValueError("record exceeds the streamed reader's size bound")
            for raw in parts:
                take(raw)
        if tail:
            take(tail)
    except Exception as exc:  # pylint: disable=broad-except
        failure.append(exc)
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-pump-records


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-parse-name-status
def _walk_name_status(records: List[str]) -> List[Tuple[str, str]]:
    """Walk ``git diff --name-status -z`` records into ``(status, path)`` pairs.

    Under ``-z`` the output is a flat record stream, not one record per change: a
    status is followed by **one** path, except renames and copies which are followed by
    **two** — the old name then the new one. So the stream has to be walked with that
    arity in mind rather than zipped in pairs; getting it wrong desynchronises every
    subsequent entry, not just the rename.

    The *new* path is the one that exists to be read, so it is the one kept. Taking the
    old name would send every rename to the unreadable branch and silently drop its
    requirement links. Truncated output stops the walk instead of raising.
    """
    entries: List[Tuple[str, str]] = []
    index = 0
    while index < len(records):
        status_field = records[index]
        index += 1
        if not status_field:
            continue
        status = status_field[0]
        wanted = 2 if status in ("R", "C") else 1
        paths = records[index:index + wanted]
        index += wanted
        if len(paths) < wanted or not paths[-1]:
            continue
        entries.append((status, paths[-1]))
    return entries
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-parse-name-status


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-classify-path
def _in_project_scope(candidate: Path, project_root: Path) -> Optional[bool]:
    """Report whether a changed path is one this project owns.

    Three answers, not two. ``None`` means the question could not be answered, which
    used to be folded into "excluded by policy" — a policy decision reported for what
    was actually a filesystem error, so the report claimed a judgement it never made.

    Delegates to :func:`codebase.resolve_entry_code_files`, the single shared exclusion
    policy, rather than re-deriving containment rules that already exist in one place.
    Two things that delegation does *not* handle, both guarded here:

    * **A directory-shaped entry.** A changed submodule appears in the diff as a
      gitlink, which is a directory on disk, so the shared resolver takes its ``rglob``
      branch and walks the entire nested tree purely to answer a boolean. Regular files
      are the only linkable entries, so anything else is refused before that walk.
    * **Conventional non-source directory names**, which the resolver applies to
      traversal-discovered candidates but not to an explicitly named file. So a tracked
      change under a vendored path is reported rather than hidden — the safer direction
      for a review digest, since over-reporting costs a reader a moment while
      under-reporting hides work that really did change.

    **No extension policy applies, by design.** The resolver's extension list only
    selects candidates when it walks a directory; for a single file it is not consulted,
    so an empty list is passed rather than a fabricated one that would suggest a filter
    is in force. The registry's code extensions would be the wrong filter anyway: the
    digest reports both directions, and a changed feature artifact — Markdown, never a
    code extension — *declares* requirements. Filtering it out would report a changed
    specification as tracing to nothing, which is the inversion this module exists to
    avoid. What a file *does* with IDs is decided by reading it, not by its suffix.
    """
    try:
        if not candidate.is_file():
            return False
        files, _excluded = codebase.resolve_entry_code_files(
            candidate, [], project_root=project_root,
        )
    except OSError as exc:
        logger.debug("change-summary scope check failed: %s", exc)
        return None
    return bool(files)
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-classify-path


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-file-markers
def _file_traceability(path: Path) -> Tuple[List[str], List[str], str]:
    """Return ``(references, defines, reason)`` for one changed file.

    Both directions are asked, because a file's suffix is not a reliable guide and the
    authoritative extension list lives in a ``commands`` module this layer must not
    import. Asking what the file *does* with IDs is language-agnostic and needs no list:

    * :func:`codebase.CodeFile.from_text` yields code markers — IDs the file
      **references** from code.
    * :func:`document.scan_cpt_id_lines` yields document IDs — those tagged
      ``definition`` are IDs the file **declares**; those tagged ``reference`` are IDs
      the document cites, which are references too. A document's mentions of IDs it
      declares itself are left out: they point at nothing else.

    The two are complementary in practice: this module's own source reports its code
    references and no definitions, while the feature artifact declaring its algorithm
    reports definitions, plus references to the other requirements it cites.

    A binary file lands in the unreadable branch, because the loader reports a decode
    failure — returned as *could not read* rather than as "carries no markers". Those
    are different claims and only one of them is true.

    **The file is read once**, and both parsers see that one snapshot. Two independent
    reads let a file edited mid-scan — the live-editing case this module is for — report
    ``references`` from one version and ``defines`` from another as if they described a
    single state. The size ceiling lives in :mod:`codebase` alongside the bulk-scan path
    that already enforced it, applied to the bytes actually read, and *too large* is told
    from *unreadable* by the loader's own error code rather than by measuring the file
    a second time.
    """
    text, errors = codebase.read_code_text(path)
    if text is None:
        if any(err.get("code") == EC.FILE_TOO_LARGE for err in errors):
            return [], [], REASON_FILE_TOO_LARGE
        logger.debug("change-summary could not read a changed file")
        return [], [], REASON_FILE_UNREADABLE
    code_file, errors = codebase.CodeFile.from_text(path, text)
    if code_file is None or errors:
        # Read fine, parsed badly. A test file full of deliberately malformed marker
        # fixtures is the everyday case, and "could not be read" was untrue of it.
        logger.debug("change-summary could not parse code markers in a changed file")
        return [], [], REASON_MARKERS_INVALID
    hits = document.scan_cpt_id_lines(text.splitlines())
    defines = {str(h.get("id")) for h in hits if h.get("type") == "definition" and h.get("id")}
    # A document that points at an ID references it as surely as a code marker does —
    # a design note citing a requirement is a link to that requirement. Only its
    # mentions of IDs it declares *itself* are left out: those point at nothing else.
    cited = {str(h.get("id")) for h in hits if h.get("type") == "reference" and h.get("id")}
    references = {ref.id for ref in code_file.references if ref.id} | (cited - defines)
    return sorted(references), sorted(defines), REASON_OK
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-file-markers


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-collect-changed
def _collect_changed_entries(
    project_root: Path,
    base_sha: str,
) -> Optional[Tuple[List[Tuple[str, str]], int]]:
    """List ``(status, path)`` for everything changed since ``base_sha``, plus the total.

    Returns ``(entries, total)``: at most :data:`MAX_CHANGED_ENTRIES` entries returned
    for examination, and the count of every distinct path git reported. The tracked diff
    is captured whole: its size is bounded by the repository's tracked-file count, which
    git holds in memory to produce it, so streaming it would bound nothing the
    repository does not already. The untracked sweep is the unbounded one — an
    unignored dependency tree can run to hundreds of thousands of paths — so it is
    streamed: it keeps only as many paths as the shared ceiling can still seat once the
    diff is in hand, *counts* the rest, and is deduplicated against the diff as it
    streams, so a path already seen is neither stored nor counted, and takes no slot
    from a path that is genuinely new.

    Rename detection is pinned with ``-M`` rather than left to the ambient
    ``diff.renames`` setting, because :func:`_walk_name_status` keeps a rename's new
    path precisely so the rename keeps its requirement link — a guarantee that would
    otherwise hold on one machine and fail on another with the same repository state.

    Compares the base commit against the **working tree**, not against ``HEAD``, so
    uncommitted work is included — a developer asking what changed before committing is
    the main caller.

    Untracked files are collected separately and reported with status ``?``. ``git
    diff`` cannot see them, so omitting them would let a brand-new module be absent
    from the digest entirely: the silent omission this module exists to avoid.

    **The two streams overlap and are deduplicated by path, diff status winning.** One
    physical file can appear in both: `git rm --cached` on a file present in the base
    commit leaves it deleted in the index and untracked on disk, so the diff reports
    ``D`` and the untracked sweep reports it as new. Concatenating produced two
    contradictory rows for one file and inflated every counter. Git emits repo-relative
    POSIX paths from both commands, so the raw string is an exact key — resolving each
    path instead would cost a syscall per entry *and* wrongly merge two distinct
    symlinks that happen to share a target.

    **Either query failing makes the whole listing unavailable.** An earlier version
    turned a failed untracked sweep into an empty one, so a report could come back
    available while silently missing every new file — the exact partial-presented-as-
    complete result this module exists to prevent.
    """
    diffed = _git_records(
        project_root,
        # `--end-of-options` for the same reason as the ref lookups: the base sha comes
        # from a window the caller may have built, so it must not be read as an option.
        ["diff", "-M", "--name-status", "-z", "--end-of-options", base_sha],
    )
    if diffed is None:
        return None
    seen: Dict[str, str] = {}
    for status, rel_path in _walk_name_status(diffed):
        seen.setdefault(rel_path, status)
    # The sweep keeps only as many paths as the shared ceiling can still seat. The
    # interleave gives tracked entries at most half of it, so once the diff is in hand
    # the room left for new files is known, and nothing is retained only to be dropped.
    keep = MAX_CHANGED_ENTRIES - min(len(seen), (MAX_CHANGED_ENTRIES + 1) // 2)
    swept = _git_records_bounded(
        project_root, ["ls-files", "--others", "--exclude-standard", "-z"], keep,
        # Deduplicated inside the stream, before the ceiling. Checked afterwards, a
        # `git rm --cached` file — in the diff already — was counted a second time once
        # past the ceiling, and below it had taken a kept slot from a genuinely new file.
        skip=seen,
    )
    if swept is None:
        return None
    untracked, untracked_total = swept
    new = [(path, "?") for path in untracked]
    total = len(seen) + untracked_total
    tracked = list(seen.items())
    if len(tracked) + len(new) <= MAX_CHANGED_ENTRIES:
        picked = tracked + new
    else:
        # The ceiling is shared fairly rather than filled from the diff first: filling
        # in order dropped exactly the untracked files — brand-new work, the one thing
        # the sweep exists to keep in the digest — whenever the diff alone reached it.
        picked = _interleave(tracked, new, MAX_CHANGED_ENTRIES)
    # The map is keyed by path for deduplication, but the contract is (status, path),
    # so the pairs are flipped back rather than returned in the map's own order.
    return [(status, rel_path) for rel_path, status in picked], total
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-collect-changed


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-share-ceiling
def _interleave(first: List[Tuple[str, str]], second: List[Tuple[str, str]], cap: int) -> List[Tuple[str, str]]:
    """Take from two lists alternately until ``cap`` items, so neither is starved.

    Used only when the ceiling bites. Below it, the natural order — diff entries then
    untracked — is kept, so a report that was never capped reads as it always did.
    """
    picked: List[Tuple[str, str]] = []
    i = j = 0
    while len(picked) < cap and (i < len(first) or j < len(second)):
        if i < len(first):
            picked.append(first[i])
            i += 1
        if len(picked) < cap and j < len(second):
            picked.append(second[j])
            j += 1
    return picked
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-share-ceiling


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-classify-entry
def _classify_entry(
    status: str,
    rel_path: str,
    project_root: Path,
) -> Tuple[Optional[FileLink], str]:
    """Classify one changed entry into ``(link, counter to bump)``.

    Extracted from :func:`link_changed_files` to keep that function within the
    project's local-variable budget, and because "what is this entry, and which tally
    does it belong to" is one question worth answering in one place.

    A ``None`` link means the entry is counted but not listed — that is only the
    policy-excluded case, where naming the path would imply it was examined. Every
    other outcome produces a row, because a reader needs to see that the entry existed
    even when nothing could be read from it.
    """
    absolute = project_root / rel_path
    in_scope = _in_project_scope(absolute, project_root)

    if in_scope is None:
        # The scope question could not be answered. Reporting that as "excluded by
        # policy" would claim a judgement that was never made.
        return FileLink(path=rel_path, status=status, reason=REASON_SCOPE_UNKNOWN), "unreadable"

    if not in_scope:
        # Three distinct ways to fail the scope check, kept apart: the file is gone, it
        # is not a regular file at all (a changed submodule arrives as a directory), or
        # the shared policy genuinely excluded it.
        if status == "D" or not absolute.exists():
            return FileLink(path=rel_path, status=status, reason=REASON_FILE_GONE), "deleted"
        if not absolute.is_file():
            # Its own tally: it is neither gone nor unreadable nor excluded, and a row
            # that bumps no counter is an entry the report's arithmetic cannot see.
            return FileLink(path=rel_path, status=status, reason=REASON_NOT_A_FILE), "not_a_file"
        return None, "excluded"

    references, defines, reason = _file_traceability(absolute)
    link = FileLink(
        path=rel_path, status=status,
        references=tuple(references), defines=tuple(defines), reason=reason,
    )
    return link, ("unreadable" if reason else "")
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-classify-entry


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-link-changed
def link_changed_files(window: ChangeWindow) -> LinkReport:
    """Resolve every file changed inside ``window`` to the requirements it declares.

    The project root comes from the window — the resolved path its ``base_sha`` was
    established against — not from a second argument. An earlier signature took one,
    unresolved, so a relative root plus a later ``chdir`` could diff a different
    directory from the one the window described, while every other reader of the
    window (``select_events``) already sourced the root from it.

    An unavailable window propagates its own reason, so one cause is reported rather
    than two. A window built from an explicit ``--since`` has no base commit, so there
    is nothing to diff against and that is said plainly instead of silently returning
    no files. Never raises: one entry whose classification raises something no arm
    anticipated becomes its own row with a stated reason, and every other row stands —
    the alternative was one bad file discarding the whole report.
    """
    if not window.available:
        return LinkReport(reason=window.reason)
    if not window.base_sha:
        return LinkReport(reason=REASON_NO_BASE_COMMIT)
    if not window.project_root:
        return LinkReport(reason=REASON_NO_PROJECT_ROOT)
    project_root = Path(window.project_root)

    collected = _collect_changed_entries(project_root, window.base_sha)
    if collected is None:
        return LinkReport(reason=REASON_DIFF_UNAVAILABLE)
    entries, total = collected

    # Entries beyond the ceiling are counted, not dropped quietly. The count is the
    # whole point: a digest that examined 1,000 of 40,000 changed paths and said
    # nothing about the other 39,000 would be the silent-omission defect at scale.
    examined = entries[:MAX_CHANGED_ENTRIES]

    links: List[FileLink] = []
    tally: Dict[str, int] = {"deleted": 0, "excluded": 0, "unreadable": 0, "not_a_file": 0}
    for status, rel_path in examined:
        try:
            link, counter = _classify_entry(status, rel_path, project_root)
        except Exception as exc:  # pylint: disable=broad-except
            # The isolation boundary. Everything an entry can legitimately fail with is
            # handled inside `_classify_entry`; this catches what was not foreseen, and
            # confines it to the one row rather than letting it discard the report.
            logger.warning("change-summary could not classify a changed entry: %s", type(exc).__name__)
            link, counter = FileLink(path=rel_path, status=status, reason=REASON_SCAN_FAILED), "unreadable"
        if counter:
            tally[counter] += 1
        if link is not None:
            links.append(link)

    return LinkReport(
        files=tuple(links),
        changed=total,
        examined=len(examined),
        linked=sum(1 for link in links if link.references),
        declaring=sum(1 for link in links if link.defines),
        deleted=tally["deleted"],
        excluded=tally["excluded"],
        unreadable=tally["unreadable"],
        not_a_file=tally["not_a_file"],
        truncated=total - len(examined),
        available=True,
        reason=REASON_OK,
    )
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-link-changed
