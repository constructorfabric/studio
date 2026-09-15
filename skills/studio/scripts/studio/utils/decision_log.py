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
      "event":       "validation",                       # see EVENTS; "gate" carries
                                                         #   payload.kind, see GATE_KINDS
      "command":     "validate",                         # command name, never raw argv
      "payload":     {...}                               # event-specific; keys optional
    }

Readers must ignore unknown event names and unknown payload keys so that newer
instrumentation never breaks an older reader.

@cpt-algo:cpt-studio-algo-core-infra-decision-log:p1
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

#: Event names this module writes. Readers must tolerate others.
EVENTS = ("routing", "dispatch", "validation", "review", "escalation", "invocation",
          "read", "gate", "rotate")

#: Subtypes of a ``gate`` event, carried in ``payload.kind`` rather than in the event
#: name, so a reader filtering ``event == "gate"`` sees all of them.
GATE_KINDS = ("auto-proceeded", "plan-resolved", "exception-asked",
              "blocking-confirmed", "open-question")

#: Where a resolved answer came from. Enumerated because the frozen resolution
#: contract enumerates it, and because it is the discriminator between a plan entry
#: and a ledger entry -- free text would silently create a fifth bucket and make the
#: audit under-count.
GATE_PROVENANCE = ("plan", "ledger", "workflow-recommendation", "policy")

#: Outcome of looking the answer up. ``absent`` and ``ambiguous`` both mean the gate
#: asked instead of resolving; neither is a resolution.
GATE_STATUSES = ("resolved", "absent", "ambiguous")

#: What a field with no value renders as. The frozen contract requires an omitted
#: field to be *visible*: "a missing key and a key meaning 'not specified' must not
#: be distinguishable only by absence", so an empty default is not allowed to stand
#: in for one.
UNSPECIFIED = "unspecified"

#: Cap for author-controlled text in a gate record. **Every** string field here is
#: written by whatever resolved the gate, so all of them are capped, not just the
#: two free-text ones: leaving `gate`, `declared_type`, `resolution` and
#: `provenance` unbounded made this an audit-erasure primitive, because ~500 KB of
#: padding per event drives the 5 MiB rotation and a real `auto-proceeded` record
#: is unreachable after ten such events and gone after twenty. Truncation is
#: marked rather than silent.
#: This constant has a second consumer that is easy to miss: `_capped` is also how every
#: diagnostic message in this module renders a path or an exception, so lowering the cap
#: shortens those too. The two uses share a bound deliberately — both are
#: author-controlled text heading somewhere a reader trusts — but the coupling is stated
#: here so a change made for the record's sake is known to affect the messages as well.
_GATE_TEXT_CAP = 500

#: Environment overrides.
_ENV_PATH = "CFS_DECISION_LOG"          # explicit path, or an off-value to disable
_OFF_VALUES = {"0", "off", "no", "none", "false", "disabled"}

_BRAND_DIR = ".cf-studio"               # per-user home dir for the opt-out sentinel
_OPT_OUT_SENTINEL = "decisions.off"
_CACHE_SUBDIR = ".cache"
_LOG_NAME = "decisions.jsonl"

#: Rotate once the log passes this size, keeping a single ``.1`` backup.
_MAX_BYTES = 5 * 1024 * 1024

#: The largest a rotated segment can legitimately be: the rotation threshold plus one
#: event, since `_rotate_if_large` rotates *before* the append that crossed it. Anything
#: larger was not produced by this log, so fingerprinting it would spend a held lock on
#: a file that cannot be claimed anyway.
_MAX_SEGMENT_BYTES = _MAX_BYTES + 64 * 1024

#: The largest one serialised event may be, and the "one event" the line above assumes.
#: The writes are opened with ``newline="\n"`` so this arithmetic holds everywhere: in text
#: mode Windows translates ``\n`` to ``\r\n``, which makes every event one byte longer than
#: the bound assumes and puts a full-size event one byte past the segment bound. It also
#: keeps one log byte-identical across platforms, which a fingerprinted audit trail needs.
#: Rotation happens at the threshold, so the biggest segment this log can produce is one
#: byte under it plus one whole event and its newline: `(_MAX_BYTES - 1) + L + 1`. That
#: is within `_MAX_SEGMENT_BYTES` exactly when `L <= 64 KiB`, which is why the two
#: constants share a number — the bound below is not a second opinion about size, it is
#: this one restated for the reader.
_MAX_EVENT_BYTES = 64 * 1024

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
def logging_state() -> Optional[bool]:
    """``True`` on, ``False`` deliberately off, ``None`` when it cannot be told.

    ``is_enabled()`` keeps its boolean contract for existing callers and fails
    closed, which is right for a writer. A *reporter* needs the third state: an
    unreadable home directory is not a user's opt-out, and calling it one sends
    someone looking for a setting they never changed.
    """
    raw = os.environ.get(_ENV_PATH)
    if raw is not None and raw.strip().lower() in _OFF_VALUES:
        return False
    try:
        return not opt_out_sentinel_path().exists()
    except OSError as exc:
        logger.debug("decision log opt-out state undeterminable: %s", _describe(exc))
        return None


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
        logger.debug("decision log opt-out check skipped: %s", _describe(exc))
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

# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-event-bound
def _utf8_len(text: str) -> int:
    """The byte length the file will hold, measured so a lone surrogate cannot raise.

    ``surrogatepass`` rather than the strict codec the write uses. Author-controlled text
    arrives through ``surrogateescape``, so a raw byte becomes a lone surrogate; raising
    while measuring would reach `record`'s catch-all, which latches telemetry off for the
    whole run — turning one unmeasurable event into no trail at all. The write still
    refuses such a line, exactly as it did before this existed.
    """
    return len(text.encode("utf-8", "surrogatepass"))


