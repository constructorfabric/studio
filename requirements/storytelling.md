---
cf: true
type: requirement
name: Storytelling Methodology
version: 2.0
purpose: Pedagogical companion methodology for explanatory walkthroughs of artifacts, codebases, and documents — router + module loader
---

# Storytelling Methodology


<!-- toc -->

- [Execution Protocol (MUST NOT be bypassed)](#execution-protocol-must-not-be-bypassed)
- [Agent Instructions](#agent-instructions)
- [Router Contract](#router-contract)
- [Overview](#overview)
- [EXPLAIN_MODE Activation](#explainmode-activation)
- [Module loading](#module-loading)
- [Anti-Patterns](#anti-patterns)
- [Validation Checklist](#validation-checklist)

<!-- /toc -->

**Shared block**: The dispatching controller loads and follows `{cf-studio-path}/.core/requirements/storytelling-shared.md` as a prefix block before any phase-specific section below, then publishes the needed prompt text through `prompt_context_view`.

This file is the **router**. The full methodology is split across five files for compact runtime loading: this router (~200 lines) plus four modules under `{cf-studio-path}/.core/requirements/storytelling-*.md`. Sibling methodologies are single-file (`prompt-engineering.md`, `bug-finding.md`, `reverse-engineering.md`); the storytelling spec is split because its surface — multi-mode, multi-phase, optional export — is materially larger and would otherwise force chunked loading and reduced determinism guarantees.

## Execution Protocol (MUST NOT be bypassed)

⛔ **STOP** — if you are an agent and you have just loaded this methodology in response to an explain-style request, the **most common failure mode** is to skip the interactive discovery phase and emit a single-shot summary of the input. **This is forbidden.** Producing a flat "Change Summary" / "Document Overview" / "Here's what this is about" response WITHOUT running through the four E1 user-interaction gates (mode → disposition → audience → plan approval) violates the core methodology contract. See Anti-Pattern #0 below.

The mandatory execution sequence — each step MUST emit chat output and WAIT for user response before continuing:

1. **Phase E0** — pre-flight: input access resolution + existing-session scan + size guards
2. **Phase E1 gate 1** — emit the **6-mode resolution prompt** (numbered) and WAIT for user pick (number / name / Enter for suggested)
3. **Phase E1 gate 2** — emit the **artifact disposition prompt** (4 numbered options) and WAIT for user pick
4. **Phase E1 gate 3** — if audience not already explicit, emit the **7-option audience prompt** (numbered) and WAIT
5. **Phase E1 gate 4** — emit the **numbered plan with the 4-option approval menu** (Go / Edit / Pivot / Cancel) and WAIT for user pick
6. **Phase E2** — portion-by-portion delivery loop with the 7-slot navigation block; user advances each portion explicitly
7. **Phase E5** — wrap (plan exhaustion or user `wrap`)

Until the user has explicitly approved the plan at gate 4, the agent MUST NOT emit any portion content or summary of the input. The four E1 gates are mandatory user-interaction checkpoints — even when the user's initial prompt seems "clear" (e.g. specific PR URL + audience hint), the methodology runs the gates. Skipping any gate is a CRITICAL violation.

## Agent Instructions

ALWAYS open and follow this file WHEN the user requests explanation, presentation, walkthrough, teaching, review, onboarding, decision-walk, quiz, or change-impact analysis of any input.

ALWAYS open and follow `{cf-studio-path}/.core/requirements/execution-protocol.md` for workflow context.

WHEN this methodology is loaded:
- Set `EXPLAIN_MODE=true`
- Skip Phase 2 deterministic gate of `analyze.md`
- Skip Phase 3 standard semantic checklist of `analyze.md`
- Skip Phase 5 (Offer Next Steps) of `analyze.md` — Suggested Next Steps already covered by the Storytelling Output schema (running both would duplicate)
- Use the Storytelling Output schema (see `{cf-studio-path}/.core/requirements/storytelling-phases.md` Phase E5) in `analyze.md` Phase 4 instead of the standard schema
- Override `enforceRemediationPrompts`: do NOT emit `Fix Prompt` / `Plan Prompt`

WHEN loaded with `EXPLAIN_EXPORT=true` (via `generate.md` WHEN-rule on guide/README/package-export intent), additionally load `{cf-studio-path}/.core/requirements/storytelling-export.md` and write a Markdown package to disk instead of delivering portions in chat.

**MUST** ground every non-trivial claim in the input. **MUST NOT** invent facts beyond the input. **MUST silently skip** ungrounded claims — do NOT insert `[?]` markers in the methodology's narrative; do NOT push to the open-questions buffer for gaps the methodology itself notices. Open-questions buffer entries are created **only** in response to user-asked questions the input cannot answer.

**MUST** follow phases E0 → E5 in order. **MUST NOT** skip Discovery. **MUST NOT** skip the Strict-Context Boundary.

**MUST NOT** treat storytelling output as a validation report.

## Router Contract

```text
UNIT StorytellingActivation

PURPOSE:
  Route explain-style requests into the storytelling methodology with explicit
  controller-owned prompt loading.

WHEN:
  explain-style intent is detected

DO:
  REQUIRE this router is active
  REQUIRE controller has loaded `{cf-studio-path}/.core/requirements/execution-protocol.md`
  REQUIRE controller has loaded `{cf-studio-path}/.core/requirements/storytelling-shared.md`
  SET EXPLAIN_MODE = true

RULES:
  - MUST treat storytelling prompt assets as controller-owned prompt assets
  - MUST_NOT let prompt-consuming sub-agents reopen storytelling prompt files
    from disk
  - MUST deliver storytelling prompt content through `prompt_context_view`
    whenever a sub-agent participates in the session
```

```text
UNIT StorytellingExecutionSequence

PURPOSE:
  Make the mandatory E0-E5 interaction order explicit.

STATE:
  STORYTELLING_PHASE: e0 | e1_mode | e1_disposition | e1_audience | e1_plan | e2 | e5 | done
    default: e0

DO:
  SET STORYTELLING_PHASE = e0
  REQUIRE Phase E0 pre-flight completes before any answer-style content
  SET STORYTELLING_PHASE = e1_mode
  EMIT numbered mode prompt
  WAIT user.reply
  STOP_TURN

RULES:
  - MUST_NOT emit portion content or summary before plan approval resolves
  - MUST run disposition resolution after mode resolution and before audience
    resolution
  - MUST run audience resolution before plan approval whenever the audience is
    not already explicit
  - MUST enter Phase E2 only after the numbered plan-approval gate resolves
  - MUST enter Phase E5 only after Phase E2 completes or the user requests wrap
  - MUST keep the four E1 gates as separate user-interaction boundaries
  - MUST treat skipped gates as a critical contract failure
```

```text
UNIT StorytellingModuleLoading

PURPOSE:
  Define which storytelling modules the controller loads.

DO:
  REQUIRE controller loads `{cf-studio-path}/.core/requirements/storytelling-phases.md`
  REQUIRE controller loads `{cf-studio-path}/.core/requirements/storytelling-modes.md`
  REQUIRE controller loads `{cf-studio-path}/.core/requirements/storytelling-preferences.md`
  IF EXPLAIN_EXPORT == true:
    REQUIRE controller loads `{cf-studio-path}/.core/requirements/storytelling-export.md`

RULES:
  - MUST load only the router-required modules for the active mode
  - MUST_NOT speculatively load unrelated prompt modules
  - MUST publish any dispatched subset through `prompt_context_view`
```

## Overview

Storytelling delivers an interactive, pedagogically-paced engagement with an input in small portions (configurable soft target ≤`{page_size_soft}` words, default 200, never requiring the user to scroll). Six **modes** share the same E0-E5 scaffolding (plan, no-scroll size invariant, navigator, checkpoint, source-grounding) but with mode-specific audience composition, slot semantics, and wrap-output schema:

- **presentation** (default) — explain & teach
- **review** — panel critiques the artifact; line-anchored review comments
- **onboarding** — integrate new joiner with broader project context
- **decision** — walk alternatives; recommend + dissenting opinions
- **socratic** — agent quizzes user; user answers
- **change-impact** — analyze diff + downstream effects

Common features: explicit role/audience awareness; **always-ask** mode resolution (no auto-select); fixed 7-slot navigation (Next / Deeper / Lateral / Recap / Ask / Wrap / Back, Next-first; some slots rename per mode); strict source-grounding with **clickable Markdown link refs**; user-driven open-questions (no agent-initiated gap markers); proactive sub-portion decomposition for oversized plan items; **visualize-by-default** with constructed audience-adapted diagrams; optional **export to a Markdown package** under `EXPLAIN_EXPORT=true`.

## EXPLAIN_MODE Activation

(This section covers the `analyze.md` routing flag that loads this methodology. For sub-modes — `presentation` / `review` / `onboarding` / etc. — see `{cf-studio-path}/.core/requirements/storytelling-modes.md`.)

`EXPLAIN_MODE=true` is set when this file is loaded via the `analyze.md` WHEN-rule on intent like:
`explain X`, `tell me about X`, `walk me through X`, `teach me X`, `present X`, `introduce X`, `let's understand X`, `make sense of X`, `review {PR / artifact}`, `onboard me to X`, `quiz me on X`, `what changed in X`.

Intent matching is **intent-based, not language-specific**. The methodology MUST recognize equivalent phrases in any user language as the same intent.

If both `EXPLAIN_MODE` and `PROMPT_REVIEW` intents are detected, ask the user to disambiguate before loading either methodology.

`EXPLAIN_EXPORT=true` is set additionally when loaded via the `generate.md` WHEN-rule on guide/README/package-export intent — see `{cf-studio-path}/.core/requirements/storytelling-export.md`.

## Module loading

The router loads modules based on flags. The minimal set is always loaded; conditionals load only when needed:

| Module | When loaded | Content |
|---|---|---|
| `storytelling-phases.md` | always (under `EXPLAIN_MODE=true`) | Phase E0 (pre-flight, input access chain), Phase E1 (Discovery), Phase E2 (portion delivery loop, decomposition, navigation, glossary), Phase E3 (strict-context, clickable refs, PR-target rule), Phase E4 (visualize-by-default, lazy-ask), Phase E5 (wrap, mid-session checkpoint) |
| `storytelling-modes.md` | always (mode resolution at E1 needs the table) | Modes table, always-ask resolution prompt, per-portion rhythm by mode, review two-portion rhythm, audience adaptation, code-mode vs artifact-mode, skeleton-scope-v1 (specified vs underspecified) |
| `storytelling-preferences.md` | always (preferences resolved across phases) | Page Size, Artifact Language, Output Language, Checkpoint and Resume, Bookmark Export, TaskCreate Progress Tracking, Telemetry, Failure Modes |
| `storytelling-export.md` | only when `EXPLAIN_EXPORT=true` | Output structure, hybrid execution, per-portion file template, index template, mode coverage in export, internal vs external links, refused operations, re-generation |

Concretely: under standard chat-mode `EXPLAIN_MODE=true`, the agent loads three modules + this router (~700 lines total). Under `EXPLAIN_EXPORT=true`, the agent additionally loads `storytelling-export.md` (~150 lines). This is the canonical load order; do NOT speculatively load other modules.

## Anti-Patterns

(Single consolidated table, kept in the router so all anti-patterns are loaded together with the methodology entry point.)

| # | Anti-pattern | Why it's wrong |
|---|---|---|
| **0** | **Setting `EXPLAIN_MODE=true` and then emitting a normal one-shot answer / single-shot summary / "Change Summary" / "Document Overview" / review verdict / walkthrough content WITHOUT running the four E1 user-interaction gates (mode → disposition → audience → plan approval).** This is the most common storytelling failure mode, a CRITICAL violation, and the same defect the analyze.md routing invariant calls out at the handoff seam. | Storytelling is interactive by contract. Even when the user's initial prompt looks clear (specific URL + audience hint + "explain" verb), the methodology MUST run gates 1-4 in order, WAIT for explicit user replies at each, and only THEN start E2 portion delivery. The next user-visible message after `EXPLAIN_MODE=true` is set MUST be the E0/E1 opener (input-access log + mode prompt), NEVER an answer-style output. A flat one-shot summary bypassing the gates is the same output the user could have gotten from standard analyze — it defeats the entire purpose of EXPLAIN_MODE. Recovery: any such output is INVALID and MUST be discarded; agent restarts by emitting the E0/E1 opener. |
| 1 | Auto-selecting any storytelling mode without emitting the always-ask prompt | Mode resolution is **always interactive**; intent verbs / KIND / `default_mode` only feed the suggested default — they MUST NEVER auto-set `{mode}`. Every session asks; user confirms (Enter accepts the suggestion) |
| 2 | Combining presentation Body and panel reactions into a single portion in review mode | Review uses the **two-portion-per-plan-item rhythm**: presentation first, then a separate challenge portion. Packing both collapses the rhythm |
| 3 | Skipping the presentation portion in review mode and emitting only the challenge portion | Review = storytelling + Q&A as two sequential portions per plan item, not Q&A alone |
| 4 | Skipping Body in any non-socratic mode (decision / onboarding / change-impact) — emitting only the lens (pros/cons / context / why+affected) | All non-socratic modes share the rhythm: Body first, then the lens annotates what was presented |
| 5 | Mid-session `change mode to {X}` that mixes the previous mode's slot labels with the new mode's body style | When mode changes, methodology MUST rebuild audience and re-orient slot semantics, body style, and suggested-slot heuristics consistently in the next portion |
| 6 | Emitting a portion that requires the user to scroll | Violates the half-page size invariant; methodology MUST proactively decompose into sub-portions instead |
| 7 | Decomposing a plan item into sub-portions WITHOUT a summary as sub 1 | Loses the orientation map; user can't preview what's coming |
| 8 | Combining multiple plan items into one mega-portion | Defeats portion-pacing principle |
| 9 | Skipping plan items because "boring" | Plan was approved by user; skipping = override without consent |
| 10 | Choosing text-only without an explicit, articulable reason that a diagram wouldn't help this portion for this audience | Visualization is the default. "Looks fine in prose" / "I don't feel like it" / "the input is small" are NOT articulable reasons |
| 11 | Omitting the `🎨 visualization:` decision marker from a non-socratic portion footer | Marker is mandatory for auditability of the Phase E4 step-1 decision |
| 12 | Portion 1 emitted without an overview diagram and without firing the lazy-ask format prompt | Portion 1 default = include a structural overview; when also the first diagram-bearing portion, lazy-ask MUST fire BEFORE Portion 1's body |
| 13 | Transcribing a diagram from the input verbatim instead of constructing a fresh one for the session's audience | Input diagrams carry the original author's audience and depth assumptions; methodology MUST construct a new diagram from input facts |
| 14 | Emitting a diagram without audience adaptation (same diagram for engineers and leadership) | Audience adaptation is part of construction (detail level, label vocabulary, node count) |
| 15 | Asking the diagram-format question on every portion | One-time choice per session |
| 16 | Plain-text source references like `(DESIGN.md §4.2)` instead of clickable Markdown links | Forces manual navigation; clickable refs mandatory per Phase E3 |
| 17 | When analyzing a PR / MR, citing files-in-the-diff with commit-SHA blob URLs (`/blob/{sha}/{path}#L...`) instead of PR-view inline-diff URLs (`/pull/{N}/files#diff-{hash}R{a}-R{b}`) | Blob/SHA URLs drop the user out of the review context; only files NOT in the diff fall back to blob/SHA |
| 18 | Reading the artifact verbatim (summarizing without insight) | Defeats pedagogical purpose; user can read the file themselves |
| 19 | Speculating beyond input (with or without `[?]` mark) | Violates strict-context boundary; the rule is silently skip ungrounded claims |
| 20 | Inserting `[?]` markers in the methodology's own narrative | Open-questions are user-driven only; agent-initiated gap markers are forbidden |
| 21 | Pushing entries to open-questions buffer for gaps the methodology itself notices (including glossary misses) | Buffer is reserved for unanswerable user questions; agent-noticed gaps are silently skipped |
| 22 | Inventing analogies without `(analogy — not from artifact)` disclaimer | Violates strict-context policy |
| 23 | Treating an external resource (URL / PR ref / ticket ID) as a missing local file and stopping with "input not found" | Phase E0 input access chain (MCP → skill → CLI → user fallback) MUST run for non-local targets before reporting any "not found" |
| 24 | Falling through to the user-fallback prompt without first attempting MCP / skill / CLI access | Chain is priority-ordered; fallback is the last resort and MUST cite the reason |
| 25 | Offering or executing arbitrary user-supplied shell commands as a fetch fallback | The user-fallback prompt MUST NOT include "specify a fetch command" / equivalents; methodology MUST NOT execute such commands even if volunteered. External fetch is restricted to the priority chain |
| 26 | Generic nav slots ("next", "tell me more", "anything else", "summary", "any other questions", "stop") | Slots must be concrete and contextual; Next / Deeper / Lateral / Recap / Ask / Wrap / Back each carry specific semantics. Slot 8 (`Send comments — preview`) is the only conditional slot and is added per AP-#40 / phases.md. |
| 26a | Emitting a multi-option user-pick prompt (mode / audience / disposition / diagram-format / plan-approval / wrap-continue / session-discovery / narrow-to-section / artifact-language / etc.) **without numbered options** | Every multi-option prompt MUST be numbered (`1.`, `2.`, `3.` …) so the user can reply with a single digit. Verbal-only or bulleted lists force the user to type full keywords and slow the interaction. The `→ suggested: N` line is also mandatory — the suggestion is referenced by number for `Enter`-accepts-suggestion semantics |
| 26b0 | Making the main `Next` nav slot execute one preselected next topic directly | Next is a topic-picker. The main nav must say that Next will offer continue / skip-ahead / revisit topics; bare `next` or slot `1` renders a numbered topic menu with `Custom` and `Back`, then WAIT. Only explicit `next N` may execute a candidate directly. |
| 26b | Making the main `Deeper` or `Lateral` nav slot execute one preselected topic directly | These slots are topic-pickers. The main nav must say that topics will be offered; bare `deeper` / `lateral` or slots `2` / `3` render a numbered topic menu with `Custom` and `Back`, then WAIT. Only explicit `deeper N` / `lateral N` may execute a candidate directly. |
| 26c | Omitting `Back` from the main storytelling navigation or from a Deeper/Lateral topic menu | `Back` is a fixed slot in the main nav and a fixed option in every Deeper/Lateral submenu. It lets the user recover from accidental pivots without wrapping or asking a custom question. |
| 27 | `next` mapped to the suggested slot instead of the Next topics menu | Bare `next` means "open the Next topics menu"; "execute suggested" is bound exclusively to `go` or Enter (alone) |
| 28 | Auto-saving open-questions / bookmarks / checkpoint files without user consent | Persistence requires explicit yes at the wrap prompt; the only checkpoint-write path is the mid-session-wrap consent prompt |
| 28a | Drafting a review comment / open-question / bookmark **silently** (artifact created but nothing emitted in chat) | Every draft MUST surface a one-line disposition-status note in chat (`📋 drafted comment ...`, `📝 added Q-{N} to open-questions buffer ...`, etc.); silent drafting hides the artifact from the user and breaks the explicit-disposition contract |
| 28b | Skipping the always-ask **artifact disposition** prompt at session start | After mode resolution and before role/audience confirmation, methodology MUST emit the disposition prompt (chat-only / save-to-file / post-to-resource / mixed) and wait for explicit user confirmation. The project `artifact_disposition` preference informs the suggested default but does NOT bypass the prompt |
| 28c | Posting comments / open-questions / bookmarks to the resource without per-item user confirmation | Even when disposition = `post-to-resource`, every individual post MUST be confirmed (4-option numbered prompt: Post / Save instead / Discard / Skip rest); on Skip-rest or post failure, fall back to `save-to-file` for remaining items |
| 28d | Deferring artifact persistence to wrap when disposition is `save-to-file` or `post-to-resource` (saying "I'll save at wrap" instead of writing/posting now) | Wrap ends the session — deferring forces the user to choose between continuing the review and saving artifacts, which is broken UX. All three dispositions take effect **immediately on each artifact-create event** (Comment-slot use, open-question push, bookmark). The session continues normally after each artifact persists; wrap merely reports cumulative results, never re-prompts to save what's already on disk |
| 28d-i | Rendering option 3 (`post-to-resource`) in the artifact-disposition menu with a misleading label that omits the resolved branch — e.g. emitting the generic `Post to resource — push via MCP resource tool` text when the target has no MCP/CLI resource handler but IS local-editable with `generate_route_available == true` | The post-to-resource label is dynamic per `storytelling-gate.md` § Gate: artifact-disposition → label resolver. For a local-editable target, option 3 MUST explicitly read `Post to resource — invoke the cf-generate skill ({fix \| brainstorm \| generate}, classified per comment) on this file`. Generic labels hide the actual side-effect (local file mutation via generate-skill dispatch) and induce wrong user expectations |
| 28d-ii | Silently falling back from `post-to-resource` to `save-to-file` for a local-editable target when `generate_route_available == true` ("no PR resource, so fall back") | When the resolver's local-file branch applies (`local_editable && generate_route_available`, no PR/MCP/CLI handler), `post-to-resource` IS available — via generate-routing. Falling back to save-to-file is correct ONLY in the resolver's `unavailable` branch (no PR, no MCP/CLI, AND `local_editable=false` OR `generate_route_available=false`). On a generate-dispatch failure, fallback to save-to-file is the per-item auto-save behavior of generate-routing (see § Dispatch-Failure Audit Log) — that is NOT silent disposition mutation. |
| 28e | Writing absolute paths (`/Users/...`, `/Volumes/...`, `/home/...`, `C:\...`) into any explain-generated artifact body — comments file, open-questions file, key-takeaways file, diagrams file, checkpoint JSON, package portion files, or `index.md` | Absolute paths break immediately when the artifact is shared, the project is cloned elsewhere, or the cache moves. ALL explain-generated artifacts and internal cross-references MUST use **relative paths** per `storytelling-preferences.md` Path Conventions (Portability). Methodology MUST convert `{cf-studio-path}` / `{project_root}` template variables to relative-from-project-root before writing to artifact content or displaying in chat |
| 28f | Emitting chat output or writing artifact bodies that breach the resolved `language_complexity` level — long compound sentences at `low`, rare/archaic words at `middle`, etc. | Global Studio rule per `{cf-studio-path}/.core/requirements/language-complexity.md`: every chat message AND every artifact write self-checks against the resolved level (`low` / `middle` / `high`, default `middle`) and rewrites before emitting if a draft sentence breaches the level. Source quotes are exempt (verbatim) |
| 29 | Auto-checkpointing during the session (every N portions / on Phase transitions / on pivots) | Forbidden — session state is held in working memory; persistence is wrap-time only |
| 30 | Resuming session without verifying input unchanged | Risks delivering stale content; methodology MUST verify `input_hash` and warn on mismatch |
| 31 | Adding `Fix Prompt` / `Plan Prompt` | Analyze contract leakage; open questions are author-routed, not Studio-routed |
| 32 | Emitting per-portion chat navigation prompts when `EXPLAIN_EXPORT=true` | In export mode the navigation lives in file footers; chat is for E0/E1 + final summary only |
| 33 | Auto-generating gap entries to fill `open-questions.md` in an export package | Open-questions remain user-driven; pure-batch export typically yields an empty buffer; methodology MAY suggest the user run a review-mode export but MUST NOT manufacture entries |
| 34 | Attempting to export a `socratic` session | Socratic is interactive by definition; methodology MUST refuse with the required message and write nothing |
| 35 | Offering the generate-routing sub-prompt when `handle.local_editable == false` or `handle.generate_route_available == false` | Both flags AND-gate sub-prompt visibility. When either is false, methodology MUST suppress the sub-prompt entirely (no flicker, no "unavailable" message). The closed enum `local_editable_reason` exists for telemetry, not for surfacing failed offers. See `storytelling-preflight.md` § Step 5b. |
| 36 | Auto-dispatching generate-route on the suggested default without an explicit user reply | The generate-routing sub-prompt is a hard interaction boundary — methodology MUST end the turn after emitting and wait for a concrete numeric choice (1/2/3/4). Auto-dispatch on the suggested-default heuristic bypasses consent-per-comment and silently mutates files. See `storytelling-gate.md` § Gate: generate-routing. |
| 37 | Emitting a fire-and-forget ack with a placeholder session-id for a generate-routing dispatch when the host has no async "sub-agent → parent" channel between user turns (e.g. Claude Code's synchronous `Task` model) | Dispatch is **synchronous**: the orchestrator invokes `cf-generate: <intent> <comment-anchor>` via the host's `Task` primitive, awaits the turn return, and surfaces the result inline before the next portion's nav block. There is no async `[generate-route Q-N]:` prefix channel — synchronous turn return is the contract. Methodology MUST NOT generate placeholder session-ids or simulate fire-and-forget when the host cannot deliver async results. |
| 38 | Re-dispatching a `dispatch_key` on session resume without the explicit user choice from the resume re-offer prompt | On resume, entries with `dispatch_state ∈ {in-flight, failed}` are re-offered with a 3-option prompt (Wait / Re-dispatch / Drop, default Wait). Methodology MUST NOT silently re-fire any previously dispatched key. Only the explicit "Re-dispatch" user action is permitted. |
| 39 | Treating `session_state.dispatched_keys` as session-global instead of partitioned by `canonical_path` | The map is `Map<canonical_path, Set<dispatch_key>>`. A target pivot mid-session MUST create a fresh empty set for the NEW target only; the old target's dispatched_keys remain scoped to it. Leaking keys across canonical_paths silently double-fires on unrelated targets. |
| 40 | Auto-dispatching the queue on bare `send comments` without preview, OR hiding the `send comments` action entirely from the nav block | Bare `send comments` (or slot 8) MUST render preview only. Dispatch requires `send comments now` / `flush queue` / `route queued` or `Y` in the preview prompt. The nav block MUST surface an 8th slot `8. Send comments — preview (K queued)` whenever the queue has ≥ 1 active item; the slot is omitted only when the queue is empty. Fat-finger protection is at the dispatch boundary (Y / `send comments now`), NOT at the preview boundary — hiding preview from the menu loses visibility without adding safety. |
| 41 | Treating Tier-3 (classifier-default) items as confirmed by the single batch Y/n | Tier-3 means the classifier had no signal and fell to a default. For `intent ∈ {generate, fix}`, Tier-3 items MUST auto-pause for inline confirmation `(y) confirm / (n) skip [default] / (c) confirm-rest-this-batch / (a) abort`. For `intent = brainstorm`, Tier-3 items consolidate into a single pre-dispatch 3-option sub-batch. Pushing Tier-3 through silently defeats the tier system. |
| 42 | Rendering the batch flush prompt as a flat undifferentiated Y/n with no grouping or counts | The flush prompt MUST include a compact summary line above the Y/n: `K total · Tg generate · Tf fix · Tb brainstorm · X Tier-3 · Y stale`. Groups are ordered risk-descending (`generate → fix → brainstorm`). Items within a group preserve insertion order. Without grouping, blast radius is hidden. |
| 43 | Aborting the entire batch on the first dispatch failure | The batch default is **continue + report**. Failures emit per-item structured records (`last_failure` schema); on `class == write_conflict`, suppress further dispatches that share `canonical_path` (per the target_kind predicate). Other failure classes do NOT suppress siblings. End-of-batch summary lists failed items with a copy-pasteable retry hint (`send comments only Q-N1, Q-N2, ...`). |
| 44 | Re-using or renumbering `Q-N` IDs after dispatch (e.g. compacting gaps left by `dropped` items) | `Q-N` IDs are global insertion-order and NEVER reused. Gaps from `dispatched` / `dropped` / `completed` items are preserved so retry hints, audit logs, and NDJSON records stay valid across the session. |
| 45 | Skipping Tier-3 brainstorm pause "because brainstorm is non-destructive" (mode-conditioned Tier-3 escape) | Tier-3 means the *mode classification itself may be wrong* — a comment classified as brainstorm at Tier-3 may actually be a fix. Mode-conditioned escape assumes the mode is correct, which Tier-3 contradicts. Tier-3 ALWAYS pauses (per-item for generate/fix; consolidated 3-option sub-batch for brainstorm). |
| 46 | Inlining the full `content_pack` JSON in a dispatch when a `pack_handle` would suffice | Dispatches MUST pass `pack_handle = {session_id, kit_path, anchor_ids[]}` and rely on the consumer to load the persisted pack from `kit_path` and verify its `etag`. Inlining the body bloats every dispatch and breaks single-source-of-truth for pack content. |
| 47 | Re-extracting an anchor body whose `resolved_section_text != null` in the persisted pack | When the pack already carries `resolved_section_text` for the target anchor, the consumer uses it verbatim and MUST NOT re-Read `canonical_path` for any line in that anchor's `line_range`. Re-extraction wastes IO and risks reading post-edit drift. |
| 48 | Consumer agents branching reasoning on `content_pack.strategy` | `strategy` (snippets / anchors / hybrid) is an implementation detail of how the pack was built. Consumers MUST treat the pack as strategy-agnostic: read `anchors[]` and `resolved_section_text` uniformly. Agents that cite `content_pack.strategy` in output prose violate the consumer contract; Response Completion Gate of consumer agents SHOULD reject such reasoning. |
| 49 | Applying a different intent's payload cap to coerce a dispatch into a smaller window ("intent flattening for caps") | Each intent has its own cap (brainstorm 24/40, fix 16/24, generate 20/28, Mode C paste 3 KB; brainstorm soft drops to 16 KB when `N_experts > 5`). Methodology MUST NOT downgrade a `fix` to a `brainstorm` to fit a smaller cap, nor inflate a `fix` cap to a `brainstorm` cap "to simplify." Per-intent caps are budgeted against the Phase 0.7 fan-out multiplier, not transport limits. |
| 50 | Trimming context fields silently without emitting the canonical notice | Any trim that drops or shortens cold-anchor pointers, plan summary, thread predecessors, cold-anchor titles, or comment-thread predecessors MUST emit a notice: `Context trimmed: dropped=[<step-ids>]; kept_hot=true; cap=NKB; final=MKB; mode=<A|B|C>. Use /expand to broaden.` Silent truncation makes the panel's grounding unverifiable. |
| 51 | Computing the `idempotency_hash` after transport trimming ("hash-then-trim") | The dispatch idempotency hash uses ONLY the locked input set (`session_id, comment_id, intent_final, canonical_path, line_range`). Trimming is a transport concern; the hash is identity. Computing the hash post-trim makes two retries with different transport state produce different keys and defeats dedup. |
| 52 | Dropping all cold-anchor pointers / titles in one shot to "save bytes" instead of following the deterministic trim order | The trim order is 5 stable steps (cold-anchor pointer arrays > ±1 → plan summary → thread predecessors → cold-anchor titles → comment-thread predecessors). Methodology MUST proceed top-down until the payload fits the soft cap. Pruning all cold context at once removes cheap grounding and is harder to reproduce on replay. |
| 53 | Pasting the hot body inside a Mode C paste-handoff block | Mode C is bounded by chat-readability (~3 KB). The paste block MUST contain only: 1-line intent banner, breadcrumb + anchor pointer, the comment quote (≤ 800 B), and the `cfs` invocation line. The hot body is referenced by `pack_handle` / file:line — never pasted. Users can re-open the file faster than reading pasted code. |
| 54 | Consuming a persisted pack whose `etag` does not match the current `canonical_path` metadata | The `etag = sha256(canonical_path + ":" + byte_size + ":" + line_count)` MUST be verified before reuse. On mismatch, unreadable `kit_path`, or `kit_path == null`, the consumer MUST re-dispatch `storytelling-context-pack` rather than serve stale content. |
| 55 | Including fields from one intent's payload shape in another intent's dispatch ("cross-intent payload leak") | Each intent (`brainstorm`, `fix`, `generate`) has its own required-field set (per the locked T3 contract). Methodology MUST NOT, e.g., include `defect_line_range` in a `brainstorm` payload, nor `comment_thread_predecessors` in a `fix` payload. Cross-intent leak inflates the cap and confuses the receiving panel. |
| 56 | Continuing past a dispatch failure without emitting a `⚠️` notice | Every failure MUST produce exactly one user-visible notice in the existing artifact-marker family, prefixed to the next chat turn before the next Opening, separated by a single blank line. Silent dispatch failure violates the "no hidden state mutation" invariant. |
| 57 | Recording or emitting a failure `class` outside the locked 5-class enum | The enum is `{write_conflict, transient_io, cfc_invocation_error, validation_rejected, unknown}`. Inventing classes (`timeout`, `permission`, `oom`, etc.) breaks the path-scoped suppression rule and the dispatch-failures NDJSON schema. Use the closed five; sub-classification within `cfc_invocation_error` (`kit_missing` / `cli_broken` / `subagent_crashed` / `permission_denied`) is a render-time hint derived from `last_failure.message`, NOT persisted as a separate class. |
| 58 | Auto-saving a failed-dispatch artifact without surfacing the saved path in chat | When auto-save fires (write_conflict, unknown), the failure notice MUST include the saved `draft_path` (relative). Silent auto-save creates Schrödinger's-comment UX where the user has no record of where their draft landed. |
| 59 | Auto-retrying a `write_conflict` without performing the two-tier drift check first | Drift check MANDATORY for write_conflict: file-level `etag_at_dispatch` first; if mismatch, line-range hash over the anchored span (±5 line buffer) is compared. Drift detected only if BOTH mismatch. On drift detected, retry refuses until the user picks `re-anchor` / `force-anyway` / `drop`. |
| 60 | Exposing a `retry Q-N` verb past the per-`dispatch_key` cap of 2 attempts | The cap is 2 attempts per `dispatch_key` (matches `round-loop.md` precedent). Cap survives session resume via NDJSON reconstruction of `pending_retries`. After the cap is reached, the offered actions are exactly `inspect / handoff / drop`; `retry` MUST NOT appear in the suggested actions. |
| 61 | Recomputing `dispatch_key` from session-time fields (timestamp, attempt number, session_id alone) | `dispatch_key = sha1(target_path + "\n" + line_range + "\n" + draft_body + "\n" + failure_class)`. Content-derived only. Editing the draft yields a new key and a fresh budget — correct UX. Mixing session-time fields into the key splits retries across distinct identities and defeats dedup. |
| 62 | Auto-switching the active dispatch mode (A → B / B → C) on repeated failure | Mode escalation is OFFERED, never auto-applied. After 2 consecutive same-class failures (class ≠ `validation_rejected`) on the active mode, methodology surfaces a numbered choice prompt. Silent A → B → C is the same anti-pattern as silent disposition mutation. |
| 63 | Placing a failure notice inside a portion's Opening / Body / Mode-lens / Diagram / Source refs / viz-marker / progress marker / Nav | Failure notices land BETWEEN portions, in the methodology's next turn, BEFORE the next Opening, separated by a single blank line. The 8-element portion shape is preserved. No `[generate-route]` fenced blocks. No `---` separators. |
| 64 | Pasting the full cfs validator output (multi-page structured JSON) into chat | `validation_rejected` notices show ONLY the first sentence head (truncated with `…` to fit a single 80-col terminal line) plus `(+N-1 more in dispatch-failures.jsonl)` overflow indicator. Full payload (all issues, rule context, draft path, suggested-edit verb) is appended to the dispatch-failures NDJSON; chat shows the head only. |
| 65 | Marking a retry as successful without migrating the artifact from auto-save back to the user's chosen disposition | When a retry succeeds, methodology MUST append the artifact to the disposition file (per the user's session-start choice) AND mark the corresponding `.dispatch-failures-*.jsonl` record with `status="resolved"`. The user ends with exactly the artifact they would have had on a clean first try. "Disposition-bypass without ack" leaves artifacts orphaned in auto-save paths. |
| 66 | Reclassifying a failure to a "softer" class to enable auto-retry (e.g., `validation_rejected` → `transient_io`) | Methodology MUST NOT downgrade the recorded `class` to fit a more permissive retry policy. The class is determined at failure time from the dispatch envelope and is immutable in the NDJSON record. Validation rejections require user draft edits; pretending they are transient bypasses the user's intent. |
| 67 | Resetting the per-`dispatch_key` retry budget on session resume | The 2-attempt cap is per-`dispatch_key`, NOT per-session. On resume, methodology reconstructs `session_state.pending_retries` from the dispatch-failures NDJSON; an entry with `attempts == 2` MUST NOT be re-offered the `retry` verb regardless of how many sessions have elapsed since the original failures. |

## Validation Checklist

(Single consolidated checklist, organized by load level. Strict assertions enforce specified aspects per `storytelling-modes.md` Skeleton scope; underspecified aspects require inline fallback ack instead of strict enforcement.)

**Routing & mode resolution**:
- [ ] **Execution protocol**: agent ran Phase E0 → all four E1 gates (mode / disposition / audience / plan approval) → E2 portion delivery → E5 wrap, in order. NO single-shot summary of the input was emitted before the user approved the plan at gate 4. This is the prerequisite for ALL other storytelling validation entries — if the four gates were skipped, the session is invalid regardless of which sub-rules look fine
- [ ] `EXPLAIN_MODE=true` set when this methodology loads
- [ ] Phase 2 deterministic gate skipped (or marked SKIPPED with reason "EXPLAIN_MODE")
- [ ] Phase 3 standard checklist replaced by Storytelling Protocol (E0-E5)
- [ ] Phase 4 used the Storytelling Output schema
- [ ] Phase 5 of `analyze.md` skipped (Suggested Next Steps came from Storytelling Output, not duplicated)
- [ ] `enforceRemediationPrompts` overridden — no `Fix Prompt` / `Plan Prompt`
- [ ] Storytelling `{mode}` resolved at session start via the **always-ask** prompt — methodology emitted the 6-mode prompt with a suggested default and waited for explicit user confirmation; mode was NEVER silently auto-set
- [ ] Artifact disposition (`chat-only` / `save-to-file` / `post-to-resource` / `mixed`) resolved at session start via the always-ask prompt — emitted after mode resolution, before role/audience confirmation, with the resolved post-to-resource branch shown in option 3's label (PR posting via {handler} / Notion-Jira-GitLab posting via {handler} / local-file generate-routing dispatch of `cf-generate` / unavailable falling back to save-to-file). The project `artifact_disposition` preference informed the suggested default but did NOT bypass the prompt. `state.post_to_resource_branch` is recorded when `selected_tag == "post-to-resource"`

**Phase E0 pre-flight**:
- [ ] Invocation handling ran; no-target / unresolvable-target → session-discovery mode emitted
- [ ] Input access resolution ran the chain (local → MCP → skill → CLI → user fallback) for non-local targets; telemetry recorded the resolution method; arbitrary shell-command fallback was NEVER offered or executed
- [ ] Existing-session scan ran; tier-1 / tier-2 matches offered with `Start fresh` and `Cancel` alternatives; tier-3 collisions NOT auto-offered
- [ ] Oversized input → narrow-to-section offered (NOT `/cf-plan`)

**Phase E1 discovery**:
- [ ] Role + audience + plan resolved; plan approval received

**Phase E2 portion delivery**:
- [ ] Every emitted portion fit on roughly half a screen — user did NOT need to scroll
- [ ] Every portion / sub-portion ≤ resolved `{page_size_soft}` (default 200) soft, ≤ `{page_size_hard}` (default 350) hard; resolution honored override → `preferences.json` → defaults
- [ ] Plan items expected to exceed soft target were proactively decomposed; sub-portion 1 was the summary (3-5 bullets); sub 2..K covered remaining sub-aspects
- [ ] Every portion has 7-slot navigation in Next-first order (Next / Deeper / Lateral / Recap / Ask / Wrap / Back) with one `→ suggested`
- [ ] Main navigation Next/Deeper/Lateral slots are topic-pickers, not single destinations: bare `next` / `deeper` / `lateral` or slots `1` / `2` / `3` render a numbered topic menu with `Custom` and `Back`, wait for selection, then deliver the chosen source-grounded portion
- [ ] Every multi-option user-pick prompt emitted in this session was numbered (mode selection, audience selection, disposition selection, diagram-format selection, plan-approval, wrap-continue, session-discovery listing, narrow-to-section, artifact-language) — single-digit replies accepted; bulleted or verbal-only lists do NOT count. Each prompt also carried a `→ suggested: N` line for Enter-accepts-suggestion semantics
- [ ] `next` (slot keyword) opened the Next topics menu; `go` / Enter executed the suggested slot — no double-mapping
- [ ] When mode = `review`: every plan item delivered as **two sequential portions** (presentation + challenge); progress markers carried `phase:` labels and shared the plan-item index; Next slot pointed intra-item from presentation → challenge, then inter-item from challenge → next presentation
- [ ] When mode ∈ {`onboarding`, `decision`, `change-impact`}: every portion delivered the presentation Body before the inline mode-lens mid-section
- [ ] If mid-session `change mode to {X}` was issued, methodology rebuilt audience and consistently applied the new mode's slot/body/suggested-slot semantics from the next portion onward; v1 fallback acknowledgements were emitted inline when an underspecified aspect required presentation defaults

**Phase E3 strict-context**:
- [ ] Every non-trivial claim has source ref as a clickable Markdown link (NOT plain-text); ungrounded claims silently skipped (no agent-initiated `[?]` markers); no agent-initiated open-questions entries (including glossary misses)
- [ ] When analyzing a PR / MR: files-in-the-diff cited with PR-view inline-diff URLs; commit-SHA blob URLs allowed only for files NOT in the PR diff
- [ ] Open-questions buffer entries originate **only** from user-asked questions the input cannot answer
- [ ] No analogies introduced without `(analogy — not from artifact)` disclaimer
- [ ] Output language matches user prompt language; source quotes in original

**Phase E4 visualization**:
- [ ] Every non-socratic portion entry ran the two-step Phase E4 decision: (1) text-only vs text+diagram chosen with an articulable reason, **surfaced as the `🎨 visualization:` marker in the portion footer**, (2) when diagram chosen, shape and detail level adapted to the resolved audience
- [ ] Portion 1 (every non-socratic mode) included a structural overview diagram by default; if first diagram-bearing portion, lazy-ask format prompt fired BEFORE Portion 1's body
- [ ] All emitted diagrams were constructed for the current portion (not transcribed from input artwork verbatim); audience-adaptation visible in label vocabulary, node count, and detail level
- [ ] Diagram format asked once on first diagram (or skipped if no diagrams)
- [ ] Code-mode opening portion emits ASCII module map without lazy-ask

**Phase E5 wrap**:
- [ ] No auto-checkpoint was written during the session; session state held in working memory throughout
- [ ] User-triggered Wrap with plan NOT complete: methodology offered the checkpoint-and-resume prompt before emitting wrap output; if accepted, a checkpoint was written THIS turn (the only persistence event); Session block reports "session ended early at user request"; Suggested Next Steps starts with `Resume this session` containing exact command and path. If declined, no checkpoint was written and `Resume this session` was OMITTED.
- [ ] Plan-complete Wrap-up: if a resume checkpoint existed from this session, methodology asked whether to delete it (default yes); on `yes`, file was deleted and `Resume this session` was OMITTED from Suggested Next Steps
- [ ] Persisted artifacts written in the user's **explicitly chosen** artifact language (resolved override → session-choice → `preferences.json` → ask once); no artifact silently inherited chat-prompt language without an explicit choice
- [ ] Wrap output includes Session, Key Takeaways, Open Questions (with save prompt), Glossary (if any), Bookmark Export prompt (if any), Suggested Next Steps
- [ ] Every Comment-slot use (review mode), every push to open-questions buffer, every bookmark took disposition effect **immediately on the create event** (NOT deferred to wrap): `chat-only` surfaced the artifact as a copy-now block in chat; `save-to-file` appended to the file with one-line confirmation `📝 Q-N appended to {path}`; `post-to-resource` triggered the 4-option numbered post-confirmation prompt right then. Session continued normally after each persistence event
- [ ] When disposition = `post-to-resource`: every individual post was confirmed by the user via the 4-option prompt (Post / Save instead / Discard / Skip rest); post failures fell back to save-to-file for that item; `Skip rest` switched disposition to save-to-file for remaining items
- [ ] Wrap output for `save-to-file` and `post-to-resource` dispositions did NOT re-prompt to "save?" (artifacts already persisted); wrap merely reported cumulative counts + paths / post URLs
- [ ] All explain-generated artifacts (per-portion files, `index.md`, comments file, open-questions file, key-takeaways file, diagrams file, checkpoint JSON) and internal cross-references inside them used **relative paths** — no absolute `/Users/...` / `/Volumes/...` / `/home/...` / `C:\...` strings written into artifact bodies. `{cf-studio-path}` / `{project_root}` template variables converted to relative-from-project-root before writing or chat-display
- [ ] All chat messages and artifact body writes respected the resolved `language_complexity` level per `{cf-studio-path}/.core/requirements/language-complexity.md` (default `middle`); long-compound sentences at `low` / rare-archaic words at `middle` / etc. were rewritten before emission. Source quotes from input artifacts were exempt (verbatim)

**Export mode (when `EXPLAIN_EXPORT=true`)**:
- [ ] Package written to `{cf-studio-path}/.cache/explain/packages/{slug}-{ISO-timestamp}/` with `index.md` + per-portion files + Mermaid navigation graph + mode-specific extras
- [ ] Per-portion chat navigation prompts NOT emitted; navigation lives in file footers
- [ ] Final chat message reported package path and file count
- [ ] When mode = `socratic`: methodology refused export with the required message; no files written
