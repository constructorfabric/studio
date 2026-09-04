"""Change-summary command — an advisory digest of what changed on this branch, and why.

Thin CLI wrapper around ``studio.utils.change_summary``: the window that module resolves,
the decision-log events it selects inside that window, and the requirement IDs it finds
on the changed files are composed here into roughly ten lines a developer can paste into
a review.

Advisory is a **structural** property of this command, not a claim in its docstring:

* it exits 0 on every path except a usage error, and a test forces each failure mode
  and asserts the exit code did not move;
* every degraded dimension states its own reason **and** its denominator — "0 of 9
  changed files carry markers", never a bare list that reads as complete;
* the ceiling is a ceiling, not a quota. Only lines backed by data are emitted, then it
  stops; "no changes against ``main``" is one line, not an empty digest padded to ten.
  When the ceiling bites, the last line says how many lines it cut;
* nothing is published. It writes no file, posts nowhere and runs in no gate — the
  developer decides where the text goes.

Why this is not ``usage-report --since``: ``usage-report`` is a *cost* lens, tokens and
reads per method over the whole log. This is a *review* lens — what changed on a branch,
why, and against which requirement. Different audience, output and window, so one
command with two unrelated modes was rejected.

The digest never counts itself. The dispatcher records an ``invocation`` event for every
command including this one, so a naive digest would carry its own previous runs in the
payload's totals and two consecutive ``--json`` runs would differ by one event.
Telemetry events (``invocation``, ``read``) are excluded from the "why" line, and this
command's own invocations are excluded from the payload entirely.

@cpt-flow:cpt-studio-flow-developer-experience-change-summary:p1
@cpt-algo:cpt-studio-algo-developer-experience-change-summary-digest:p1
"""

# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-datamodel
from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils import change_summary as core
from ..utils.files import find_studio_directory
from ..utils.ui import ui

logger = logging.getLogger(__name__)

#: Hard ceiling on the human digest, in lines. When it bites, the last line says so.
LINE_CEILING = 10

#: How many requirement IDs, and how many runs, are named inline before the line falls
#: back to "(+N more)". The JSON payload always carries all of them.
_MAX_NAMED_REQUIREMENTS = 5
_MAX_NAMED_RUNS = 3

#: Event kinds that record cost or plumbing rather than a decision. They stay in the
#: payload's totals but are not what a reviewer means by "why".
_TELEMETRY_EVENTS = frozenset({"invocation", "read"})

#: This command's own name, so its invocation events never appear in its own digest.
_SELF_COMMAND = "change-summary"

#: Status is always OK: the digest is advisory, and a dimension it could not build is a
#: stated line, not a failed command.
_STATUS = "OK"

#: The project check itself failed — a permission error, an unreadable mount — which is
#: a different fact from "this is not a Studio project", and is said as one.
REASON_PROJECT_UNCHECKED = "the project root could not be checked"
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-datamodel


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-project-gate
def _project_gate(root: Path) -> Optional[str]:
    """Return ``None`` inside a Studio project, else the reason there is nothing to digest.

    One stated reason rather than three "unavailable" dimensions: outside a project there
    is no decision log to read and no exclusion policy to apply, so the git half alone
    would be a digest of the wrong thing.

    Two reasons, not one. "Not a Studio project" is a fact about the directory; the
    check *failing* — a permission error, an unreadable mount — is a fact about the
    machine, and folding it into the first sent a developer on a flaky mount to look for
    a missing project. The failure is also logged at warning level, the same level the
    last-resort guard uses, because a debug line nobody sees is a silence with a label.
    """
    try:
        studio_dir = find_studio_directory(root)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.warning("change-summary could not check the project root: %s", type(exc).__name__)
        return f"{REASON_PROJECT_UNCHECKED} ({type(exc).__name__})"
    return None if studio_dir is not None else core.REASON_NOT_A_PROJECT
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-project-gate


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-window-line
def _window_line(window: core.ChangeWindow) -> str:
    """Say what span the digest covers, or why it could not be established.

    With no window there is nothing to scope changes or decisions to, so the line also
    names the remedy: an explicit ``--since`` scopes decisions by time without git.
    """
    if not window.available:
        return f"window: unavailable ({window.reason}); --since <timestamp> scopes decisions without git"
    if window.base_sha:
        return f"window: since {window.base_ref} @ {window.base_sha[:8]} ({window.since})"
    return f"window: since {window.since} (explicit; no base commit to diff against)"
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-window-line


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-changes-lines
def _marked(report: core.LinkReport) -> int:
    """Files that carry at least one requirement marker, in either direction."""
    return sum(1 for link in report.files if link.references or link.defines)


