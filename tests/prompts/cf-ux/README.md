# cf-skill UX scenario evals (promptfoo pilot)

End-to-end UX tests for the `cf` skill, running real `claude` and `codex` CLIs
inside isolated, freshly-`cfs init`-ed `tempfile.mkdtemp()` sandboxes built
from the **local repo source** (not `.bootstrap/`, not GitHub).

## Prerequisites

| Needs | Why, and the part that bites |
|---|---|
| **Node >= 22.22** | promptfoo's own `engines.node`. An older one fails inside npx talking about the package, not about node. |
| A node `make` can **spawn** | Under nvm's lazy loader `node` is a *shell function*: an interactive shell answers `node --version` while `make`, which runs recipes in `sh`, finds no program at all. Put a real one on PATH for the command: `PATH="$NVM_DIR/versions/node/v22.22.2/bin:$PATH" make test-prompts`. |
| `claude`, `codex`, `cfs` on PATH | The pilot drives the real CLIs. `cfs` comes from `make install-proxy`. |
| Both CLIs **logged in** | Providers inherit only `ANTHROPIC_*`/`CLAUDE_*` and `OPENAI_*`/`CODEX_*`; there is no key to pass in. |
| A codex model the account **has** | Slugs are withdrawn over time. A stale default costs all 8 codex cases with a 400 in a table cell. |

`make test-prompts` checks what is checkable locally first — the binaries are
present, node can run promptfoo, the codex model is one the account has. See
`preflight.py`, which reads `codex`'s own model cache and never touches the
network. Run it on its own with `make check-prompt-tests`.

It does **not** verify that either CLI is logged in: that costs a call to find
out, and a preflight that spends money to say the run may proceed is not a
preflight. A logged-out CLI passes here and fails once the run starts.

## Run

```bash
make test-prompts              # preflight, then the full pilot
make test-prompts-view         # HTML report
```

Or directly, skipping the preflight:

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
| `CF_UX_SHARED_SANDBOX=/path` | Reuse a pre-initialized sandbox; skip setup/teardown. **Point this only at a throwaway directory** — the Claude provider runs with `--permission-mode bypassPermissions` and writes wherever this says. |
| `CF_UX_KEEP_SANDBOX=1` | Keep the sandbox after the run; print its path. The isolated home below is removed even then: it links to the credential store. |
| `CF_UX_ISOLATED_HOME=1` | Give each CLI child a home inside the sandbox holding only a link to its credential (`~/.claude/.credentials.json`, `~/.codex/auth.json`). **A different measurement, not a stricter run** — see below. Declines out loud when the file is absent, which on macOS (Keychain) it usually is. |
| `CF_UX_CLAUDE_MODEL` / `CF_UX_CLAUDE_EFFORT` | Override the claude model and reasoning effort. |
| `CF_UX_CODEX_MODEL` / `CF_UX_CODEX_EFFORT` / `CF_UX_CODEX_CONTEXT` | Override the codex model, reasoning effort and context window. Set the model when the default slug is withdrawn — `codex` lists what the account may use. |
| `CF_UX_GRADER_MODEL` / `CF_UX_GRADER_EFFORT` | Override the LLM-rubric judge. |
| `CF_UX_SKIP_CLAUDE_VERSION_CHECK=1` | Run on a `claude` older than the floor in `preflight.py` (`CLAUDE_MIN`). Only `1` skips; any other value is named on stderr and the check runs. A skip is printed too, since verdicts from that run rest on an output shape nobody measured on that CLI. |
| `CF_UX_CODEX_DISABLE_PLUGINS` | Comma-separated `name@marketplace` to disable, for isolation debugging only — by default the skill is expected to win against competing plugins. |

Defaults live beside the code they configure: `providers/*.py`. This table says
they exist and what they are for, not what today's value is.

**What the CLI children actually receive.** These providers spawn their CLIs unattended
— `claude -p --permission-mode bypassPermissions`, `codex exec` with
`approval_policy="never"` — so they do **not** inherit this process's environment. Each
gets an allowlist built by `_sandbox.child_env()`: the process basics (`PATH`, `HOME`,
locale, `TMPDIR`, …) plus one credential namespace — `ANTHROPIC_`/`CLAUDE_` for the
Claude provider and the grader, `OPENAI_`/`CODEX_` for Codex.

Two consequences worth knowing:

- `CF_UX_*` variables in this table are read by the **Python parent**, not forwarded to
  the CLI. Setting one affects how the provider is invoked, not what the CLI sees.