def _json_key(key: Any) -> str:
    """A payload key named the way the record would have named it.

    `str()` is the obvious choice and the wrong one: `json.dumps` coerces mapping keys by
    its own rules, so `None` becomes `"null"` and `True` becomes `"true"` while `str()`
    gives `"None"` and `"True"`. The marker exists to tell an auditor what the event held,
    and a name that does not match what the log would have written fails at exactly that.

    Derived by running the same coercion rather than restating its table, so the two cannot
    disagree. Only key types `json.dumps` accepts reach here -- anything else fails the
    serialisation above before this is called.
    """
    return next(iter(json.loads(json.dumps({key: 0}))))


def _bounded_event(record_obj: Dict[str, Any]) -> str:
    """One event's JSON line, never longer than ``_MAX_EVENT_BYTES``.

    Here rather than at the call sites. Eight typed wrappers reach this module and only
    the gate path caps its fields -- through `_gate_payload`, not in `record_gate` itself
    -- which is precisely how an uncapped 70 KiB `source` field pushed a genuine segment
    past the reader's bound and had this log's own history refused as a substitution. A
    choke point every wrapper already passes through covers the seven that do not cap
    today and the ninth nobody has written yet.

    Eight and seven, counted rather than carried: the report that raised this listed six
    uncapped wrappers and omitted `record_dispatch`, and the count was repeated from it
    three times before anyone counted.

    On the serialised line, not per field: an event of many small fields still adds up,
    and it is the line that lands in the file.

    An event too large to record leaves a marker saying so. Dropping it silently would
    put a hole in the trail where a record used to be, which is the same defect one level
    down — the trail must say a record was cut, not go quiet.

    No warning, unlike every other place this module gives something up. Those warn
    because the trail itself cannot say what happened: a segment excluded from a read
    leaves no trace inside the log. Here it can and does, in the record's own place in
    the order, and a command that logs large payloads would otherwise warn on every
    event it writes.

    """
    line = json.dumps(record_obj, ensure_ascii=False, default=str)
    if _utf8_len(line) <= _MAX_EVENT_BYTES:
        return line
    # Keep what identifies the event and drop only what made it too big. A reader looking
    # for this decision still finds it, in its place in the order, saying what is missing.
    # Capped, not merely carried. `command`, `event` and `decision_id` are caller-supplied,
    # so a 200 KB `command` produced a 200 KB marker -- the bound broken by the record that
    # exists to report the bound being broken. The floor below covered `dropped_keys` only,
    # which is the reported field rather than the class of field (B10). `schema`, `ts` and
    # `run_id` are engine-generated and fixed-width.
    kept: Dict[str, Any] = {key: record_obj.get(key) for key in ("schema", "ts", "run_id")}
    kept.update({key: _capped(str(record_obj.get(key, "")))
                 for key in ("decision_id", "event", "command")})
    original_bytes = _utf8_len(line)
    kept["payload"] = {
        "truncated": True,
        "original_bytes": original_bytes,
        "dropped_keys": sorted(_capped(_json_key(key))
                               for key in (record_obj.get("payload") or {})),
    }
    marked = json.dumps(kept, ensure_ascii=False, default=str)
    if _utf8_len(marked) <= _MAX_EVENT_BYTES:
        return marked
    # The key names alone can exceed the bound, so the marker needs its own floor: a
    # record whose own explanation does not fit still has to fit.
    kept["payload"] = {"truncated": True,
                       "original_bytes": original_bytes,
                       "dropped_keys": "omitted: the key names alone exceed the bound"}
    return json.dumps(kept, ensure_ascii=False, default=str)


# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-event-bound



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
        _capped(str(path)), _ENV_PATH, _capped(str(opt_out_sentinel_path())),
    )


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-restrict-perms
def _restrict_to_owner(path: Path, mode: int) -> None:
    """Best-effort ``chmod`` so the log stays as private as this module says it is.

    The docstring at the top of this file calls the log private; nothing enforced that.
    ``mkdir`` and ``open`` take their permissions from the ambient umask, so the usual
    0o022 produced a 0o755 directory and a 0o644 log -- world-readable on any shared
    machine, for a file recording which commands ran against which paths.

    Applied at creation rather than on every append, and on POSIX only: ``chmod`` is a
    no-op for this purpose on Windows, where the ACL is what matters. Failure is
    ignored on purpose -- the same reasoning as everything else here, that telemetry
    must never be the thing that breaks a command.
    """
    if os.name != "posix":
        return
    try:
        os.chmod(path, mode)
    except OSError as exc:
        # `_redact` on the exception too, not only the path: an OSError renders as
        # "[Errno 13] Permission denied: '/home/<user>/...'", so passing it raw puts
        # back the $HOME this module strips everywhere else.
        logger.debug("decision log: could not restrict %s: %s",
                     _redact(str(path)), _redact(str(exc)))
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-restrict-perms


def _rotate_if_large(path: Path) -> None:
    """Keep a single ``.1`` backup once the log passes ``_MAX_BYTES``. Best-effort."""
    try:
        if path.exists() and path.stat().st_size >= _MAX_BYTES:
            backup = path.with_name(path.name + ".1")
            os.replace(path, backup)
            _write_rotation_link(path, backup)
    except OSError as exc:
        # Rotation is a convenience; failing it must not stop a write attempt.
        logger.debug("decision log rotation skipped: %s", _describe(exc))


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-rotation-link
#: Both halves of a segment fingerprint. A claim carrying one of them was written
#: by a rotation whose hash failed, and cannot be verified.
_IDENTITY_FIELDS = frozenset({"segment_bytes", "segment_sha256"})