def _changes_lines(report: core.LinkReport) -> List[str]:
    """State what changed, with its denominator on every line.

    ``linked`` and ``declaring`` are not summed — a file can do both — so the marker
    line counts files carrying any marker against the files that changed. Every tally
    that is non-zero is named; a tally that is zero is not a line.

    The tallies are computed over the entries the report *examined*. When the scan was
    capped that is fewer than the files that changed, so the lines name that population
    explicitly rather than let "300 of 1,500" read as a breakdown of 1,500.
    """
    if not report.available:
        return [f"changes: unavailable ({report.reason})"]
    tallies = [
        (report.linked, "reference requirements"),
        (report.declaring, "declare requirements"),
        (report.excluded, "excluded by the project's scope policy"),
        (report.deleted, "deleted"),
        (report.unreadable, "could not be read or parsed"),
        (report.not_a_file, "not regular files"),
    ]
    detail = "; ".join(f"{count} {label}" for count, label in tallies if count)
    if report.truncated:
        head = f"changes: {report.changed} file(s); {report.examined} examined"
        population = f"{report.examined} examined files"
    else:
        head = f"changes: {report.changed} file(s)"
        population = f"{report.changed} changed files"
    lines = [head + (f": {detail}" if detail else "")]
    lines.append(f"markers: {_marked(report)} of {population} carry requirement markers")
    if report.truncated:
        lines.append(f"changes: scan capped; {report.truncated} more file(s) were not examined")
    return lines
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-changes-lines


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-requirements-line
def _requirement_ids(report: core.LinkReport) -> List[str]:
    """Every requirement ID the changed files reference or declare, sorted, once each."""
    return sorted({rid for link in report.files for rid in (*link.references, *link.defines)})


def _requirements_line(ids: List[str]) -> Optional[str]:
    """Name the requirements served, capped and counted — never truncated silently."""
    if not ids:
        return None
    shown = ", ".join(ids[:_MAX_NAMED_REQUIREMENTS])
    more = len(ids) - _MAX_NAMED_REQUIREMENTS
    return f"requirements: {shown}" + (f" (+{more} more)" if more > 0 else "")
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-requirements-line


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-decision-lines
def _is_own_invocation(event: Dict[str, Any]) -> bool:
    return event.get("event") == "invocation" and event.get("command") == _SELF_COMMAND


def _decision_runs(selection: core.EventSelection) -> List[Tuple[str, int]]:
    """Runs in first-seen order with how many *decisions* each recorded; runs that only
    logged telemetry are not listed, because they explain nothing about the change."""
    runs: List[Tuple[str, int]] = []
    for run_id, events in core.group_by_run(selection).items():
        decisions = sum(1 for e in events if e.get("event") not in _TELEMETRY_EVENTS)
        if decisions:
            runs.append((run_id, decisions))
    return runs


