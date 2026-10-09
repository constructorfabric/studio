"""One hardened way to ask git a read-only question.

Two readers in this package need the same thing -- run a git query, never raise, and keep a
tool failure apart from a valid negative -- and a second copy of that is a second place for
the hardening to drift out of step. The callers differ only in how they shape the answer, so
the invocation lives here and the shaping stays with them.

Nothing here interprets git's output. A caller that wants the first line takes the first
line; this returns what git wrote.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# @cpt-begin:cpt-studio-algo-core-infra-git-read:p1:inst-git-read-limits
#: Seconds any single git read may take, so a hung repository cannot hang a command.
TIMEOUT = 10

#: Configuration forced off for every read, because a **repository can supply it**. `git status`
#: honours `core.fsmonitor`, which names a program git then launches -- so inspecting an untrusted
#: checkout could make this read-only check run that project's chosen binary. `-c` overrides the
#: repository's own config file, and these are passed before the subcommand.
SAFE_CONFIG = ("-c", "core.fsmonitor=false", "-c", "core.fsmonitorHookVersion=0")

REDIRECT_VARS = (
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
    # A ref *namespace*, and the honest note is that it changes **nothing these queries
    # answer**. Measured against every command above -- `rev-parse --is-inside-work-tree`,
    # `--absolute-git-dir`, `--verify HEAD`, `symbolic-ref --short HEAD`, and plain ref
    # lookups -- and the output is identical with and without it. `GIT_NAMESPACE` is a
    # ref-advertisement mechanism: it bites `fetch`, `ls-remote` and the pack protocols,
    # not local resolution.
    #
    # It is here because it is one of git's redirection variables and this tuple is the
    # place they are removed, so the shared list holds the union rather than the larger of
    # two partial lists -- the reversal fixtures were sanitising it locally and adopting
    # this tuple dropped it. Not because it affects the queries below; an earlier version
    # of this comment claimed it did, which was written without measuring.
    #
    # Where it *would* bite is `git_utils._run_git`, which runs `fetch` and passes no
    # sanitised environment at all. That is a separate exposure this tuple does not reach.
    "GIT_NAMESPACE",
)

#: Refs and paths are bytes and need not be UTF-8, so `text=True`'s strict default would
#: raise past the handler below and break the never-raises contract. The filesystem codec
#: is the one Python uses for paths, so a value round-trips to the same bytes.
PATH_ENCODING = "utf-8"
PATH_ERRORS = "surrogateescape"
# @cpt-end:cpt-studio-algo-core-infra-git-read:p1:inst-git-read-limits


# @cpt-begin:cpt-studio-algo-core-infra-git-read:p1:inst-git-read-env
def env() -> Dict[str, str]:
    """The ambient environment with git's repository-redirecting variables removed."""
    cleaned = dict(os.environ)
    for name in REDIRECT_VARS:
        cleaned.pop(name, None)
    return cleaned
# @cpt-end:cpt-studio-algo-core-infra-git-read:p1:inst-git-read-env


# @cpt-begin:cpt-studio-algo-core-infra-git-read:p1:inst-git-read-query
def query(root: Path, args: Sequence[str], *,
          failed_log: str = "git could not be read: %s",
          exited_log: str = "git query exited %d") -> Tuple[Optional[str], bool]:
    """Run a read-only git query as ``(stdout or None, tool_failed)``. Never raises.

    Each caller supplies its own log lines. The hardening is shared; the voice is not --
    "change-summary git query could not run" tells an operator which command degraded,
    where a generic line from a shared helper would not.

    The two halves of "no answer" are kept apart, because conflating them lets a transient
    tool failure be reported as a conclusion about history -- "no merge base" when git
    simply timed out.

    * **Tool failure** is git not launching, timing out, or writing undecodable bytes.
      Nothing was learned.
    * **A non-zero exit is a valid negative**, not a failure: ``merge-base`` exits 1 when two
      histories genuinely have no common ancestor, and ``rev-parse`` exits non-zero outside a
      repository. Those are answers, and treating them as breakage would mislead just as
      badly in the other direction.
    """
    command: List[str] = ["git", *SAFE_CONFIG, *args]
    try:
        done = subprocess.run(
            command, cwd=str(root), env=env(), capture_output=True, text=True,
            encoding=PATH_ENCODING, errors=PATH_ERRORS, timeout=TIMEOUT, check=False)
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as exc:
        # Warning, not debug: git not launching is an environment fault an operator should
        # see, unlike the routine non-zero exit below.
        logger.warning(failed_log, type(exc).__name__)
        return None, True
    if done.returncode:
        logger.debug(exited_log, done.returncode)
        return None, False
    return done.stdout, False
# @cpt-end:cpt-studio-algo-core-infra-git-read:p1:inst-git-read-query