- A variable a CLI genuinely needs must be added to `ENV_NAMES` or covered by that
  provider's prefix tuple. The symptom of a missing one is the CLI failing to start or
  to authenticate, not a silent fallback.

Anything the CLI prints back — stderr, the stdout tail, the withheld result — is passed
through `_sandbox.redact_secrets()` before it reaches promptfoo metadata, so a CLI that
echoes its own key in an error does not put it in a stored report.

### What the sandbox is, and what it is not

The per-run directory is where the child **works**. It is not a wall the child cannot
see past. `--permission-mode bypassPermissions` switches off the approval prompts, and
an ungated `Read`, `Write` or `Bash` resolves `~` and absolute paths against the real
filesystem of the user running the suite. Codex gets an OS boundary on writes from
`--sandbox workspace-write`; the Claude invocation has no counterpart, so it leans on
three narrower things:

- **Deny rules**, passed inline with `--settings`, close the runner's home
  (`Read(//<home>/**)`, `Edit(//<home>/**)`, and the `~` spellings) to the child's
  tools. Deny rules hold in every permission mode, `bypassPermissions` included; this
  was measured on claude 2.1.281 for `Read`, `Write`, and `cat`, `head`, `find`,
  `grep -r` and `ls` of the path in `Bash`. That release has no separate `Glob` or
  `Grep` tool -- the model is offered `Bash` for both -- so those two are covered by
  the `Bash` measurement. `preflight.py` refuses a CLI older than that release. The
  rules match on what a call *names*, so a path reached through indirection is not
  caught. Every refusal comes back as `permission_denials` in the metadata and as a
  `WARNING` in the log — a run in which the model reached for the runner's home is a
  finding for this suite, not noise.
- **`CF_UX_ISOLATED_HOME=1`** points the child's `HOME` at a directory inside the
  sandbox that holds only a link to its credential, and drops `CLAUDE_CONFIG_DIR` /
  `CODEX_HOME`. Programs that find their keys through `~` (`ssh`, `gh`, `aws`) then
  find nothing. It also removes the runner's plugins, hooks and user-level settings —
  and this pilot deliberately measures the skill *against* competing plugins (see
  `CF_UX_CODEX_DISABLE_PLUGINS`). An isolated run is therefore a different
  measurement; every result carries `home: runner | isolated` so the two are never
  compared as one. Linux only in practice: macOS keeps claude's credential in the
  Keychain, and the mode declines there rather than run unauthenticated. Off by
  default for both reasons.
- **The redaction and the allowlist** above, which are about what leaves the child and
  what enters it, not about where it can reach.

What none of this covers, and what a person running `make test-prompts` is accepting:
the child runs as you, with your plugins loaded, and without asking. A change to a
scenario in this directory, or to the skill text it invokes, is code that runs on the
machine of whoever runs the suite next. Review such changes as you would a script.
Nor are the child's descendants reaped: a process the CLI detaches outlives it and
can still be running while the sandbox is removed. Teardown refuses to follow a
symlink it finds, but a directory swapped for one *during* the removal is a race it
does not win.
The OS-level boundary that would change this — Claude Code's own sandbox (Seatbelt
on macOS, bubblewrap + socat on Linux, and it *disables itself* when those are
missing) or a container — is tracked as a follow-up, not shipped here.

## Layout

