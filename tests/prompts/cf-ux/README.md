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
| `CF_UX_SHARED_SANDBOX=/path` | Reuse a pre-initialized sandbox; skip setup/teardown. **Point this only at a throwaway directory** — the Claude provider runs with `--permission-mode bypassPermissions`, which is safe against the per-run temp sandbox it normally builds, but writes wherever this says. |
| `CF_UX_KEEP_SANDBOX=1` | Keep the sandbox after the run; print its path. |

## Layout

```
tests/prompts/cf-ux/
├── promptfooconfig.yaml
├── providers/
│   ├── _sandbox.py          — tmpdir + local cfs init context manager
│   ├── claude_provider.py   — claude -p, bypassPermissions, stream-json
│   ├── codex_provider.py    — codex exec, approval=never, workspace-write
│   └── grader_claude.py     — claude -p --disable-slash-commands (judge)
└── README.md
```

## A run that did not load the skill is an error, not a score

The Claude provider decides from the tool-call trace whether the `cf` skill
actually executed, and returns a promptfoo **error** when it did not — before
the rubric ever sees the text.

This matters because the failure is silent and looks like success. Skill
*execution* asks for permission and `-p` has nobody to ask, so without
`--permission-mode bypassPermissions` the skill is denied, the agent answers the
request directly, and the answer is plausible enough for the rubric to pass it.
The suite then reports confidently on an agent that never loaded Studio. Any
measurement built on that — question counts, gate behaviour, UX assertions —
describes the fallback path.

So the check is positive rather than a substring search over the answer: one
`Skill` tool-use event whose input names `cf`, and a non-error `tool_result`
bound to *that* call's id. Each half of that matters.

- The name is compared **whole**, after dropping any `plugin:` namespace. The
  prompt is `/cf <request>`, so the argument text carries "cf" on every
  scenario here — under substring containment a competing skill that quoted the
  user message back counted as this one running.
- The result must belong to the cf call. "Some `Skill` call succeeded" and
  "some call named cf" can both hold while the cf call is the one that errored.
- No result at all is not a non-error result. A trace cut off after the call is
  refused, not read as a success.

### One false positive is accepted on purpose

Which key holds the skill name is not part of any stable contract, so **every
identifier-shaped value in the tool input is a candidate, at any depth** — and
an input that is not a dict at all is scanned rather than refused, for the same
reason. That means a rival skill invoked with some unrelated field whose value
happens to be `cf` — `{"command": "superpowers:brainstorming", "mode": "cf"}` —
reads as this skill running. `plugin:cf` in that position does too, since the
comparison happens after the namespace is dropped.

This is a deliberate trade, not an oversight. Narrowing the scan to a fixed set
of name keys would close it and open a worse hole:

| | every value (today) | narrowed to name keys |
|---|---|---|
| rival skill with a bare `cf` field | rare false **pass** | correct |
| the real key is not in the list | correct | certain false **failure**, on every run |

Nobody here has run the CLI, so the input's real shape is unknown — the fixtures
use `{"command": …}` because someone chose it, not because it was measured. Under
that uncertainty the scan errs toward recall, which is also why it descends into
nested values: a name one level down that went unfound would produce the certain
failure rather than the rare pass.

Two things keep the accepted case from being silent:

- **`skill_match_other_candidates`**, and a matching stderr warning, listing the
  other identifiers whenever the matched call's input named more than one. That
  is the shape a false pass takes, so it is reported per run rather than left
  for whoever thinks to look. It is an **over-approximation, named for what it
  observes rather than what it suspects**: it cannot tell a wrong-field match
  from a correct call that merely carries a second identifier, so a genuine
  `{"command": "cf", "mode": "auto"}` is listed too. Narrowing it would need the
  very knowledge whose absence created the trade. It is a flag, not a verdict —
  the run is still scored.
- **`skill_call_inputs`**, the raw inputs verbatim, so the verdict can be checked.

`test_a_bare_cf_in_an_unrelated_field_still_counts` pins the trade. If the real
key is ever established, that test is where it gets renegotiated.

Three more shapes are errors for the same reason — there is no answer to grade,
or no trace to trust:

| Shape | Why it cannot be scored |
|---|---|
| No terminal `result` event | Nothing to grade, and the transcript is incomplete. Names both causes: the `--max-budget-usd` ceiling reached mid-turn ends the stream exactly as an unhonoured `--output-format` does. |
| `result` with a non-success `subtype` | The turn stopped short (`error_max_turns`, `error_during_execution`), so `result` holds a fragment, not an answer — even when the skill did load. An *absent* subtype is not treated this way: an unfamiliar shape should not manufacture failures. |
| A line that will not parse | Counted in `unparsed_lines` rather than dropped silently, because a lost line can be a lost `tool_result` and the verdict above is read off exactly those. |

Metadata: `skill_state` (`ran` / `failed` / `absent`), `skills_invoked` (the
names), `skill_call_inputs` (those inputs verbatim, for when a name did not
resolve), `skill_match_other_candidates` (above), `unparsed_lines`, and
`unscored_output` — the answer that was withheld
from the grader, kept for diagnosis. Every return *that reached the CLI*, answer
or error, carries `duration_s` and `sandbox`; a failure before the sandbox
exists — setup error, setup timeout — has no sandbox path to name. The
missing-`result` case adds `events_seen` and `last_event_type`, which is what
tells a budget ceiling apart from a format regression without reading the tail
by hand.

Expect errors, not just failures, if the CLI's invocation contract changes
again. That is the intended behaviour: an error says the suite could not
measure, which is different from Studio behaving badly, and the two were
previously indistinguishable.

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

- Assert directly on sub-agent dispatches from the tool-call trace, the way
  the `Skill` invocation now is (would replace several llm-rubric blocks
  with deterministic checks). The stream-json parsing this needs is already
  in `claude_provider.py`; what is missing is the per-scenario assertions.
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
