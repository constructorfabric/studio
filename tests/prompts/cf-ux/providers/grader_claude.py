"""Lightweight Claude grader for promptfoo llm-rubric assertions.

`claude -p --disable-slash-commands` — uses the existing Claude Code auth
(keychain / subscription) but disables every skill so cf can't hijack the
grader. This is the *judge*; it must reason about the response, not act.

`--bare` is avoided because it requires ANTHROPIC_API_KEY (refuses keychain).
"""

from __future__ import annotations

import os
import subprocess

from _sandbox import MAX_DIAGNOSTIC_CHARS, child_env, redact_secrets, safe_head
import time
from typing import Any

CLAUDE_BIN = "claude"

#: Namespaces the grader's `claude` CLI is entitled to -- the same as the provider it
#: grades for. It inherited the whole runner environment until #229's review.
_CHILD_ENV_PREFIXES = ("ANTHROPIC_", "CLAUDE_")
CALL_TIMEOUT_S = 180

# The grader must reason carefully about which of the five cf-skill
# structural states a response demonstrates. Haiku at low effort was
# flaky on edge cases (e.g. judging a clear Sub-Agent Approval Gate
# menu as "not an analyze run" because it lacked the literal word
# "analyze"). Sonnet 4.6 at medium effort gives stable judgments at
# a small per-run cost. Override via env if a leaner grader works for
# your scenario set.
GRADER_MODEL = os.environ.get("CF_UX_GRADER_MODEL", "claude-sonnet-4-6")
GRADER_EFFORT = os.environ.get("CF_UX_GRADER_EFFORT", "medium")


#: This file's own ceiling, shorter than the providers': a grader's stderr is a
#: rubric failure, not a transcript, and 400 has always been enough of it.
_STDERR_CHARS = MAX_DIAGNOSTIC_CHARS - 100

# Derived rather than written, because "shorter than the providers'" was a claim in a
# comment and nothing held it to it: lowering `MAX_DIAGNOSTIC_CHARS` for an unrelated
# size budget would have left this one larger than the cap it documents itself as
# staying under, with every test still green (#229 review).
assert _STDERR_CHARS < MAX_DIAGNOSTIC_CHARS


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    started = time.monotonic()
    # One mapping for spawning and for redacting, as in the other two providers.
    env = child_env(*_CHILD_ENV_PREFIXES)
    try:
        proc = subprocess.run(
            [
                CLAUDE_BIN, "-p",
                "--model", GRADER_MODEL,
                "--effort", GRADER_EFFORT,
                "--disable-slash-commands",
                "--output-format", "text",
                "--max-budget-usd", "0.20",
                prompt,
            ],
            capture_output=True, text=True,
            timeout=CALL_TIMEOUT_S, check=False,
            stdin=subprocess.DEVNULL,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"grader timed out after {CALL_TIMEOUT_S}s"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"grader unexpected: {type(exc).__name__}: {exc}"}

    duration = time.monotonic() - started
    if proc.returncode != 0:
        return {
            "error": f"grader exited {proc.returncode}: "
                     f"{safe_head(proc.stderr.strip(), env, _STDERR_CHARS)}",
            "metadata": {"duration_s": round(duration, 2)},
        }
    return {
        "output": proc.stdout.strip(),
        "metadata": {"duration_s": round(duration, 2)},
    }
