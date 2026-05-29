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

The methodology **always asks** the user explicitly. Mode MUST NEVER be silently set from intent verbs / artifact KIND / project preference — those signals only inform the **suggested default**.

Prompt template (emitted at the start of every session, before role/audience derivation):
```text
Which storytelling mode for this session?
  1. presentation — explain & teach (single role+audience)
  2. review       — panel critiques the artifact; line-anchored comments
  3. onboarding   — integrate new joiner with broader project context
  4. decision     — walk alternatives; recommend + dissenting opinions
  5. socratic     — agent quizzes you; you answer
  6. change-impact — analyze diff + downstream effects
→ suggested: {S} ({why-suggested})
```

`{S}` is computed in priority order: explicit intent verbs → KIND defaults → `default_mode` from `{cf-studio-path}/.cache/explain/preferences.json` → fallback `presentation`. `{why-suggested}` is a one-line note (`you said "review this PR"` / `KIND=PRD typically presentation` / `project default per preferences.json` / `fallback default`). User confirms by number / name / Enter for the suggestion. Methodology MUST NOT proceed past this prompt without an explicit user response.

**Override mid-session**: `change mode to {X}` rebuilds audience and resumes the plan with the new slot semantics and body style; plan items unchanged. `remember new mode` persists `default_mode` (future sessions still always ask; the suggested default updates).

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

For all non-socratic modes: Body is always present; lens annotates what was just presented. Lens-only output (pros-only / context-only / why-only / questions-only) is forbidden.

## Review mode rhythm (two portions per plan item)

Review is **storytelling + Q&A interleaved as separate portions**, not "presentation with panel reactions appended". For each plan item the methodology emits TWO portions in sequence:

1. **Presentation portion** — Body presents the chunk (source-grounded, audience-adapted, ≤ resolved page-size, with diagram per Phase E4). Identical shape to a presentation-mode portion. Progress marker: `📍 {idx}/{N} • phase: presentation • topic: "{plan-item}"`. The Next topics menu includes **"Challenge: panel reactions for {plan-item}"** as the suggested continue candidate (intra-item, not next plan item).

2. **Challenge portion** — emitted only after user advances. Body: a 1-2 sentence recap of what was just presented + numbered panel reactions `Q1` / `Q2` / … from each panellist (1-2 critical questions / concerns per panellist, anchored to lines/sections where possible). Diagram per Phase E4 if relevant (panel-topology, gap diagram). Progress marker: `📍 {idx}/{N} • phase: challenge • topic: "{plan-item}"`. The Next topics menu includes **"Presentation: {next-plan-item}"** as the suggested continue candidate (or Wrap if last). **Comment slot** is most useful here — picking it asks `Which panel question to draft as a review comment? [Q1 / Q2 / Q3 / your own wording]`.

**classified_mode label.** Every comment drafted in review mode is automatically classified by intent into one of `generate` / `fix` / `brainstorm`, using a tiered heuristic (Tier 1: prefix tokens like `fix:`, `add:`, `idea:`; Tier 2: signals like imperative on a code line ⇒ `fix`, question form on an artifact ⇒ `brainstorm`; Tier 3: defaults — code-mode ⇒ `fix`, artifact-mode ⇒ `brainstorm`). The classified mode appears as a label on the comment (e.g. `Q-3 [fix]`) and is stored as `intent_initial` plus `intent_initial_tier ∈ {1,2,3}` on the buffer entry (see `{cf-studio-path}/.core/requirements/storytelling-phases.md` § Open-question buffer entry shape). The label is informational; the user may override it via `change to {mode}` or via the inline shorthand `1 fix` / `2 brainstorm` at the generate-routing sub-prompt.

**generate-routing sub-prompt visibility.** When the session is local-editable (`handle.local_editable == true`) AND generate-skill dispatch is available (`handle.generate_route_available == true`), each drafted comment surfaces a secondary generate-routing sub-prompt AFTER the per-item disposition (Post / Save / Discard / Skip-rest) resolves. The sub-prompt offers four options: Route now / Queue / No / Never-ask-again-this-session (default: No). See `{cf-studio-path}/.core/skills/studio/agents/storytelling-gate.md` § Gate: generate-routing for the full menu and parse rules. When either flag is false, the sub-prompt is suppressed entirely (no flicker, no "unavailable" message) and the comment is recorded per the chosen disposition only.

**See also:**
- `{cf-studio-path}/.core/skills/studio/agents/storytelling-preflight.md` § Step 5b — Local-editable detection (defines `local_editable` / `generate_route_available`)
- `{cf-studio-path}/.core/skills/studio/agents/storytelling-gate.md` § Gate: generate-routing (the sub-prompt mechanics)
- `{cf-studio-path}/.core/requirements/storytelling-phases.md` § Open-question buffer entry shape (`classified_mode`, `intent_initial_tier`, etc.)
- `{cf-studio-path}/.core/requirements/storytelling-preferences.md` § Dispatch-Failure Audit Log (NDJSON record format)

The same plan-item index is shared between the pair; `{N}` (total plan items) is unchanged. Total portion count up to `2 × N`. The split is NOT proactive sub-portion decomposition (which uses letter suffixes `3a`, `3b` for oversized items) — it's a fixed two-phase rhythm specific to review. The mechanisms compose: an oversized plan item could yield `3a-presentation` → `3b-presentation` → `3-challenge` (one challenge for the whole item, summarising panel reactions across sub-portions).

## Audience adaptation heuristics

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

**Underspecified** (best-effort with required inline fallback ack):
- Panel composition algorithm — exact role set per artifact KIND beyond table examples
- Comment / answer / hint buffer file formats and on-disk layout
- Wrap-output mode-specific extras' precise field schema
- Scoring heuristics for socratic
- Impact-map structure for change-impact

When the agent enters an underspecified region: (a) apply best-effort interpretation grounded in the spec's spirit, (b) emit a one-line fallback acknowledgement inside the affected portion (e.g. `(review-mode v1: comment-buffer file format not yet specified — using ad-hoc Markdown bullet list)`). This makes the v1 gap explicit and sidesteps false-success on the validation checklist.