def _claim_summary(identity: Dict[str, Any]) -> str:
    """One short rendering of a fingerprint, for a warning an operator has to act on.

    "does not match" alone cannot distinguish a truncated segment from a rewritten one
    from a wholly different file, and those want different responses. The digest is cut
    to twelve characters: enough to compare two lines by eye, far too little to be
    mistaken for the value itself.
    """
    if not identity:
        return "nothing readable"
    size = identity.get("segment_bytes", "?")
    digest = str(identity.get("segment_sha256", ""))[:12] or "no digest"
    return f"{size} bytes / {digest}"


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-segment-bytes
def _read_bounded(segment: Path, consequence: str) -> Optional[bytes]:
    """A segment's bytes, or ``None`` when it is larger than any this log rotates.

    The bound is enforced by the read, not by a prior ``stat()``. Those are two separate
    observations of one path and a replacement landing between them makes the first a
    lie, so a size check alone would let an arbitrarily large file be hashed while a
    lock is held — on the writer's side at rotation and on the reader's on the way in.
    One byte past the bound is enough to know.

    ``consequence`` names what the caller gives up when the bytes do not arrive. The
    two sides give up different things — the rotation falls back to a claim resting on
    the filename, the read excludes the segment outright — and a helper that asserted
    either one would be telling half its callers something untrue.

    The cheap ``stat()`` stays as a first filter: it avoids opening a file that is
    already known to be too large, at a small fraction of the read it saves. An earlier
    version of this sentence put figures on that ratio and both were wrong -- the numbers
    were never measured, so they are gone rather than restated.

    The whole segment is held at once rather than streamed. That is what makes the
    bound meaningful — the ceiling is the rotation threshold, ~5 MiB, so the peak is
    knowable and small — and the verifying caller needs the bytes in hand anyway, since
    fingerprinting a file and then reopening it leaves the window this exists to close.
    """
    try:
        if segment.stat().st_size > _MAX_SEGMENT_BYTES:
            logger.warning(
                "decision log: %s is larger than any segment this log rotates, %s",
                _capped(str(segment)), consequence)
            return None
        with segment.open("rb") as handle:
            data = handle.read(_MAX_SEGMENT_BYTES + 1)
    except OSError as exc:
        logger.warning("decision log: the rotated segment %s could not be read, %s: %s",
                       _capped(str(segment)), consequence, _describe(exc))
        return None
    if len(data) > _MAX_SEGMENT_BYTES:
        logger.warning(
            "decision log: %s grew past the segment bound while being read, %s",
            _capped(str(segment)), consequence)
        return None
    return data


# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-segment-bytes


def _identity_of(data: bytes) -> Dict[str, Any]:
    """The fingerprint of bytes already read, so nothing can change between the two.

    Validation used to open the segment, fingerprint it, close it, and then the read
    reopened it by path — a window in which a replacement is consumed silently, and one
    the advisory lock does not close, since `flock` serialises this module's own callers
    and not an external `mv`. Fingerprinting the bytes that will actually be used
    removes the window rather than narrowing it.
    """
    return {"segment_bytes": len(data), "segment_sha256": hashlib.sha256(data).hexdigest()}


def _segment_identity(segment: Path) -> Dict[str, Any]:
    """A content-derived fingerprint of a rotated segment, taken while it is known-good.

    The name alone proves only that *some* file with that name was rotated into. Any
    file later placed at that path is then accepted as the claimed predecessor, so a
    swapped segment joins the trail silently — which is the one thing an audit read
    must not do.

    Size plus a digest of the **whole** file. The first version hashed only the first
    line, on the argument that a rotated segment is complete and that hashing 5 MiB per
    read costs more than the read -- but a modification can preserve the first line and
    the byte length while changing any later record, which is exactly the substitution
    this exists to catch. The bound is 5 MiB by rotation, the read that follows walks
    the same bytes anyway, and a cheap check that misses the attack is worse than a
    costed one that does not.

    Best effort: an unreadable or oversized segment yields no fingerprint rather than
    failing the write, since a rotation that cannot be described is still a rotation
    that happened. Both fields or neither, never a partial -- populating the dict as it
    went left `segment_bytes` behind when `stat()` succeeded and the hash failed, which
    is the ordinary shape of an unreadable file since mode bits gate the read and not
    the stat. A size-only claim is weaker than no claim at all: it reads as a
    fingerprint, and an equal-size replacement satisfies it.
    """
    data = _read_bounded(
        segment, "so it is not fingerprinted and its claim will rest on the filename alone")
    return _identity_of(data) if data is not None else {}


def _identity_matches(claimed: Dict[str, Any], actual: Dict[str, Any],
                      segment: Path) -> bool:
    """Whether a claim describes `actual`, which the caller computed from bytes it holds.

    Takes the actual fingerprint rather than a path, so the thing verified and the thing
    used are the same bytes. `segment` is carried only to name the file in a warning.

    A claim carrying no fingerprint is accepted: logs rotated before this existed have
    none, and rejecting them would drop history that is very probably genuine. What is
    rejected is a fingerprint that is *present and disagrees* — that is a different
    file wearing the expected name.
    """
    if not claimed:
        return True
    if set(claimed) != _IDENTITY_FIELDS:
        # A claim carrying one field of the two was written by a rotation whose hash
        # failed. It is not a legacy claim -- those carry neither -- and it cannot be
        # verified, so it is excluded rather than half-trusted.
        logger.warning(
            "decision log: %s carries an incomplete fingerprint (%s), so it is excluded "
            "rather than matched on part of one",
            _capped(str(segment)), ", ".join(sorted(claimed)))
        return False
    if not actual:
        # A claim *with* a fingerprint that cannot be checked is not a match. An early
        # version returned True here, conflating "no fingerprint was recorded" with
        # "one was recorded and cannot be read" -- so a segment whose identity was
        # unreadable at check time joined anyway, and a later successful read pulled in
        # content nothing had verified.
        logger.warning(
            "decision log: %s carries a recorded fingerprint that could not be read, so "
            "it is excluded rather than joined unverified", _capped(str(segment)))
        return False
    if all(actual.get(key) == value for key, value in claimed.items()):
        return True
    logger.warning(
        "decision log: %s does not match the segment this log rotated into, so it is "
        "excluded; a file with the expected name replaced the recorded one. "
        "Recorded %s, found %s",
        _capped(str(segment)), _claim_summary(claimed), _claim_summary(actual))
    return False


