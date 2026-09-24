#!/usr/bin/env python3
"""Preconditions for the cf-ux prompt pilot, checked before anything is spent.

`make check-prompt-tests` proves that `claude`, `codex` and `cfs` exist.
Existing is not the same as usable, and the two ways it is not cost a real run
each (node it checks here too, for the reason in `check_node`):

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
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

#: promptfoo's own floor, from its `engines.node`. Raise this when the pinned
#: promptfoo does; there is no way to read it without installing it first, and
#: installing it first is the wait this check exists to avoid.
NODE_MIN = (22, 22, 0)

#: How many installed nvm nodes to probe. Each probe is a process with a
#: timeout, and a long-lived nvm directory accumulates dozens of versions; the
#: newest few are where a qualifying one will be. Probed newest first.
NVM_PROBE_LIMIT = 8

#: The claude-code release the grading was measured against. `_skill_trace` reads a
#: `tool_result` with no `is_error` key as a success, because that is the shape this
#: CLI emits for a successful `Skill` call -- measured, not promised by any schema.
#: A CLI that starts emitting `is_error: false` explicitly, or stops emitting the key
#: on failures, would be misread silently and every verdict in the run would be
#: wrong in the same direction (#229 review).
#:
#: A floor, not a pin: the shape has held since this version, and refusing to run on
#: anything newer would make the check the thing that breaks the suite. What it
#: catches is a CLI older than the measurement, where the shape is simply unknown.
CLAUDE_SHAPE_MEASURED = (2, 1, 276)

#: The release the deny rules were measured on: `--settings` deny rules holding
#: under `bypassPermissions` for Read, Write, and `cat`/`head`/`find`/`grep -r`/`ls`
#: of the runner's home in Bash. That is the security claim of the claude
#: provider, and it was guarded by nothing while the grading shape had a floor
#: (#229 review). Same reasoning as above: a CLI older than this is unmeasured.
CLAUDE_DENY_RULES_MEASURED = (2, 1, 281)

#: The floor preflight enforces: the higher of the two, so neither claim runs on a
#: CLI it was never measured on.
CLAUDE_MIN = max(CLAUDE_SHAPE_MEASURED, CLAUDE_DENY_RULES_MEASURED)

#: Runs the pilot on a CLI below :data:`CLAUDE_MIN` anyway. Only the exact value
#: ``1`` counts, as for every other CF_UX_* switch: a bare truthiness test read
#: ``0`` and ``false`` as "skip", so the spelling that means "keep checking"
#: switched the check off (#229 review).
SKIP_CLAUDE_CHECK_ENV = "CF_UX_SKIP_CLAUDE_VERSION_CHECK"

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
    except (OSError, subprocess.SubprocessError) as exc:
        # Not swallowed: "no version" is the answer the caller acts on, and the
        # reason belongs in the log rather than in the sentence a person reads.
        logger.debug("cf-ux preflight: %s did not report a version: %s", binary, exc)
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
    try:
        # A traversal, so it can fail the way traversals do: a permission-denied
        # directory, a broken symlink, a path that is not one. None of that is
        # worth a traceback out of a preflight -- it means "no candidate here".
        entries = list(root.glob("*/bin/node")) if root.is_dir() else []
    except OSError as exc:
        logger.debug("cf-ux preflight: could not scan %s: %s", root, exc)
        return []

    # Ordered by the version in the directory name, not by the name itself:
    # sorting paths as text puts `v9.0.0` above `v24.21.0`, so the cap below
    # could discard every node new enough to qualify and report that none was
    # installed. Names that carry no version sort last rather than being
    # dropped -- they are still worth a probe if there is room.
    def newest_first(path: Path) -> tuple[int, tuple[int, int, int]]:
        parsed = _version(path.parent.parent.name)
        return (1, parsed) if parsed else (0, (0, 0, 0))

    candidates = sorted(entries, key=newest_first, reverse=True)

    found = []
    for candidate in candidates[:NVM_PROBE_LIMIT]:
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


def check_claude() -> list[str]:
    """Whether the installed `claude` is at least the release grading was measured on.

    Silent when the version cannot be read at all. `claude --version` not
    answering is its own failure and the suite will report it far more clearly
    than a preflight guess would; inventing a problem here from a missing answer
    would be the "unknown means broken" reading this file avoids everywhere else.
    """
    try:
        proc = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                              timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []

    have = _version(proc.stdout)
    if have is None or have >= CLAUDE_MIN:
        return []

    def _dotted(version: tuple[int, int, int]) -> str:
        return ".".join(str(part) for part in version)

    # Each claim named with the release it was measured on. Naming only the floor
    # attributed both to it, and the grading shape was measured on an older one
    # (#229 review).
    got = _dotted(have)
    return [
        f"claude {got} is older than {_dotted(CLAUDE_MIN)}, the newest of the releases "
        "this suite's two measurements were taken on:",
        "  * a successful `Skill` call is recognised by its result carrying no",
        f"    `is_error` key -- measured on {_dotted(CLAUDE_SHAPE_MEASURED)}; on an older CLI",
        "    that shape is unknown, and every verdict in the run would be wrong the",
        "    same way;",
        "  * the deny rules that keep the unattended child out of your home directory",
        f"    -- measured on {_dotted(CLAUDE_DENY_RULES_MEASURED)}.",
        f"  Upgrade, or set {SKIP_CLAUDE_CHECK_ENV}=1 to run anyway.",
    ]


def check_codex_model(model: str) -> list[str]:
    """Whether `codex` still lists the model the pilot is about to ask for.

    Silent on every uncertainty. A missing cache, an unreadable one, a shape
    that is not the one known here -- none of those say the model is gone, and
    a preflight that blocks a run on its own ignorance is worse than the 400 it
    was meant to pre-empt.
    """
    try:
        data = json.loads(MODELS_CACHE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.debug("cf-ux preflight: no usable model cache at %s: %s", MODELS_CACHE, exc)
        return []
    entries = data.get("models") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    # `visibility` is the CLI's own word for what it offers a person. The cache
    # also carries internal entries (`codex-auto-review`, `gpt-reserve`) marked
    # otherwise, and suggesting one of those as the model to switch to would be
    # worse than saying nothing.
    # Ordered by the CLI's own `priority`, not alphabetically. Alphabetical put
    # `gpt-5.5` -- the previous generation -- at the head of the suggestion,
    # which is a worse default than the one the CLI itself would offer.
    listed = [
        entry for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("slug"), str)
        and entry.get("visibility") == "list"
    ]
    ranked = sorted(listed, key=lambda e: (e.get("priority")
                                           if isinstance(e.get("priority"), int) else 10**6,
                                           e["slug"]))
    slugs = list(dict.fromkeys(entry["slug"] for entry in ranked))
    if not slugs or model in slugs:
        return []
    return [
        f"codex model {model!r} is not among the ones this account is entitled to.",
        f"  {MODELS_CACHE} lists: {', '.join(sorted(slugs))}",
        "  Pick one and set it:",
        "",
        f"    CF_UX_CODEX_MODEL={slugs[0]} make test-prompts",
        "",
        "  (If the cache is stale, `codex` refreshes it -- this check reads it, "
        "never the network.)",
    ]


def main(argv: list[str] | None = None) -> int:
    # `--node-only` exists for `install-prompt-tests`, which caches an npm
    # package: that needs a node, and has no business requiring a live account.
    if "--node-only" in (sys.argv[1:] if argv is None else argv):
        return _report(check_node())

    sys.path.insert(0, str(Path(__file__).resolve().parent / "providers"))
    try:
        from codex_provider import DEFAULT_MODEL  # noqa: PLC0415 -- optional import
    except ImportError as exc:
        # Reported, not shrugged off. The override keeps a run possible, but the
        # pilot cannot run at all if its own provider will not import, and
        # falling back to an unset env var meant the model check quietly did
        # nothing and the preflight said everything was fine.
        override = os.environ.get("CF_UX_CODEX_MODEL", "")
        if not override:
            return _report([f"the codex provider will not import: {exc}",
                            "  The pilot cannot run without it, and the model "
                            "check has nothing to check."])
        DEFAULT_MODEL = override
    except ValueError as exc:
        # Importing the provider *runs* it: its module body reads the CF_UX_*
        # knobs, and `int(CF_UX_CODEX_CONTEXT)` raises on anything non-numeric.
        # Catching only ImportError meant a typo in an env var reached the
        # person as a traceback out of a preflight whose entire job is to
        # replace exactly that with a sentence.
        return _report([f"a CF_UX_* setting is not valid: {exc}",
                        "  (read while importing the codex provider; check "
                        "CF_UX_CODEX_CONTEXT)"])

    claude_problems = _claude_problems_unless_skipped()
    return _report(check_node()
                   + claude_problems
                   + (check_codex_model(DEFAULT_MODEL) if DEFAULT_MODEL else []))


def _claude_problems_unless_skipped() -> list[str]:
    """:func:`check_claude`, unless :data:`SKIP_CLAUDE_CHECK_ENV` is ``1``.

    Either way the person is told. A skip that leaves no trace makes a run graded
    on an unmeasured CLI indistinguishable afterwards from one that was checked,
    and a value that is set but is not ``1`` is almost certainly someone who meant
    one or the other -- so it is named rather than silently read as "check"
    (#229 review).
    """
    value = os.environ.get(SKIP_CLAUDE_CHECK_ENV)
    if value == "1":
        print(f"cf-ux preflight: claude version check skipped ({SKIP_CLAUDE_CHECK_ENV}=1); "
              "verdicts from this run rest on an output shape not measured on this CLI",
              file=sys.stderr)
        return []
    if value:
        print(f"cf-ux preflight: {SKIP_CLAUDE_CHECK_ENV}={value!r} is not 1, so the "
              "claude version check runs", file=sys.stderr)
    return check_claude()


def _report(problems: list[str]) -> int:
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
