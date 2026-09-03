"""Change-summary core — resolve the window a digest covers, and select the
decision-log events recorded inside it.

The digest answers "what changed on this branch, and why". This module owns the two
halves that have no output format: **which span of work counts as "the run"**, and
**which recorded decisions fall inside it**. Rendering belongs to the command
wrapper; linking changed files to requirements is separate again.

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

@cpt-algo:cpt-studio-algo-developer-experience-change-summary:p1
"""

# @cpt-begin:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-datamodel
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import decision_log

logger = logging.getLogger(__name__)

#: Seconds any single git query may take before it is treated as unavailable.
_GIT_TIMEOUT = 10

#: Environment variables that redirect git away from the repository it was pointed at.
#:
#: ``cwd=`` is *not* sufficient on its own: an ambient ``GIT_DIR`` overrides it, so a
#: query about project A answered from project B's repository. Verified —
#: ``GIT_DIR=b/.git git -C a log`` reports b's commit, not a's. Every one of these is
#: cleared so the answer describes the project the caller named and nothing else.
_GIT_REDIRECT_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CEILING_DIRECTORIES",
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
REASON_NO_BASE_TIME = "base commit has no readable timestamp"
REASON_NOT_A_PROJECT = "not inside a Studio project"
REASON_LOG_DISABLED = "decision log disabled"
REASON_LOG_ABSENT = "no decision log yet"
REASON_LOG_UNREADABLE = "decision log unreadable"
REASON_INVALID_SINCE = "the supplied lower bound is not an absolute timestamp"

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
            # break the never-raises contract. `surrogateescape` is the handler Python
            # uses for filesystem values, so they round-trip to the same bytes.
            errors="surrogateescape",
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as exc:
        logger.debug("change-summary git query could not run: %s", exc)
        return None, True
    if result.returncode:
        logger.debug("change-summary git query exited %d", result.returncode)
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

    Returns ``(sha, tool_failed)``. Unrelated histories and a missing ref yield a
    ``None`` sha with ``tool_failed`` false — there is genuinely no branch point. A
    ``True`` flag means git never answered, which is a different fact and must not be
    reported as a finding about history.
    """
    return _git_query(project_root, ["merge-base", "--end-of-options", "HEAD", base_ref])
# @cpt-end:cpt-studio-algo-developer-experience-change-summary:p1:inst-change-summary-merge-base


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

    ``since`` short-circuits git entirely — an explicit lower bound is the caller's
    assertion and needs no branch point. Otherwise the window starts at the merge-base
    with ``base`` (or the first of :data:`_DEFAULT_BASE_REFS` that exists).

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
    if since:
        # A caller-supplied bound is validated here rather than surfacing later as a
        # complaint about a base commit that was never consulted.
        if _parse_ts(since) is None:
            return ChangeWindow(project_root=root, reason=REASON_INVALID_SINCE)
        return ChangeWindow(project_root=root, since=since, available=True, reason=REASON_OK)

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
    return _window_from_base_ref(project_root, base_ref)
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
        return ChangeWindow(project_root=root, base_ref=base_ref, reason=REASON_NO_MERGE_BASE)

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