def _write_rotation_link(path: Path, backup: Path) -> None:
    """Open the new live segment with the event that names its predecessor.

    Nothing on disk distinguishes a `.1` this log rotated into from one left behind
    by a previous lifecycle -- an operator clearing the live log leaves the backup
    untouched, and a reader then prepends events the operator meant to be gone and
    presents them as continuous history. There is no marker in the filesystem to
    check, so the link has to be written when it is known, which is here.

    Written as an ordinary event, so nothing about the format changes and the trail
    records its own rotation rather than hiding it.
    """
    try:
        # Through the same choke point as every other line. This one is bounded already --
        # the only variable field is a `_capped` filename -- but "bounded because each
        # field happens to be capped" is a property a reader has to re-derive, and the
        # segment bound assumes it of *every* line, not of the ones `record` wrote (B10).
        line = _bounded_event({
            "schema": SCHEMA_VERSION,
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": _RUN_ID,
            "decision_id": "",
            "event": "rotate",
            "command": "",
            # `_capped` first: a filesystem name arrives through surrogateescape, so a
            # raw byte becomes a lone surrogate that `json.dumps` cannot encode. Left
            # alone it raised `UnicodeEncodeError` -- a `ValueError`, straight past the
            # `OSError` guard below -- which aborted the write *after* `os.replace` had
            # already rotated the file, leaving the backup permanently unclaimed and so
            # unreadable by the very check this link exists to satisfy.
            "payload": {"segment": _capped(backup.name), **_segment_identity(backup)},
        })
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
    except (OSError, ValueError) as exc:
        # A rotation whose link is unwritten costs the old segment its place in a
        # later read. That is the safe direction: a short trail, never a fabricated
        # one.
        logger.warning("decision log rotation link unwritten, so %s will be treated "
                       "as unrelated history: %s", _capped(str(backup)), _describe(exc))


def _rotation_payload(first_line: str) -> Optional[Dict[str, Any]]:
    """The rotation payload in ``first_line``, or ``None`` if it is not one.

    Split out of the claim check, which reached eleven branch points assembling and
    comparing this in place. A near-identical shape earned a cognitive-complexity
    finding on the reader in this module once already; stating each question once and
    naming it is both simpler and what stopped that recurring.
    """
    try:
        obj = json.loads(first_line)
    except (ValueError, TypeError) as exc:
        # Debug, not warning: a first line that will not parse is how a log with no
        # rotation link looks, which is the ordinary case for a log that has never
        # rotated. The caller says out loud that the segment went unclaimed.
        logger.debug("decision log: first line is not a rotation record: %s", _describe(exc))
        return None
    if not isinstance(obj, dict) or obj.get("event") != "rotate":
        return None
    payload = obj.get("payload")
    return payload if isinstance(payload, dict) else None


def _names_this_segment(first_line: str, backup: Path) -> bool:
    """Whether the first line is a rotation claiming a file of this name."""
    payload = _rotation_payload(first_line)
    # `_capped(backup.name)`: the link stores the capped form, which neutralises lone
    # surrogates, so comparing the raw name meant a rotation with a hostile name could
    # never claim its own genuine backup and the reader dropped valid history.
    return bool(payload) and payload.get("segment") == _capped(backup.name)


# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-rotation-link


#: Seconds an append waits for a sibling process's lock before writing unlocked. Shorter
#: than the read bound: a read is something the user asked for and will wait a moment
#: for, while this runs on the hot path of every command and nobody asked for it.
_APPEND_LOCK_TIMEOUT_SECONDS = 2.0


