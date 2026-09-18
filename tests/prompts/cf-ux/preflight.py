#!/usr/bin/env python3
"""Preconditions for the cf-ux prompt pilot, checked before anything is spent.

`make check-prompt-tests` already proves the four binaries exist. Existing is
not the same as usable, and the two ways it is not cost a real run each:

  * `node` may be too old for promptfoo, which then fails deep inside npx with
    a message about the package and not about node -- or may not be a program
    at all. Under nvm's lazy loader `node` is a *shell function* that installs
    the real one on first call, so it answers an interactive shell and does not
    exist for anything `make` spawns;
  * the codex model may have been withdrawn, which surfaces as a 400 inside a
    promptfoo table cell, after every sandbox has already been built.

Both are knowable up front, so they are checked up front, and reported as the
one thing the person has to change.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

#: promptfoo's own floor, from its `engines.node`. Raise this when the pinned
#: promptfoo does; there is no way to read it without installing it first, and
#: installing it first is the wait this check exists to avoid.
NODE_MIN = (22, 22, 0)

#: Where the `codex` CLI caches what the account may use. Written by the CLI
#: itself, so consulting it costs nothing and needs no API call -- and when it
#: is missing or stale, that is a reason to say nothing rather than to refuse.
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
MODELS_CACHE = CODEX_HOME / "models_cache.json"

_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _version(text: str) -> tuple[int, int, int] | None:
    found = _VERSION.search(text or "")
    return (int(found[1]), int(found[2]), int(found[3])) if found else None


def _node_version(binary: str = "node") -> tuple[int, int, int] | None:
    try:
        done = subprocess.run([binary, "--version"], capture_output=True, text=True,
                              timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return _version(done.stdout) if done.returncode == 0 else None


def _nvm_candidates() -> list[tuple[tuple[int, int, int], Path]]:
    """Installed nvm nodes new enough for promptfoo, oldest first.

    `make` runs its recipes in `sh`, which never sources nvm's shell function,
    so an nvm user's `node` is whichever version nvm's default symlink points
    at -- and that is routinely not the one promptfoo needs. Finding the usable
    one is a directory listing; making the person find it is the half hour this
    function exists to give back.
    """
    root = Path(os.environ.get("NVM_DIR") or Path.home() / ".nvm") / "versions" / "node"
    found = []
    for candidate in sorted(root.glob("*/bin/node")) if root.is_dir() else []:
        version = _node_version(str(candidate))
        if version and version >= NODE_MIN:
            found.append((version, candidate.parent))
    return sorted(found)


def check_node() -> list[str]:
    """Whether a node `make` can actually spawn is new enough for promptfoo.

    Two failures, one remedy. Too old is the obvious one. The other is that
    there is no `node` program at all: nvm's lazy loader defines `node` as a
    shell function that sources nvm and re-dispatches, so an interactive shell
    answers `node --version` while `make`, which uses `sh`, finds nothing --
    and `command -v node` agrees with whichever of the two asked it.

    Both end in the same place, so both get the same answer: the path of an
    installed node that qualifies.
    """
    want = ".".join(str(part) for part in NODE_MIN)
    have = _node_version()
    if have is not None and have >= NODE_MIN:
        return []

    if have is None:
        problem = [f"no usable `node` program on PATH. promptfoo needs >= {want}.",
                   "  (Under nvm's lazy loader `node` is a shell function, so an"
                   " interactive shell",
                   "   answers it and `make`, which runs recipes in `sh`, does not.)"]
    else:
        got = ".".join(str(part) for part in have)
        problem = [f"node {got} is too old for promptfoo, which needs >= {want}."]

    candidates = _nvm_candidates()
    if candidates:
        version, bindir = candidates[-1]
        newest = ".".join(str(part) for part in version)
        problem += [
            f"  nvm has {newest} installed. Put it on PATH for the command:",
            "",
            f"    PATH={bindir}:$PATH make test-prompts",
        ]
    else:
        problem += ["  Install one:  nvm install 22 && nvm use 22"]
    return problem


def check_codex_model(model: str) -> list[str]:
    """Whether `codex` still lists the model the pilot is about to ask for.

    Silent on every uncertainty. A missing cache, an unreadable one, a shape
    that is not the one known here -- none of those say the model is gone, and
    a preflight that blocks a run on its own ignorance is worse than the 400 it
    was meant to pre-empt.
    """
    try:
        data = json.loads(MODELS_CACHE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    entries = data.get("models") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    # `visibility` is the CLI's own word for what it offers a person. The cache
    # also carries internal entries (`codex-auto-review`, `gpt-reserve`) marked
    # otherwise, and suggesting one of those as the model to switch to would be
    # worse than saying nothing.
    slugs = sorted({
        entry["slug"] for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("slug"), str)
        and entry.get("visibility") == "list"
    })
    if not slugs or model in slugs:
        return []
    return [
        f"codex model {model!r} is not among the ones this account is entitled to.",
        f"  {MODELS_CACHE} lists: {', '.join(slugs)}",
        "  Pick one and set it:",
        "",
        f"    CF_UX_CODEX_MODEL={slugs[0]} make test-prompts",
        "",
        "  (If the cache is stale, `codex` refreshes it -- this check reads it, "
        "never the network.)",
    ]


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "providers"))
    try:
        from codex_provider import DEFAULT_MODEL  # noqa: PLC0415 -- optional import
    except ImportError:
        DEFAULT_MODEL = os.environ.get("CF_UX_CODEX_MODEL", "")

    problems = check_node() + (check_codex_model(DEFAULT_MODEL) if DEFAULT_MODEL else [])
    if not problems:
        return 0
    print("", file=sys.stderr)
    print("ERROR: the prompt pilot cannot run as configured.", file=sys.stderr)
    print("", file=sys.stderr)
    for line in problems:
        print(f"  {line}" if not line.startswith(" ") else line, file=sys.stderr)
    print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
