"""What a vendor CLI says the local account may actually use.

`generate-agents` writes whatever the model matrix resolves to, and nothing
checks the result: a slug the vendor has withdrawn is written into a config that
looks correct and fails only when an agent is used. That is how gpt-5.4 and
gpt-5.4-mini reached 43 of the 44 shipped agents.

The `codex` CLI caches the set its account is entitled to, so the check costs a
file read and no network call. The shape read here was taken from a real cache
written by codex-cli 0.154.0 on 2026-09-18 -- `{"models": [{"slug": ...,
"visibility": "list"|"hide", ...}], ...}` -- and is not a published contract.
Every field is therefore treated as optional and every departure from the
expected shape as "unknown" rather than as a verdict. It is advisory on purpose -- a run is never
refused over it. The cache belongs to another program: it can be absent, stale,
written by a different account type, or change shape without notice, and none of
those mean the model is gone. Only a cache that is present, readable, and names
models *without* the one in hand is evidence, and even then the answer is a
warning rather than a verdict.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet, Optional

logger = logging.getLogger(__name__)

#: Honoured the way the CLI honours it, so a non-default home is not mistaken
#: for a missing cache.
_CODEX_HOME_ENV = "CODEX_HOME"
#: Kept small on purpose: this list goes into a warning a person reads, and a
#: vendor that starts listing fifty models should not turn one line into a page.
_MAX_LISTED_IN_MESSAGE = 12
_CODEX_CACHE_NAME = "models_cache.json"

#: Where `codex` records how it is logged in, beside the cache, and the one value
#: of its `auth_mode` the cache is known to describe. Measured on codex-cli
#: 0.154.0: a ChatGPT login writes `"auth_mode": "chatgpt"`, and the cache it
#: writes lists that plan's models. An API-key login is billed and entitled
#: differently, so the same cache is not evidence about it (#245 review).
_CODEX_AUTH_NAME = "auth.json"
_CACHE_DESCRIBES_AUTH_MODE = "chatgpt"

#: The CLI's own word for a model it offers a person. The cache also carries
#: internal entries, and treating one of those as entitled would make a
#: withdrawn slug look fine.
_LISTED = "list"


# @cpt-begin:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-cache-path
def codex_cache_path() -> Path:
    """Where `codex` keeps its cache, honouring `CODEX_HOME` as the CLI does."""
    return Path(os.environ.get(_CODEX_HOME_ENV) or Path.home() / ".codex") / _CODEX_CACHE_NAME


def _cache_describes_this_login(codex_home: Path) -> bool:
    """False only when codex says it is logged in some other way than the cache covers.

    Reads one field and nothing else from a file that also holds tokens, and
    never logs what it read. Anything short of a positive answer -- no file, an
    unreadable one, no `auth_mode`, an unfamiliar shape -- keeps the check as it
    was, because not knowing the login type is not evidence that it differs.
    """
    try:
        data = json.loads((codex_home / _CODEX_AUTH_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return True     # a condition, not a failure: the check simply keeps running
    mode = data.get("auth_mode") if isinstance(data, dict) else None
    return not isinstance(mode, str) or mode == _CACHE_DESCRIBES_AUTH_MODE


# @cpt-end:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-cache-path


# @cpt-begin:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-read-cache
def _cache_worth_reading() -> Optional[Path]:
    """The cache path, or None when there is nothing to read -- each reason said once.

    Split out of `entitled_codex_models` so each of the three ways of having
    nothing to check stays its own short branch with its own reason.
    """
    # `Path.home()` raises RuntimeError where no home can be determined -- a
    # container with no `$HOME` and no passwd entry, and no `CODEX_HOME` either.
    # Warned, not debug-logged: "codex cannot have run here" was an assumption,
    # not a measurement, and what is certain is only that the check is off for
    # this run. `debug` is not a visible signal by this repository's own contract
    # (`scripts/pylint_plugins/silent_exceptions.py`), and the answer is cached,
    # so this is said once per process (#245 review).
    try:
        path = codex_cache_path()
    except RuntimeError as exc:
        logger.warning("model entitlements: no home directory and no %s, so the "
                       "withdrawn-model check is skipped for this run: %s",
                       _CODEX_HOME_ENV, exc)
        return None

    # A plain condition rather than a caught `FileNotFoundError`, because that is
    # what it is: no cache file means codex has not run on this machine, which is
    # the ordinary state of most machines and not a failure to absorb. Asking
    # first also takes this branch out of the silent-swallowing question entirely
    # -- there is no handler here to route anywhere (#245 review).
    if not path.is_file():
        logger.debug("model entitlements: no codex cache at %s", path)
        return None

    # The cache describes a ChatGPT-plan login. Under an API key it is not
    # evidence about the account, and reading it as evidence was a confident false
    # "withdrawn" for a model that account may well be served -- which the opt-out
    # left to the person to diagnose (#245 review). Quiet for the same reason a
    # missing cache is: nothing has gone wrong, the check just has nothing to say.
    if not _cache_describes_this_login(path.parent):
        logger.debug("model entitlements: codex is not on a ChatGPT login; its cache "
                     "does not describe this account")
        return None

    return path


@lru_cache(maxsize=1)
def entitled_codex_models() -> Optional[FrozenSet[str]]:
    """The slugs `codex` lists for this account, or None when that is unknown.

    None and an empty set mean different things, and the caller must not
    conflate them: None is "the cache said nothing usable", an empty set is
    "the cache was read and lists nothing". Only the latter is evidence, and
    even it is thin -- which is why the caller warns rather than refuses.

    Cached for the process. Reading a file once per run is the point; a warning
    that changes halfway through a generate would be worse than either answer.
    Call `entitled_codex_models.cache_clear()` if the file is known to have
    changed underneath -- there is no wrapper for it, because nothing in
    production has a reason to.
    """
    path = _cache_worth_reading()
    if path is None:
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        # A cache that exists and still cannot be read is the opposite case:
        # something is wrong with a file this machine wrote, and the only
        # consequence is that entitlement checking goes quiet for the rest of
        # the run. `debug` is not a visible signal by this repository's own
        # contract -- `scripts/pylint_plugins/silent_exceptions.py` leaves it out
        # of `_VISIBLE_SIGNAL_NAMES` deliberately -- so reporting this failure at
        # debug was reporting it nowhere (#245 review). Same split, and the same
        # reason, as `doc_index._read_cache_file`: the caller already knows the
        # file is there.
        logger.warning("model entitlements: codex cache at %s cannot be read, "
                       "so no model can be checked against it: %s", path, exc)
        return None

    entries = data.get("models") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        logger.warning("model entitlements: codex cache at %s has an unfamiliar shape, "
                       "so no model can be checked against it", path)
        return None

    listed = frozenset(
        entry["slug"] for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("slug"), str)
        and entry["slug"].strip()
        and entry.get("visibility") == _LISTED
    )
    if entries and not listed:
        # Models are described but none of them match what this reads as
        # "offered to a person". Far likelier that the shape moved than that an
        # account is entitled to nothing, and the two are indistinguishable from
        # here -- so the honest answer is that nothing is known.
        #
        # A blank slug is excluded above for the same reason it is not skipped
        # quietly: an entry whose slug is empty names no model, and counting it
        # would turn this branch's "nothing is known" into a set of one that
        # every real model then appears to be missing from (#245 review).
        logger.warning("model entitlements: %d entries in the codex cache at %s, "
                       "none of them listed; treating the shape as unfamiliar", len(entries), path)
        return None
    return listed


# @cpt-end:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-read-cache


# @cpt-begin:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-verdict
def listed_for_message(entitled: FrozenSet[str]) -> str:
    """The entitled set as one bounded line for a person to read."""
    ordered = sorted(entitled)
    shown = ordered[:_MAX_LISTED_IN_MESSAGE]
    suffix = "" if len(ordered) <= _MAX_LISTED_IN_MESSAGE else f", and {len(ordered) - _MAX_LISTED_IN_MESSAGE} more"
    return ", ".join(shown) + suffix


def codex_model_is_withdrawn(model_id: str) -> bool:
    """Whether the cache positively contradicts `model_id`.

    False on every uncertainty, so a missing or unreadable cache never produces
    a warning. An empty entitled set counts as no knowledge rather than as
    "nothing is allowed": a cache that lists nothing is far more likely to be a
    CLI that has not populated it yet than an account entitled to no models.
    """
    entitled = entitled_codex_models()
    if not entitled:
        return False
    return model_id not in entitled


# @cpt-end:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-verdict
