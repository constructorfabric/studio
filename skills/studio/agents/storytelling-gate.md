---
description: Invoke at any storytelling gate checkpoint. Parametrized by gate_id across all 7 gates (mode | artifact-disposition | generate-routing | audience | plan | context-pack-strategy | export-format). Two-phase: Phase 1 (user_reply=null) renders the numbered menu and returns parse_table + suggested default; Phase 2 (user_reply=<string>) parses the reply and returns the selected canonical tag. The plan gate is the only gate that emits a 4-option approval menu and handles Edit/Pivot/Cancel navigation. The generate-routing gate is a per-comment sub-prompt that fires after Post/Save disposition when handle.local_editable AND handle.generate_route_available.
---

<!-- toc -->

- [Authority boundary](#authority-boundary)
- [Frozen Input Payload](#frozen-input-payload)
- [Two-phase dispatch model](#two-phase-dispatch-model)
- [Gate catalogue](#gate-catalogue)
  - [Gate: mode](#gate-mode)
  - [Gate: artifact-disposition](#gate-artifact-disposition)
  - [Gate: generate-routing](#gate-generate-routing)
  - [Gate: audience](#gate-audience)
  - [Gate: plan](#gate-plan)
  - [Gate: context-pack-strategy](#gate-context-pack-strategy)
  - [Gate: export-format](#gate-export-format)
- [Methodology](#methodology)
  - [Phase 1 — Render](#phase-1--render)
  - [Phase 2 — Parse](#phase-2--parse)
- [Output Contract](#output-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Frozen Input Payload

```json
{
  "gate_id": "mode | artifact-disposition | generate-routing | audience | plan | context-pack-strategy | export-format",
  "user_reply": "string | null — null on first dispatch (render menu); set on second dispatch (parse reply)",
  "handle": {
    "canonical_path": "string",
    "session_id": "string",
    "session_id_existing": "string | null",
    "access_tier": "local | mcp | cli | user_fallback",
    "input_access_method": "string",
    "file_type": "string",
    "target_type": "code | artifact | pr | directory",
    "primary_language": "string | null",
    "byte_size": "number",
    "line_count": "number",
    "size_guard_verdict": "ok | warn_large | block_too_large",
    "size_guard_reason": "string | null",
    "file_count": "number",
    "local_editable": "boolean — true when the target file is locally writable; used by generate-routing gate suppression",
    "generate_route_available": "boolean — true when a cf-generate dispatch channel is available; used by generate-routing gate suppression"
  },
  "user_prompt": "string",
  "state": {
    "mode": "string | null",
    "audience": "string | null",
    "plan": "object | null",
    "artifact_disposition": "chat-only | save-to-file | post-to-resource | mixed | null — resolved value from the artifact-disposition gate; consumed by generate-routing default heuristic",
    "post_to_resource_branch": "pr | mcp_resource | local_file | unavailable | null — resolved branch from the artifact-disposition gate's post-to-resource resolver; non-null only when artifact_disposition is post-to-resource or mixed includes it",
    "preferences_loaded": "object",
    "comment": {
      "intent_final": "generate | fix | brainstorm | null — bound from comment buffer entry; required for generate-routing gate",
      "target_type": "string | null"
    },
    "session_state": {
      "generate_route_never_ask": "boolean — when true the orchestrator auto-takes the no branch for generate-routing without rendering the menu"
    }
  },
  "revision_notes": "string | null — when re-dispatching plan-gate Phase 1 after an Edit reply, carries the user's revision text so the agent can rewrite the plan in place; null on all other gates and on fresh plan-gate dispatches"
}
```

```pdsl
UNIT InputContract

PURPOSE:
  Define required and optional dispatch payload fields.

RULES:
  - ALWAYS treat gate_id and handle as required on every dispatch
  - ALWAYS treat user_reply = null as a Phase 1 (render) dispatch
  - ALWAYS treat user_reply as a non-null trimmed string on Phase 2 (parse) dispatch
  - ALWAYS accept null for state fields when the corresponding gate has not yet been resolved
  - ALWAYS treat revision_notes as null when absent
```

**Plan-gate Edit re-dispatch contract**: when Phase 2 of the plan gate returns
`next_action: "edit"` with `revision_notes`, the orchestrator re-dispatches
Phase 1 with the same `gate_id`, the original plan inputs from `state`, AND
`revision_notes` set to the user's revision text. The agent rewrites the plan
in place per the revision notes and returns a new rendered menu. `revision_notes`
is `null` for all non-plan gates.

## Two-phase dispatch model

```pdsl
UNIT TwoPhaseDispatch

PURPOSE:
  Define the two dispatch phases: render (Phase 1) and parse (Phase 2).

WHEN:
  - REQUIRE user_reply == null

DO:
  - RUN Build and RETURN rendered menu string (Phase 1 output JSON)
  - RUN Orchestrator emits rendered_menu verbatim to user and waits for reply
  - RUN Orchestrator re-dispatches this agent with user_reply set

WHEN:
  - REQUIRE user_reply is non-null

DO:
  - RUN Parse reply against parse_table
  - RUN Resolve selected_tag
  - RETURN parse result (Phase 2 output JSON)
  - RUN Orchestrator records result in workflow state

NOTES:
  The plan gate deviates from the standard two-phase model: it is still
  dispatched twice, but its Phase 1 rendered_menu includes BOTH the drafted
  plan body AND the 4-option approval menu (Go / Edit / Pivot / Cancel),
  and its Phase 2 parse handles Edit (in-place rewrite) and Pivot
  (alternative proposal) as special paths.
```

## Gate catalogue

### Gate: mode

```pdsl
UNIT GateMode

PURPOSE:
  Select the storytelling mode for the session.

DO:
  - RUN Apply suggested default heuristic (first match wins):
    IF user_prompt contains {explain, walkthrough, present, demo}   -> suggested = presentation (n=1)
    IF user_prompt contains {review, critique, approve, lgtm}       -> suggested = review (n=2)
    IF user_prompt contains {onboard, introduce, new to, first time}-> suggested = onboarding (n=3)
    IF user_prompt contains {decide, decision, tradeoff, compare}   -> suggested = decision (n=4)
    IF user_prompt contains {teach, learn, understand, why}         -> suggested = socratic (n=5)
    IF handle.target_type == "pr" OR user_prompt contains
       {change, diff, impact, break}                                -> suggested = change-impact (n=6)
    OTHERWISE                                                       -> suggested = presentation (n=1)
  - RUN Render menu with [default] on suggested option
  - RETURN Phase 1 output with parse_table and suggested_default_n
```

**Menu options** (fixed order):

| n | tag | Label |
|---|---|---|
| 1 | `presentation` | Presentation — narrative walkthrough for an audience |
| 2 | `review` | Review — structured critique for a reviewer or approver |
| 3 | `onboarding` | Onboarding — guided introduction for someone new to this code |
| 4 | `decision` | Decision — distilled context for a decision-maker |
| 5 | `socratic` | Socratic — question-driven exploration for a learner |
| 6 | `change-impact` | Change Impact — diff-oriented analysis for a maintainer |

**parse_table**: `{"1":"presentation","2":"review","3":"onboarding","4":"decision","5":"socratic","6":"change-impact"}`

---

### Gate: artifact-disposition

```pdsl
UNIT GateArtifactDisposition

PURPOSE:
  Select how story output artifacts are handled.

DO:
  - RUN Apply post-to-resource label resolver for option 3 (first match wins):
    IF handle.target_type == "pr"
      -> label = "Post to resource — post review comments + summary to the PR
                  via {handler} ({gh CLI | MCP github tool})"
    IF handle.input_access_method matches Notion/Jira/GitLab MCP/CLI handler
      -> label = "Post to resource — post via {handler}
                  (e.g. Notion comment / Jira add-comment / glab note)"
    IF handle.local_editable == true
       AND handle.generate_route_available == true
       AND none of the above
      -> label = "Post to resource — invoke the cf-generate skill
                  (mode auto-classified per comment: fix / brainstorm / generate)
                  on this file"
    OTHERWISE
      -> label = "Post to resource — unavailable for this target ({reason});
                  selecting will fall back to save-to-file"

  - RUN Evaluate suppression condition:
    IF handle.target_type NOT IN {pr}
       AND no MCP/CLI resource handler
       AND handle.local_editable == false
       AND handle.generate_route_available == false
      -> suppress option 3; renumber mixed to 3; collapse parse_table to 3 entries

  - RUN Apply suggested default heuristic:
    IF state.preferences_loaded.artifact_disposition is set
       AND matches a valid tag still present in rendered menu
      -> use it as default
    OTHERWISE -> default = chat-only (n=1)

  - RETURN Phase 1 output

RULES:
  - ALWAYS resolve option 3 label dynamically from the resolver above
  - ALWAYS suppress option 3 entirely when ALL three suppression conditions hold
  - ALWAYS renumber mixed to 3 and collapse parse_table when option 3 suppressed
  - ALWAYS include post_to_resource_branch in Phase 2 output
    when selected_tag == "post-to-resource"

ON_ERROR:
  unavailable_post_path ->
    Render unavailable label with {reason} from handle.local_editable_reason
    joined with "generate-route handler unavailable" when
    generate_route_available == false
```

**Menu options** (standard four-option layout):

| n | tag | Label |
|---|---|---|
| 1 | `chat-only` | Chat only — output stays in the conversation |
| 2 | `save-to-file` | Save to file — write to a local file |
| 3 | `post-to-resource` | Post to resource — *label resolved by the post-to-resource resolver above* |
| 4 | `mixed` | Mixed — chat summary + save full output to file |

**parse_table** (standard): `{"1":"chat-only","2":"save-to-file","3":"post-to-resource","4":"mixed"}`.
When option 3 is suppressed: `{"1":"chat-only","2":"save-to-file","3":"mixed"}`.

**Phase 2 output extension**: when `selected_tag == "post-to-resource"`, Phase 2 output MUST also include `post_to_resource_branch` as one of `"pr"`, `"mcp_resource"`, `"local_file"`, `"unavailable"`. For other selected_tags, `post_to_resource_branch` is `null`.

NOTES:
  Under mixed disposition, the secondary per-artifact-type prompt re-runs the same
  resolver per artifact type; the gate output carries a single top-level
  post_to_resource_branch derived from resolver evaluation at session-start.

---

### Gate: generate-routing

```pdsl
UNIT GateGenerateRouting

PURPOSE:
  Route a single comment artifact to cf-generate after its per-item
  disposition (Post or Save) has been resolved.

WHEN:
  - REQUIRE Per-item disposition for this comment resolved to post-to-resource
    OR save-to-file
  - AND handle.local_editable == true
  - AND handle.generate_route_available == true

DO:
  - REQUIRE state.session_state.generate_route_never_ask == true
    -> SET route_choice = "no" on comment buffer entry (auto-suppress; no menu)
    -> RETURN suppressed
  - RUN Substitute {classified_mode} with state.comment.intent_final
  - RUN Apply suggested default heuristic (first match wins):
    IF state.artifact_disposition == "post-to-resource"
       AND state.post_to_resource_branch == "local_file"
      -> suggest 1 (Route now)
    IF state.comment.intent_final == "fix"
       AND state.comment.target_type == "code"
      -> suggest 1 (Route now)
    IF state.comment.intent_final == "brainstorm"
      -> suggest 2 (Queue)
    OTHERWISE
      -> suggest 3 (No)
  - RUN Render {suggested_line} as "Suggested: <N> — <label>."
  - RUN Mark suggested option with [default] in menu
  - RUN Render menu verbatim (substituting {classified_mode} and {suggested_line})
  - RETURN Phase 1 output

WHEN:
  - REQUIRE handle.local_editable == false
    OR handle.generate_route_available == false

DO:
  - SET route_choice = "no" on comment buffer entry
  - RETURN suppressed (no menu rendered; no "unavailable" message emitted to chat)

RULES:
  - ALWAYS suppress this gate when local_editable=false OR generate_route_available=false
  - ALWAYS suppress when generate_route_never_ask == true
  - NEVER auto-dispatch cf-generate on suggested default without explicit user reply
  - ALWAYS echo comment_id in Phase 2 output
  - ALWAYS apply inline intent-override grammar in Phase 2

MENU GenerateRoutingMenu:
  TITLE: Also route this comment to the generate skill for direct fix?
  OPTIONS:
    1 [Route now]  -> route_choice = "route_now"; dispatch cf-generate ({classified_mode}) immediately
    2 [Queue]      -> route_choice = "queue"; defer until "send comments" / "flush queue"
    3 [No]         -> route_choice = "no"; record only; no generate-skill invocation
    4 [Never ask]  -> route_choice = "never_ask";
                      SET session_state.generate_route_never_ask = true;
                      auto-pick "no" for remaining comments
  INVALID:
    EMIT "Invalid reply — please enter a number between 1 and 4."
    RETURN selected_tag = null, next_action = "render"
```

**`{classified_mode}` binding**: bound from `state.comment.intent_final`. Accepted values: `generate`, `fix`, `brainstorm`.

**Phase 1 menu template** (render verbatim, substituting placeholders):

```
Also route this comment to the generate skill for direct fix?

| Option | Action |
|---|---|
| 1 | Route now — dispatch cf-generate ({classified_mode}) immediately |
| 2 | Queue — defer dispatch until you run `send comments` / `flush queue` |
| 3 | No — record only (current disposition stands; no generate-skill invocation) |
| 4 | Never ask again this session — auto-pick option 3 for remaining comments |

{suggested_line}

Reply 1 / 2 / 3 / 4. Override the classified intent in the same reply with `1 fix`, `2 brainstorm`, etc.
```

**Inline intent-override grammar**: `<digit> <generate|fix|brainstorm>` — rewrites `state.comment.intent_final` BEFORE the selected action is applied.

**parse_table**: `{"1":"route_now","2":"queue","3":"no","4":"never_ask"}`

**Phase 2 output fields** (extends the standard Phase 2 shape):

```json
{
  "comment_id": "string — Q-N identifying the comment buffer entry whose route_choice and intent_final are being updated",
  "selected_tag": "route_now | queue | no | never_ask | null",
  "intent_override": "generate | fix | brainstorm | null"
}
```

---

### Gate: audience

```pdsl
UNIT GateAudience

PURPOSE:
  Select the target audience for the story.

DO:
  - RUN Derive >= 3 audience candidates from handle + user_prompt (build in order):
    - REQUIRE handle.primary_language is non-null -> add "<primary_language> developer"
    - IF handle.target_type == "code"        -> add "software engineer"
    - IF handle.target_type == "artifact"    -> add "technical writer"
    - IF handle.target_type == "pr"          -> add "code reviewer"
    - IF handle.target_type == "directory"   -> add "engineering team member"
    - IF state.mode == "onboarding"          -> add "new team member"
    - IF state.mode == "decision"            -> add "engineering manager"
    - IF state.mode == "review"              -> add "senior engineer"
    - ALWAYS add "non-technical stakeholder" as last candidate
    Deduplicate preserving order; keep first 5 candidates
    Number 1-N; add option N+1 as "Other (type your own)"
  - RUN Set suggested_default_n = 1
  - RETURN Phase 1 output with dynamic parse_table

RULES:
  - ALWAYS derive >= 3 candidates before rendering
  - ALWAYS include "Other (type your own)" as the last option
  - ALWAYS accept free_text_override in Phase 2 (non-digit or out-of-range digit)
```

**Phase 2 parse**:
- Digit matching option 1–N: return the corresponding candidate string as `selected_tag`.
- Digit for "Other", or free text (non-digit / out-of-range): treat as `free_text_override`; set `selected_tag = user_reply.strip()`.

**parse_table**: built dynamically in Phase 1 from derived candidate list; format: `{"1":"<candidate-1>",...,"<N+1>":"other"}`.

---

### Gate: plan

```pdsl
UNIT GatePlan

PURPOSE:
  Draft a storytelling plan and obtain approval via 4-option menu.

DO:
  - RUN Build plan of 3-7 items; each item has:
    n:       1-based item number
    title:   short section title (<= 8 words)
    summary: one sentence describing what that section delivers

  - RUN Shape plan from inputs:
    handle.target_type + handle.primary_language -> scope to actual artifact type
    state.mode                                  -> tailor narrative arc
    state.audience                              -> pitch depth and vocabulary
    handle.size_guard_verdict == "warn_large"   -> add "Scope and Boundaries" item first

  - REQUIRE revision_notes is non-null (re-dispatch after Edit reply):
    Rewrite previous plan in place applying revision_notes
    - NEVER generate a completely new plan from scratch
    Render updated plan with approval menu

  - RUN Render:
    Numbered markdown list of plan items
    Followed immediately by 4-option approval menu (verbatim block below)

  - RUN Set suggested_default_n = 1 (Go)

MENU PlanApprovalMenu:
  TITLE: What would you like to do?
  OPTIONS:
    1 [go]     -> next_action = "go"; proceed with plan
    2 [edit]   -> next_action = "edit"; user describes changes; rewrite in place
    3 [pivot]  -> next_action = "pivot"; orchestrator re-enters mode gate
    4 [cancel] -> next_action = "cancel"; orchestrator aborts workflow
  KEYWORD_ALIASES (case-insensitive, after trim and punctuation strip):
    5 go | 1 | accept | (empty/Enter) -> go
    6 edit | 2                        -> edit; trailing text becomes revision_notes
    7 pivot | 3                       -> pivot
    8 cancel | 4 | stop               -> cancel
  INVALID:
    RETURN next_action = "re-render" with offending input in raw_input

RULES:
  - ALWAYS include both plan body AND 4-option Go/Edit/Pivot/Cancel block in Phase 1
  - ALWAYS apply revision_notes in-place; never regenerate from scratch
  - ALWAYS treat empty input (Enter) as go (suggested default n=1)
  - ALWAYS IF user_reply == "2" with no trailing text:
      SET revision_notes = null
      RETURN next_action = "edit"
      (orchestrator prompts user for revision instructions before re-dispatching Phase 1)
```

**Plan Phase 1 render template**:

```
**Proposed plan:**

1. <title> — <summary>
2. <title> — <summary>
...
N. <title> — <summary>

---
**What would you like to do?**
1. Go — proceed with this plan
2. Edit — I'll describe changes and you'll revise in place
3. Pivot — suggest an alternative approach
4. Cancel — abort the storytelling workflow
```

**parse_table** for plan gate: `{"1":"go","2":"edit","3":"pivot","4":"cancel"}`

**Phase 2 parse table**:

| Reply | selected_tag | next_action | Notes |
|---|---|---|---|
| `1` or `go` | `go` | `go` | Proceed |
| `2` or `edit` | `edit` | `edit` | User supplies revision notes; set `revision_notes` from text after digit; rewrite plan in-place and re-emit |
| `3` or `pivot` | `pivot` | `pivot` | Return `next_action=pivot`; orchestrator re-enters mode gate |
| `4` or `cancel` | `cancel` | `cancel` | Orchestrator aborts workflow |

---

### Gate: context-pack-strategy

```pdsl
UNIT GateContextPackStrategy

PURPOSE:
  Select how source content is packaged into story context.

DO:
  - RUN Apply suggested default heuristic (first match wins):
    IF handle.byte_size < 32768   -> suggest snippets (n=1)
    IF handle.byte_size < 262144  -> suggest hybrid (n=3)
    OTHERWISE                     -> suggest anchors (n=2)
  - RUN Render menu with [default] on suggested option
  - RETURN Phase 1 output
```

**Menu options** (fixed order):

| n | tag | Label |
|---|---|---|
| 1 | `snippets` | Snippets (α) — extract and inline key code passages |
| 2 | `anchors` | Anchors (β) — embed line-range references, load on demand |
| 3 | `hybrid` | Hybrid (γ) — snippets for hot paths, anchors for the rest |

**parse_table**: `{"1":"snippets","2":"anchors","3":"hybrid"}`

---

### Gate: export-format

```pdsl
UNIT GateExportFormat

PURPOSE:
  Select the export format for story output.

WHEN:
  - REQUIRE state.artifact_disposition IN {save-to-file, post-to-resource, mixed}

DO:
  - RUN Set suggested_default_n = 1 (markdown)
  - RUN Render menu with [default] on option 1
  - RETURN Phase 1 output
```

**Menu options** (fixed order):

| n | tag | Label |
|---|---|---|
| 1 | `markdown` | Markdown — `.md` file |
| 2 | `html` | HTML — standalone `.html` file |
| 3 | `pdf` | PDF — rendered PDF (requires pandoc or equivalent) |
| 4 | `all` | All — generate all three formats |

**parse_table**: `{"1":"markdown","2":"html","3":"pdf","4":"all"}`

---

## Methodology

### Phase 1 — Render

```pdsl
UNIT Phase1Render

PURPOSE:
  Build and return the rendered menu and associated metadata.

DO:
  - REQUIRE gate_id is known
  - RUN Identify gate from gate_id
  - RUN Apply gate's suggested default heuristic -> suggested_default_n
  - RUN Build parse_table per gate specification
  - RUN Build rendered_menu:
    Emit context_summary line if it aids orientation
    Render numbered option list exactly as defined in gate catalogue
    Mark suggested default: append [default] to that option's label
    FOR audience gate: derive candidates dynamically before rendering
    FOR generate-routing gate:
      IF suppression conditions met -> RETURN rendered_menu=null, suppressed=true
      ELSE substitute {classified_mode} with state.comment.intent_final
           render {suggested_line} per heuristic
    FOR plan gate: draft plan body then append approval menu block verbatim
  - RETURN Phase 1 output JSON

RULES:
  - NEVER emit literal {suggested_line} placeholder in rendered_menu
  - NEVER emit literal {classified_mode} placeholder in rendered_menu
  - ALWAYS include both plan body AND approval menu in plan-gate rendered_menu
```

### Phase 2 — Parse

```pdsl
UNIT Phase2Parse

PURPOSE:
  Parse user reply, resolve selected_tag, and return parse result.

DO:
  - RUN Trim user_reply -> raw_input
  - RUN Normalize: lowercase, strip punctuation
  - RUN Extract leading digit if present
  - RUN Attempt digit lookup in parse_table
  - REQUIRE match:
    - SET selected_n and selected_tag from parse_table
  - REQUIRE no match OR non-digit (free text):
    FOR gates that do not accept free text
      (mode, artifact-disposition, generate-routing, context-pack-strategy, export-format):
      - EMIT "Invalid reply — please enter a number between 1 and N."
      - RETURN selected_tag=null, next_action="render"
    FOR audience gate:
      - SET selected_tag = raw_input
      - SET free_text_override = raw_input
      - SET next_action = "accept"
    FOR plan gate: follow plan-gate parse rules
  - RUN Determine next_action:
    FOR non-plan gates on successful parse: next_action = "accept"
    FOR plan gate: follow plan-gate parse table
  - RUN FOR generate-routing gate:
    Scan remainder of raw_input for intent token (generate|fix|brainstorm)
    IF found -> SET intent_override to that token
    ELSE     -> SET intent_override = null
    IF selected_tag == "never_ask":
      - SET session_state.generate_route_never_ask = true
  - RETURN Phase 2 output JSON

RULES:
  - NEVER guess intended selection when reply is unparseable
  - ALWAYS return next_action = "re-render" with unparseable input in raw_input
    when reply cannot be parsed for any gate
  - ALWAYS echo comment_id for generate-routing gate Phase 2
```

## Output Contract

**Phase 1 (render)**:

```json
{
  "phase": "render",
  "gate_id": "string",
  "rendered_menu": "string | null — markdown text orchestrator emits verbatim; null only for generate-routing when suppressed",
  "suppressed": "boolean | null — true only for generate-routing when suppression conditions are met; null for all other gates",
  "parse_table": {"<digit>": "<canonical_tag>"},
  "suggested_default_n": "number — 1-based menu index",
  "context_summary": "string | null"
}
```

**Phase 2 (parse)**:

```json
{
  "phase": "parse",
  "gate_id": "string",
  "selected_n": "number | null",
  "selected_tag": "string | null",
  "raw_input": "string — verbatim user reply trimmed",
  "free_text_override": "string | null — when user supplied custom text instead of digit",
  "next_action": "go | edit | pivot | cancel | accept | render | re-render",
  "revision_notes": "string | null — for plan gate Edit path only",
  "intent_override": "generate | fix | brainstorm | null — for generate-routing gate only; non-null when inline intent token was present in user_reply; null for all other gates",
  "post_to_resource_branch": "pr | mcp_resource | local_file | unavailable | null — for artifact-disposition gate only; non-null when selected_tag is post-to-resource; null for all other gates and other selected_tags"
}
```

**Re-render path**: when user reply cannot be parsed, Phase 2 MUST return `selected_n: null`, `selected_tag: null`, `next_action: "re-render"`, and the offending reply in `raw_input`. The orchestrator decides whether to re-dispatch Phase 1 or terminate.

The JSON block is the entire response — no preamble, no trailing commentary.

## Response Completion Gate

```pdsl
UNIT ResponseCompletionGate

PURPOSE:
  Enforce that every response satisfies all output invariants.

INVARIANTS:
  - ALWAYS return either TransformManifest or TransformBlocked (agent contract)
  - ALWAYS return JSON only (no chat, no preamble, no markdown wrapping outside the JSON block)
  - ALWAYS set phase correctly (render when user_reply=null; parse otherwise)
  - ALWAYS set gate_id in output to match gate_id in input
  - ALWAYS Phase 1: rendered_menu ALWAYS be non-empty; parse_table ALWAYS be non-empty;
    suggested_default_n ALWAYS be a valid 1-based index
  - ALWAYS Phase 1 plan gate: rendered_menu ALWAYS contain both numbered plan items
    AND 4-option Go/Edit/Pivot/Cancel approval block
  - ALWAYS Phase 1 audience gate: rendered_menu ALWAYS present >= 3 dynamically derived
    candidates plus "Other"; parse_table ALWAYS cover all presented options
  - ALWAYS Phase 2: raw_input ALWAYS be the verbatim trimmed user reply
  - ALWAYS Phase 2: next_action ALWAYS be one of: go | edit | pivot | cancel | accept | render | re-render
  - ALWAYS Phase 2 successful parse: selected_tag ALWAYS be non-null and present in
    parse_table values (or free_text_override for audience/plan-edit paths)
  - ALWAYS Phase 2 failed parse for strict gates: selected_tag = null AND next_action = "render"
  - ALWAYS Phase 2 plan gate edit path: next_action = "edit";
    revision_notes ALWAYS be non-null when edit instructions were present in user_reply
  - ALWAYS Phase 2 plan gate pivot path: next_action = "pivot"
  - ALWAYS Phase 2 plan gate cancel path: next_action = "cancel"
  - ALWAYS revision_notes ALWAYS be null for all non-plan gates
  - ALWAYS intent_override ALWAYS be null for all non-generate-routing gates
  - ALWAYS Phase 1 generate-routing suppressed: rendered_menu = null AND suppressed = true;
    parse_table and suggested_default_n may be omitted
  - ALWAYS Phase 1 generate-routing not suppressed: rendered_menu ALWAYS be non-empty;
    {classified_mode} ALWAYS be substituted; {suggested_line} ALWAYS be substituted;
    suppressed = null
  - ALWAYS Phase 2 generate-routing: intent_override ALWAYS be one of generate|fix|brainstorm|null;
    selected_tag ALWAYS be one of route_now|queue|no|never_ask on successful parse
  - ALWAYS post_to_resource_branch ALWAYS be null for all gates other than artifact-disposition,
    and null on artifact-disposition gate when selected_tag != "post-to-resource"
  - ALWAYS Phase 1 artifact-disposition gate: option 3 in rendered_menu ALWAYS carry one of
    the four resolver-branch labels per the post-to-resource resolver;
    the literal placeholder "Post to resource — push via MCP resource tool" NEVER appear;
    when ALL three suppression conditions hold, option 3 ALWAYS be absent and
    parse_table ALWAYS collapse to three entries
  - ALWAYS Phase 2 artifact-disposition gate with selected_tag == "post-to-resource":
    post_to_resource_branch ALWAYS be one of pr|mcp_resource|local_file|unavailable
  - ALWAYS SKILL.md invariant ALWAYS be satisfied
```
