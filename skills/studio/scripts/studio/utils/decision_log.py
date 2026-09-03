"""Local decision/outcome log — a private JSONL record of what the engine decided.

This is **not** the proxy's ``telemetry.py`` (which records a command name plus git
identity and sends them to a remote endpoint). This module is deliberately the
opposite on every axis that matters:

  * **Local only.** It writes one JSONL file inside the project's studio ``.cache/``
    directory. There is no network code here and no new remote surface.
  * **Never fatal.** Every failure path degrades to "no line written" and returns
    normally. Instrumentation must never change what a command does or its exit code.
  * **Opt-out honoured.** Disabled by an environment variable or a persistent
    sentinel file (see :func:`is_enabled`).
  * **No project, no log.** Outside a Constructor Studio project there is nowhere to
    write, so the writer is a clean no-op rather than an error.
  * **Decisions, not content.** It records *what was decided* (intent, tier, verdict),
    never artifact or source text, and collapses ``$HOME`` to ``~`` so a log is safe to
    paste into a bug report.
  * **stdlib only.**

Schema — one JSON object per line, newline-terminated::

    {
      "schema":      1,                                  # bump on incompatible change
      "ts":          "2026-08-12T09:34:12.123456+00:00", # UTC, ISO-8601
      "run_id":      "9b7953324c12",                     # one CLI invocation
      "decision_id": "1f2e3d4c5b6a7182",                 # chains the events of one decision
      "event":       "validation",                       # see EVENTS
      "command":     "validate",                         # command name, never raw argv
      "payload":     {...}                               # event-specific; keys optional
    }

Readers must ignore unknown event names and unknown payload keys so that newer
instrumentation never breaks an older reader.

@cpt-algo:cpt-studio-algo-core-infra-decision-log:p1
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

#: Event names this module writes. Readers must tolerate others.
EVENTS = ("routing", "dispatch", "validation", "review", "escalation", "invocation", "read")

#: Environment overrides.
_ENV_PATH = "CFS_DECISION_LOG"          # explicit path, or an off-value to disable
_OFF_VALUES = {"0", "off", "no", "none", "false", "disabled"}

_BRAND_DIR = ".cf-studio"               # per-user home dir for the opt-out sentinel
_OPT_OUT_SENTINEL = "decisions.off"
_CACHE_SUBDIR = ".cache"
_LOG_NAME = "decisions.jsonl"

#: Rotate once the log passes this size, keeping a single ``.1`` backup.
_MAX_BYTES = 5 * 1024 * 1024

#: Fixed for the life of the process, so every event of one invocation shares it.
_RUN_ID = uuid.uuid4().hex[:12]

#: Correlation id for the current context. The dispatcher sets this once per run so
#: events recorded deep inside a command (e.g. validation) share the run's decision.
_CURRENT_DECISION_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "cfs_current_decision_id", default="")

#: Guards the one-time transparency notice.
_NOTICE_SHOWN = False

#: Guards the one-time "could not write the log" warning (fail-open, not fail-silent).
_FAILURE_WARNED = False


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-id
def new_decision_id() -> str:
    """Return a fresh id used to chain the events (routing → dispatch → …) of one decision."""
    return uuid.uuid4().hex[:16]


def set_current_decision_id(decision_id: str) -> None:
    """Set the correlation id for the current context.

    Later ``record()`` calls that pass no explicit ``decision_id`` inherit this one,
    so events emitted deep inside a command chain to the same decision as the run.
    """
    _CURRENT_DECISION_ID.set(decision_id)
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-id


# ---------------------------------------------------------------------------
# Location and opt-out
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-locate
def _brand_dir() -> Path:
    return Path.home() / _BRAND_DIR


def opt_out_sentinel_path() -> Path:
    """Return the path whose existence disables logging permanently for this user."""
    return _brand_dir() / _OPT_OUT_SENTINEL


def override_log_path() -> Optional[Path]:
    """Return the log named by ``$CFS_DECISION_LOG``, or ``None`` when unset or an off-value.

    The override is process-wide: the writer honours it in every project the process
    runs in, so a reader that wants to read what the writer wrote must honour it too —
    and may want to know that it did, since one shared log cannot be attributed to any
    single project.
    """
    override = os.environ.get(_ENV_PATH, "").strip()
    if override and override.lower() not in _OFF_VALUES:
        return Path(override).expanduser()
    return None


def default_log_path(start: Optional[Path] = None) -> Optional[Path]:
    """Resolve the log location, or ``None`` when there is nowhere to write.

    Order:
      1. ``$CFS_DECISION_LOG`` if it names a path (an off-value there disables logging).
      2. ``<studio-dir>/.cache/decisions.jsonl`` for the project containing ``start``.
      3. ``None`` — outside a project, so the writer no-ops.

    ``start`` defaults to the cwd, which is right for the writer: it logs whatever
    project the command is running in. A *reader* working against an explicitly named
    project must pass that root, or it can resolve a different project's log than the
    one it is reporting on. The override wins over ``start`` deliberately — see
    :func:`override_log_path`.
    """
    override = override_log_path()
    if override is not None:
        return override

    try:
        from .files import find_studio_directory
        studio_dir = find_studio_directory(start or Path.cwd())
    except Exception:  # pylint: disable=broad-except
        studio_dir = None
    if studio_dir is None:
        return None
    return studio_dir / _CACHE_SUBDIR / _LOG_NAME
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-locate


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-enabled
def is_enabled() -> bool:
    """Report whether decision logging is active.

    Disabled by any of: ``$CFS_DECISION_LOG`` set to an off-value; the sentinel file
    ``~/.cf-studio/decisions.off`` existing. The sentinel lets an opt-out survive a new
    shell without remembering an environment variable.
    """
    raw = os.environ.get(_ENV_PATH)
    if raw is not None and raw.strip().lower() in _OFF_VALUES:
        return False
    try:
        if opt_out_sentinel_path().exists():
            return False
    except OSError as exc:
        # An unreadable home directory is not a reason to fail a command.
        logger.debug("decision log opt-out check skipped: %s", exc)
        return False
    return True
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-enabled


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-redact
def _redact(value: Any) -> Any:
    """Collapse absolute paths under ``$HOME`` to ``~/…`` form, recursively.

    The log records decisions, never artifact or source content. Removing the home
    prefix keeps a username out of a file a user may paste into a bug report.
    """
    if isinstance(value, str):
        try:
            home = str(Path.home()).rstrip(os.sep)
        except (OSError, RuntimeError):
            return value
        if not home:
            return value
        # Substitute $HOME only at a path boundary (separator or end-of-string), so a
        # sibling like ``/Users/maxine`` is never mangled into ``~ine`` for home ``/Users/max``.
        return re.sub(re.escape(home) + r"(?=" + re.escape(os.sep) + r"|$)", "~", value)
    if isinstance(value, dict):
        return {_redact(k): _redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-redact


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-record
def _show_notice_once(path: Path) -> None:
    """Tell the user once, on stderr, that a local log was started."""
    global _NOTICE_SHOWN  # pylint: disable=global-statement
    if _NOTICE_SHOWN:
        return
    _NOTICE_SHOWN = True
    logger.warning(
        "Constructor Studio is recording its decisions to a local log:\n"
        "  %s\n"
        "  Nothing is sent anywhere. Turn it off with %s=off, or permanently: touch %s",
        _redact(str(path)), _ENV_PATH, _redact(str(opt_out_sentinel_path())),
    )


def _rotate_if_large(path: Path) -> None:
    """Keep a single ``.1`` backup once the log passes ``_MAX_BYTES``. Best-effort."""
    try:
        if path.exists() and path.stat().st_size >= _MAX_BYTES:
            backup = path.with_name(path.name + ".1")
            os.replace(path, backup)
    except OSError as exc:
        # Rotation is a convenience; failing it must not stop a write attempt.
        logger.debug("decision log rotation skipped: %s", exc)


def _append_locked(target: Path, line: str) -> None:
    """Append one line, serialising rotation + write across processes where possible.

    Two concurrent invocations can both observe an oversized log; without a lock, one
    could rotate the file the other is mid-write on, dropping events. Where ``fcntl`` is
    available (POSIX) an exclusive advisory lock on a sibling ``.lock`` file serialises
    the rotate-then-append; elsewhere it degrades to a best-effort unlocked append.
    """
    try:
        import fcntl  # pylint: disable=import-outside-toplevel
    except ImportError:
        fcntl = None
    if fcntl is None:
        _rotate_if_large(target)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return
    with open(target.with_name(target.name + ".lock"), "a", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        _rotate_if_large(target)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        # The exclusive lock is released when lock_fh closes.


def record(
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    command: str = "",
    decision_id: str = "",
    path: Optional[Path] = None,
) -> bool:
    """Append one event to the decision log.

    Returns ``True`` when a line was written, ``False`` otherwise (disabled, no project,
    or an unwritable/unserialisable record). **Never raises** — callers are
    instrumentation, so a failure here must not change what the command does.
    """
    global _FAILURE_WARNED  # pylint: disable=global-statement
    try:
        if not is_enabled():
            return False
        if _FAILURE_WARNED:
            # A prior write failed and we already warned: telemetry is genuinely off for
            # the rest of this run. Don't keep retrying a target we know is unwritable.
            return False
        target = path or default_log_path()
        if target is None:
            return False
        is_new = not target.exists()
        record_obj = {
            "schema": SCHEMA_VERSION,
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": _RUN_ID,
            "decision_id": decision_id or _CURRENT_DECISION_ID.get(),
            "event": event,
            "command": _redact(command),
            "payload": _redact(payload or {}),
        }
        line = json.dumps(record_obj, ensure_ascii=False, default=str)
        target.parent.mkdir(parents=True, exist_ok=True)
        _append_locked(target, line)
        if is_new:
            _show_notice_once(target)
        return True
    except Exception as exc:  # pylint: disable=broad-except
        # A real write/serialization failure (disabled, no-project and already-warned
        # cases return early above and never reach here, so this only fires on the first
        # failure). Surface it once — fail-open, not fail-silent — and latch telemetry off
        # for the run via _FAILURE_WARNED. Redact the exception: an OSError carries the
        # absolute log path ($HOME included).
        _FAILURE_WARNED = True
        logger.warning(
            "Constructor Studio could not write its decision log; "
            "telemetry is off for this run: %s", _redact(str(exc)))
        return False
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-record


# Thin wrappers so call sites read as intent, and a schema change lands in one place.

# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-api
def record_routing(intent: str, candidates: List[str], selected: str,
                    reason: str = "", *, command: str = "", decision_id: str = "",
                    path: Optional[Path] = None) -> bool:
    """Log which candidate a routing decision chose, and why."""
    return record("routing", {
        "intent": intent, "candidates": list(candidates),
        "selected": selected, "reason": reason,
    }, command=command, decision_id=decision_id, path=path)


def record_dispatch(agent: str, tier: str = "", model: str = "", provider: str = "",
                    target: str = "", *, command: str = "", decision_id: str = "",
                    path: Optional[Path] = None) -> bool:
    """Log the tier and concrete model a dispatch resolved to."""
    return record("dispatch", {
        "agent": agent, "tier": tier, "model": model,
        "provider": provider, "target": target,
    }, command=command, decision_id=decision_id, path=path)


def record_validation(check: str, status: str, findings: int = 0,
                      rules: Optional[Dict[str, int]] = None, *,
                      command: str = "", decision_id: str = "",
                    path: Optional[Path] = None) -> bool:
    """Log a validator verdict and its finding counts."""
    return record("validation", {
        "check": check, "status": status,
        "findings": findings, "rules": dict(rules or {}),
    }, command=command, decision_id=decision_id, path=path)


def record_review(subject: str, decision: str, actor: str = "human", *,
                  command: str = "", decision_id: str = "",
                    path: Optional[Path] = None) -> bool:
    """Log a human accept/reject on generated output."""
    return record("review", {
        "subject": subject, "decision": decision, "actor": actor,
    }, command=command, decision_id=decision_id, path=path)


def record_escalation(from_tier: str, to_tier: str, reason: str = "", *,
                      command: str = "", decision_id: str = "",
                    path: Optional[Path] = None) -> bool:
    """Log a move to a more capable/expensive tier."""
    return record("escalation", {
        "from_tier": from_tier, "to_tier": to_tier, "reason": reason,
    }, command=command, decision_id=decision_id, path=path)


def record_invocation(command: str, exit_code: int = 0, duration_ms: int = 0,
                      args_shape: Optional[Dict[str, Any]] = None, *,
                      decision_id: str = "", path: Optional[Path] = None) -> bool:
    """Log a command invocation: exit code, duration, and an argument *shape* summary.

    ``args_shape`` is a pre-summarised description of the arguments (counts / kinds),
    never the raw argv — some commands take paths or user data.
    """
    return record("invocation", {
        "exit_code": exit_code, "duration_ms": duration_ms,
        "args": dict(args_shape or {}),
    }, command=command, decision_id=decision_id, path=path)


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-read-wrapper
def record_read(method: str, target: str, lines: int, tokens: int, source: str = "", *,
                command: str = "", decision_id: str = "",
                path: Optional[Path] = None) -> bool:
    """Log one read-and-answer event: which retrieval method fired, and its
    real cost, in the one shared schema every method's cost is measured in.
    """
    return record("read", {
        "method": method, "target": _redact(target),
        "lines": lines, "tokens": tokens, "source": source,
    }, command=command, decision_id=decision_id, path=path)
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-read-wrapper
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-api


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-read
def parse_events(lines: Iterable[str]) -> Iterator[Dict[str, Any]]:
    """Yield the event objects among ``lines``, skipping any line that will not parse.

    The parsing rules of :func:`read_events`, on their own. A reader that has taken its
    own snapshot of the file — to count lines and select events from the *same* bytes,
    so nothing appended between two reads can be mistaken for corruption — parses that
    snapshot the way this module does, rather than growing a second copy of the rules.
    """
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError) as exc:
            logger.debug("decision log: skipping unparseable line: %s", exc)
            continue
        if not isinstance(obj, dict):
            continue
        yield obj


def read_events(path: Optional[Path] = None, *, event: str = "",
                run_id: str = "", decision_id: str = "",
                limit: int = 0) -> Iterator[Dict[str, Any]]:
    """Yield events oldest-first, skipping any line that will not parse.

    A truncated or hand-edited log stays readable: a bad line is dropped, not raised,
    because a partially corrupt log is still evidence.
    """
    target = path or default_log_path()
    if target is None:
        return
    try:
        if not target.is_file():
            return
        with target.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError as exc:
        logger.debug("decision log unreadable: %s", exc)
        return

    matched: List[Dict[str, Any]] = []
    for obj in parse_events(lines):
        if event and obj.get("event") != event:
            continue
        if run_id and obj.get("run_id") != run_id:
            continue
        if decision_id and obj.get("decision_id") != decision_id:
            continue
        matched.append(obj)

    if limit > 0:
        matched = matched[-limit:]
    yield from matched


def summarize(path: Optional[Path] = None) -> Dict[str, Any]:
    """Count events by type and by run — a small read view over the log."""
    counts: Dict[str, int] = {}
    runs: Dict[str, int] = {}
    total = 0
    first_ts = ""
    last_ts = ""
    for obj in read_events(path):
        total += 1
        name = str(obj.get("event", "?"))
        counts[name] = counts.get(name, 0) + 1
        run = str(obj.get("run_id", "?"))
        runs[run] = runs.get(run, 0) + 1
        ts = str(obj.get("ts", ""))
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
    target = path or default_log_path()
    return {
        "path": _redact(str(target)) if target else None,
        "exists": bool(target and target.is_file()),
        "enabled": is_enabled(),
        "schema": SCHEMA_VERSION,
        "total_events": total,
        "event_counts": counts,
        "runs": len(runs),
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-summarize-reads
def summarize_reads(path: Optional[Path] = None) -> Dict[str, Any]:
    """Aggregate logged ``"read"`` events into a per-method token table.

    Returns ``{"methods": {method: {"count", "total_tokens", "total_lines"}},
    "total_tokens": int}`` -- the per-method cost comparison a caller needs
    to see which retrieval method is actually earning its keep on a real
    document, not just how many events were logged.

    A record whose ``payload`` isn't a dict, or whose ``tokens``/``lines``
    values aren't numeric, is skipped rather than raising -- the same
    "a partially corrupt log is still evidence" tolerance
    :func:`read_events` already applies to unparseable lines, extended to a
    parseable line with a malformed payload shape.
    """
    methods: Dict[str, Dict[str, int]] = {}
    total_tokens = 0
    for obj in read_events(path, event="read"):
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        try:
            tokens = int(payload.get("tokens", 0) or 0)
            lines = int(payload.get("lines", 0) or 0)
        except (TypeError, ValueError) as exc:
            logger.debug("decision log: skipping read event with non-numeric tokens/lines: %s", exc)
            continue
        method = str(payload.get("method", "?"))
        entry = methods.setdefault(method, {"count": 0, "total_tokens": 0, "total_lines": 0})
        entry["count"] += 1
        entry["total_tokens"] += tokens
        entry["total_lines"] += lines
        total_tokens += tokens
    return {"methods": methods, "total_tokens": total_tokens}
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-summarize-reads
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-read
