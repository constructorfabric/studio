"""What a vendor CLI says the local account may actually use.

`generate-agents` writes whatever the model matrix resolves to, and nothing
checks the result: a slug the vendor has withdrawn is written into a config that
looks correct and fails only when an agent is used. That is how gpt-5.4 and
gpt-5.4-mini reached 43 of the 44 shipped agents.

The `codex` CLI caches the set its account is entitled to, so the check costs a
file read and no network call. It is advisory on purpose -- a run is never
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
_CODEX_CACHE_NAME = "models_cache.json"

#: The CLI's own word for a model it offers a person. The cache also carries
#: internal entries, and treating one of those as entitled would make a
#: withdrawn slug look fine.
_LISTED = "list"


# @cpt-begin:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-cache-path
def codex_cache_path() -> Path:
    """Where `codex` keeps its cache, honouring `CODEX_HOME` as the CLI does."""
    return Path(os.environ.get(_CODEX_HOME_ENV) or Path.home() / ".codex") / _CODEX_CACHE_NAME


# @cpt-end:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-cache-path


# @cpt-begin:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-read-cache
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
    path = codex_cache_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.debug("model entitlements: no usable codex cache at %s: %s", path, exc)
        return None

    entries = data.get("models") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        logger.debug("model entitlements: unfamiliar cache shape at %s", path)
        return None

    return frozenset(
        entry["slug"] for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("slug"), str)
        and entry.get("visibility") == _LISTED
    )


# @cpt-end:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-read-cache


# @cpt-begin:cpt-studio-algo-agent-integration-generate-shims:p1:inst-entitlement-verdict
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

