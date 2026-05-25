# cf-skill UX scenario evals (promptfoo pilot)

End-to-end UX tests for the `cf` skill, running real `claude` and `codex` CLIs
inside isolated, freshly-`cfs init`-ed `tempfile.mkdtemp()` sandboxes built
from the **local repo source** (not `.bootstrap/`, not GitHub).

## Run

```bash
cd tests/prompts/cf-ux
REQUEST_TIMEOUT_MS=900000 npx promptfoo@latest eval
npx promptfoo@latest view     # HTML report
```

Each scenario:
1. Creates `$TMPDIR/cf-ux-XXXXXX/`, `git init`, and runs the in-tree
   `studio.commands.init.cmd_init` with `CACHE_DIR` patched to repo root
   and the kit-install prompt stubbed out (no network calls).
2. Runs `cfs generate-agents --agent claude` and `--agent openai`.
3. Invokes `claude -p` or `codex exec` in that sandbox.
4. Tears the sandbox down (unless `CF_UX_KEEP_SANDBOX=1`).

A grader (`grader_claude.py` — `claude -p --disable-slash-commands`) drives
the `llm-rubric` asserts; sub-100ms text guards catch skill-load failures.

## Env knobs

| Env | Effect |
|---|---|
| `REQUEST_TIMEOUT_MS=900000` | promptfoo python-worker timeout (default 300s is too short for sandbox init + cold codex). |
| `CF_UX_SHARED_SANDBOX=/path` | Reuse a pre-initialized sandbox; skip setup/teardown. |
| `CF_UX_KEEP_SANDBOX=1` | Keep the sandbox after the run; print its path. |

## Layout

```
tests/prompts/cf-ux/
├── promptfooconfig.yaml
├── providers/
│   ├── _sandbox.py          — tmpdir + local cfs init context manager
│   ├── claude_provider.py   — claude -p, JSON output, returns metadata
│   ├── codex_provider.py    — codex exec, approval=never, workspace-write
│   └── grader_claude.py     — claude -p --disable-slash-commands (judge)
└── README.md
```

## Current baseline (pilot)

3 scenarios × 2 providers = 6 cases, ~3-4 min total wall-clock.

| Scenario | claude-code | codex |
|---|---|---|
| ADR routing → cf-generate inputs flow | ✅ | ❌ silently writes ADR file |
| Brainstorm topic → cf-brainstorm framing | ✅ | ❌ free-form ideation, no panel |
| Analyze missing artifact → refuse cleanly | ✅ | ✅ |

The codex failures are **real UX gaps**, not test miscalibration:
`cfs generate-agents --agent openai` produces `.codex/agents/*.toml` but
codex has no auto-routing layer equivalent to Claude Code's skill loader,
so the model defaults to free-agent behavior and ignores the cf flow.

## Known findings (audit-driven failing scenarios)

The pilot deliberately surfaces real UX gaps as failing tests rather
than green checkmarks the skill doesn't deserve. Current expected fails
on cheap models:

1. **Codex silently writes files on direct edit requests** (S1.F1,
   S5.F2). When the user says "Edit README.md and add a Quick Start
   section" or "Generate a complete ADR with sensible defaults", codex
   with `$cf` prefix loads the skill but the umbrella Anti-Improvisation
   Hard Rule + write-confirmation gate do not block — codex emits
   "Created README.md ..." or "Created the ADR at ...". Claude-Haiku
   catches the same scenarios via the Sub-Agent Approval Gate. Fix
   lives in `skills/studio/SKILL.md` (Anti-Improv rule needs explicit
   coverage of "any file write in a `{cf-studio-path}` project") and
   possibly in the proxy-workflow handshake for write tools.

2. **Grader can misread the Sub-Agent Approval Gate as plain "dispatch
   options"** (intermittent, S4.F1). The Haiku grader occasionally sees
   the gate's "Option 1 / Option 2" menu and judges it as implementation
   dispatch options rather than the canonical gate. Calibration issue,
   not a skill bug. Workaround: `CF_UX_GRADER_MODEL=claude-sonnet-4-6`,
   or rewrite the rubric to name the gate text more concretely.

These findings come from the cf-skill UX audit (`/cf analyze prompts ...`)
and drive the next skill-hardening iteration.

## Next steps

- Parse `claude -p --output-format stream-json` to capture tool-call
  traces and assert directly on `Skill` invocations / sub-agent
  dispatches (would replace several llm-rubric blocks with deterministic
  checks).
- Cover write-paths end-to-end (`cf-generate` actually creating an ADR
  after inputs are collected) with `--sandbox workspace-write` + per-
  test fresh sandbox.
- Add remaining audit Top 6-10 scenarios (CF_BYPASS context-sensitive
  parsing, AP-002 MEMORY_VALIDATION, plan.md never executes, S1.F6 /
  S1.F7 anti-improv + proxy regression).
- Add `make ux-quick` reusing one shared sandbox via
  `CF_UX_SHARED_SANDBOX` for fast iteration on assertion text.
- Wire into CI as a non-blocking job; promote to gating once the known
  findings above are driven to green.
