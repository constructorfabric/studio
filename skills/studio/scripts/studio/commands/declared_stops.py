"""Fail the build when a workflow starts stopping the user more often than it did.

The story this belongs to reduces how often Studio interrupts you. A number that only ever
gets reported can drift back up one pull request at a time, each rise too small to argue
with, so the count is a **gate** rather than a report: the walk runs per pull request and
the build goes red on any increase.

**Per workflow, never the total.** A total hides the case that actually matters -- one
workflow gaining four stops while another loses five reads as an improvement of one, and
the workflow someone has just made worse is invisible. The baseline is therefore a map,
and the comparison is per key.

**A fall is not automatic.** When a workflow legitimately loses stops the baseline is
updated in the same commit, by hand, so the new number is reviewed by whoever reduced it.
Auto-updating on a fall would mean an accidental reduction -- a workflow that stopped
loading half its modules, say -- silently becomes the new normal.

**A new workflow fails until it is recorded.** A workflow the tree has and the baseline
does not is not a free pass. Without this, an inflation renamed onto a fresh path arrives
as a brand-new workflow -- the old name gone, the new one unrecorded -- and sails straight
through a per-key compare. So an unrecorded workflow fails the gate the same way a rise
does, cleared by reviewing its number and re-recording in the same commit. The one
direction left open is a workflow that *vanishes*: a deletion only ever lowers the count,
so it is reported for re-recording rather than failed.

**A floor is a fault, not a pass.** If the walk could not read a file, or a `LOAD` target
is missing from the tree, every count is a lower bound. A real rise that a skipped file
happened to hide would then read as no change -- the exact silent pass this gate exists to
stop -- so a floor exits as a **fault (1, ERROR)**, distinct from a **check failure (2, FAIL)**,
the gate reporting it could not run rather than certifying a surface it only half-measured.
Those codes follow the project's CLI contract (`architecture/specs/cli.md`), where 1 is a
runtime/filesystem error and 2 is a check that failed -- so CI keying on 2 for a regression is
never confused by a gate that could not run.

**What it still cannot see is a reshuffle inside one workflow that nets to zero** -- a stop
moved from one branch to another, or one added while another is removed in the same file.
The count is per workflow, not per site, so a same-total change reads as no change. This is
a floor against the count drifting up, not a diff of where every stop lives.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..utils import gate_surface, ui
from ..utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

#: Where the recorded counts live, relative to the project root.
BASELINE = Path("architecture/baselines/declared-stops.json")

#: The one key inside it. Named rather than positional so the file can grow a second
#: measurement later without the reader guessing which list it is looking at.
DECLARED_STOPS = "declared_stops"


# @cpt-begin:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-read
def _reject_duplicate_keys(pairs: List[Tuple[str, object]]) -> Dict[str, object]:
    """A ``json.loads`` object hook that refuses a duplicate key instead of last-key-wins.

    A baseline recording ``workflows/w.md`` twice would otherwise keep only the last value and
    silently drop the other -- a workflow's recorded count vanishing, the exact quiet
    under-record this gate exists to catch. Raising here turns it into a named fault instead.
    """
    seen: Dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"{key!r} is recorded more than once")
        seen[key] = value
    return seen


def _read_baseline(path: Path) -> Tuple[Optional[Dict[str, int]], str]:
    """``(the recorded counts, why they could not be read)``.

    Every failure is its own sentence rather than a shared "could not read the baseline":
    a missing file is a setup problem, a non-UTF-8 or malformed one is a corrupted commit, a
    duplicate key is a merge slip, and a count that is not a whole number is a hand edit that
    went wrong. An operator fixes them differently, and the gate is only useful if it says which
    it hit.
    """
    try:
        # --baseline is a developer/CI path in a local dev-only CLI gate; no untrusted input.
        raw = path.read_text(encoding="utf-8")  # NOSONAR
    except (OSError, UnicodeDecodeError) as exc:
        # One handler, two sentences, one return: a missing/permission file is a setup problem;
        # non-UTF-8 bytes are a corrupted baseline. UnicodeDecodeError is a ValueError, not an
        # OSError, so without it here an invalid-encoding file crashed instead of reporting.
        if isinstance(exc, UnicodeDecodeError):
            why = (f"{path} is not valid UTF-8 text, so it is a corrupted baseline rather "
                   "than a hand edit -- re-record it with --update")
        else:
            why = (f"{path} could not be read ({exc.strerror or type(exc).__name__}), "
                   "so there is nothing to compare against")
        return None, why
    try:
        data = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        return None, f"{path} is not valid JSON: {exc.msg} at line {exc.lineno}"
    except ValueError as exc:
        # The duplicate-key hook raises a plain ValueError, which is not a JSONDecodeError.
        return None, f"{path} records a workflow more than once: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get(DECLARED_STOPS), dict):
        return None, (f"{path} carries no {DECLARED_STOPS!r} object, so it is not a "
                      "declared-stop baseline")
    counts = data[DECLARED_STOPS]
    # `bool` is an `int` in Python, and `true` in JSON would otherwise read as 1.
    bad = sorted(name for name, value in counts.items()
                 if not isinstance(value, int) or isinstance(value, bool) or value < 0)
    if bad:
        return None, (f"{path} records a count that is not a whole number for: "
                      f"{', '.join(bad[:5])}")
    return {str(name): int(value) for name, value in counts.items()}, ""
# @cpt-end:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-read


# @cpt-begin:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-compare
def _compare(measured: Dict[str, int],
             recorded: Dict[str, int]) -> Dict[str, List[Tuple[str, int, int]]]:
    """What changed, in the three ways it can change, each reported separately.

    ``risen`` and ``added`` both fail the build (the decision is in ``_payload``). ``fallen``
    does not, and is listed so the author knows the baseline needs updating in this commit.
    ``gone`` is a workflow the baseline names and the tree no longer has -- reported rather
    than ignored, because a workflow deleted by accident removes its stops and looks exactly
    like progress, but not failed, because a deletion can only lower the count.

    ``added`` is a workflow the tree has and the baseline does not. There is nothing to
    compare it against, so it is scored against an implicit zero and left for ``_payload`` to
    fail: an unrecorded workflow is the gap a renamed-and-inflated file slips through, so it
    cannot pass until its number has been reviewed and recorded.
    """
    risen: List[Tuple[str, int, int]] = []
    fallen: List[Tuple[str, int, int]] = []
    added: List[Tuple[str, int, int]] = []
    for workflow in sorted(measured):
        now = measured[workflow]
        before = recorded.get(workflow)
        if before is None:
            added.append((workflow, 0, now))
        elif now > before:
            risen.append((workflow, before, now))
        elif now < before:
            fallen.append((workflow, before, now))
    gone = [(workflow, recorded[workflow], 0)
            for workflow in sorted(set(recorded) - set(measured))]
    return {"risen": risen, "fallen": fallen, "added": added, "gone": gone}
# @cpt-end:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-compare


# @cpt-begin:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-report
def _say(payload: Dict[str, object]) -> None:
    """The whole outcome, in the order an author needs it.

    The failure comes first and names the workflow, both numbers and the difference,
    because "declared stops rose" sends someone to read a diff where "plan.md 9 -> 11 (+2)"
    sends them to a file. Everything else follows, so a passing run still says what moved.

    Rendered from the same payload the JSON carries rather than built beside it: a human
    summary assembled separately is how the two drift until they disagree about whether a
    run passed.
    """
    labels = (("risen", "ROSE    "), ("fallen", "fell    "),
              ("added", "new     "), ("gone", "gone    "))
    for key, label in labels:
        for row in payload[key]:                       # type: ignore[union-attr]
            workflow, before, now = row["workflow"], row["before"], row["now"]
            if key == "added":
                ui.substep(f"  {label} {workflow}: {now}")
            elif key == "gone":
                ui.substep(f"  {label} {workflow}: was {before}")
            else:
                ui.substep(f"  {label} {workflow}: {before} -> {now} ({now - before:+d})")
    ui.substep(f"  total declared stops: {payload['total_declared_stops']}")
    if payload["status"] == "FAIL":
        reasons: List[str] = []
        if payload["risen"]:
            reasons.append(f"{len(payload['risen'])} workflow(s) now stop the user more "
                           "often than the recorded baseline")
        if payload["added"]:
            reasons.append(f"{len(payload['added'])} workflow(s) are not in the baseline at "
                           "all, and an unrecorded workflow cannot pass -- a renamed file is "
                           "how an inflation would otherwise arrive as new and sail through")
        ui.error("declared stops: " + "; ".join(reasons) + ". If that is intended, say why "
                 "in the commit and re-record with --update.")
    elif payload["needs_recording"]:
        ui.hint("declared stops: no rise. Re-record with --update so the baseline matches.")


# @cpt-end:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-report


# @cpt-begin:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-shape
def _payload(changes: Dict[str, List[Tuple[str, int, int]]], total: int) -> Dict[str, object]:
    """One shape, emitted on every outcome.

    Every key is present on every path -- `risen` is an empty list on a pass rather than
    absent -- so a caller keying on it never has to ask which outcome it is holding.

    A rise **or** an unrecorded workflow fails: `added` is a regression here, not a note,
    because an inflation renamed onto a fresh path arrives as `added` and nothing else would
    catch it. `fallen` and `gone` only need re-recording, so they set `needs_recording`
    without failing.
    """
    rows = {key: [{"workflow": w, "before": b, "now": n} for w, b, n in changes[key]]
            for key in ("risen", "fallen", "added", "gone")}
    regressed = bool(rows["risen"] or rows["added"])
    moved = any(rows[key] for key in ("fallen", "gone"))
    return {"status": "FAIL" if regressed else "PASS",
            "total_declared_stops": total,
            "needs_recording": regressed or moved,
            **rows}
# @cpt-end:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-shape


# @cpt-begin:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-command
def _parser() -> ui.JsonSafeArgumentParser:
    """The gate's arguments. ``--update`` is the only way the baseline ever changes.

    A ``JsonSafeArgumentParser`` rather than a plain one so a bad argument under ``--json``
    still emits a structured ERROR object on stdout, the way every other JSON-aware command
    does, instead of argparse's plain-text usage banner and a bare process exit.
    """
    parser = ui.JsonSafeArgumentParser(
        prog="cfs declared-stops",
        description="Fail when a workflow stops the user more often than its recorded baseline. "
                    "The count is a static reachability walk of workflows/ and skills/, not a "
                    "trace of one run -- an upper bound on how often a workflow can stop.")
    parser.add_argument("--root", default=".",
                        help="the tree to walk (default: the current directory)")
    parser.add_argument("--baseline", default=None,
                        help=f"the recorded counts (default: {BASELINE} under --root)")
    parser.add_argument("--update", action="store_true",
                        help="rewrite the baseline from what was measured, after review")
    return parser


def _floor(surface: gate_surface.GateSurface) -> str:
    """Why the measured counts are a floor rather than a count, or ``""`` if they are a count.

    ``unreadable`` and ``missing_loads`` each mean the walk skipped something -- a file it
    could not open, or a `LOAD` whose target the tree does not provide. Every per-workflow
    number is then a lower bound, and a real rise a skipped file happened to hide reads as no
    change: the exact silent pass this gate exists to stop. So a floor is a **fault**, not a
    pass -- returned to the caller as such rather than compared.

    ``duplicate_menu_definitions`` is deliberately not a floor: a name defined twice does not
    lower any stop count, so folding it in would fail the build on a cosmetic clash.
    """
    if surface.unreadable:
        return (f"{len(surface.unreadable)} file(s) could not be read, so the count is a "
                "floor and a hidden rise would read as no change: "
                f"{', '.join(surface.unreadable[:5])}")
    if surface.missing_loads:
        return (f"{len(surface.missing_loads)} LOAD target(s) are missing from the tree, so "
                "a workflow was read short and the count is a floor: "
                f"{', '.join(surface.missing_loads[:5])}")
    return ""


def _fault(message: str) -> int:
    """Emit the standard ERROR result and return the ERROR exit code (1).

    A **fault** is a runtime or filesystem problem -- the walk failing, an unreadable or
    malformed baseline, a floor surface -- as opposed to a **check** failing. Per this project's
    CLI exit-code contract (`architecture/specs/cli.md`) a fault exits **1** (ERROR), distinct
    from **2** (a check FAILED), so CI keying on 2 for a regression is not confused by a gate
    that could not run. It goes through `ui.result` rather than `ui.error` so a `--json` caller
    gets a JSON object -- `ui.error` is a no-op in JSON mode and would leave stdout empty.
    """
    ui.result({"status": "ERROR", "message": message},
              human_fn=lambda d: ui.error(f"declared stops: {d['message']}"))
    return 1


def _do_update(baseline: Path, measured: Dict[str, int], total: int) -> int:
    """Rewrite the baseline from what was measured, atomically, and report what it dropped.

    ``atomic_write_text`` (temp file + ``os.replace``) so a shared baseline is never left half
    written if the process dies mid-write, and a write that fails -- a read-only mount, a full
    disk -- is turned into a clean fault (1) rather than an unhandled traceback, like every
    other error path here. The old baseline is read best-effort only to name the workflows it
    records that the tree no longer has: ``--update`` writes the current truth either way, but a
    workflow silently vanishing from the baseline is the quiet under-record the gate exists to
    surface, so it is named rather than dropped in silence.
    """
    recorded, _why = _read_baseline(baseline)
    dropped = sorted(set(recorded) - set(measured)) if recorded else []
    try:
        # --baseline is a developer/CI path in a local dev-only CLI gate; no untrusted input.
        atomic_write_text(baseline,  # NOSONAR
                          json.dumps({DECLARED_STOPS: dict(sorted(measured.items()))},
                                     indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        logger.exception("declared stops: the baseline write failed: %s", type(exc).__name__)
        return _fault(f"{baseline} could not be written ({exc.strerror or type(exc).__name__})")
    ui.result({"status": "OK", "recorded": len(measured), "total_declared_stops": total,
               "baseline": str(baseline), "dropped": dropped},
              human_fn=lambda d: ui.success(
                  f"declared stops: recorded {d['recorded']} workflows, "
                  f"{d['total_declared_stops']} stops, in {d['baseline']}"
                  + (f"; dropped {len(d['dropped'])} no longer in the tree: "
                     f"{', '.join(d['dropped'][:5])}" if d["dropped"] else "")))
    return 0


def cmd_declared_stops(argv: List[str]) -> int:
    """Walk the tree, compare against the baseline, and fail on any rise or unrecorded workflow.

    Exit codes follow the project contract (`architecture/specs/cli.md`): **0** pass, **2** a
    check FAILED (a workflow rose, or one the baseline has never recorded), **1** a fault -- a
    tree or baseline that could not be read, or a walk that came back a floor (a skipped file or
    a missing `LOAD`), which would let a hidden rise read as no change. A bad argument also exits
    2, via the JSON-safe parser. Every path emits a JSON object on stdout under `--json`.
    """
    args = ui.parse_args_or_json_error(_parser(), argv)
    if args is None:
        return 2
    root = Path(args.root)
    # An unspecified --baseline resolves under --root, so pointing the gate at another tree
    # compares against that tree's baseline rather than the current directory's.
    baseline = Path(args.baseline) if args.baseline else root / BASELINE
    try:
        surface = gate_surface.walk(root)
    except (FileNotFoundError, RuntimeError) as exc:
        # Logged as well as shown. The message a person reads names the tree; the log keeps the
        # traceback, which is what tells a misconfigured root apart from a cycle guard that
        # stopped holding. `exception`, not `error`, so the stack is captured inside the handler.
        logger.exception("declared stops: the walk failed: %s", type(exc).__name__)
        return _fault(str(exc))
    # A floor fails before either path -- compare or --update. Comparing a floor lets a hidden
    # rise read as no change; recording one writes an under-count as the new baseline, which
    # every later run is then measured against.
    floor = _floor(surface)
    if floor:
        logger.error("declared stops: the surface is a floor, not a count: %s", floor)
        return _fault(floor)
    measured = {w.workflow: w.stop_sites for w in surface.workflows}
    total = sum(measured.values())

    if args.update:
        return _do_update(baseline, measured, total)

    recorded, why = _read_baseline(baseline)
    if recorded is None:
        return _fault(why)
    payload = _payload(_compare(measured, recorded), total)
    ui.result(payload, human_fn=_say)
    return 2 if payload["status"] == "FAIL" else 0
# @cpt-end:cpt-studio-algo-developer-experience-declared-stop-gate:p1:inst-stops-command