def _append_locked(target: Path, line: str) -> None:
    """Append one line, serialising rotation + write across processes where possible.

    Two concurrent invocations can both observe an oversized log; without a lock, one
    could rotate the file the other is mid-write on, dropping events. An exclusive
    advisory lock on a sibling ``.lock`` file serialises the rotate-then-append via
    :func:`studio.utils.atomic_io.with_file_lock`, which degrades to running unlocked
    where ``fcntl`` is unavailable (e.g. Windows).

    The wait for that lock is **bounded**. :func:`record` promises never to change what
    a command does, and a blocking ``flock`` cannot keep that promise: a sibling process
    that is hung -- or was killed without releasing the lock -- would freeze the user's
    terminal inside instrumentation, and :func:`record`'s ``except Exception`` cannot
    intercept a call that blocks rather than raises. On timeout this falls back to the
    same best-effort unlocked append already used off POSIX: under contention, losing
    the rotation guarantee for one event is a better failure than losing the command.
    """
    def _append() -> None:
        _rotate_if_large(target)
        # newline="\n" from origin/main (#189): the log is JSONL and must stay
        # byte-identical across platforms, so the writer never translates to CRLF.
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")

    from .atomic_io import with_file_lock  # pylint: disable=import-outside-toplevel

    lock_path = target.with_name(target.name + ".lock")
    try:
        with_file_lock(lock_path, _append, timeout=_APPEND_LOCK_TIMEOUT_SECONDS)
    except TimeoutError:
        # Debug, not warning: contention is normal for parallel commands, and the event
        # is still recorded. Only a genuine write failure deserves the user's attention.
        logger.debug(
            "decision log: lock busy after %.1fs, appending unlocked",
            _APPEND_LOCK_TIMEOUT_SECONDS)
        _append()


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
        # An empty file counts as new: a first write that failed left a 0-byte log,
        # and `not exists()` then stayed False forever, so the one-time disclosure
        # that a log is being kept never printed again for that user.
        is_new = not target.exists() or not target.stat().st_size
        record_obj = {
            "schema": SCHEMA_VERSION,
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": _RUN_ID,
            "decision_id": decision_id or _CURRENT_DECISION_ID.get(),
            "event": event,
            "command": _redact(command),
            "payload": _redact(payload or {}),
        }
        line = _bounded_event(record_obj)
        parent_is_new = not target.parent.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        if parent_is_new:
            _restrict_to_owner(target.parent, 0o700)
        _append_locked(target, line)
        if is_new:
            # Both files, and only once: a rotated `.1` inherits its mode through
            # `os.replace`, so restricting the live log covers the backup too.
            _restrict_to_owner(target, 0o600)
            _restrict_to_owner(target.with_name(target.name + ".lock"), 0o600)
            _show_notice_once(target)
        return True
    except Exception as exc:  # pylint: disable=broad-except
        # A real write/serialization failure (disabled, no-project and already-warned
        # cases return early above and never reach here, so this only fires on the first
        # failure). Surface it once — fail-open, not fail-silent — and latch telemetry off
        # for the run via _FAILURE_WARNED. `_capped`, not `_redact`: an OSError carries
        # the absolute log path ($HOME included) *and* whatever bytes are in it, and a
        # log record holding a lone surrogate cannot be serialised — it killed a
        # `pytest-xdist` worker and aborted a whole run when this module raised one
        # message from debug to warning.
        _FAILURE_WARNED = True
        logger.warning(
            "Constructor Studio could not write its decision log; "
            "telemetry is off for this run: %s", _describe(exc))
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
# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-fields
def capped_text(value: str) -> str:
    """The record's own redact-then-cap transform, for a caller that reports a field.

    `cfs gate-log` echoes the gate it was given back to its caller. That echo used
    to carry the raw argument while the persisted record carried a redacted, capped
    one, so the transform meant to keep a username out of a decision trail was
    applied to one of the two places the text comes out. A reported field is a
    third sink, alongside the record and the module's own warnings.
    """
    return _capped(value)


def _gate_types() -> tuple:
    """The declared gate-risk types, from the checker that already validates them.

    Imported lazily so a logging call does not pull the PDSL parser into every
    process that writes an event, and so this module keeps no second copy of a set
    that would then be free to drift from the lint's.
    """
    try:
        from .pdsl import GATE_TYPES  # pylint: disable=import-outside-toplevel
        return GATE_TYPES
    except Exception as exc:  # pylint: disable=broad-except
        # Not just `ImportError`: this runs *outside* the guard around
        # `_gate_payload`, so anything the imported module raises at import time --
        # an `AttributeError` from a partial module, a `SyntaxError` from an edit in
        # progress -- escaped `record_gate` and broke the contract that
        # instrumentation never changes what a command does.
        logger.warning("could not read the declared gate types, so a gate record's "
                       "type is unchecked: %s", _describe(exc))
        return ()


def _core_version() -> str:
    """Return the engine version this process is running, or ``""``.

    Imported lazily: the package root does ``from .utils import *``, so a
    module-level import back into it would be circular. ``main()`` defers its
    ``cli`` import for the same reason.

    A failure is warned about rather than swallowed: the version is what a later
    audit compares a gate's declared type against, so an event without one has no
    anchor, and a silently empty field would read as "no version" rather than
    "could not be read".
    """
    try:
        from studio import __version__  # pylint: disable=import-outside-toplevel
        return __version__
    except Exception as exc:  # pylint: disable=broad-except
        # Broad for the same reason as `_gate_types`: a version lookup must not be
        # the thing that raises into a caller who only asked to log an event.
        logger.warning(
            "Constructor Studio could not read its own version, so gate records "
            "will carry none and cannot be pinned to a source version: %s", _describe(exc))
        return ""


_TRUNCATION_MARKER = "…[truncated]"


def is_blank(value: str) -> bool:
    """Report whether a value carries no visible character.

    ``str.strip()`` is not enough. It removes NBSP (U+00A0) and NEL (U+0085) but
    leaves a BOM (U+FEFF) and a zero-width space (U+200B), so a ``cost_if_wrong``
    of those satisfied a guard that exists to require a real answer -- an
    autonomous ruling recorded with nothing stated. Format and control characters
    are therefore discounted alongside whitespace.
    """
    return not any(
        not ch.isspace() and unicodedata.category(ch) not in ("Cf", "Cc")
        for ch in value)


def _capped(value: str) -> str:
    """Redact, then cap author-controlled text, marking the cut so it is not silent.

    **Redaction has to come first.** ``_redact`` collapses ``$HOME`` only where the
    path ends at a separator or at end-of-string, and a truncation marker sits in
    exactly that position -- so capping first put the marker where the boundary
    should be, the lookahead failed, and a home path cut at char 500 reached the
    log verbatim, username included. ``record()`` redacts the payload again
    afterwards, which is harmless because the substitution is idempotent.

    The marker counts against the budget, so the result never exceeds the cap: an
    earlier version appended it afterwards and returned 519 characters for a
    stated bound of 500.
    """
    # argv arrives through surrogateescape, so a raw byte like \xff becomes a lone
    # surrogate that `json.dumps` cannot encode. Left alone it failed the *write*,
    # which then reported "the log could not be written" for a log that was fine,
    # and latched telemetry off for the whole run over one bad character.
    text = _redact(str(value)).encode("utf-8", "replace").decode("utf-8")
    if len(text) <= _GATE_TEXT_CAP:
        return text
    keep = _GATE_TEXT_CAP - len(_TRUNCATION_MARKER)
    return text[:keep] + _TRUNCATION_MARKER

# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-fields

# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-ruling
@dataclass(frozen=True)
class GateRuling:
    """What was decided, why, and what it costs if wrong -- plus where it came from.

    A type rather than loose parameters, because the three-part record is the thing
    that makes a resolution auditable rather than merely recorded, and because
    passing them flat put ``record_gate`` over this repo's argument cap. The cap was
    right: these belong together.

    **The first four names are the frozen resolution contract's, deliberately.**
    That contract is ``decision_key → value → provenance → status``, and its fourth
    amendment requires the ledger to share the plan's shape "distinguished by
    ``provenance`` -- not a second format to look in". An earlier draft here called
    ``value`` ``resolution`` and carried neither ``decision_key`` nor ``status``,
    which would have left the plan reader mapping between two vocabularies. Renamed
    before any log exists, which is the only cheap time to do it.

    Every field defaults to ``UNSPECIFIED`` rather than ``""`` so an omitted value
    is visible in the record, per the contract's first amendment.
    """

    decision_key: str = UNSPECIFIED
    value: str = UNSPECIFIED
    provenance: str = UNSPECIFIED
    status: str = UNSPECIFIED
    why: str = UNSPECIFIED
    cost_if_wrong: str = UNSPECIFIED


# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-ruling


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-wrapper
def _describe(exc: BaseException) -> str:
    """Describe an exception without trusting it to describe itself.

    The recovery path this feeds exists because a value whose `__str__` raises used
    to escape `record_gate`. It then called `str()` on the exception it had caught,
    which is the same act of trust one level up: an exception with a hostile
    `__str__` raised straight out of the handler meant to contain it, so the guard
    reproduced the defect it was written to fix.

    Falls back to the class name, which needs nothing from the object.

    `_capped`, not `_redact` alone: this is a sink for the same author-controlled
    text as the record and the command's echo, and it was the one left redacted but
    uncapped and without the surrogate-neutralising re-encode. A diagnostic line is
    not exempt from the transform every other field gets -- and an unpaired
    surrogate reaching the logging machinery is the failure the re-encode exists to
    prevent.
    """
    try:
        return _capped(str(exc))
    except Exception as inner:  # pylint: disable=broad-except
        # Said out loud, even here. The class name alone is a usable description,
        # so the fallback is right -- but returning it silently made a failure
        # *inside* the failure path invisible, which is the one place a reader has
        # nothing else to go on. `Exception` is the correct width: `KeyboardInterrupt`,
        # `GeneratorExit` and `SystemExit` derive from `BaseException` and are not
        # caught here, so control flow is not being swallowed.
        logger.debug("decision log: an exception could not describe itself (%s); "
                     "reporting its class instead", type(inner).__name__)
        return type(exc).__name__


def _warn_off_list(label: str, value: str, allowed: tuple) -> None:
    """Warn that a field is off its closed set, recording it as given regardless.

    Parity with the command, which rejects an off-list value outright through
    argparse. Without this the CLI refused a paraphrase while a library caller
    wrote one, and these are the fields an auditor compares against -- so the
    looser of the two paths silently decided what a record could contain.

    All four vocabularies, not the two that had it. `provenance` and `status` were
    declared as closed sets and then never checked, so the asymmetry the
    `declared_type` check was added to close was still open on the other half of
    the ruling. `unspecified` is exempt: it is the documented default and means
    the field was omitted, not misspelled.

    Warn rather than refuse: instrumentation must never change what a caller does.
    """
    if value == UNSPECIFIED or value in allowed:
        return
    logger.warning(
        "decision log: %r is not a recognised %s, recording it as given; "
        "expected one of %s", capped_text(str(value)), label,
        ", ".join(allowed) or "(unavailable)")


def _warn_incoherent(kind: str, ruling: "GateRuling") -> None:
    """Warn where two fields cannot both be true, recording the record regardless.

    Only where a combination is *impossible*, not merely unusual. A full
    cross-product of kind x provenance x status would refuse combinations nobody
    has shown to be wrong, and this is instrumentation: refusing a shape the caller
    believes in would make logging change what a command does.

    The two that cannot hold:

    - `plan-resolved` names its own source, so any other provenance contradicts the
      kind. `auto-proceeded` does not: policy, a workflow recommendation and the
      plan can each legitimately be what it proceeded on.
    - a status of `resolved` says the lookup found something, so a value of
      `unspecified` says it found nothing -- resolved to what?

    Everything else stays unchallenged and undocumented as a constraint, because
    asserting a rule this code cannot justify is worse than leaving the gap named.
    """
    if kind == "plan-resolved" and ruling.provenance not in (UNSPECIFIED, "plan"):
        logger.warning(
            "decision log: a plan-resolved gate names the plan as its source, so a "
            "provenance of %r contradicts it; recording it as given",
            capped_text(str(ruling.provenance)))
    if ruling.status == "resolved" and ruling.value == UNSPECIFIED:
        logger.warning(
            "decision log: a status of resolved says the lookup found something, but "
            "the value is unspecified; recording it as given")


