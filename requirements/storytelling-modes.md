---
cf: true
type: requirement
name: Storytelling Modes
version: 1.0
purpose: Mode-specific deltas (audience, slot semantics, per-portion rhythm) for the storytelling methodology
---

# Storytelling Modes


<!-- toc -->

- [Modes table](#modes-table)
- [Mode resolution (always-ask)](#mode-resolution-always-ask)
- [Per-portion rhythm by mode](#per-portion-rhythm-by-mode)
- [Review mode rhythm (two portions per plan item)](#review-mode-rhythm-two-portions-per-plan-item)
- [Audience adaptation heuristics](#audience-adaptation-heuristics)
- [Code-mode vs Artifact-mode](#code-mode-vs-artifact-mode)
- [Skeleton scope (v1)](#skeleton-scope-v1)

<!-- /toc -->

Loaded by `{cf-studio-path}/.core/requirements/storytelling.md` (router). Defines what changes per `{mode}` ∈ {`presentation`, `review`, `onboarding`, `decision`, `socratic`, `change-impact`}. The E0-E5 scaffolding (plan, page-size invariant, no-scroll, navigator, checkpoint) is shared across modes — see `{cf-studio-path}/.core/requirements/storytelling-phases.md`.

The flow-neutral definitions of the **audience** and **narrator/role** dimensions (and their cross-flow resolution rules and anti-contracts) are owned by `{cf-studio-path}/.core/requirements/storytelling-dimensions.md` (§ Audience Dimension, § Narrator / Role Dimension). This module holds storytelling's delivery-time specifics: the per-mode audience character and role panels in the Modes table, and the full adaptation heuristics below.

## Modes table

| Mode | Suggested-default trigger verbs (used ONLY to populate the default in the always-ask mode prompt **after** EXPLAIN_MODE is already active — these verbs do NOT activate EXPLAIN_MODE on their own; activation requires explain-family verbs per `analyze.md` WHEN-rule) | Default for KIND (used ONLY to populate suggested default after EXPLAIN_MODE is already active) | Audience character | Slot semantic deltas (vs presentation) | Wrap-output deltas |
|---|---|---|---|---|---|
| **presentation** (default) | `explain`, `tell me about`, `walk me through`, `teach me`, `present`, `introduce`, `let's understand`, `make sense of` | PRD, FEATURE, DESIGN, ADR, code (when no review/diff intent) | Single chosen role + audience | none (Next/Deeper/Lateral/Recap/Ask/Wrap) | Key Takeaways + Open Questions + Glossary + Bookmarks |
| **review** | `review`, `critique`, `challenge`, `audit`, `look at this PR`, `defend the design` | PR-REVIEW, PR-STATUS-REPORT, DECOMPOSITION (when reviewing decomposition quality) | Panel of relevant roles (PRD → PM+Architect+QA+Security; code change → senior engineer+tester+on-call; ADR → architect+EM+adjacent-team-lead) | **Two-portion-per-plan-item rhythm** (presentation → challenge); `Ask` → **`Comment`** (line-anchored review note: file + line range + severity, most useful in challenge portions); Deeper/Lateral lean critical (gap-finding, contradiction-finding) | `review-comments-{slug}-{date}.md` (ready-to-paste line-anchored notes) + Open Concerns list with severity + Recommended verdict (approve / request-changes / comment-only) |
| **onboarding** | `onboard me`, `I'm new`, `introduce me to`, `help me start with`, `getting started with` | (intent-only) | "New joiner" + project-wide context (parents, siblings, owners, adjacent teams) | `Lateral` → **`Context`**: jumps to broader project context where this artifact fits | Reading roadmap + People to know + Glossary |
| **decision** | `which option`, `should we`, `compare alternatives`, `trade-offs`, `decide between`, `pick one` | ADR (with options not yet decided), FEATURE (with alternatives section) | Stakeholder panel (decision-makers + impacted parties; ADR → architect + EM + downstream-team-leads + on-call) | `Deeper` → **`Pros`** / **`Cons`**: alternates pros vs cons of current option; `Lateral` jumps to alternative options | Recommendation + dissenting opinions + decision criteria + reversibility note |
| **socratic** | `quiz me`, `test my understanding`, `ask me questions`, `check my knowledge`, `let me try` | (intent-only) | The user (one-on-one; agent flips role to instructor) | INVERTED: per portion the agent **poses** a question; user picks `Answer` (free-text) / `Skip` / `Hint` / `Recap` / `Wrap`; agent grades with source ref | Comprehension scorecard (X/N correct) + topics to revisit + suggested re-walk in `presentation` for weak topics |
| **change-impact** | `what changed`, `diff this`, `impact of`, `review the change`, `before vs after`, `what's new in` | (intent + diff context) | Engineer + downstream consumers + on-call | `Deeper` → **`Why`** (motivation + author intent); `Lateral` → **`Affected`** (downstream consumers / dependent code / call sites) | Impact map + risk list + migration notes (if any) |

## Mode resolution (always-ask)

The methodology **always asks** the user explicitly before role and audience derivation. The signals in the modes table (trigger verbs, KIND defaults) only inform the **suggested default**; they never set the mode on their own.

```pdsl
UNIT StorytellingModeResolution

PURPOSE:
  Always ask the user to select a storytelling mode before role and audience derivation; never derive it silently.

STATE:
  - SET current_mode: unset | presentation | review | onboarding | decision | socratic | change-impact
    default: unset
  - SET suggested_mode: presentation | review | onboarding | decision | socratic | change-impact
    default: presentation

WHEN:
  - REQUIRE EXPLAIN_MODE == active
  - AND current_mode == unset

DO:
  - SET suggested_mode = first match: explicit intent verbs → KIND defaults → preferences.json default_mode → fallback presentation
  - EMIT_MENU ModeSelectionMenu
  - WAIT user.reply
  - STOP_TURN

MENU ModeSelectionMenu:
  TITLE: Which storytelling mode for this session? → suggested: {suggested_mode} ({why-suggested})
  OPTIONS:
    1 presentation  -> SET current_mode = presentation
                       CONTINUE RoleAudienceDerivation
    2 review        -> SET current_mode = review
                       CONTINUE RoleAudienceDerivation
    3 onboarding    -> SET current_mode = onboarding
                       CONTINUE RoleAudienceDerivation
    4 decision      -> SET current_mode = decision
                       CONTINUE RoleAudienceDerivation
    5 socratic      -> SET current_mode = socratic
                       CONTINUE RoleAudienceDerivation
    6 change-impact -> SET current_mode = change-impact
                       CONTINUE RoleAudienceDerivation
  INVALID:
    EMIT "Reply with 1–6 or the mode name. Press Enter to accept the suggestion."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER set current_mode from intent verbs, artifact KIND, or project preference without user confirmation
  - NEVER proceed past ModeSelectionMenu without an explicit user response
  - ALWAYS use priority order for suggested_mode: explicit intent verbs → KIND defaults → preferences.json default_mode → fallback presentation
  - ALWAYS include a one-line why-suggested note with the suggestion

NOTES:
  {why-suggested} examples: "you said 'review this PR'" / "KIND=PRD typically presentation" /
  "project default per preferences.json" / "fallback default".
  User confirms by number, name, or Enter for the suggestion.
```

```pdsl
UNIT ModeOverrideMidSession

PURPOSE:
  Rebuild audience and resume plan with new slot semantics when the user changes mode mid-session.

WHEN:
  - REQUIRE user.message contains "change mode to"

DO:
  - SET current_mode = X
  - RUN RoleAudienceDerivation
  - CONTINUE plan at current item with new slot semantics and body style

RULES:
  - ALWAYS preserve existing plan items unchanged on mode change
  - ALWAYS persist default_mode to preferences.json when user says "remember new mode"

NOTES:
  "remember new mode" updates the suggested default for future sessions; future sessions still always ask.
```

## Per-portion rhythm by mode

Every portion preserves the core structure (Opening → Body → Mode-lens → Diagram → Source refs → `🎨 visualization:` marker → Progress marker → Navigation). The mode determines whether the lens content is **inline** (mid-section between Body and Source refs) or **a separate follow-up portion** for the same plan item.

| Mode | Rhythm | Lens content placement |
|---|---|---|
| presentation | one portion per plan item | (none — Body is the content) |
| **review** | **two portions per plan item** (presentation → challenge, alternating) | **Challenge portion** is its own portion (see Review mode rhythm below) |
| onboarding | one portion per plan item | **Context note** mid-section: 1-2 sentences placing the topic in the broader project (where it fits, who owns it, what comes before/after) |
| decision | one portion per plan item | **Pros / Cons block** mid-section: bulleted pros and cons of the option presented; alternative options surface via Lateral |
| socratic | one portion per plan item, INVERTED | Body replaced by a **question** the agent poses; user picks Answer / Skip / Hint slots; "presentation" appears only when user picks Hint or after answering |
| change-impact | one portion per plan item | **Why + Affected block** mid-section: short "why this changed" + "what depends on it" subsections |

```pdsl
UNIT PortionLensInvariants

PURPOSE:
  Prohibit lens-only output in all non-socratic portions.

RULES:
  - NEVER emit lens-only output (pros-only, context-only, why-only, questions-only) in non-socratic modes
  - ALWAYS emit Body before lens annotation in every non-socratic portion
```

## Review mode rhythm (two portions per plan item)

Review is **storytelling + Q&A interleaved as separate portions**, not "presentation with panel reactions appended". For each plan item the methodology emits TWO portions in sequence:

1. **Presentation portion** — Body presents the chunk (source-grounded, audience-adapted, ≤ resolved page-size, with diagram per Phase E4). Identical shape to a presentation-mode portion. Progress marker: `📍 {idx}/{N} • phase: presentation • topic: "{plan-item}"`. The Next topics menu includes **"Challenge: panel reactions for {plan-item}"** as the suggested continue candidate (intra-item, not next plan item).

2. **Challenge portion** — emitted only after user advances. Instead of a flat panel Q-list, the challenge portion **delegates to a single `cf-brainstorm` topic round**: the agent synthesizes reviewer roles from the topic and artifact content, invokes the skill, and walks questions one by one using the standard brainstorm per-question mechanics. Progress marker: `── Challenge Round ──` then `📍 {idx}/{N} • phase: challenge • topic: "{plan-item}"`. After the round, storytelling reclaims navigation and offers: `[Post comment | Save | Next: {next-plan-item} | Wrap]`. See `UNIT ChallengePortion` below for the full lifecycle spec.

```pdsl
UNIT ReviewModeRhythm

PURPOSE:
  Enforce the two-portion-per-plan-item sequence (presentation → challenge) in review mode.

STATE:
  - SET review_phase: presentation | challenge
    default: presentation

WHEN:
  - REQUIRE current_mode == review

DO:
  - RUN PresentationPortion
    NOTES: Progress marker: 📍 {idx}/{N} • phase: presentation • topic: "{plan-item}".
           Next menu includes "Challenge: panel reactions for {plan-item}" as suggested continue candidate.
  - WAIT user.advance
  - RUN ChallengePortion
    NOTES: Progress marker: 📍 {idx}/{N} • phase: challenge • topic: "{plan-item}".
           Next menu includes "Presentation: {next-plan-item}" (or Wrap if last).
           Comment slot prompts: "Which panel question to draft as a review comment? [Q1 / Q2 / Q3 / your own wording]"

RULES:
  - ALWAYS share the same plan-item index between presentation and challenge portions of the same item
  - ALWAYS emit ChallengePortion only after user advances from PresentationPortion
  - NEVER increment plan-item index between presentation and challenge for the same item
  - ALWAYS allow sub-portion decomposition to compose: oversized item may split into sub-portions (3a, 3b) for presentation, then one challenge for the whole item
```

```pdsl
UNIT ChallengePortion

PURPOSE:
  Run an interactive per-question challenge round. Synthesize a reviewer panel,
  dispatch cf-brainstorm-panel to collect questions, then walk each question
  one at a time via ChallengeQuestionLoop. NEVER emit a flat Q-list.

STATE:
  - SET challenge_label: string
    default: "challenge:round-{idx}:{plan-item-slug}"
  - SET question_queue: list
    default: []
  - SET drafted_comments: list
    default: []
  - SET scorer_triggered: bool
    default: false

WHEN:
  - REQUIRE current_mode == review
  - AND user selects "Challenge" from post-PresentationPortion menu

DO:
  # Context Collection
  - RUN ContextSliceExtraction
    NOTES: Collect from current presentation portion:
           heading, opening (1-2 sentences), bullets (2-3 key points),
           source_refs, artifact_kind, topic (plan-item label).
  - RUN Scorer
    NOTES: IF context.sub_items > 5 OR context.word_count > 500:
             SET scorer_triggered = true;
             DISPATCH cf-explorer to enrich context (at most once);
             IF cf-explorer empty: proceed with available context.

  # Panel Synthesis
  - RUN PanelSynthesis
    NOTES: Derive reviewer roles from topic + artifact content. No static KIND table.
  - REQUIRE panel.roles.count >= 2
    NOTES: Violation -> HALT.

  # Entry
  - EMIT ── Challenge Round ──
  - EMIT 📍 {idx}/{N} • phase: challenge • topic: "{plan-item}"

  # Panel dispatch — build question_queue
  - LOAD {cf-studio-path}/.core/skills/studio/agents/cf-brainstorm-panel.md
    NOTES: Open, load, and strictly follow the agent contract from that file.
           Payload (match the agent's frozen input contract):
             panel=synthesized_roles,
             topic={ id, text: "{plan-item}", section },
             state (kind, rules_loaded, panel, decisions, rounds, round_count, ...),
             round_number,
             resource_context=context_slice,
             mode="challenge",
             protocol="independent-then-critique".
           Transform the returned envelope (blocks[]) into question_queue:
             take ONLY blocks[].kind=="independent" rows
               ({persona_id, question_id, decision_key, text, proposed_default,
                 rationale, stance}); ignore critique blocks.
             Map each independent row to a question_queue item
               { queue_index, persona: persona_id, text, rationale, status="pending" },
               with queue_index ordered by panel order then question order.
           ON empty question_queue:
             EMIT "No questions generated for this topic.";
             EMIT_MENU ChallengePostRoundMenu; WAIT user.reply; STOP_TURN.

  # Question loop — one question per turn
  - CONTINUE ChallengeQuestionLoop

RULES:
  - ALWAYS load cf-brainstorm-panel.md explicitly; NEVER synthesize questions inline without it
  - NEVER emit more than one question before STOP_TURN
  - NEVER show a storytelling navigation menu (Next/Deeper/Lateral) during the question loop
  - ALWAYS use ChallengeQuestionLoop for every question; NEVER walk questions inline in DO
  - ALWAYS return to ReviewModeRhythm after ChallengePostRoundMenu resolves
  - NEVER increment plan-item index during ChallengePortion
```

```pdsl
UNIT ChallengeQuestionLoop

PURPOSE:
  Ask exactly one pending question per turn. After user reacts, loop back.
  When queue is empty, continue to post-round menu.

DO:
  - SET q = first question_queue item with status == "pending"

  - REQUIRE q is not null:
    - EMIT Q{q.queue_index}/{total} — {q.persona}
    - EMIT "{q.text}"
    - EMIT "Why it matters: {q.rationale}"
    - EMIT_MENU ChallengeReactionMenu
    - WAIT user.reply
    - STOP_TURN

  - EMIT "Challenge complete. Returning to {plan-item}..."
  - EMIT_MENU ChallengePostRoundMenu
  - WAIT user.reply
  - STOP_TURN

RULES:
  - ALWAYS emit exactly ONE question per turn
  - ALWAYS STOP_TURN immediately after ChallengeReactionMenu
  - NEVER continue to the next question in the same turn
  - NEVER emit a storytelling navigation menu here

MENU ChallengeReactionMenu:
  TITLE: Reply with a number, or write a counter-argument.
  OPTIONS:
    1 agree         -> SET q.status = "agreed"
                       CONTINUE ChallengeQuestionLoop
    2 push back     -> IF no free text: EMIT "Write your counter-argument.", WAIT user.reply, STOP_TURN
                       SET q.status = "pushed_back"; SET q.counter = user_text
                       CONTINUE ChallengeQuestionLoop
    3 draft comment -> SET q.status = "queued_as_comment"
                       APPEND q to drafted_comments
                       CONTINUE ChallengeQuestionLoop
    4 defer         -> SET q.status = "deferred"
                       CONTINUE ChallengeQuestionLoop
    5 skip          -> SET q.status = "skipped"
                       CONTINUE ChallengeQuestionLoop
    6 wrap          -> EMIT "Challenge complete. Returning to {plan-item}..."
                       EMIT_MENU ChallengePostRoundMenu
                       WAIT user.reply
                       STOP_TURN
  INVALID:
    IF reply is non-empty free text: treat as option 2 push-back
    ELSE:
      EMIT "Reply with 1 agree, 2 push back, 3 draft comment, 4 defer, 5 skip, 6 wrap."
      WAIT user.reply
      STOP_TURN

MENU ChallengePostRoundMenu:
  TITLE: Challenge round complete for "{plan-item}". What next?
  OPTIONS:
    1 Post comment  -> RUN CommentClassification
    2 Save          -> RUN PersistRoundOutput
    3 Next          -> SET review_phase = presentation
                       CONTINUE ReviewModeRhythm
    4 Wrap          -> CONTINUE WrapPhase
  INVALID:
    EMIT "Reply with 1–4."
    WAIT user.reply
    STOP_TURN
```

**ChallengePortion handoff object.** Returned to `ReviewModeRhythm` on exit:

```yaml
round_output: <cf-brainstorm round result>    # full brainstorm output
panel_decisions: []                           # accepted decisions from round
drafted_comments: []                          # comments drafted during round
timestamp: <ISO 8601>
merge_strategy: success | error
challenge_label: "challenge:round-{N}:{slug}"
parent_round_id: null                         # null if first round
validation_status: passed | <error_code>
scorer_triggered: false                       # true if cf-explorer was invoked
summary_mode: false                           # true if payload was compressed
recovery_action: null                         # null on success
```

```json
{
  "round_output": "...",
  "panel_decisions": [],
  "drafted_comments": [],
  "timestamp": "...",
  "merge_strategy": "success",
  "challenge_label": "challenge:round-1:plan-item-slug",
  "parent_round_id": null,
  "validation_status": "passed",
  "scorer_triggered": false,
  "summary_mode": false,
  "recovery_action": null
}
```

**classified_mode label.** Every comment drafted in review mode is automatically classified by intent into one of `generate` / `fix` / `brainstorm`, using a tiered heuristic (Tier 1: prefix tokens like `fix:`, `add:`, `idea:`; Tier 2: signals like imperative on a code line ⇒ `fix`, question form on an artifact ⇒ `brainstorm`; Tier 3: defaults — code-mode ⇒ `fix`, artifact-mode ⇒ `brainstorm`). The classified mode appears as a label on the comment (e.g. `Q-3 [fix]`) and is stored as `intent_initial` plus `intent_initial_tier ∈ {1,2,3}` on the buffer entry (see `{cf-studio-path}/.core/requirements/storytelling-phases.md` § Open-question buffer entry shape). The label is informational; the user may override it via `change to {mode}` or via the inline shorthand `1 fix` / `2 brainstorm` at the generate-routing sub-prompt.

```pdsl
UNIT CommentClassification

PURPOSE:
  Classify every review-mode drafted comment by intent using a three-tier heuristic.

STATE:
  - SET intent_initial: generate | fix | brainstorm
  - SET intent_initial_tier: 1 | 2 | 3

WHEN:
  - REQUIRE current_mode == review
  - AND a comment is being drafted

DO:
  - RUN Tier1Classification
    NOTES: Prefix tokens — "fix:" → fix; "add:" → generate; "idea:" → brainstorm
  - RUN Tier2Classification if Tier 1 yields no match
    NOTES: Signals — imperative on a code line → fix; question form on an artifact → brainstorm
  - RUN Tier3Classification if Tier 2 yields no match
    NOTES: Defaults — code-mode → fix; artifact-mode → brainstorm
  - SET intent_initial = classification result
  - SET intent_initial_tier = resolving tier
  - EMIT comment with label "Q-{N} [{intent_initial}]"

RULES:
  - ALWAYS display intent_initial as a label on the comment
  - ALWAYS store intent_initial and intent_initial_tier on the buffer entry
  - ALWAYS allow user override via "change to {mode}" or inline shorthand "1 fix" / "2 brainstorm"
```

**generate-routing sub-prompt visibility.** When the session is local-editable (`handle.local_editable == true`) AND generate-skill dispatch is available (`handle.generate_route_available == true`), each drafted comment surfaces a secondary generate-routing sub-prompt AFTER the per-item disposition (Post / Save / Discard / Skip-rest) resolves. The sub-prompt offers four options: Route now / Queue / No / Never-ask-again-this-session (default: No). See `{cf-studio-path}/.core/skills/studio/agents/storytelling-gate.md` § Gate: generate-routing for the full menu and parse rules. When either flag is false, the sub-prompt is suppressed entirely (no flicker, no "unavailable" message) and the comment is recorded per the chosen disposition only.

```pdsl
UNIT GenerateRoutingSubPrompt

PURPOSE:
  Surface the generate-routing sub-prompt after per-item disposition resolves in local-editable sessions.

WHEN:
  - REQUIRE handle.local_editable == true
  - AND handle.generate_route_available == true
  - AND per-item disposition has resolved

DO:
  - DISPATCH storytelling-gate.md Gate:generate-routing
  - WAIT user.reply
  - STOP_TURN

RULES:
  - NEVER emit the generate-routing sub-prompt when handle.local_editable == false
  - NEVER emit the generate-routing sub-prompt when handle.generate_route_available == false
  - NEVER show an "unavailable" message when the sub-prompt is suppressed
```

**See also:**
- `{cf-studio-path}/.core/skills/studio/agents/storytelling-preflight.md` § Step 5b — Local-editable detection (defines `local_editable` / `generate_route_available`)
- `{cf-studio-path}/.core/skills/studio/agents/storytelling-gate.md` § Gate: generate-routing (the sub-prompt mechanics)
- `{cf-studio-path}/.core/requirements/storytelling-phases.md` § Open-question buffer entry shape (`classified_mode`, `intent_initial_tier`, etc.)
- `{cf-studio-path}/.core/requirements/storytelling-preferences.md` § Dispatch-Failure Audit Log (NDJSON record format)

The same plan-item index is shared between the pair; `{N}` (total plan items) is unchanged. Total portion count up to `2 × N`. The split is NOT proactive sub-portion decomposition (which uses letter suffixes `3a`, `3b` for oversized items) — it's a fixed two-phase rhythm specific to review. The mechanisms compose: an oversized plan item could yield `3a-presentation` → `3b-presentation` → `3-challenge` (one challenge for the whole item, summarising panel reactions across sub-portions).

## Audience adaptation heuristics

Neutral definition of the audience dimension: `{cf-studio-path}/.core/requirements/storytelling-dimensions.md` § Audience Dimension. The table below is storytelling's delivery-time adaptation of that dimension.

Adapt content style based on `{audience}`:

| Audience | Amplify | Soften | Jargon | Invariant depth |
|---|---|---|---|---|
| engineers | API contracts, edge cases, invariants, code refs | business framing | technical OK | high |
| product | outcomes, user value, launch risks | low-level algorithms | unfold on first mention | low-medium |
| leadership | impact, timelines, dependencies, risks | implementation detail | avoid | low |
| mixed | balance, definitions inline | extremes either way | unfold first mention | medium |
| new joiners | context, vocabulary, "why this not that" | implementation minutiae | always unfold + glossary | medium with recaps |
| customers | observable behavior, contracts, limits | internals | avoid | low |

Heuristics applied contextually per portion, not hard rules. Diagram detail level follows the same audience map (see Phase E4 in `{cf-studio-path}/.core/requirements/storytelling-phases.md`).

## Code-mode vs Artifact-mode

| Aspect | Artifact-mode (registered Studio artifact or generic doc) | Code-mode (code directory or files; default role = Tech Lead) |
|---|---|---|
| Plan walk | document structure (top-level sections) | **entry points → core → data → integration**, NOT file order |
| Source refs | IDs as anchors | file paths + line numbers |
| Lateral slot | parents/children from registry | linked design artifact (via `@cpt-*` markers from `{cfs_cmd} --json validate`); adjacent module / sibling component |
| Diagrams | document semantics (flow, hierarchy, state) | first portion **always** emits ASCII module map (no lazy-ask); subsequent diagrams use lazy-ask normally |
| Glossary | as needed | heavily used (function names, type names, domain terms) |

## Skeleton scope (v1)

This module specifies the table-row level deltas per mode. Strict vs underspecified:

**Strictly specified** (Validation Checklist enforces):
- Per-portion rhythm — number of portions per plan item, presence of Body before lens, mid-section vs separate-portion placement
- Slot-name deltas — Ask → Comment (review); Lateral → Context (onboarding); Deeper → Pros/Cons (decision); Deeper → Why + Lateral → Affected (change-impact); 7-slot count, Back availability, and Next-first ordering invariant
- Source-grounding, page-size invariant, no-scroll rule, clickable Markdown refs, audience adaptation, visualize-by-default — all unchanged
- ChallengePortion lifecycle — entry/exit conditions, pre-flight validation, cf-brainstorm INVOKE semantics, panel synthesis, post-round menu, handoff object, error states (see `UNIT ChallengePortion`)

**Underspecified** (best-effort with required inline fallback ack):
- Panel composition algorithm — role synthesis heuristic beyond examples given in `UNIT ChallengePortion`
- Comment / answer / hint buffer file formats and on-disk layout
- Wrap-output mode-specific extras' precise field schema
- Scoring heuristics for socratic
- Impact-map structure for change-impact

```pdsl
UNIT UnderspecifiedRegionFallback

PURPOSE:
  Emit a visible fallback acknowledgement whenever the agent processes an underspecified region.

WHEN:
  - REQUIRE agent enters an underspecified region (see underspecified list above)

DO:
  - RUN best-effort interpretation grounded in the spec's spirit
  - EMIT one-line fallback acknowledgement inline in the affected portion
    NOTES: Format: "(review-mode v1: {topic} not yet specified — using ad-hoc {approach})"
  - CONTINUE normal portion output

RULES:
  - ALWAYS apply best-effort interpretation grounded in the spec's spirit
  - ALWAYS emit the fallback acknowledgement in the affected portion
  - NEVER silently apply an interpretation in an underspecified region without the acknowledgement
```