def _decision_lines(selection: core.EventSelection) -> List[str]:
    """State the decisions recorded inside the window, and every way the log fell short.

    Skipped lines, undated events and a shared log are each a line of their own: a
    reviewer reading "5 decisions" is entitled to know that 3 lines could not be read.
    """
    if not selection.available:
        return [f"decisions: unavailable ({selection.reason})"]
    events = [e for e in selection.events if not _is_own_invocation(e)]
    decisions = [e for e in events if e.get("event") not in _TELEMETRY_EVENTS]
    runs = _decision_runs(selection)
    if decisions:
        by_kind = Counter(str(e.get("event")) for e in decisions)
        kinds = ", ".join(f"{kind} ×{n}" for kind, n in sorted(by_kind.items(), key=lambda kv: (-kv[1], kv[0])))
        lines = [f"why: {len(decisions)} decision(s) in {len(runs)} run(s): {kinds}"]
        named = ", ".join(f"{run_id[:8]} ×{n}" for run_id, n in runs[:_MAX_NAMED_RUNS])
        more = len(runs) - _MAX_NAMED_RUNS
        lines.append(f"runs: {named}" + (f" (+{more} more)" if more > 0 else ""))
    else:
        lines = [f"why: no decisions recorded in this window ({len(events)} event(s) scanned)"]
    if selection.skipped_lines:
        lines.append(f"decision log: {selection.skipped_lines} unparseable line(s) skipped")
    if selection.undated:
        lines.append(f"decision log: {selection.undated} undated event(s) excluded")
    if selection.log_overridden:
        lines.append("decision log: shared via CFS_DECISION_LOG; decisions are not attributable to this project")
    return lines
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-decision-lines


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-ceiling
def _apply_ceiling(lines: List[str]) -> Tuple[List[str], int]:
    """Cut the digest to the ceiling, and say so — never pad, never cut silently."""
    if len(lines) <= LINE_CEILING:
        return lines, 0
    omitted = len(lines) - (LINE_CEILING - 1)
    kept = lines[: LINE_CEILING - 1]
    return kept + [f"(+{omitted} more line(s) omitted; --json carries everything)"], omitted
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-ceiling


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-payload
def _window_payload(window: core.ChangeWindow) -> Dict[str, Any]:
    # The project root is deliberately absent: it is an absolute path, and the digest
    # must carry nothing a home directory or username could reach a review through.
    return {
        "available": window.available, "reason": window.reason,
        "base_ref": window.base_ref, "base_sha": window.base_sha, "since": window.since,
    }


def _changes_payload(report: core.LinkReport) -> Dict[str, Any]:
    return {
        "available": report.available, "reason": report.reason,
        "changed": report.changed, "examined": report.examined, "marked": _marked(report),
        "linked": report.linked, "declaring": report.declaring,
        "excluded": report.excluded, "deleted": report.deleted,
        "unreadable": report.unreadable, "not_a_file": report.not_a_file,
        "truncated": report.truncated,
        "files": [
            {"path": f.path, "status": f.status, "references": list(f.references),
             "defines": list(f.defines), "reason": f.reason}
            for f in report.files
        ],
    }


def _decisions_payload(selection: core.EventSelection) -> Dict[str, Any]:
    events = [e for e in selection.events if not _is_own_invocation(e)]
    decisions = [e for e in events if e.get("event") not in _TELEMETRY_EVENTS]
    return {
        "available": selection.available, "reason": selection.reason,
        "events": len(events), "decisions": len(decisions),
        "by_event": dict(sorted(Counter(str(e.get("event")) for e in events).items())),
        "runs": [{"run_id": run_id, "decisions": n} for run_id, n in _decision_runs(selection)],
        "undated": selection.undated, "runless": selection.runless,
        "skipped_lines": selection.skipped_lines, "log_overridden": selection.log_overridden,
    }
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-payload


# @cpt-begin:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-compose
def _digest_lines(
    window: core.ChangeWindow, selection: core.EventSelection, report: core.LinkReport,
) -> List[str]:
    """The lines a human reads, before the ceiling — each one backed by data.

    Two single-line digests are deliberate: no window means nothing to scope the other
    two dimensions to, so repeating one reason three times would be padding; and no
    changes means there is nothing to review, so the log is not consulted for a line.
    """
    if not window.available:
        return [_window_line(window)]
    if report.available and not report.changed:
        return [f"no changes against {window.base_ref}"]
    lines = [_window_line(window)] + _changes_lines(report)
    requirements = _requirements_line(_requirement_ids(report))
    if requirements:
        lines.append(requirements)
    return lines + _decision_lines(selection)