def record_gate(kind: str, gate: str, declared_type: str,
                ruling: Optional[GateRuling] = None, *,
                command: str = "", decision_id: str = "",
                path: Optional[Path] = None) -> bool:
    """Log how one gate resolved, and under which engine version.

    ``declared_type`` is the **literal** token from that gate's own MENU block, not
    a paraphrase -- the CLI constrains it to the closed set the PDSL lint uses --
    and the engine version is read here rather than accepted from the caller. It used
    to be an argument, which only tests ever passed: a handed-in value landed in the
    record indistinguishable from one the engine reported, so an auditor could not
    tell which they were reading. A test that needs a fixed version patches
    ``_core_version``.

    **What those two do not yet buy.** They were introduced as the anchor for a
    later audit comparing an ``auto-proceeded`` event against the gate's source as
    it was. They cannot do that on their own: ``studio.__version__`` is a
    hand-edited literal last moved in June, with 55 commits to the prompt modules
    since, so gate events across all of them carry one string. The record also
    holds no source identity -- no path, no line, no digest, no rev. Pinning an
    event to the source it read needs one of those, and adding it belongs with the
    change that builds the audit.

    An unrecognised ``kind`` is written anyway and warned about on every call.
    Dropping it would hide a caller's bug from the audit, and raising would break
    the contract that logging never changes what a command does.

    Every field is capped, including the identity fields: uncapped, they let a
    caller flush real audit history past the log's rotation bound.
    """
    # The guard opens *before* the validation, not after it. The warnings compare
    # caller-supplied values and stringify the off-list ones, so a hostile
    # `__eq__` or `__str__` raised out of `record_gate` from the checks meant to
    # make a record trustworthy -- the same boundary mistake as the lazy gate-type
    # import, one layer further in. Everything a caller's object can influence now
    # sits inside the one handler.
    try:
        ruling = ruling or GateRuling()
        _warn_off_list("gate kind", kind, GATE_KINDS)
        _warn_off_list("declared gate type", declared_type, _gate_types())
        _warn_off_list("ruling provenance", ruling.provenance, GATE_PROVENANCE)
        _warn_off_list("ruling status", ruling.status, GATE_STATUSES)
        _warn_incoherent(kind, ruling)
        payload = _gate_payload(kind, gate, declared_type, ruling)
    except Exception as exc:  # pylint: disable=broad-except
        # `_capped` calls `str(value)`, and it runs *before* `record()`'s guard, so a
        # value whose `__str__` raises escaped `record_gate` and broke the contract
        # that instrumentation never changes what a command does. Only a library
        # caller can reach this -- the CLI always passes strings -- but the contract
        # is stated on this function too.
        logger.warning(
            "decision log: a gate record could not be assembled, so this resolution "
            "is unrecorded: %s", _describe(exc))
        return False
    return record("gate", payload,
                  command=command, decision_id=decision_id, path=path)


def _gate_payload(kind: str, gate: str, declared_type: str,
                  ruling: "GateRuling") -> Dict[str, Any]:
    """Assemble the capped, redacted gate payload."""
    return {
        "kind": _capped(kind),
        "gate": _capped(gate),
        "declared_type": _capped(declared_type),
        "decision_key": _capped(ruling.decision_key),
        "value": _capped(ruling.value),
        "provenance": _capped(ruling.provenance),
        "status": _capped(ruling.status),
        "why": _capped(ruling.why),
        "cost_if_wrong": _capped(ruling.cost_if_wrong),
        "core_version": _capped(_core_version()),
    }
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-gate-wrapper
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
            logger.debug("decision log: skipping unparseable line: %s", _describe(exc))
            continue
        if not isinstance(obj, dict):
            continue
        yield obj


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-read-snapshot
#: Seconds a read waits for the writer's lock before giving up the snapshot. Matches
#: `doc_index`'s escalation-lock bound. A reader that waits longer than a person will
#: wait is indistinguishable from a hang, which is the defect this bound exists for.
_READ_LOCK_TIMEOUT_SECONDS = 5.0


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-verify-before-use
def _claimed_backup_bytes(target: Path, backup: Path) -> Optional[bytes]:
    """The backup's bytes when the live segment's first event claims *these* bytes.

    Returns ``None`` when there is no backup, no claim, no readable bytes within the
    segment bound, or a claim that does not describe what is on disk. Reading before
    verifying is what makes the check meaningful: the fingerprint is computed from the
    same bytes the caller goes on to use, so there is no window between the two for a
    substitution to slip through.
    """
    try:
        if not backup.is_file():
            return None
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            first = next((line for line in handle if line.strip()), "")
        if not _names_this_segment(first, backup):
            # Before the read, so an unclaimed file is never opened: the name check is
            # what decides whether these bytes are ours to spend a lock hashing.
            logger.warning(
                "decision log: %s is not claimed by this log's first event, so it is "
                "excluded from this read; a log cleared while its backup remained would "
                "otherwise read as continuous history", _capped(str(backup)))
            return None
        data = _read_bounded(backup, "so it is excluded from this read")
        if data is None:
            return None
        payload = _rotation_payload(first) or {}
        claimed = {k: payload[k] for k in _IDENTITY_FIELDS if k in payload}
        return data if _identity_matches(claimed, _identity_of(data), backup) else None
    except (OSError, ValueError) as exc:
        logger.warning("decision log: %s could not be read for verification, so it is "
                       "excluded from this read: %s", _capped(str(backup)), _describe(exc))
        return None

# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-verify-before-use

