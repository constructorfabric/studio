"""promptfoo native python provider — OpenAI Codex CLI in a cf-studio sandbox."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from _sandbox import (SandboxError, child_env, isolated_home, redact_secrets, safe_head,
                      safe_tail, sandbox)

CODEX_BIN = "codex"
#: Where this CLI keeps its credential, relative to its home -- or under `CODEX_HOME`.
_CODEX_CREDENTIAL = ".codex/auth.json"


def _codex_credential() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return (Path(codex_home) if codex_home else Path.home() / ".codex") / "auth.json"

#: Namespaces the `codex` CLI is entitled to. It runs with `approval_policy="never"`,
#: so it acts without asking -- and inherited the whole runner environment until
#: constructorfabric/studio#229's review pointed out that only its sibling was fixed.
_CHILD_ENV_PREFIXES = ("OPENAI_", "CODEX_")
CALL_TIMEOUT_S = 850  # under promptfoo worker timeout (900s)

DEFAULT_MODEL = os.environ.get("CF_UX_CODEX_MODEL", "gpt-5.4-mini")
# "minimal" is incompatible with image_gen / web_search tools — use "low".
DEFAULT_EFFORT = os.environ.get("CF_UX_CODEX_EFFORT", "low")
# Shrink context window from default 400k to keep cold-start fast and cheap.
DEFAULT_CONTEXT_WINDOW = int(os.environ.get("CF_UX_CODEX_CONTEXT", "128000"))

# By default we DO NOT disable competing plugins — the cf-skill is expected
# to survive in aggressive multi-skill environments where other plugins
# (e.g. superpowers' "You MUST" brainstorming) try to outrank it. The pilot
# treats it as a real UX failure if cf loses skill selection in this case.
# Override via env if you want to isolate cf for debugging: e.g.
#   CF_UX_CODEX_DISABLE_PLUGINS="superpowers@claude-plugins-official"
_env_override = os.environ.get("CF_UX_CODEX_DISABLE_PLUGINS", "")
DISABLED_PLUGINS = [p.strip() for p in _env_override.split(",") if p.strip()]


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    started = time.monotonic()
    try:
        with sandbox() as cwd:
            return _invoke(prompt, cwd, started)
    except SandboxError as exc:
        return {"error": f"sandbox setup failed: {exc}"}
    except subprocess.TimeoutExpired:
        return {"error": f"codex timed out after {CALL_TIMEOUT_S}s"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"unexpected: {type(exc).__name__}: {exc}"}


def _invoke(prompt: str, cwd: Path, started: float) -> dict:
    # Explicit skill invocation: Codex uses `$cf <prompt>`.
    invoked = f"$cf {prompt}"
    cmd = [
        CODEX_BIN, "exec",
        "--skip-git-repo-check",
        "--sandbox", "workspace-write",
        "-m", DEFAULT_MODEL,
        "-c", 'approval_policy="never"',
        "-c", f'model_reasoning_effort="{DEFAULT_EFFORT}"',
        "-c", f"model_context_window={DEFAULT_CONTEXT_WINDOW}",
    ]
    # Disable competing plugins so cf-skill wins skill selection.
    for plugin in DISABLED_PLUGINS:
        cmd += ["-c", f'plugins."{plugin}".enabled=false']
    cmd.append(invoked)
    # Built once: the same mapping spawns the child and defines what must not come back
    # out of it, exactly as in `claude_provider`. Applying the allowlist to all three
    # providers and the redaction to one of them was the same half-fix twice (#229).
    home = isolated_home(cwd, _codex_credential(), _CODEX_CREDENTIAL)
    env = child_env(*_CHILD_ENV_PREFIXES, tmpdir=cwd, home=home)
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=CALL_TIMEOUT_S, check=False,
        stdin=subprocess.DEVNULL, env=env,
    )
    duration = time.monotonic() - started

    if proc.returncode != 0:
        return {
            "error": f"codex exited {proc.returncode}: "
                     f"{safe_head(proc.stderr.strip(), env)}",
            "metadata": {"duration_s": round(duration, 2)},
        }

    # `codex exec` streams progress to stderr; final agent message goes to stdout.
    output_text = proc.stdout.strip()
    metadata: dict[str, Any] = {
        "duration_s": round(duration, 2),
        "sandbox": str(cwd),
        # An isolated run is a different measurement (no competing plugins), so
        # the report says which one this was.
        "home": "isolated" if home is not None else "runner",
        "stderr_tail": (safe_tail(proc.stderr.strip(), env)
                        if proc.stderr else None),
    }
    # Redacted, not capped, as in `claude_provider`: the whole answer is what gets
    # graded, and it is model-authored (#229 review).
    return {"output": redact_secrets(output_text, env), "metadata": metadata}
