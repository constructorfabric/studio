"""Sandbox lifecycle helpers for cf-ux promptfoo providers.

Initializes a fresh cf-studio project in `$TMPDIR/cf-ux-sandboxes/<id>/` using
the **local** repo as the source of truth.

Cleanup is hardened: each sandbox is registered in a process-wide set wiped
by `atexit` and by SIGTERM/SIGINT handlers, so a killed promptfoo worker
does not leak the directory. On startup, any sandbox older than 24h under
the parent dir is also swept.

Env overrides:
  CF_UX_SHARED_SANDBOX  — reuse an already-initialized path (no setup/teardown).
  CF_UX_KEEP_SANDBOX=1  — skip teardown on success and print the path.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Iterator


REPO_ROOT = Path(__file__).resolve().parents[4]
STUDIO_SCRIPTS = REPO_ROOT / "skills" / "studio" / "scripts"

_SANDBOX_PARENT = Path(tempfile.gettempdir()) / "cf-ux-sandboxes"
_STALE_AFTER_SECONDS = 24 * 60 * 60  # 24h

_LIVE_SANDBOXES: set[Path] = set()
_HANDLERS_INSTALLED = False


class SandboxError(RuntimeError):
    pass


def _wipe(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _atexit_cleanup() -> None:
    for p in list(_LIVE_SANDBOXES):
        _wipe(p)
        _LIVE_SANDBOXES.discard(p)


def _signal_cleanup(signum, _frame) -> None:  # noqa: ANN001
    _atexit_cleanup()
    # Re-raise via default handler so the process actually exits.
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _install_handlers_once() -> None:
    global _HANDLERS_INSTALLED  # noqa: PLW0603
    if _HANDLERS_INSTALLED:
        return
    atexit.register(_atexit_cleanup)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _signal_cleanup)
        except (ValueError, OSError):
            pass  # not available in this thread/platform
    _HANDLERS_INSTALLED = True


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    return True


def _sweep_stale_sandboxes() -> None:
    """Wipe leftover sandboxes from dead promptfoo workers or stale runs.

    Sandbox name pattern is `<pid>-<rand>`. If the pid is no longer running,
    the dir cannot belong to a live worker — safe to remove. Also wipes
    anything older than _STALE_AFTER_SECONDS regardless of pid.
    """
    if not _SANDBOX_PARENT.exists():
        return
    cutoff = time.time() - _STALE_AFTER_SECONDS
    for child in _SANDBOX_PARENT.iterdir():
        try:
            owner_pid = int(child.name.split("-", 1)[0])
        except (ValueError, IndexError):
            owner_pid = None
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            _wipe(child); continue
        if owner_pid is not None and not _pid_alive(owner_pid):
            _wipe(child); continue


#: Environment every provider in this directory hands its CLI child, by exact name.
#: An allowlist, not a denylist: these providers run CLIs unattended -- `claude -p
#: --permission-mode bypassPermissions`, `codex exec --sandbox workspace-write` with
#: `approval_policy="never"` -- and `subprocess.run` without `env=` hands the whole
#: parent environment to them. On CI that includes GITHUB_TOKEN, cloud credentials, and
#: whatever else the pipeline holds. `cwd=` sandboxes the filesystem and does nothing at
#: all for environment variables.
#:
#: A denylist would need an edit every time CI gains a secret and would be silently
#: wrong in between. This fails closed: a variable a CLI turns out to need is a visible
#: one-line addition here, while a leak is not visible anywhere.
ENV_NAMES = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TERM", "USER", "SHELL")


#: Prefixed variables that do not carry credentials or configuration but decide
#: *which backend answers*. A prefix match forwards them along with the API key, so
#: a runner that happens to export `ANTHROPIC_BASE_URL` or `CLAUDE_CODE_USE_BEDROCK`
#: silently grades a different service than the one the numbers are compared
#: against -- and nothing in the transcript would say so (#229 review).
#:
#: Dropped rather than allowed, and said out loud rather than dropped quietly: a
#: suite whose whole output is a comparison cannot let the thing being compared
#: move without telling anyone.
BACKEND_ROUTING_NAMES = frozenset({
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_API_URL",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
    "CLAUDE_CODE_SKIP_VERTEX_AUTH",
})


def child_env(*prefixes: str, tmpdir: Path | None = None) -> dict:
    """The environment for a CLI child: :data:`ENV_NAMES` plus the namespaces named in
    ``prefixes`` -- the credential and configuration that particular CLI is entitled to,
    and nothing else the runner happens to be carrying.

    Shared rather than per-provider so the three CLI-spawning providers here cannot
    drift: the first version of this lived in `claude_provider` alone, and its siblings
    kept inheriting everything (constructorfabric/studio#229 review).

    Two things the prefix match is not allowed to do. It does not forward the
    variables in :data:`BACKEND_ROUTING_NAMES`, which would redirect the child to a
    different service while the run still reports as a measurement of this one. And
    when *tmpdir* is given, ``TMPDIR`` points inside it rather than at the runner's,
    so a child that writes scratch files leaves them in the sandbox that is wiped
    rather than in a directory that outlives the run.

    ``HOME`` is deliberately **not** remapped. These children are real CLIs
    authenticating with real credentials, and their credential store lives under the
    runner's home; pointing it elsewhere does not sandbox the run, it ends it
    (#229 review).
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if (name in ENV_NAMES or (prefixes and name.startswith(prefixes)))
        and name not in BACKEND_ROUTING_NAMES
    }
    dropped = sorted(BACKEND_ROUTING_NAMES & set(os.environ))
    if dropped:
        print(
            f"cf-ux: not forwarding {', '.join(dropped)} to the graded CLI -- these "
            "choose which service answers, and the run reports as a measurement of "
            "the default one",
            file=sys.stderr,
        )
    if tmpdir is not None:
        scratch = Path(tmpdir) / ".tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        env["TMPDIR"] = str(scratch)
    return env


#: Minimum length a forwarded value must have before it is worth redacting. Short
#: values -- a one-letter LANG, an empty key -- would otherwise match everywhere and
#: turn a readable diagnostic into a wall of markers.
_REDACT_MIN_LENGTH = 8

REDACTED = "[redacted]"


def redact_secrets(text: str, env: dict) -> str:
    """Replace any credential value in ``env`` that appears in ``text``.

    These providers hand their CLI a real API key and then return that CLI's stderr,
    stdout tail and result text as promptfoo metadata, where it is stored and read by
    people. A CLI that echoes its key in an error message -- "invalid x-api-key:
    sk-ant-..." is an ordinary shape for one -- would put it in the report.

    Only the values of credential-ish names are redacted, not every forwarded variable:
    PATH and HOME appear in legitimate diagnostics constantly, and blanking them would
    destroy the thing a reader needs. Longest first, so a value containing another is
    not left half-substituted.
    """
    if not text:
        return text
    secrets = sorted(
        (value for name, value in env.items()
         if len(value) >= _REDACT_MIN_LENGTH
         and any(mark in name.upper() for mark in ("KEY", "TOKEN", "SECRET", "PASSWORD"))),
        key=len, reverse=True,
    )
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    return text

#: The ceiling every diagnostic string these providers return is held to. Named
#: here because all three of them return one, and a cap that lives in one
#: provider is a cap the other two quietly do without.
MAX_DIAGNOSTIC_CHARS = 500


def safe_head(text: str, env: dict, limit: int = MAX_DIAGNOSTIC_CHARS) -> str:
    """Redact, *then* cut -- never the other way round.

    `redact_secrets` replaces whole values. Cutting first can land inside a
    credential, and what survives is a prefix it no longer recognises: a key
    straddling the boundary left its opening characters in the metadata,
    redacted nowhere. Redacting first replaces the whole value, so the cut then
    falls in text that carries no secret at all.
    """
    return redact_secrets(text, env)[:limit]


def safe_tail(text: str, env: dict, limit: int = MAX_DIAGNOSTIC_CHARS) -> str:
    """`safe_head` from the other end, and for the same reason."""
    return redact_secrets(text, env)[-limit:]



def _new_sandbox_path() -> Path:
    _SANDBOX_PARENT.mkdir(parents=True, exist_ok=True)
    return _SANDBOX_PARENT / f"{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        timeout=180, check=False, env=env,
    )
    if proc.returncode != 0:
        raise SandboxError(
            f"cmd failed: {' '.join(cmd)}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )


def _git_bootstrap(root: Path) -> None:
    _run(["git", "init", "-q", "-b", "main"], cwd=root)
    _run(
        ["git", "-c", "user.email=ux@test", "-c", "user.name=ux",
         "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=root,
    )


def _local_cfs_init(project_root: Path) -> None:
    bootstrap = (
        "import sys\n"
        f"sys.path.insert(0, {str(STUDIO_SCRIPTS)!r})\n"
        "from studio.commands import init as _init\n"
        f"_init.CACHE_DIR = __import__('pathlib').Path({str(REPO_ROOT)!r})\n"
        "_init._prompt_kit_install_flag = lambda interactive: False\n"
        "from studio.cli import main\n"
        "sys.argv = ['studio', 'init', '--yes',\n"
        "            '--migrate-from-cypilot=no',\n"
        "            '--update-legacy-studio=no']\n"
        "raise SystemExit(main())\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", bootstrap],
        cwd=project_root, capture_output=True, text=True,
        timeout=300, check=False,
    )
    if proc.returncode != 0:
        raise SandboxError(
            "local cfs init failed:\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )


def _local_generate_agents(project_root: Path, agent: str) -> None:
    bootstrap = (
        "import sys\n"
        f"sys.path.insert(0, {str(STUDIO_SCRIPTS)!r})\n"
        "from studio.cli import main\n"
        f"sys.argv = ['studio', 'generate-agents', '--agent', {agent!r}, '-y']\n"
        "raise SystemExit(main())\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", bootstrap],
        cwd=project_root, capture_output=True, text=True,
        timeout=180, check=False,
    )
    if proc.returncode != 0:
        raise SandboxError(
            f"generate-agents --agent {agent} failed:\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )


def _init_sandbox(root: Path) -> None:
    _git_bootstrap(root)
    _local_cfs_init(root)
    _local_generate_agents(root, "claude")
    _local_generate_agents(root, "openai")


@contextlib.contextmanager
def sandbox() -> Iterator[Path]:
    _install_handlers_once()
    _sweep_stale_sandboxes()

    shared = os.environ.get("CF_UX_SHARED_SANDBOX")
    if shared:
        path = Path(shared)
        if not path.exists():
            raise SandboxError(f"CF_UX_SHARED_SANDBOX does not exist: {path}")
        yield path
        return

    path = _new_sandbox_path()
    path.mkdir(parents=True, exist_ok=False)
    _LIVE_SANDBOXES.add(path)
    keep = os.environ.get("CF_UX_KEEP_SANDBOX") == "1"
    try:
        _init_sandbox(path)
        yield path
    finally:
        if keep:
            print(f"[cf-ux] kept sandbox: {path}", file=sys.stderr)
            _LIVE_SANDBOXES.discard(path)  # do not wipe on atexit
        else:
            _wipe(path)
            _LIVE_SANDBOXES.discard(path)