```
tests/prompts/cf-ux/
├── promptfooconfig.yaml
├── providers/
│   ├── _sandbox.py          — tmpdir + local cfs init context manager
│   ├── claude_provider.py   — claude -p, bypassPermissions, stream-json
│   ├── codex_provider.py    — codex exec, approval=never, workspace-write
│   └── grader_claude.py     — claude -p --disable-slash-commands (judge)
├── preflight.py             — node version + codex model entitlement, pre-run
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
- **`skill_call_inputs`**, the raw inputs, so the verdict can be checked — capped
  at 500 chars like every other diagnostic here, since a model decides how long
  they are.

`test_a_bare_cf_in_an_unrelated_field_still_counts` pins the trade. If the real
key is ever established, that test is where it gets renegotiated.

Three more shapes are errors for the same reason — there is no answer to grade,
or no trace to trust:

| Shape | Why it cannot be scored |
|---|---|
| No terminal `result` event | Nothing to grade, and the transcript is incomplete. Names both causes: the `--max-budget-usd` ceiling reached mid-turn ends the stream exactly as an unhonoured `--output-format` does. |
| `result` with a non-success `subtype` | The turn stopped short (`error_max_turns`, `error_during_execution`), so `result` holds a fragment, not an answer — even when the skill did load. An *absent* subtype is not treated this way: an unfamiliar shape should not manufacture failures. |
| A line that will not parse | Counted in `unparsed_lines` rather than dropped silently, because a lost line can be a lost `tool_result` and the verdict above is read off exactly those. |

`skill_state` has four values:

| State | Meaning | Graded? |
|---|---|---|
| `ran` | The `cf` router was invoked and its call came back clean. | yes |
| `bypassed` | A `cf-*` workflow ran **directly**, the router never did. Studio produced the answer, so it is worth grading — but no gate, menu or routing decision happened, which is what this suite measures. Counted as a pass by promptfoo's own tally, so the metadata and the `WARNING` in the log are where a bypass is actually visible. | yes |
| `absent` | No `Skill` call at all — *and* no error mark in the raw text. The mark is checked first, so a transcript that made no call but whose prose contains `<error>Execute skill: cf</error>` is `failed`, not `absent`. | no |
| `failed` | A `Skill` call that is neither of the above: it named nothing recognizable, came back an error, or came back not at all. | no |

Order matters, and deliberately so. A router that was **tried and failed**
outranks a bypass, because "the router failed" is a finding about the router and
"the router was never invoked" is not a softer version of it — it is a different
and false statement. That holds two ways: `<error>Execute skill: cf</error>`
anywhere in the transcript is `failed` before anything else is considered, and
so is an unambiguous `cf` call that came back an error or did not come back.
The workflow is still named in `skills_invoked`, so the bypass is ranked rather
than lost.

"Unambiguous" carries weight there: a call naming `cf` *among other candidates*
is the documented false positive, and letting that outrank a bypass would hide a
real one behind an unrelated error. Only a call that names `cf` and nothing else
suppresses the bypass — and when the bypass is reported despite some `cf` match
existing, the detail says "no unambiguous `cf` call" rather than "never
invoked".

No `Skill` call at all is `absent` before the rest. `skill_match_other_candidates` is populated for `ran`
and for `bypassed`, and is empty whenever the verdict rested on a single name.

A bypass needs the *whole* call to name `cf-` identifiers and nothing else. `_invoked_names` reports every identifier-shaped string at any depth, so a rival skill carrying a `cf-` name in an unrelated field would otherwise read as one — the loose match the name matcher exists to avoid, widened across a whole prefix.

Metadata: `skill_state` (above), `skills_invoked` (the
names), `skill_call_inputs` (those inputs, for when a name did not
resolve — capped at 500 chars like every other diagnostic here, since a model
decides their length), `claude_code_version` (what the CLI called itself; the
verdict rests on an output shape that was measured rather than promised, and
nothing pins the installed CLI), `skill_match_other_candidates` (above),
`unparsed_lines`, `permission_denials` (the tool calls the deny rules refused —
tool and input, the input redacted and capped like any other model-authored
field), and `unscored_output` — the answer that was withheld
from the grader, kept for diagnosis. Every return *that reached the CLI*, answer
or error, carries `duration_s`, `sandbox` and `home` (`runner` or `isolated`,
see above); a failure before the sandbox
exists — setup error, setup timeout — has no sandbox path to name. The
missing-`result` case adds `events_seen` and `last_event_type`, which is what
tells a budget ceiling apart from a format regression without reading the tail
by hand.

Expect errors, not just failures, if the CLI's invocation contract changes
again. That is the intended behaviour: an error says the suite could not
measure, which is different from Studio behaving badly, and the two were
previously indistinguishable.

## Current baseline (pilot)

8 scenarios × 2 providers = 16 cases, ~1.5 min wall-clock at the configured
concurrency (measured 2026-09-18; the table below predates several scenarios).

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
  findings above are driven to green. Run it with `CF_UX_ISOLATED_HOME=1`
  there: a runner has no plugins worth measuring against and does have
  credentials worth keeping out of reach.
- Give the Claude child the OS boundary its sibling already has: Claude Code's
  own sandbox via `--settings '{"sandbox": {"enabled": true}}'`. Needs a
  measurement on macOS (Seatbelt) first, and a preflight check on Linux for
  `bwrap` and `socat` — measured on 2.1.281, the sandbox disables itself with a
  stderr warning when either is missing, even with
  `allowUnsandboxedCommands: false`, so enabling it without the check would
  report a boundary that was not there.
