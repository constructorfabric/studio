---
version: 0.1.0
significant_changes:
  - version: 0.1.0
    date: 2026-09-28
    summary: Initial FEATURE draft for Studio CLI off-by-default engagement (issue #144), covering the always-injected pre-check, literal explicit-signal match, the appended one-line suggestion, the new `[routing]` posture config table, generation-time config baking, atomic posture-change regeneration, and passive drift detection.
---

# Feature: Studio CLI — Off by Default

<!-- toc -->

- [1. Feature Context](#1-feature-context)
  - [1.1 Overview](#11-overview)
  - [1.2 Purpose](#12-purpose)
  - [1.3 Actors](#13-actors)
  - [1.4 References](#14-references)
- [2. Actor Flows (CDSL)](#2-actor-flows-cdsl)
  - [Engage or Answer Directly](#engage-or-answer-directly)
  - [Change Engagement Posture](#change-engagement-posture)
  - [Inspect Posture and Drift](#inspect-posture-and-drift)
- [3. Processes / Business Logic (CDSL)](#3-processes--business-logic-cdsl)
  - [Evaluate Explicit Signal](#evaluate-explicit-signal)
  - [Bake Engagement Posture Into Injected Block](#bake-engagement-posture-into-injected-block)
  - [Detect Posture Drift](#detect-posture-drift)
- [4. States (CDSL)](#4-states-cdsl)
  - [Engagement Posture](#engagement-posture)
- [5. Definitions of Done](#5-definitions-of-done)
  - [No Unconditional Interception](#no-unconditional-interception)
  - [Literal Explicit-Signal Match](#literal-explicit-signal-match)
  - [Direct Answer for Concrete Work](#direct-answer-for-concrete-work)
  - [Appended, Non-Blocking Suggestion](#appended-non-blocking-suggestion)
  - [No Disable-and-Retype Loop](#no-disable-and-retype-loop)
  - [Configurable Posture Surface](#configurable-posture-surface)
  - [Bounded Idle Cost](#bounded-idle-cost)
  - [Discoverability Preserved](#discoverability-preserved)
  - [Guidance and Behavior Agreement](#guidance-and-behavior-agreement)
  - [Generation-Time Posture Baking](#generation-time-posture-baking)
  - [Atomic Posture-Change Regeneration](#atomic-posture-change-regeneration)
  - [Passive Drift Detection](#passive-drift-detection)
  - [Always-On Escape Hatch](#always-on-escape-hatch)
- [6. Acceptance Criteria](#6-acceptance-criteria)
- [7. Open Implementation Questions](#7-open-implementation-questions)
- [8. Applicability](#8-applicability)
- [Additional Context (optional)](#additional-context-optional)

<!-- /toc -->

## 1. Feature Context

- [ ] `p1` - **ID**: `cpt-studio-featstatus-studio-cli-off-by-default`

### 1.1 Overview

This feature turns Studio's routing precondition from an unconditional interception of every prompt into a decision made once per turn, cheaply, before any Studio module loads. By default (`engagement_mode = "opt-in"`), a prompt in a Studio-enabled repository is answered directly unless it carries an explicit signal — the `cf` entry point, `cf ` as the first token, or a recognized cf-* skill alias as the first token. A project or user that wants today's always-on behavior keeps it with one documented `core.toml` setting.

### 1.2 Purpose

GitHub issue #144 ("Studio CLI — Off by Default: Opt Into the Full Flow Instead of Intercepting Every Prompt") reports that Studio's routing precondition is installed unconditionally into a project's root `AGENTS.md`/`CLAUDE.md`, so every prompt is routed through `IntentRouting` regardless of size. `guides/USAGE-GUIDE.md` best practice 7 already tells users to "use the smallest workflow that still preserves control," but the runtime does not follow its own advice: the default behavior routes every request, and the cost is paid twice — once on the way in (tokens/latency spent routing a request that was never going to use the flow) and once on the way out (the user notices, disables Studio, and restates the request). This feature makes engagement a decision rather than a default: answer direct work directly, enter the full flow on an explicit signal, and make the runtime default and the written guidance agree.

**Relationship to issue #128**: #128 makes the flow autonomous *once engaged* (fewer menus/questions/gates). This feature is about whether the flow engages at all. Neither subsumes the other; both are needed.

**Decision locus — why the pre-check cannot live in `IntentRouting`**: `IntentRouting` (`skills/studio/modules/routing/root-intent-routing.md`) is a `.core/` module gated on `REQUIRE cf root routing is active`, which is only true after `StudioInstructionsMemoryGate` has already loaded Studio's instruction files for the turn. Putting the engagement decision there would mean Studio has already paid the module-load cost the decision is supposed to avoid. The pre-check therefore has to live in the text that is *always* injected regardless of engagement — the `ROOT_AGENTS_PIPELINE_INSTRUCTION` constant (`skills/studio/scripts/studio/constants.py`) baked into the root `AGENTS.md`/`CLAUDE.md` managed block by `_compute_managed_block()` (`skills/studio/scripts/studio/commands/init.py`) — because that is the only text an agent reads before any Studio module load. This placement is a revision of an initial design that considered `IntentRouting` and was corrected after this bootstrap-ordering conflict was found; the correction is recorded here as the feature's actual design, not as an ADR-level debate.

**Forward-looking note (depends on issue #143 landing)**: once hook-based session routing (`cpt-studio-feature-hook-based-session-routing`, issue #143) ships, the per-harness hook payload — not the always-injected file text — should be the thing that decides whether the routing instruction is delivered for a turn at all, which would let a `HookInstalled` harness skip injecting the pre-check text into the read-every-turn file entirely. This feature's file-injection-text approach does not require #143 to be merged first; it is designed to sit inside the same injected block #143 already manages for `routing_mode == file` harnesses. As of this revision, #143 (PR #252) is `APPROVED` and `MERGEABLE` but still unmerged — see Section 7, item (d).

**Requirements**: no unconditional interception of a default prompt (FR1); explicit engagement via `cf` or an equivalent unambiguous opt-in (FR2); straight, unmediated answers for direct work (FR3); a cheap, never-blocking suggestion rather than a gate (FR4); no disable-and-retype loop (FR5); a discoverable, configurable posture (FR6); bounded per-turn cost while idle (FR7); preserved discoverability of the full flow (FR8); and agreement between written guidance and runtime default behavior (FR9) — together with efficiency, compatibility, discoverability, and consistency non-functional requirements, all as stated verbatim in GitHub issue #144 (constructorfabric/studio) since no PRD FR/NFR IDs are yet registered for this issue.

**Principles**: `cpt-studio-principle-occams-razor` (the pre-check is a plain string comparison against text already loaded, not a new abstraction or classifier) and `cpt-studio-principle-zero-harm` (opt-in by default, with `always-on` as a true escape hatch, so adopting this feature imposes no forced behavior change on a team that wants today's routing).

### 1.3 Actors

| Actor | Role in Feature |
|-------|-----------------|
| Prompt author | Types a message into a Studio-enabled repository; receives either a direct answer (with an optional one-line suggestion) or the full engaged flow, depending on whether the message carries an explicit signal. |
| Project maintainer | Sets `[routing].engagement_mode` in `core.toml` and runs the command that regenerates the injected block so the setting takes effect; reads the passive drift warning surfaced by `cfs doctor`/`cfs info`. |

### 1.4 References

- **PRD**: [PRD.md](../PRD.md)
- **Design**: [DESIGN.md](../DESIGN.md)
- **CLI contract**: [specs/cli.md](../specs/cli.md) — the existing `generate-agents` / `agents` / `doctor` / `info` command contracts this feature extends
- **Dependencies**: `cpt-studio-feature-hook-based-session-routing` (issue #143 — gives the routing decision "somewhere to live that is not an unconditional line in a file the agent always reads"; this feature's Section 1.2 forward-looking note and Section 7 item (b) depend on it, but this feature's own file-injection-text design does not require it merged first), `cpt-studio-feature-core-infra` (config resolution and the `MARKER_START`/`MARKER_END` managed-block mechanism this feature's config-baking and drift detection reuse), `cpt-studio-feature-agent-integration` (the `cfs generate-agents` pipeline and per-harness support matrix this feature's config-baking and regeneration hook into)
- **Source issue**: GitHub issue #144, constructorfabric/studio — "Studio CLI — Off by Default: Opt Into the Full Flow Instead of Intercepting Every Prompt"
- **Related issue**: GitHub issue #128 — complementary, not overlapping (see Section 1.2)
- **Precedent**: `[ui].skill_invocation_art_enabled` in `core.toml` (issue #145 / PR #166) — the config-surface pattern this feature's `[routing]` table reuses exactly; see `schemas/core-config.schema.json`'s `ui` object and `skills/studio/modules/ui/skill-invocation-art.md`
- **Out of scope**:
  - Prescribing the classifier beyond the literal-match rule in `cpt-studio-algo-studio-cli-off-by-default-evaluate-signal` (design freedom preserved per the source issue).
  - Prescribing the opt-in keyword beyond the existing `cf` entry point and recognized cf-* skill aliases.
  - Prescribing where the posture setting is stored beyond `core.toml` (`.cf-workspace.toml` was already ruled out for the sibling `[ui]` precedent as scoped to multi-repo federation with no generic toggle field, and the same reasoning applies here).
  - Editing `guides/CONFIGURATION.md` or `guides/USAGE-GUIDE.md` in this FEATURE-authoring pass. Both guides need updates — `CONFIGURATION.md` to document the new `[routing]` table (closing the doc gap the `[ui]` precedent left open, per `cpt-studio-dod-studio-cli-off-by-default-guidance-agreement`), and `USAGE-GUIDE.md` best practice 7 to state the same default this feature ships — but those edits are a later CODE-phase deliverable, not part of this FEATURE document.
  - Any per-harness hook-payload equivalent of config-baking for `routing_mode == hook` harnesses (see Section 7, item (b)); this feature's regeneration scope is `routing_mode == file` harnesses only, matching `cpt-studio-dod-hook-based-session-routing-fallback`'s file-fallback path.
  - Adding a new domain-model entity for the `[routing]` config table. `DESIGN.md`'s existing `Config` entity ("Structured TOML in `config/` directory — core.toml + per-kit configs") already covers this the same way it covers `[ui].skill_invocation_art_enabled`, which received no dedicated `DESIGN.md` entity of its own.

## 2. Actor Flows (CDSL)

### Engage or Answer Directly

- [ ] `p1` - **ID**: `cpt-studio-flow-studio-cli-off-by-default-engage-or-answer`

**Actor**: Prompt author

**Success Scenarios**:
- A small, concrete request ("fix this typo", "what does this function do") is answered directly, with no workflow or mode selection, in a repository at the default `engagement_mode = "opt-in"`.
- Typing `cf` alone, or a message starting with `cf ` as its first token, or a message starting with a recognized cf-* skill alias as its first token, engages the full flow (`IntentRouting` and downstream Studio modules) exactly as it does today.
- A direct answer to a request that would clearly benefit from the full flow carries one appended line naming `cf` as an option, with no separate message and no second prompt.
- A repository configured with `engagement_mode = "always-on"` behaves exactly as Studio does today: every prompt is routed through `IntentRouting`, with zero functional change from pre-feature behavior.

**Error Scenarios**:
- The injected pre-check text itself is missing or stale (drift) — see the `Inspect Posture and Drift` flow; a prompt author sees this only indirectly, as `engagement_mode` behaving inconsistently with what `core.toml` says.

**Steps**:
1. [ ] - `p1` - Prompt author sends a message in a Studio-enabled repository - `inst-prompt-author-sends`
2. [ ] - `p1` - Algorithm: evaluate the message against the literal explicit-signal rule using `cpt-studio-algo-studio-cli-off-by-default-evaluate-signal` - `inst-run-evaluate-signal`
3. [ ] - `p1` - **IF** the injected block's baked `engagement_mode` is `always-on` - `inst-if-always-on`
   1. [ ] - `p1` - Proceed to `IntentRouting` exactly as today, ignoring the explicit-signal evaluation result - `inst-always-on-route`
4. [ ] - `p1` - **ELSE IF** the message matches the explicit-signal rule - `inst-elseif-signal-matches`
   1. [ ] - `p1` - Proceed to `IntentRouting` and the full engaged flow - `inst-signal-route`
5. [ ] - `p1` - **ELSE** - `inst-else-no-signal`
   1. [ ] - `p1` - Answer the request directly with no workflow selection, no mode gate, and no routing preamble - `inst-answer-directly`
   2. [ ] - `p1` - **IF** the request would clearly benefit from the full flow, per a relevance judgment left to Section 7 item (a) - `inst-if-relevant`
      1. [ ] - `p1` - Append one line to the end of the direct answer suggesting `cf` for the full flow - `inst-append-suggestion`
   3. [ ] - `p1` - **RETURN** the direct answer (with the optional appended suggestion) as the complete turn - `inst-return-direct-answer`
6. [ ] - `p1` - **RETURN** control to `IntentRouting`'s existing menu/match behavior when routed - `inst-return-routed`

### Change Engagement Posture

- [ ] `p1` - **ID**: `cpt-studio-flow-studio-cli-off-by-default-change-posture`

**Actor**: Project maintainer

**Success Scenarios**:
- Maintainer sets `[routing].engagement_mode` in `core.toml` (directly or via a config-set command) and the injected root `AGENTS.md`/`CLAUDE.md` block is regenerated synchronously as one atomic action, with no separate manual "now run generate-agents" step.
- Maintainer runs `cfs generate-agents` after any other config or harness change; the currently configured `engagement_mode` is baked into the regenerated block alongside every other value that command already manages.

**Error Scenarios**:
- Regeneration fails after a posture change; the failure is surfaced loudly (non-zero exit, explicit error) rather than left as silently stale injected text.

**Steps**:
1. [ ] - `p1` - Maintainer sets `engagement_mode` to `opt-in` or `always-on` under `[routing]` in `core.toml` - `inst-maintainer-sets-mode`
2. [ ] - `p1` - Algorithm: bake the newly configured posture into the injected block using `cpt-studio-algo-studio-cli-off-by-default-bake-posture` - `inst-run-bake-posture`
3. [ ] - `p1` - **IF** the regeneration step fails - `inst-if-regen-fails`
   1. [ ] - `p1` - Fail loudly with the underlying error rather than leaving the previous block's baked posture silently in place - `inst-fail-loud`
4. [ ] - `p1` - **ELSE** - `inst-else-regen-succeeds`
   1. [ ] - `p1` - **RETURN** the regenerated block reflecting the new `engagement_mode` as the sole source of the runtime pre-check's baked posture - `inst-return-regenerated`

### Inspect Posture and Drift

- [ ] `p2` - **ID**: `cpt-studio-flow-studio-cli-off-by-default-inspect`

**Actor**: Project maintainer

**Success Scenarios**:
- Maintainer runs `cfs doctor` or `cfs info` and, when the persisted `core.toml` `engagement_mode` and the value baked into the injected block agree, sees no drift warning at all.
- Maintainer runs `cfs doctor` or `cfs info` after a hand edit of the injected block (or of `core.toml`) that left the two out of sync; a single passive, non-blocking line names the mismatch and the fix command (regenerate), without gating or failing the command.

**Error Scenarios**:
- None. Drift detection is passive by design (`cpt-studio-dod-studio-cli-off-by-default-drift-detection`); it never blocks `cfs doctor`/`cfs info` or any other command.

**Steps**:
1. [ ] - `p1` - Maintainer runs `cfs doctor` or `cfs info` - `inst-maintainer-runs-doctor`
2. [ ] - `p1` - Algorithm: detect drift between `core.toml`'s `engagement_mode` and the injected block's baked value using `cpt-studio-algo-studio-cli-off-by-default-detect-drift` - `inst-run-detect-drift`
3. [ ] - `p1` - **IF** drift is detected - `inst-if-drift`
   1. [ ] - `p1` - EMIT one passive, non-blocking warning line naming the mismatch and the regeneration fix command - `inst-emit-drift-warning`
4. [ ] - `p1` - **ELSE** - `inst-else-no-drift`
   1. [ ] - `p1` - **RETURN** the command's existing output unchanged - `inst-return-unchanged`

## 3. Processes / Business Logic (CDSL)

### Evaluate Explicit Signal

- [ ] `p1` - **ID**: `cpt-studio-algo-studio-cli-off-by-default-evaluate-signal`

**Input**: The current user message text, plus the static list of current cf-* skill alias names already baked into the injected block by `cpt-studio-algo-studio-cli-off-by-default-bake-posture` (this text is already loaded as part of the always-injected block — evaluating this algorithm requires no additional module load or corpus scan).

**Output**: A boolean — whether the message carries an explicit engagement signal.

**Steps**:
1. [ ] - `p1` - Normalize the message for comparison (leading/trailing whitespace only; no case folding, no fuzzy matching, no intent classification) - `inst-normalize-message`
2. [ ] - `p1` - **IF** the normalized message is exactly `cf` - `inst-if-exact-cf`
   1. [ ] - `p1` - **RETURN** true - `inst-return-true-exact`
3. [ ] - `p1` - **IF** the normalized message's first token is `cf` (i.e. the message starts with `cf ` followed by more text) - `inst-if-cf-prefix`
   1. [ ] - `p1` - **RETURN** true - `inst-return-true-prefix`
4. [ ] - `p1` - **IF** the normalized message's first token exactly string-matches an entry in the static cf-* skill alias list already inline in the injected block (a plain prefix comparison against the baked list — no `WorkflowResolution` call, no workflow-corpus scan, no runtime skill discovery) - `inst-if-alias-token`
   1. [ ] - `p1` - **RETURN** true - `inst-return-true-alias`
5. [ ] - `p1` - **RETURN** false - `inst-return-false`

**Note (staleness)**: the static alias list is only as current as the last `cfs generate-agents` run. Adding a new cf-* skill without regenerating means that skill's alias will not yet match at step 4 until regeneration. This is the same class of staleness `engagement_mode` itself already accepts (Section 3, `cpt-studio-algo-studio-cli-off-by-default-bake-posture`'s Input note), and it is covered by the existing passive drift-detection mechanism (`cpt-studio-dod-studio-cli-off-by-default-drift-detection`, `cfs doctor`/`cfs info`) rather than by a new detection mechanism.

### Bake Engagement Posture Into Injected Block

- [ ] `p1` - **ID**: `cpt-studio-algo-studio-cli-off-by-default-bake-posture`

**Input**: The current `[routing].engagement_mode` value resolved from `core.toml` (default `opt-in` when the table or key is absent), and the current cf-* skill alias list resolved via `WorkflowResolution` at generation time — this is the one point in this feature where a `WorkflowResolution` corpus load is acceptable, because `cfs generate-agents` runs once per invocation, not once per turn; it is not called from the per-turn `cpt-studio-algo-studio-cli-off-by-default-evaluate-signal` check.

**Output**: An updated root `AGENTS.md`/`CLAUDE.md` managed block whose pre-check text encodes both the resolved posture and a static list of current cf-* skill alias names.

**Steps**:
1. [ ] - `p1` - Resolve `engagement_mode` from `[routing]` in `core.toml`, defaulting to `opt-in` when the table or key is absent - `inst-resolve-engagement-mode`
2. [ ] - `p1` - **IF** `engagement_mode` is present and is not one of `"opt-in"` or `"always-on"` - `inst-if-engagement-mode-invalid`
   1. [ ] - `p1` - FAIL loudly (non-zero exit, explicit error naming the invalid value and the two accepted values) rather than defaulting or resolving to no opinion, mirroring the existing `severity` enum's "an unrecognised value fails the run" validation pattern (`schemas/core-config.schema.json`) - `inst-fail-invalid-engagement-mode`
3. [ ] - `p1` - Resolve the current cf-* skill alias list via `WorkflowResolution` - `inst-resolve-alias-list`
4. [ ] - `p1` - Extend `_compute_managed_block()`'s output to encode the resolved `engagement_mode` value and the resolved static alias list directly in the injected text, alongside the existing `ROOT_AGENTS_PIPELINE_INSTRUCTION` line, so no runtime `core.toml` read and no runtime `WorkflowResolution` call is required to evaluate the pre-check - `inst-encode-mode-in-block`
5. [ ] - `p1` - **FOR EACH** managed file already covered by the existing root-injection mechanism (root `AGENTS.md`, root `CLAUDE.md`) - `inst-for-each-managed-file`
   1. [ ] - `p1` - Write or update the managed block via the existing `MARKER_START`/`MARKER_END` mechanism - `inst-write-managed-block`
   2. [ ] - `p1` - **NOTE**: this is the single shared write for every harness whose routing delivery mode is `file` — per `cpt-studio-feature-hook-based-session-routing`'s "two files, one resource" rule, there is no per-harness managed block to update separately; every file-mode harness reads the one block written here - `inst-shared-block-note`
6. [ ] - `p1` - **RETURN** the regenerated block set as the new source of truth for the runtime pre-check (both posture and alias list) until the next regeneration - `inst-return-baked-block`

### Detect Posture Drift

- [ ] `p2` - **ID**: `cpt-studio-algo-studio-cli-off-by-default-detect-drift`

**Input**: The persisted `[routing].engagement_mode` value in `core.toml` and the `engagement_mode` value currently baked into the injected managed block.

**Output**: A drift verdict (match / mismatch) and, when mismatched, a one-line description plus fix command.

**Steps**:
1. [ ] - `p1` - Read the persisted `engagement_mode` from `core.toml` (default `opt-in` when absent) - `inst-read-persisted-mode`
2. [ ] - `p1` - Read the `engagement_mode` value currently encoded in the injected managed block, using the same `MARKER_START`/`MARKER_END` scan `cpt-studio-algo-core-infra-inject-root-agents` already performs - `inst-read-baked-mode`
3. [ ] - `p1` - **IF** the two values differ - `inst-if-values-differ`
   1. [ ] - `p1` - **RETURN** mismatch, naming both values and the regeneration command that resolves it - `inst-return-mismatch`
4. [ ] - `p1` - **ELSE** - `inst-else-values-match`
   1. [ ] - `p1` - **RETURN** match, with no output - `inst-return-match`

## 4. States (CDSL)

### Engagement Posture

- [ ] `p2` - **ID**: `cpt-studio-state-studio-cli-off-by-default-posture`

**States**: OptIn, AlwaysOn

**Initial State**: OptIn

**Transitions**:
1. [ ] - `p1` - **FROM** OptIn **TO** AlwaysOn **WHEN** maintainer sets `[routing].engagement_mode = "always-on"` and regeneration succeeds - `inst-optin-to-alwayson`
2. [ ] - `p1` - **FROM** AlwaysOn **TO** OptIn **WHEN** maintainer sets `[routing].engagement_mode = "opt-in"` (or removes the key/table) and regeneration succeeds - `inst-alwayson-to-optin`

## 5. Definitions of Done

### No Unconditional Interception

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-no-interception`

At `engagement_mode = "opt-in"` (the default), the system **MUST NOT** route a prompt in a Studio-enabled repository into `IntentRouting` or any other cf-* workflow unless the prompt matches the explicit-signal rule.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-engage-or-answer`

**Touches**:
- Entities: (none new — see Section 1.4's "Out of scope" note on `Config`)

### Literal Explicit-Signal Match

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-explicit-signal`

The system **MUST** treat a message as carrying an explicit engagement signal if and only if it is exactly `cf`, starts with `cf ` as its first token, or starts with a recognized cf-* skill alias as its first token — a literal-only match with no fuzzy or natural-language intent detection.

**Implements**:
- `cpt-studio-algo-studio-cli-off-by-default-evaluate-signal`

### Direct Answer for Concrete Work

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-direct-answer`

When no explicit signal is present and `engagement_mode = "opt-in"`, the system **MUST** answer the request directly, with no workflow selection, no mode gate, and no routing preamble emitted.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-engage-or-answer`

### Appended, Non-Blocking Suggestion

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-suggestion-surface`

Where a direct-answer turn would clearly benefit from the full flow, the system **MUST** append a single line naming `cf` to the end of that same direct answer — never as a separate message, a menu, or a second prompt — and this suggestion **MUST NOT** block the answer or require a further reply to proceed.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-engage-or-answer`

**Constraints**: the exact relevance threshold that decides when the suggestion fires is intentionally left open — see Section 7, item (a).

### No Disable-and-Retype Loop

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-no-restatement`

The system **MUST NOT** require a user to disable Studio and restate a request in order to get a direct answer: at `engagement_mode = "opt-in"`, a non-signaling prompt already receives a direct answer without any disable step.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-engage-or-answer`

### Configurable Posture Surface

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-posture-config`

The system **MUST** expose the engagement posture as `[routing].engagement_mode` (`"opt-in"` | `"always-on"`, default `"opt-in"`) in `core.toml`, following exactly the config-surface pattern already established by `[ui].skill_invocation_art_enabled` (schema location, additivity, default-driven absence handling).

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-change-posture`

**Touches**:
- DB: `core.toml` (`[routing]` table)

### Bounded Idle Cost

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-bounded-cost`

When Studio is not engaged for a turn, the system **MUST** trigger zero cf-* module loads and zero `EMIT_MENU` calls beyond the pre-check evaluation itself; the per-turn routing decision **MUST NOT** call `WorkflowResolution` or otherwise load the workflow corpus to make itself. Both the `engagement_mode` value and the cf-* skill alias list the pre-check consults **MUST** already be inline in the always-injected block text (baked at generation time by `cpt-studio-algo-studio-cli-off-by-default-bake-posture`), so the pre-check's cost is limited to a string comparison against text the agent has already loaded, not an additional read.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-engage-or-answer`

### Discoverability Preserved

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-discoverability`

The system **MUST** keep the `cf` entry point discoverable from ordinary use (e.g. the appended one-line suggestion, and documentation surfaced per `cpt-studio-dod-studio-cli-off-by-default-guidance-agreement`) even though it is no longer the unconditional default path.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-engage-or-answer`

### Guidance and Behavior Agreement

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-guidance-agreement`

`guides/USAGE-GUIDE.md` best practice 7 ("use the smallest workflow that still preserves control") and `guides/CONFIGURATION.md`'s documentation of `[routing].engagement_mode` **MUST** state the same default behavior the runtime ships (opt-in by default), closing the doc gap the `[ui]` precedent left open (PR #166 never documented `[ui]` in `CONFIGURATION.md`). These edits are a later CODE-phase deliverable — see Section 1.4's "Out of scope" note — but the requirement to make the edit is recorded here.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-change-posture`

### Generation-Time Posture Baking

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-config-baking`

Because the always-injected pre-check text cannot execute a runtime `core.toml` lookup or a runtime `WorkflowResolution` call, `cfs generate-agents` **MUST** bake both the currently configured `engagement_mode` value and the current static list of cf-* skill alias names directly into the generated managed block at generation time; a changed posture setting or a newly added cf-* skill **MUST** take effect only by regenerating that block, not by a per-session runtime read of `core.toml` or a per-turn `WorkflowResolution` call. If `engagement_mode` is present in `core.toml` but is not one of `"opt-in"` or `"always-on"` (e.g. a typo or a non-string value), `cfs generate-agents` **MUST** fail loudly and name the invalid value rather than defaulting silently or baking an unrecognized value into the block, consistent with the existing `severity` enum's "an unrecognised value fails the run" validation precedent (`schemas/core-config.schema.json`).

**Implements**:
- `cpt-studio-algo-studio-cli-off-by-default-bake-posture`

### Atomic Posture-Change Regeneration

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-posture-change-ux`

Setting `engagement_mode` (directly in `core.toml` or via a config-set command) **MUST** synchronously trigger regeneration of the injected managed block as one atomic action, with no separate manual "now run generate-agents" step; a regeneration failure **MUST** fail loudly rather than silently leave stale injected text in place.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-change-posture`

### Passive Drift Detection

- [ ] `p2` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-drift-detection`

At points that already read the managed block (`cfs doctor`, `cfs info`), the system **MUST** detect drift between `core.toml`'s `engagement_mode` and the value baked into the injected text (for example, from a hand edit), reusing the existing `MARKER_START`/`MARKER_END` tamper-detection pattern, and **MUST** surface it as a passive, one-line, non-blocking warning naming the fix command. This same passive mechanism is the accepted way of surfacing staleness in the baked cf-* skill alias list (Section 3, `cpt-studio-algo-studio-cli-off-by-default-evaluate-signal`'s staleness note) when a new cf-* skill has been added without a regeneration — no separate detection mechanism is introduced for the alias list. Drift detection **MUST NOT** become a blocking gate.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-inspect`
- `cpt-studio-algo-studio-cli-off-by-default-detect-drift`

### Always-On Escape Hatch

- [ ] `p1` - **ID**: `cpt-studio-dod-studio-cli-off-by-default-always-on-compat`

With `engagement_mode = "always-on"`, the system **MUST** reproduce today's unconditional `IntentRouting` behavior with zero functional change — a true escape hatch for teams that want current behavior, satisfying NFR-Compatibility.

**Implements**:
- `cpt-studio-flow-studio-cli-off-by-default-engage-or-answer`

## 6. Acceptance Criteria

- [ ] AC1 — A small, concrete request in a Studio-enabled repository at the default `engagement_mode = "opt-in"` is answered directly, with no workflow or mode selection.
- [ ] AC2 — Typing `cf` (or a message starting with `cf ` or a recognized cf-* skill alias as its first token) with the same request engages the full flow.
- [ ] AC3 — No path requires a user to disable Studio and restate a request to receive a direct answer.
- [ ] AC4 — A one-line suggestion to use the flow, where offered, is appended to the direct answer, never blocks it, and never requires a second prompt.
- [ ] AC5 — Setting `[routing].engagement_mode = "always-on"` in `core.toml` and regenerating restores today's unconditional-routing behavior with a single documented setting.
- [ ] AC6 — A non-engaging turn triggers zero cf-* module loads (including zero `WorkflowResolution` calls) and zero `EMIT_MENU` calls beyond the pre-check evaluation itself, because both `engagement_mode` and the cf-* skill alias list the pre-check consults are already baked inline into the always-injected block text (the structural, falsifiable proxy for "materially lower token cost" — no percentage baseline exists to compute against).
- [ ] AC7 — A user unfamiliar with `cf` can discover the flow from ordinary use (the appended suggestion line and the documentation updates tracked by `cpt-studio-dod-studio-cli-off-by-default-guidance-agreement`).
- [ ] AC8 — `guides/USAGE-GUIDE.md` best practice 7 and the default runtime behavior (opt-in) state the same thing about matching workflow weight to task size, once the CODE-phase documentation update lands.

## 7. Open Implementation Questions

These side-topics are deliberately left open. They **MUST** be resolved before or during implementation, not silently decided by this FEATURE document:

- [ ] **(a) Suggestion relevance threshold**: The one-line suggestion (`cpt-studio-dod-studio-cli-off-by-default-suggestion-surface`) must not fire on every direct answer or it becomes the new unwanted interruption, but no concrete relevance-threshold rule was specified during design. The exact rule for when a request "would clearly benefit" from the full flow is left to implementation.
- [ ] **(b) Hook-capable-harness regeneration equivalent**: `cpt-studio-algo-studio-cli-off-by-default-bake-posture`'s regeneration scope is `routing_mode == file` harnesses only (Section 1.4, out of scope). Hook-capable harnesses (`routing_mode == hook` per `cpt-studio-feature-hook-based-session-routing`) need an equivalent mechanism delivered via the hook payload rather than file regeneration, and that equivalent has not been designed.
- [ ] **(c) Non-Claude-Code explicit-signal conventions**: `cpt-studio-dod-studio-cli-off-by-default-explicit-signal`'s literal `cf`/cf-* alias rule was designed Claude-Code-centric. What exactly counts as "explicit signal" for harnesses with their own native slash-command conventions (e.g. Cursor, Copilot) is untested and left open.
- [ ] **(d) Relationship to issue #143 / PR #252**: As of this revision, #143 (PR #252) is `APPROVED` and `MERGEABLE` but still unmerged. This feature's design — particularly the file-injection-text approach in `cpt-studio-algo-studio-cli-off-by-default-bake-posture` — does not require #143 merged first and can proceed in parallel. Full realization of Section 1.2's forward-looking hook-payload note and item (b) above do depend on #143 landing. **Correction**: an earlier revision of this item cited `.prs/252/status.md`'s "two open human-judgment flags" (Windsurf/Cursor fallback marker permanence; the compile-harness algorithm) as still open — that status snapshot is stale. `hook-based-session-routing.md`'s current text already resolves both with explicit, dated decisions (its v0.7.0 changelog entry and dedicated Section 1.4 subsection for the Windsurf marker-permanence decision; its v0.3.0 changelog entry correcting ADR-0016's "Cursor has no hook support" claim). Neither blocks this feature's implementation.
- [ ] **(e) Migration for pre-existing projects (no `[routing]` table yet)** — **not yet decided, flagged for owner review**: Every already-initialized Studio project's `core.toml` predates this feature and has no `[routing]` table. `cpt-studio-algo-studio-cli-off-by-default-bake-posture` step 1 currently resolves an absent table/key to `opt-in`, meaning any such project's *next* regeneration for any unrelated reason would silently flip its live behavior from today's unconditional `IntentRouting` engagement to `opt-in` direct-answering, with no config change the maintainer ever made and no notice. This directly contradicts the feature's own no-surprises goal (Section 1.2, FR5) in the other direction. Two candidate resolutions, neither chosen here: (i) treat an absent `[routing]` table as equivalent to `always-on` for regeneration purposes, reserving the true `opt-in` default for `cfs init` on genuinely new projects only; or (ii) keep the `opt-in` default for absent-table projects too, but print a one-time, visible notice at the first regeneration that transitions a project from "no table" to a baked value, so the change is disclosed rather than silent. This choice **MUST NOT** be made silently by an implementer — it changes runtime behavior for every existing Studio user.
- [ ] **(f) Failure/rollback/concurrency semantics for the persist-then-bake write — not yet decided, flagged for owner review**: `cpt-studio-flow-studio-cli-off-by-default-change-posture` persists `engagement_mode` to `core.toml` *before* baking it into the managed block; if the bake/regeneration step then fails, the document specifies only that the command "fails loudly" — it never states whether the already-persisted `core.toml` value is rolled back, left in place pending manual retry, or automatically re-applied on the next successful `cfs generate-agents` run. Nor does it address what happens if two config-change operations, or a config-change and an unrelated `cfs generate-agents` run (e.g. one triggered by `cpt-studio-feature-hook-based-session-routing`'s own reconciliation), race against the same shared `core.toml` and the same shared, project-wide managed block. No locking, ordering, or last-writer-wins policy is specified. This is a genuine gap in the design, not an implementation detail — a maintainer who runs a posture change to urgently restore `always-on` routing during an incident could get a "success" persisted in config while every session keeps running the stale value, with no automatic correction path.
- [ ] **(g) Test methodology for the per-turn precheck is undefined**: `cpt-studio-algo-studio-cli-off-by-default-evaluate-signal` is not executed as compiled code — it is natural-language instruction text that an LLM harness reads and follows inside the always-injected `AGENTS.md`/`CLAUDE.md` block. Conventional unit/integration tests (as apply to `cpt-studio-algo-studio-cli-off-by-default-bake-posture` and `-detect-drift`, which are ordinary code paths) cannot verify that an LLM harness reliably performs literal string matching rather than drifting into fuzzy/natural-language interpretation. No eval-harness, golden-transcript, or per-harness behavioral-compliance test approach is named anywhere in this document. Since this is the single behavior issue #144 exists to fix, and every acceptance criterion depending on it (AC1–AC4, AC7) is otherwise unverifiable as specified, a test methodology for this class of LLM-instruction-executed logic **MUST** be defined before or during implementation.

**Implementation status note**: as of this revision, no PR or code exists for issue #144 — this document is a design-only FEATURE spec, staged but uncommitted. Items (e), (f), and (g) above are pre-implementation design gaps surfaced for the feature owner's explicit decision, not defects in shipped behavior; they must not be resolved silently by whoever picks up implementation.

## 8. Applicability

This feature is a CLI/runtime behavior change: a per-turn pre-check evaluated inside already-injected instruction text, plus a `core.toml` config table and its generation-time baking. Per the checklist's CLI-command domain prioritization, ARCH, MAINT, and TEST are the priority domains for this feature; DATA and INT are secondary. The domains below are addressed explicitly rather than silently skipped.

- **ARCH** (priority): addressed throughout — the decision locus (Section 1.2), the config-baking algorithm, and the state machine in Section 4 are the architectural surface of this feature.
- **MAINT** (priority): addressed — the `[routing]` table reuses the exact `[ui].skill_invocation_art_enabled` pattern rather than inventing a new config convention, and drift detection reuses the existing `MARKER_START`/`MARKER_END` mechanism rather than a new one, minimizing new surface area to maintain.
- **TEST** (priority): addressed — Section 6's acceptance criteria are written as falsifiable, structural checks (module-load counts, literal-match cases, regeneration outcomes) rather than subjective judgments, per `cpt-studio-dod-studio-cli-off-by-default-bounded-cost` and AC6.
- **DATA** (secondary): Not applicable beyond the `[routing]` config table itself — no PII, no user-generated data, only a boolean-like enum toggle in `core.toml`.
- **INT** (secondary): addressed narrowly — this feature integrates with the existing `cfs generate-agents` pipeline (config-baking) and with `cfs doctor`/`cfs info` (drift detection); it introduces no new external integration surface.
- **SEC**: Not applicable. There is no authentication or authorization surface, and the config value is a plaintext local toggle with no secret material — this is the same reasoning `cpt-studio-feature-hook-based-session-routing`'s Section 8 uses for its installer command.
- **COMPL**: Not applicable because no regulated data is read, stored, or transmitted.
- **UX**: Not applicable as a *graphical*-UI checklist domain — there is no UI; output is CLI/terminal text using the existing CDSL menu/answer conventions. The feature's interaction-cost goals themselves (FR3–FR5, FR8) are covered as functional requirements and DoDs above, not re-litigated here as a UX checklist item.
- **OPS**: Not applicable — no infrastructure or deployment surface; this is local config and generated-file behavior only.
- **PERF**: Addressed, not skipped — NFR-Efficiency and AC6 are performance requirements for this feature, but they are measured structurally (module-load and `EMIT_MENU` counts) rather than by latency/throughput targets, per `cost_reduction_baseline`'s resolution that no percentage baseline exists to compute against.

## Additional Context (optional)

**Terminology carried over from the sibling feature**: this document uses `engagement_mode` values `opt-in` and `always-on` as the two serialized states of the `Engagement Posture` state machine (Section 4), mirroring the lifecycle-state / serialized-value vocabulary convention `cpt-studio-feature-hook-based-session-routing` establishes for `HarnessRoutingState`/`routing_mode`. No new entity is introduced in `DESIGN.md`; the `[routing]` table is a config surface under the existing `Config` entity, exactly as `[ui].skill_invocation_art_enabled` is.