def _read_segments_locked(target: Path) -> List[str]:
    """Read the rotated segment and the live one as one snapshot.

    Both under the writer's own lock: a rotation landing between the two reads
    moves the pre-rotation live events into the segment already read, so they
    appear in neither and vanish from a trail meant to be audited. Where ``fcntl``
    is unavailable this degrades to two unlocked reads, as the writer degrades to
    an unlocked append.
    """
    try:
        import fcntl  # pylint: disable=import-outside-toplevel
    except ImportError:
        # A platform without `fcntl`, which is the documented degradation.
        fcntl = None
    try:
        # Lazily, like every other import in this module: the package root does
        # `from .utils import *`, so a module-level import back into the package
        # is circular.
        from .atomic_io import with_file_lock  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        # Separately, and said out loud. Sharing one `try` with the `fcntl` import
        # meant a missing helper was reported as a platform without file locking --
        # two unrelated causes wearing the same degradation.
        logger.warning("decision log: the shared file-lock helper is unavailable, so "
                       "reads are unsynchronised with the writer: %s", _describe(exc))
        fcntl = None

    def _both() -> List[str]:
        out: List[str] = []
        backup = target.with_name(target.name + ".1")
        # The backup is read once and verified against *those* bytes. Validating by
        # path and then reopening by path leaves a window in which a replacement is
        # consumed silently, and the advisory lock does not close it: `flock`
        # serialises this module's own callers, not an external `mv`.
        claimed_bytes = _claimed_backup_bytes(target, backup)
        if claimed_bytes is not None:
            out.extend(claimed_bytes.decode("utf-8", "replace").splitlines(keepends=True))
        for segment in [target]:
            try:
                if not segment.is_file():
                    continue
                # `errors="replace"` rather than a strict decode: a log with one
                # bad byte used to raise `UnicodeDecodeError` out of `read_events`,
                # which is a `ValueError` and so passed straight through the
                # `OSError` guard below. That contradicted this module's stated
                # tolerance -- a partially corrupt log is still evidence -- and it
                # lost the whole trail, not the damaged line. Replacing the byte
                # keeps every intact line readable; the damaged one then fails
                # `json.loads` and is dropped by `parse_events`, as a malformed
                # line already was.
                with segment.open("r", encoding="utf-8", errors="replace") as handle:
                    out.extend(handle.readlines())
            except (OSError, ValueError) as exc:
                # Warning, not debug. Absence is handled above by `continue`, so
                # reaching here means a segment that exists could not be read --
                # half an audit trail silently missing, reported at a level nobody
                # turns on. The read still returns what it has: a partial trail is
                # worth more than none, but not silently.
                logger.warning("decision log segment %s could not be read, so the "
                               "trail it holds is missing from this read: %s",
                               _capped(str(segment)), _describe(exc))
        return out

    if fcntl is None:
        return _both()
# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-log-read-bounded
    try:
        # `with_file_lock`, not a fresh `flock`: this repo already fixed an
        # unbounded `flock(LOCK_EX)` that let one process holding a lock hang an
        # entire command (#136, round-4 review, Major), and the bounded poll loop
        # that fixed it lives there. Writing a second lock call here reintroduced
        # the defect the helper exists to prevent -- a reader waiting forever on a
        # writer, with no way out.
        return with_file_lock(
            target.with_name(target.name + ".lock"), _both,
            timeout=_READ_LOCK_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        # The fourth degradation, and the same direction as the other three: a log
        # that cannot be snapshotted is still evidence, so read it unlocked rather
        # than block or return nothing. Warned, not debugged, because the snapshot
        # guarantee is the thing being given up.
        logger.warning(
            "decision log read lock timed out after %.1fs (another process appears to "
            "hold it); reading without the snapshot, so a rotation landing mid-read "
            "could hide events from this read", _READ_LOCK_TIMEOUT_SECONDS)
        return _both()
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-read-bounded
    except OSError as exc:
        # An unlockable log is still evidence; read it without the snapshot rather
        # than report an empty trail.
        logger.debug("decision log lock unavailable, reading unlocked: %s", _describe(exc))
        return _both()
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-log-read-snapshot


def read_events(path: Optional[Path] = None, *, event: str = "",
                run_id: str = "", decision_id: str = "",
                limit: int = 0) -> Iterator[Dict[str, Any]]:
    """Yield events oldest-first, skipping any line that will not parse.

    A truncated or hand-edited log stays readable: a bad line is dropped, not raised,
    because a partially corrupt log is still evidence.

    **The rotated ``.1`` segment is read first**, because it holds the older half and
    this function's contract is oldest-first. It used to be skipped, so the moment a
    log passed its size bound half the history was on disk and unreachable through
    the module's own reader -- which mattered little while the log was telemetry and
    matters a great deal now that a gate resolution is audited from it.

    **It is read only when the live segment claims it.** The rotation writes a link
    naming the segment it created and fingerprinting its contents, and that fingerprint
    is verified against the bytes this read goes on to use. A backup the live log does
    not claim, or claims and does not describe, is **excluded with a warning** rather
    than joined -- because a log cleared while its backup remained would otherwise read
    as continuous history, and a substituted file would read as the real one. A link
    carrying no fingerprint is still honoured: logs rotated before that existed have
    none, and dropping them would discard history that is very probably genuine.
    """
    target = path or default_log_path()
    if target is None:
        return
    lines = _read_segments_locked(target)
    if not lines:
        return

    wanted = {"event": event, "run_id": run_id, "decision_id": decision_id}
    matched = [obj for obj in parse_events(lines) if _matches(obj, wanted)]
    if limit > 0:
        matched = matched[-limit:]
    yield from matched


def _matches(obj: Dict[str, Any], wanted: Dict[str, str]) -> bool:
    """Whether one event satisfies every non-empty filter.

    Extracted because reading two segments pushed `read_events` to a cognitive
    complexity of 19 against a limit of 15 -- three near-identical guard clauses
    are one rule, and stating it once is both simpler and cheaper to extend.
    """
    return all(not value or obj.get(field) == value for field, value in wanted.items())


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
            logger.debug("decision log: skipping read event with non-numeric "
                         "tokens/lines: %s", _describe(exc))
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