def compose_digest(root: Path, *, base: str = "", since: str = "") -> Dict[str, Any]:
    """Build the digest payload for ``root``: the lines, and the data behind them.

    Never raises — see :func:`cmd_change_summary` for the last-resort guard — and
    every dimension the core could not build arrives here as a stated reason.
    """
    root = Path(root).resolve()
    reason = _project_gate(root)
    if reason:
        return {"status": _STATUS, "reason": reason,
                "lines": [f"{reason}: nothing to summarise"], "omitted": 0}
    window = core.resolve_window(root, base=base, since=since)
    selection = core.select_events(window)
    report = core.link_changed_files(window)
    lines, omitted = _apply_ceiling(_digest_lines(window, selection, report))
    return {
        "status": _STATUS,
        "lines": lines,
        "omitted": omitted,
        "window": _window_payload(window),
        "changes": _changes_payload(report),
        "requirements": _requirement_ids(report),
        "decisions": _decisions_payload(selection),
    }
# @cpt-end:cpt-studio-algo-developer-experience-change-summary-digest:p1:inst-digest-compose


# @cpt-begin:cpt-studio-dod-developer-experience-change-summary:p1:inst-advisory-exit-zero
def _compose_safely(root: Path, *, base: str, since: str) -> Dict[str, Any]:
    """The last-resort guard that makes "advisory" true even against a defect the tests
    did not foresee: a stated reason and exit 0, never a traceback and exit 1.

    The core never raises by contract, so this should be unreachable — which is exactly
    why it exists. The exception's type is reported, not its text, which could carry a
    path.
    """
    try:
        return compose_digest(root, base=base, since=since)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("change-summary could not build the digest: %s", type(exc).__name__)
        reason = f"digest unavailable ({type(exc).__name__})"
        return {"status": _STATUS, "reason": reason,
                "lines": [f"{reason}; nothing to summarise"], "omitted": 0}
# @cpt-end:cpt-studio-dod-developer-experience-change-summary:p1:inst-advisory-exit-zero


# @cpt-begin:cpt-studio-flow-developer-experience-change-summary:p1:inst-change-summary-cmd
def cmd_change_summary(argv: List[str]) -> int:
    """Print an advisory digest of what changed on this branch, and why."""
    p = ui.JsonSafeArgumentParser(
        prog="cfs change-summary",
        description=(
            "Advisory digest of what changed on this branch, why, and which requirements "
            "the changes serve. At most ten lines; exits 0 on every path except a usage error."
        ),
        # The rules that shape the output live in source comments a user of --help never
        # reads, so a file that is excluded or a change set that is capped would look
        # like a bug. Said here, once, where the user actually looks.
        epilog=(
            "How the digest is built: the window runs from the merge-base with the canonical "
            "remote's default branch (--base or --since override it). Changed files are "
            "listed from git against the working tree, untracked files included; a file "
            "is included or excluded by the project's own scope policy (the same one "
            f"`cfs validate` uses), and at most {core.MAX_CHANGED_ENTRIES:,} entries are "
            "examined, the rest counted and stated. Requirement links are the @cpt markers "
            "a file references or declares, read in both directions rather than guessed "
            "from its suffix. \"Why\" is the decisions recorded in the project's local "
            f"decision log inside the window. The digest never exceeds {LINE_CEILING} "
            "lines; when it would, the last line says how many were cut and --json carries "
            "everything. Nothing is written, posted, or sent anywhere."
        ),
    )
    p.add_argument("--root", default=".", help="Project root (default: current directory)")
    p.add_argument("--base", default="",
                   help="Base ref the window is measured from (default: the canonical remote's default branch)")
    p.add_argument("--since", default="",
                   help="Explicit ISO-8601 lower bound for decisions; skips git entirely")
    args = ui.parse_args_or_json_error(p, argv)
    if args is None:
        return 2

    ui.result(_compose_safely(Path(args.root), base=args.base, since=args.since), human_fn=_human_digest)
    return 0
# @cpt-end:cpt-studio-flow-developer-experience-change-summary:p1:inst-change-summary-cmd


# @cpt-begin:cpt-studio-flow-developer-experience-change-summary:p1:inst-change-summary-cmd-format
def _human_digest(data: Dict[str, Any]) -> None:
    """The digest is the output: its lines and nothing else, so it pastes cleanly."""
    for line in data["lines"]:
        ui.info(line)
# @cpt-end:cpt-studio-flow-developer-experience-change-summary:p1:inst-change-summary-cmd-format
