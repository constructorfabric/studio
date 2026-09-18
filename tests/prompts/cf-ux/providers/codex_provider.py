"""promptfoo native python provider — OpenAI Codex CLI in a cf-studio sandbox."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from _sandbox import SandboxError, sandbox

CODEX_BIN = "codex"
CALL_TIMEOUT_S = 850  # under promptfoo worker timeout (900s)

#: A slug, not a promise: the set a `codex` account is entitled to changes, and
#: this one is only the cheapest of that set as of 2026-09-18 (`codex` reports
#: gpt-5.6-sol, -terra, -luna, gpt-6-astra, gpt-5.5). Its predecessor here,
#: `gpt-5.4-mini`, had been withdrawn, and every codex case in the pilot errored
#: with `The 'gpt-5.4-mini' model is not supported when using Codex with a
#: ChatGPT account.` -- half the suite red for a reason that had nothing to do
#: with the skill under test. When that happens again, re-pick from `codex` and
#: move the date; `CF_UX_CODEX_MODEL` is the escape hatch meanwhile.
#:
#: Not shared with `studio.commands.agents._MODEL_MATRIX`, which names OpenAI
#: slugs for generated agent configs, and deliberately so: that matrix maps a
#: *tier* a user chose onto a model, while this picks the cheapest thing that
#: can run a test. One constant serving both would make a pilot cost decision
#: change what users' agents run. They do go stale together, though, so a
#: withdrawal found here is worth checking there.
DEFAULT_MODEL = os.environ.get("CF_UX_CODEX_MODEL", "gpt-5.6-sol")
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
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=CALL_TIMEOUT_S, check=False,
        stdin=subprocess.DEVNULL,
    )
    duration = time.monotonic() - started

    if proc.returncode != 0:
        return {
            "error": f"codex exited {proc.returncode}: {proc.stderr.strip()[:500]}",
            "metadata": {"duration_s": round(duration, 2)},
        }

    # `codex exec` streams progress to stderr; final agent message goes to stdout.
    output_text = proc.stdout.strip()
    metadata: dict[str, Any] = {
        "duration_s": round(duration, 2),
        "sandbox": str(cwd),
        "stderr_tail": proc.stderr.strip()[-500:] if proc.stderr else None,
    }
    return {"output": output_text, "metadata": metadata}
