---
cf: true
type: requirement
name: Storytelling Phases (E0-E5)
version: 1.0
purpose: Phase-by-phase protocol for the storytelling methodology
---

# Storytelling Phases


<!-- toc -->

- [Phase E0: Pre-flight](#phase-e0-pre-flight)
- [Phase E1: Discovery](#phase-e1-discovery)
  - [Step 1: Parse intent](#step-1-parse-intent)
  - [Step 2: Resolve mode (always-ask)](#step-2-resolve-mode-always-ask)
  - [Step 3: Auto-derive role from artifact](#step-3-auto-derive-role-from-artifact)
  - [Step 4: Confidence routing](#step-4-confidence-routing)
  - [Step 5: Build and approve plan](#step-5-build-and-approve-plan)
- [Phase E2: Portion Delivery Loop](#phase-e2-portion-delivery-loop)
  - [Portion shape](#portion-shape)
  - [Proactive sub-portion decomposition](#proactive-sub-portion-decomposition)
  - [First-portion special shape (portion 1)](#first-portion-special-shape-portion-1)
  - [Navigation block (6 fixed slots, Next-first; conditional 7th)](#navigation-block-6-fixed-slots-next-first-conditional-7th)
  - [User input handling](#user-input-handling)
  - [Periodic gates](#periodic-gates)
  - [Glossary buffer](#glossary-buffer)
- [Phase E3: Strict-Context Boundary](#phase-e3-strict-context-boundary)
- [Phase E4: Visualize-by-Default](#phase-e4-visualize-by-default)
- [Phase E5: Wrap](#phase-e5-wrap)
  - [Wrap output (final response — replaces analyze.md Phase 4 schema)](#wrap-output-final-response--replaces-analyzemd-phase-4-schema)

<!-- /toc -->

Loaded by `requirements/storytelling.md` (router). Defines the E0-E5 protocol shared by all storytelling modes. For mode-specific deltas (audience, slot renames, two-portion review rhythm) see `storytelling-modes.md`. For preferences (page size, artifact language, checkpoint) see `storytelling-preferences.md`. For export-mode behavior see `storytelling-export.md`.

## Phase E0: Pre-flight

Before any user interaction:

- [ ] **Invocation handling** — interpret the user's prompt:
  - **Resume intent** — prompt contains `explain --resume {session-id}` or `resume explain session {session-id}` (or equivalent in the user's language) → load the checkpoint at `{cf-studio-path}/.cache/explain/session-{slug}-{session-id}.json` directly (skip session-discovery listing) and continue from saved state. Verify `input_hash` and abort if input is missing per the resume rules in `storytelling-preferences.md` Checkpoint and Resume.
  - **No target / unresolvable target** (typo, ambiguous, unknown ID) → enter **session-discovery mode**: list saved sessions from `{cf-studio-path}/.cache/explain/session-*.json` newest-first with role / audience / progress / age / input-status (`unchanged` / `changed since checkpoint` / `missing`); user resumes by number or specifies a target; offer `start new` and `cancel`. If no saved sessions exist, prompt for a target directly.
  - **Clear target** (file path, registered artifact ID, or recognized external resource) → set `{target}` and continue to Input access resolution.

- [ ] **Input access resolution** — resolve how to read the target's content. Branch by shape:
  - **Local file path** → check existence/readability/non-empty (inherits `analyze.md` Phase 1).
  - **Studio artifact ID** (`REQ-001` etc.) → resolve via `{cfs_cmd} --json where-defined {id}`, continue as local file.
  - **External resource** (HTTP/HTTPS URL, `gh:owner/repo#123`, `JIRA-456`, Notion / Linear / Confluence / Slack URL, etc.) → run the **access chain** in priority order, falling through on absence or fetch failure:
    1. **MCP** — check for an MCP server that handles the resource type (e.g. `mcp__github__*`, `mcp__plugin_Notion_notion__*`, `mcp__plugin_atlassian_jira__*`, `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`, `mcp__plugin_playwright_*`). Fetch via the MCP tool. Telemetry: `External input resolved via MCP {server}.{tool}`.
    2. **Skill** — scan registered skills (e.g. `Notion:find` / `Notion:search`, `coderabbit:autofix`). Telemetry: `via skill {name}`.
    3. **CLI tool** — known fixed-shape commands only: `gh pr view {N} --repo {owner}/{repo} --json title,body,files,commits` + `gh pr diff {N} ...`; `gh issue view`; `glab mr view`; `WebFetch`/`curl` for non-auth URLs. Verify install with `command -v`. Auth-gated URLs MUST stay in MCP/skill/`gh` tier — never plaintext credentials in `curl`. Telemetry: `via CLI {command}`.
    4. **User fallback** — prompt:
       ```text
       Cannot fetch `{resource}` automatically. {reason}.
       How do you want to provide the content?
         1. Paste the content here as text in your reply
         2. Specify a local path to a downloaded copy
         3. Cancel this explain session
       → suggested: 2
       ```
       **Safety**: methodology MUST NOT execute arbitrary user-supplied shell commands even if volunteered in free-text. External fetch is restricted to the priority chain above; arbitrary shell delegation is forbidden. If the user pastes a candidate command, refuse and remind of the available options.

  Whatever the resolution path: fetched content becomes the in-memory input; the original resource identifier is recorded as `input_path` (alongside `input_hash` for change detection); source refs in portions link back to the **original external URL**, not the local cache. Track `target_is_pr` for the PR-view URL rule (Phase E3).

  `{slug}` derivation for external resources: lowercase + hyphenate. Examples: GitHub PR → `gh-{owner}-{repo}-pr-{N}`, Jira ticket → `jira-{key}`, Notion page → `notion-{slugified-title}`, generic URL → `url-{domain}-{path}`.

- [ ] **Existing-session scan** — before building a new plan, scan `{cf-studio-path}/.cache/explain/session-*.json` for prior sessions on this target. Three-tier match:
  1. Exact stored-input-path match AND `input_hash` matches current → tier-1 "exact match, input unchanged"
  2. Exact stored-input-path match but `input_hash` differs → tier-2 "same file, content changed since checkpoint"
  3. Same `{slug}` but different stored path → tier-3 collision (NOT auto-offered)

  Tier-1/2 matches are offered with `Start fresh` and `Cancel` alternatives before E1 Discovery proceeds.

- [ ] **Input size guards**: `<50 lines` → warn "input small, continue?" (default yes); `≤2000 lines` → proceed; `>2000 lines` → offer **narrow-to-section** (NOT `/cf-plan` — that workflow is for autonomous execution): parse top-level headings (markdown `^#{1,3} ` for docs; entry-points / module boundaries for code; best-effort heuristics elsewhere); show as scope options; default suggestion = High-level overview. If user picks a section, narrow Read-range; override (continue full) tagged as reduced fidelity.

- [ ] **Registry resolution**: target in `artifacts.toml` → load KIND, retrieve linked artifacts via `{cfs_cmd} --json where-defined {id}` and `{cfs_cmd} --json where-used {id}`. Unregistered → graceful degrade (role defaults to SME, no auto-Lateral candidates).

- [ ] **Language config**: respect `[validation] allowed_content_languages` from `.studio-workspace.toml` for source quotes.

## Phase E1: Discovery

Goal: settle `{mode}`, `{role}`, `{audience}`, `{plan}` before any content delivery.

### Step 1: Parse intent

Extract from the prompt:
- **Mode hint** (per `storytelling-modes.md` table) — only feeds the suggested default in the **always-ask mode prompt** (next step); MUST NEVER auto-set `{mode}`
- Explicit role hint: "as architect", "as PM"
- Explicit audience: "for engineers", "to leadership"
- Explicit angle: "briefly", "deep dive", "high level only"
- Section / topic focus: "explain only the data model"

### Step 2: Resolve mode (always-ask)

Methodology emits the 6-mode prompt (template in `storytelling-modes.md`); waits for explicit user confirmation (Enter accepts the suggestion, or pick by number/name). Mode resolution is interactive every session — intent verbs / KIND defaults / `default_mode` from preferences.json only inform the suggested default, never bypass the prompt.

After mode resolution but BEFORE role/audience derivation, methodology emits the **artifact disposition** prompt (template + resolution rules in `storytelling-preferences.md` Artifact Disposition). The list of accumulating artifact types in the prompt depends on the resolved mode (review adds review-comments; all modes have open-questions and bookmarks). The methodology MUST wait for explicit user confirmation; the project `artifact_disposition` preference informs the suggested default but does NOT bypass the prompt.

### Step 3: Auto-derive role from artifact

| KIND | Default role |
|---|---|
| PRD | Product Manager |
| FEATURE | PM / Tech Lead (mixed) |
| DESIGN, ADR | Software Architect |
| code, codebase | Tech Lead |
| PR-REVIEW, PR-STATUS-REPORT | Reviewer / QA |
| DECOMPOSITION, plan | Engineering Manager |
| Unregistered / ambiguous | Subject Matter Expert |

### Step 4: Confidence routing

| State | Gates before content |
|---|---|
| Both role + audience derived with high confidence | **0 gates**: 1-line confirmation header + plan-approval prompt |
| Role known, audience missing | **1 gate**: ask audience |
| Both missing or low-confidence | **Strict-A fallback**: 4 sequential gates — propose role and ask for confirmation → ask audience → build plan → approve plan |

Audience prompt (always numbered for single-digit reply):
```text
Who's the audience for this session?
  1. engineers
  2. product
  3. leadership
  4. mixed
  5. new joiners
  6. customers
  7. other — specify in your reply
→ suggested: {S} ({why-suggested, e.g. "you mentioned 'for engineers' in the prompt"})
```

User confirms by number / name / Enter for the suggestion.

### Step 5: Build and approve plan

Plan size by input size: `≤500 lines` → 3-4 portions; `≤2000` → 5-7. Plan items MUST be concrete topics from the input's actual headings ("data model", "auth flow"), not generic ("intro", "details"). Show plan as numbered list with one-line subtitles, then numbered approval prompt:
```text
Plan ({N} portions, as {role} for {audience}):
  1. {item 1} — {one-line subtitle from input}
  2. {item 2} — {one-line subtitle from input}
  ...

Approve and proceed?
  1. Go — start delivering portions
  2. Edit — describe what to change
  3. Pivot — rebuild plan around a different focus
  4. Cancel — exit explain mode
→ suggested: 1 (Go)
```

User confirms by number / keyword / Enter for the suggestion. Free-text shorthand also accepted: `go`/`yes`/Enter → E2; `edit X` / `swap N and M` → adjust; `pivot to {topic}` → rebuild; `cancel` → exit. Cancel ack: `Explain mode cancelled. Run /cf-analyze for standard analysis.`

## Phase E2: Portion Delivery Loop

### Portion shape

**Mandatory size invariant — no scrolling**: every portion ≤ resolved `{page_size_soft}` words (default 200) soft target, ≤ `{page_size_hard}` (default 350) hard ceiling. User MUST NEVER scroll. Before emitting, **estimate** body length; if > soft target, **proactively decompose** into sub-portions (see below) — do NOT emit oversized portions and rely on after-the-fact recovery.

Each portion has, in order:
- **Opening** (1-2 sentences): what and why now
- **Body**: 1 concentrated point from current plan item or sub-portion; ≤ `{page_size_soft}` soft / `{page_size_hard}` hard
- **Mode lens** mid-section (per `storytelling-modes.md` per-mode rhythm; review uses a separate challenge portion instead of a mid-section)
- **Optional diagram** per Phase E4
- **Source references** — clickable Markdown links per Phase E3
- **`🎨 visualization: {text-only | text+diagram} — {reason}`** decision marker (mandatory for all non-socratic portions; counts toward page-size budget)
- **Per-portion progress marker**: `📍 {X}/{N} • {K} open questions • topic: "{plan-item}"` (review mode adds `phase: presentation | challenge`)
- **Navigation block** (6 fixed slots, Next-first; conditional 7th)

Hard-cap recovery (fallback only — primary tool is proactive decomposition): **auto-trim with ack** when removing connective / framing sentences brings under cap while preserving substance; **split** only when the body itself genuinely exceeds the cap. Split shares the plan-item index with letter suffixes (`📍 3a/{N}`, `📍 3b/{N}`); `{N}` does NOT grow.

### Proactive sub-portion decomposition

Trigger: estimated body for a plan item > resolved `{page_size_soft}`. Decompose **before emitting anything** for the item.

Shape (K ≥ 2 sub-portions):
- **Sub-portion 1 — Summary**: 3-5 bullets stating "what's covered, key thoughts to remember"; ≤ round(`{page_size_soft}` × 0.6) words (default ≤120)
- **Sub-portions 2..K** — each covers one sub-aspect; ≤ `{page_size_soft}` words each. Set collectively covers the entire plan item.

Progress marker: `📍 {X}/{N} • sub {S}/{K} • {role-tag} • {Y} open questions • topic: "{plan-item}"`. Sub 1 tag = `summary`. Plan approved at E1 stays high-level; runtime decomposition is a delivery mechanism, not a plan change. May tell user once on sub 1: `this item needs K sub-portions to fit half-page each`.

### First-portion special shape (portion 1)

Anchors the session — different shape:
- **What this is** (1 sentence): `this is `{path}` — {KIND or type-from-content}, {one-line purpose from input}`
- **TL;DR** (1 sentence): `if you remember one thing — it's **{key takeaway}**` (with source ref)
- **Plan preview**: numbered list (re-anchored from E1)
- **Body** for plan item 1 (≤ `{page_size_soft}` words)
- **Per-portion progress marker** `📍 1/{N} • 0 open questions • topic: "{plan-item-1}"`
- **Navigation block**

By end of portion 1, the listener knows what they're learning, why, and the route ahead.

### Navigation block (6 fixed slots, Next-first; conditional 7th)

The 6 fixed slots are Next / Deeper / Lateral / Recap / Ask / Wrap. When the cfs-routing queue has ≥ 1 active item, methodology MUST append slot `7. Send comments — preview (K queued)` to the nav block. Slot 7 emits the structured preview only (per `storytelling.md` AP-#40); dispatch remains gated by `send comments now` / `Y`. The slot is omitted only when the queue is empty.

```text
Next:
  1. Next    — {next plan item: "{plan-item}"}
  2. Deeper  — {concrete question about current topic}
  3. Lateral — {related topic / linked artifact: "{ref}"}
  4. Recap   — summary of what's been covered so far
  5. Ask     — type your own question
  6. Wrap    — wrap up, save open questions
→ suggested: {1|2|3|4|5|6}
```

Slot rules:
- **Next** (slot 1, primary default) — actual next plan item; collapses into Wrap (slot 6) at last item; in review mode, points intra-item from presentation → challenge, then inter-item from challenge → next presentation
- **Deeper** — concrete question about the current topic, never generic
- **Lateral** — registered artifact: parent/child/related ID; unregistered: related concept/section; no candidate → `(no lateral candidates)` + End-of-thread mark
- **Recap** — bullet-form summary of everything covered so far, ordered by plan item, source-refs included; itself a portion (≤ soft target — decompose if too big, sub 1 = framing, sub 2..K = per-plan-item bullets); fresh nav block emits after
- **Ask** — methodology prompts `What's your question?` and reads free-text; routes through user-input rows (answer from input or push to open-questions)
- **Wrap** — always present

Suggested-slot heuristics:
- After intro/context-setting → `Next`
- After complex concept (new term first-mention, 3+ source quotes, recently-pushed user open-question) → `Deeper`
- Mid-plan with concrete linked artifact available → `Lateral`
- Every 4-5 portions OR after a user pivot → `Recap`
- At `X ≥ N-1` of plan → `Wrap`
- `Ask` rarely auto-suggested — user invokes it; methodology may suggest when ≥3 sub-aspects mentioned and Deeper would only cover one
- Default → `Next`

### User input handling

Recognition is intent-based; user may type these in any language (methodology MUST treat semantic equivalents as the same input).

| Input | Action |
|---|---|
| `1`/`2`/`3`/`4`/`5`/`6` or `next`/`deeper`/`lateral`/`recap`/`ask`/`wrap` (slot keyword alone) | Execute that slot literally; `next` is unambiguously slot 1 |
| `go` or Enter (alone) | Execute **suggested** slot |
| `recap`/`summary so far`/`summarize` | Execute Recap slot directly |
| `ask`/`question` (alone) | Execute Ask slot — prompt `What's your question?` and read free-text reply |
| Free-text question answerable from input | Answer with source ref |
| Free-text question NOT answerable from input | Acknowledge briefly + push as Q-{N} entry to the open-questions buffer (the **only** path that creates entries) |
| `change role to {X}` / `change audience to {X}` / `change diagram format to {X}` / `change plan` / `change mode to {X}` / `change page size to {soft}[/{hard}]` / `change artifact language to {X}` / `change disposition to {X}` | Update preference, ack, continue from next portion (mid-session override; does NOT update project preference unless followed by `remember new {field}`). For `disposition`, `{X}` ∈ {`chat-only`, `save-to-file`, `post-to-resource`, `mixed`} |
| `remember new mode` / `remember new page size` / `remember new language` / `remember new disposition` | Persist current value to `{cf-studio-path}/.cache/explain/preferences.json` |
| `bookmark` / `mark` / `важно` (or equivalents) | Push current point to takeaways buffer |
| `stop` / `wrap` / `enough` | Jump to Phase E5 (user-triggered wrap) |
| `send comments` / `flush queue` / `route queued` / intent equivalents | Trigger **batch flush** of all comment buffer entries with `dispatch_state == "queued"`. Render preview-then-confirm gate (unless `now` qualifier present). |
| `send comments now` / `<verb> now` | Trigger batch flush with one structured Y/n confirmation (skip preview-only step). Subject to Tier-3 inline pauses per `only intent` / `only tier` filter rules. |
| bare `send comments` / `preview comments` / `preview queue` | **Preview only** — render the queued-items report grouped by intent (risk-descending: generate → fix → brainstorm). NO dispatch. |
| `send comments [only Q-N,...] [except Q-N,...] [only intent <generate\|fix\|brainstorm>] [only tier <1\|2\|1-2>] [only fresh]` | Apply filters before flush. `only` / `except` mutually exclusive. Filters AND-combine. `only` + `except` together → parse error: `Cannot combine 'only' and 'except' in the same command — use one or the other.` Unknown tokens → parse error with quoted offending token. |
| `change to {generate\|fix\|brainstorm}` (when issued at a per-comment generate-routing sub-prompt before pressing 1/2) | Override the comment's `intent_final` BEFORE the action is applied. Same effect as inline shorthand `1 fix` / `2 brainstorm`. |
| `retry Q-N` | Retry the dispatch identified by Q-N. Subject to per-`dispatch_key` cap of 2 attempts, drift check (file etag + line-range hash, ±5 line buffer), and class-specific policy (see Dispatch-failure UX § below). |
| `inspect Q-N` | Open the auto-saved draft path (or the latest NDJSON record for Q-N) in the user's chat as a reference; no state change. |
| `drop Q-N` | Set comment buffer entry `dispatch_state = "dropped"`. Removes Q-N from any further retry / flush consideration. |
| `handoff Q-N` | Force Mode C paste-handoff for Q-N regardless of size gate. Emits the canonical Mode C paste block in chat. |

### Dispatch-failure notices (generate routing)

When a generate-routing dispatch fails, methodology emits ONE single-line notice per failure in the existing artifact-marker family (alongside `📋` / `📝` / `📤`):

```
⚠️ Q-N <class> ({subclass-hint?}) — <one-line message head>; <suggested-actions>
```

Placement rules:
- Notices land in the methodology's NEXT chat turn, BEFORE the next portion's Opening, separated from the portion by a single blank line.
- One notice line per failure.
- Multiple concurrent failures collapse into N consecutive lines sorted ascending by Q-N.
- NEVER appear inside Opening / Body / Mode-lens / Diagram / Source-refs / viz-marker / progress-marker / Nav. The 8-element portion shape is preserved.
- NO `---` separator. NO fenced `[generate-route]` block. NO new portion-structure element.

Per-class notice templates (one-line each; truncate first sentence with `…` if exceeds 80 cols; append ` (+N-1 more in dispatch-failures.jsonl)` overflow indicator when multiple validator issues):
- write_conflict: `⚠️ Q-3 write_conflict — target moved (etag mismatch); 'retry Q-3' / 'inspect Q-3' / 'drop Q-3'`
- transient_io:   `⚠️ Q-3 transient_io ({errno}) — retry possible (last attempt <60s); 'retry Q-3' / 'drop Q-3'`
- cfc_invocation_error/{subclass}: `⚠️ Q-3 cfc_invocation_error/kit_missing — {remediation-hint}; 'retry Q-3' / 'handoff Q-3' / 'drop Q-3'`
- validation_rejected: `⚠️ Q-3 validation_rejected ({rule-id}) — {first sentence of first issue}; 'edit-draft' / 'inspect Q-3' / 'drop Q-3'` (NO 'retry' in default suggested actions — content will re-fail unchanged)
- unknown:        `⚠️ Q-3 unknown — {message-head}; 'inspect Q-3' / 'retry Q-3' / 'drop Q-3'`

Full failure payload (all issues, rule context, full message, draft path) is appended to the dispatch-failures NDJSON per `requirements/storytelling-preferences.md` § Dispatch-Failure Audit Log. Notice in chat is the head; NDJSON is the canonical record.

Cross-reference: the 2-attempts-per-key cap (see Phase E3 buffer entry shape below), two-tier drift check, and mode escalation rules live in the comment buffer schema; this notice section documents the rendering surface only.

### Periodic gates

- **Open-questions reminder** every 3-4 portions if buffer ≥ 2: `📝 K open questions accumulated. Save now? (yes / no / wrap)`
- **Comprehension check** every 2-3 portions: `Before continuing — anything unclear from the last N portions? (yes / no)` — yes branches into Deeper on user-specified topic; no continues

(Auto-checkpoint during the session is **forbidden** — see `storytelling-preferences.md` Checkpoint and Resume.)

The two gates can stack on the same portion; consolidate into a single footer block.

### Glossary buffer

First mention of a term unfamiliar to the audience: inline parenthetical definition (`idempotency (property of an operation — repeated invocation produces the same result)`); push to glossary buffer; appears in wrap output. Definitions MUST come from the input or its registered linked artifacts; if no definition is available, **skip the inline gloss silently** — do NOT invent, do NOT push to open-questions on methodology's own initiative (open-questions are user-driven only).

## Phase E3: Strict-Context Boundary

Hard rules, enforced inside every portion:

1. **Information SHALL come from the input only**: target artifact / codebase region + its registered linked artifacts (parents/children fetched in E0) + the user's prompt. **Nothing else.**

2. **No invention. No agent-initiated gap markers.** If a claim cannot be grounded, the rule is **silently skip**. MUST NOT insert `[?]` markers in the methodology's narrative; MUST NOT push to open-questions buffer on its own initiative. Open-questions entries created **only** when the user asks a question the input cannot answer (see User input handling). NEVER paraphrase domain knowledge as if from the input.

3. **Source reference required** for every non-trivial claim, as a **clickable Markdown link** (plain-text refs like `(DESIGN.md §4.2)` are forbidden):
   - Unregistered file with heading: `(see [{file} §{section}]({path}#{anchor}))` — ex: `(see [DESIGN.md §4.2 Data Model](DESIGN.md#42-data-model))`
   - Unregistered file no anchor: `(see [{file}]({path}))`
   - Registered Studio artifact: `(see [{ID} §{section}]({resolved-path}#{anchor}))` — resolve path via `{cfs_cmd} --json where-defined {id}`
   - Code single line: `(see [{file}:{line}]({path}#L{line}))`
   - Code line range: `(see [{file}:{a}-{b}]({path}#L{a}-L{b}))`
   - Multiple refs same file: `(see [{file} §a]({path}#a), [§b]({path}#b))` — file name only on first
   - Anchor derivation matches GitHub-flavored Markdown / `{cfs_cmd} --json toc`: lowercase, drop punctuation other than spaces and hyphens, replace spaces with hyphens, collapse repeats. Ex: `## 4.2 Data Model & Schemas` → `#42-data-model--schemas`
   - **PR-target rule** (when target is a PR/MR): files-in-the-diff MUST use the PR-view inline-diff URL, NOT a commit-SHA blob URL. GitHub: `https://github.com/{owner}/{repo}/pull/{N}/files#diff-{file-hash}R{a}-R{b}` (R=right/added, L=left/removed; `{file-hash}` from `gh pr view --json files`). GitLab MR: `/merge_requests/{N}/diffs#{hash}_{a}_{b}`. Bitbucket PR: `/pull-requests/{N}/diff#chg-{path}`. Files NOT in the diff fall back to upstream + head-SHA blob URL (never branch — fork branches 404).
   - Trivial framing/connective sentences exempt.

4. **Analogies allowed with explicit disclaimer**: `(analogy — not from artifact): works similarly to {analogy}`. MUST NOT introduce facts; only illustrates an already-stated fact. MUST NOT be from another Studio artifact unless it's in scope. ≤ 1 analogy per 3 portions.

### Open-question buffer entry shape

5. **Open-question buffer entry shape** (in-memory, serialized at wrap):
   ```text
   {
     "id": "Q-{N}",
     "question": "{plain question to artifact author}",
     "context": "{portion / plan item / location}",
     "source_gap": "{what specifically is missing}",
     "likely_author": "{auto-guess: 'PRD author' | 'DESIGN author' | 'QA lead' | 'TBD'}",
     "dispatch_state": "drafted" | "queued" | "in-flight" | "completed" | "failed" | "dropped",
     "intent_initial": "generate" | "fix" | "brainstorm" | null,
     "intent_initial_tier": 1 | 2 | 3 | null,
     "intent_final": "generate" | "fix" | "brainstorm" | null,
     "intent_override_reason": string | null,
     "dispatch_key": "<sha1 — content-derived; see formula below>" | null,
     "dispatched_at": ISO-timestamp | null,
     "result_received_at": ISO-timestamp | null,
     "cfc_session_id": string | null,
     "result_summary": string | null,      // one-line, truncated to terminal width
     "paused_at": ISO-timestamp | null,    // Tier-3 inline pause marker
     "context_fingerprint": { "mtime": ISO-timestamp, "git_rev": "<short-sha or null>" },
     "last_failure": {
       "class": "write_conflict" | "transient_io" | "cfc_invocation_error" | "validation_rejected" | "unknown",
       "message": string,
       "ts": ISO-timestamp,
       "etag_at_dispatch": "<sha or null>",
       "line_range_hash_at_dispatch": "<sha or null>",
       "draft_path": "<relative path of preserved draft when auto-save fired, else null>"
     } | null
   }
   ```

   All new fields are additive; default null/absent for backward compatibility.

   **dispatch_key formula**:
   ```
   dispatch_key = sha1(
     target_path + "\n" +
     line_range +  "\n" +
     draft_body +  "\n" +
     failure_class
   )
   ```
   Content-derived. Editing the draft yields a new key (and a fresh 2-attempt budget). Replay produces the same key for unchanged inputs.

   **Initial dispatch (before any failure).** Compute the key with `failure_class = ""` (empty string). The key inserted into `session_state.dispatched_keys` at dispatch time uses this empty sentinel. After a failure occurs and a retry is issued, the key is recomputed using the recorded `failure_class` value — producing a different key, a fresh 2-attempt budget for the retry, and a new entry in `dispatched_keys` scoped to the new key. This is intentional: the initial dispatch and a failure-retry are distinct identity events.

   **Idempotence partition**: `session_state.dispatched_keys` is a `Map<canonical_path, Set<dispatch_key>>`. Pivoting target mid-session creates a fresh empty set for the new target only; the old target's dispatched_keys remain scoped to it.

   **Resume reconstruction**: `session_state.pending_retries: Map<dispatch_key, {attempts, first_failed_at, last_class, drift_status?}>` is reconstructed on session resume from the dispatch-failures NDJSON (`requirements/storytelling-preferences.md` § Dispatch-Failure Audit Log). Records with `status="resolved"` are excluded; the 2-attempts-per-key cap survives restarts.

## Phase E4: Visualize-by-Default

**Default disposition: visualize**. Aim for a visualization in every portion and every sub-portion. Text-only is the rare exception that requires an explicit, surfaced decision. Two-step decision **before** writing the body, surfaced via the `🎨 visualization:` marker:

**Step 1 — How to represent**:
- **Text + diagram** (default for any portion with multi-entity, multi-step, multi-aspect, comparative, transformational, or decision-bearing content — nearly all real inputs) → step 2.
- **Text only** — only when visualization would not aid comprehension. Permitted for genuinely single-thread linear narrative with one entity and no relationships / sequences / hierarchies / comparisons / decisions / timelines. Methodology MUST articulate *why*; "I don't feel like it" / "the prose is fine" / "the input is small" are NOT valid reasons.

**Step 2 — Construct, don't transcribe**: when diagram chosen, methodology **constructs** it from the portion's facts (Phase E3 grounding). MUST NOT copy an input diagram verbatim — input diagrams carry the original author's audience and depth assumptions, which differ from the session's audience.

Pick the shape that fits (guidance, not eligibility gates): ≥2 entities + relationships → flow / sequence; hierarchy ≥2 levels → tree / module map; ≥2 states → state diagram; ≥2 boundaries → data flow; decision tree ≥2 branches → decision diagram; ≥2 alternatives → comparison / quadrant; timeline ≥2 events → timeline.

Adapt detail to audience (per `storytelling-modes.md` Audience Adaptation):
- engineers / mixed → full technical labels, edge conditions, error paths
- product → outcome-oriented, happy-path emphasized
- leadership / customers → high-level boxes, internals collapsed
- new joiners → expanded labels with inline glossary

Diagrams MUST be self-contained — a reader looking only at the diagram should grasp the portion's structure.

**Portion-1 visualization default**: any non-socratic mode SHOULD include an overview diagram in Portion 1 by default (artifact's parts / PR scope / codebase top-level). Skipping requires an articulable reason in the marker. When Portion 1 is the first diagram-bearing portion (typical case), the **lazy-ask format prompt** MUST fire BEFORE Portion 1's body:
```text
Render this diagram as:
  1. ASCII inline in chat — instant, no files
  2. Mermaid in {cf-studio-path}/.cache/explain/diagrams-{slug}-{date}.md — open in renderer
  3. Both
→ suggested: 1
Choice applies to all diagrams this session. Override: `change diagram format to mermaid`.
```

Rendering: ASCII → fenced text in chat; Mermaid → open/append the file with `## Portion {N}: {plan-item}` header + ` ```mermaid` block (mkdir -p the directory first); Both → ASCII inline + append to file.

**Code-mode exception**: in code-mode, the **first portion always emits an ASCII module map** without lazy-asking — opening orientation requires a visual map. Subsequent diagrams use the lazy-ask flow normally.

**Decline diagrams** only when content is genuinely linear single-thread prose with no structural relationships; record the reason in the marker.

## Phase E5: Wrap

Two triggers:

1. **Plan exhausted** (last plan item delivered) → DON'T auto-finalize; methodology asks:
   ```text
   Plan complete ({N} of {N}). Next:
     1. Wrap-up — final review + open questions + key takeaways + next steps
     2. Lateral — one more related topic ("{auto-suggest}")
     3. Deeper  — dig into a covered topic ("{auto-suggest}")
     4. Another artifact — explain a related ID
   → suggested: 1
   ```
   When user picks Wrap-up, **before emitting wrap output**, methodology checks for a resume checkpoint for THIS session (e.g. session was paused mid-way and resumed). If one exists:
   ```text
   Session complete — the resume checkpoint at `{path}` is no longer needed. Delete it? (yes / no)
   → suggested: yes
   ```
   On `yes` → delete file, log `Resume checkpoint deleted ({path})`, emit wrap output without the `Resume this session` Suggested Next Step. On `no` → keep file; Resume entry MAY appear as a courtesy.

2. **User-triggered** (`stop` / `wrap` / `enough`) any time. Two cases:
   - **Plan complete** (last plan item already delivered) → equivalent to trigger 1 (jump to wrap output, after the optional checkpoint-delete prompt).
   - **Plan NOT complete** → first emit the checkpoint-and-resume prompt:
     ```text
     Session not complete — at portion {X} of {N}, plan items remaining: {list}.
     Save a checkpoint to resume later? (yes / no)
     - yes → write `{cf-studio-path}/.cache/explain/session-{slug}-{ISO-timestamp}.json`
       with the latest state. Resume by writing `explain --resume {session-id}` (or `resume explain session {session-id}`) in any new chat — the `analyze.md` WHEN-rule recognises the resume intent and routes here, then the methodology loads the checkpoint via Phase E0 invocation handling. There is no dedicated `cf explain` CLI subcommand — resume is a methodology-level intent-routed action.
     - no → continue to wrap output without writing a checkpoint. **No state is
       persisted; the session cannot be resumed.**
     → suggested: yes
     ```
     After answer (and after writing the checkpoint if accepted), emit wrap output. The Session block MUST report `Progress: {X} of {N} planned portions delivered (session ended early at user request)`. The `Resume this session` Suggested Next Step appears **only when a checkpoint was actually written** this turn.

### Wrap output (final response — replaces analyze.md Phase 4 schema)

```markdown
## Storytelling Wrap-up

### Session
- Mode: {mode}
- Role: {role}
- Audience: {audience}
- Input: `{path}` ({KIND if registered})
- Progress: {X} of {N} planned portions delivered
- Diagrams emitted: {count} ({ASCII | Mermaid → {path} | none})
- Open questions: {K}
- Bookmarks: {B}
- Glossary entries: {G}

### Key Takeaways (3-5 bullets)
1. **{takeaway}** — [{file} §{section}]({path}#{anchor}) / [{ID} §{section}]({path}#{anchor})
2. ...
(Bookmarked items appear verbatim, plus auto-selected key points up to 5 total. If `B > 5`, show all bookmarks with a one-line "auto-selected suppressed".)

### Open Questions ({K})
1. **Q-1**: {question}
   - Gap: {missing}
   - Likely author: {guess}
2. ...

Disposition for open questions this session: **{disposition}**.
- If `chat-only` → entries shown above are the only copy; copy them now or they're gone at session end.
- If `save-to-file` → already saved during the session to `{cf-studio-path}/.cache/explain/open-questions-{slug}-{YYYY-MM-DD}.md` ({K} entries). No re-prompt.
- If `post-to-resource` → already posted during the session ({K} succeeded, {failed} fell back to save-to-file → {fallback-path}). No re-prompt.

### Glossary ({G}) — if any
- **{term}**: {definition} — [{file} §{section}]({path}#{anchor})

### Bookmarked Takeaways Export ({B}) — if any
Same disposition rules as Open Questions above — `chat-only` shown inline (copy now); `save-to-file` already saved during the session to `{cf-studio-path}/.cache/explain/key-takeaways-{slug}-{YYYY-MM-DD}.md` (no re-prompt); `post-to-resource` already posted (no re-prompt).

### Suggested Next Steps (2-3, contextual; max 4 candidates)
0. **Resume this session**: write `explain --resume {session-id}` (or `resume explain session {session-id}`) in your next chat (checkpoint: `{path}`) — appears ONLY when a fresh checkpoint was written this turn (mid-session early wrap, user accepted save). Resume is a methodology-level intent-routed action, not a dedicated CLI subcommand.
1. `explain {linked-artifact-id}` — when registered linked artifacts exist
2. `validate `{path}` via /cf-analyze` — **only when target is a Studio-registered artifact** (resolved via `{cfs_cmd} --json where-defined {id}` / present in `artifacts.toml`); for unregistered files / external resources / generic codebase paths, this entry MUST NOT appear because `{cfs_cmd} validate` would fail with `Artifact not in Studio registry`
3. `forward open-questions to {likely-author}` — when buffer non-empty
4. `/cf-plan implement {path}` — only when KIND ∈ {PRD, DESIGN, FEATURE, ADR, DECOMPOSITION}
```

Pick 2-3 of the candidate next-steps contextually. **No `Fix Prompt` / `Plan Prompt`** — explicit override of `enforceRemediationPrompts`.
