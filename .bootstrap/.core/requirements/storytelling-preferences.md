---
cypilot: true
type: requirement
name: Storytelling Preferences
version: 1.0
purpose: Page size, artifact language, checkpoint, telemetry, failure modes for the storytelling methodology
---

# Storytelling Preferences


<!-- toc -->

- [Host Capability Matrix](#host-capability-matrix)
- [Page Size](#page-size)
- [Artifact Language](#artifact-language)
- [Artifact Disposition](#artifact-disposition)
- [Path Conventions (Portability)](#path-conventions-portability)
- [Output Language (chat)](#output-language-chat)
- [Checkpoint and Resume](#checkpoint-and-resume)
- [Bookmark Export](#bookmark-export)
- [TaskCreate Progress Tracking](#taskcreate-progress-tracking)
- [Telemetry / Execution Logging](#telemetry--execution-logging)
- [Failure Modes](#failure-modes)

<!-- /toc -->

Loaded by `requirements/storytelling.md` (router) for preference resolution and runtime state behavior. Project preferences live in `{cypilot_path}/.cache/explain/preferences.json` with keys: `default_mode`, `artifact_language`, `artifact_disposition`, `page_size_soft`, `page_size_hard`. Methodology MUST preserve unrelated keys when writing this file.

## Host Capability Matrix

The methodology assumes some host-runtime tools that may not be present in every Cypilot host. Methodology MUST probe for each capability at session start (Phase E0), record availability in working memory, and fall back gracefully — silent failure is forbidden.

| Capability | Used for | Probe | Fallback when absent |
|---|---|---|---|
| `Read` / `Write` / `Edit` (host file IO) | Reading inputs, writing artifacts at wrap | (always required) | None — methodology cannot run without basic file IO; abort with explicit error |
| `WebFetch` (or `curl` shell) | Phase E0 input access CLI tier — non-auth URL fetches | `command -v curl` and presence of `WebFetch` tool | Drop the URL fetch tier; jump to user-fallback step (paste / local path); MUST NOT silently fail |
| `gh` CLI | Phase E0 input access CLI tier — GitHub PR / issue fetches; Artifact Disposition `post-to-resource` (PR review comments via `gh pr review`) | `command -v gh` | MCP tier (`mcp__github__*`); skill tier; user-fallback. For posting: fall back to `save-to-file` for that artifact type with explicit note in chat |
| `glab` CLI | Phase E0 input access CLI tier — GitLab MR / issue fetches; posting via `glab mr note` | `command -v glab` | MCP tier; skill tier; user-fallback / `save-to-file` |
| MCP servers (`mcp__github__*`, `mcp__plugin_Notion_notion__*`, `mcp__plugin_atlassian_jira__*`, etc.) | Phase E0 input access MCP tier (preferred); Artifact Disposition `post-to-resource` for matching resource | Tool list at session start | Skill tier; CLI tier; user-fallback. For posting: `save-to-file` for that artifact type |
| Skills (`Notion:find`, `Notion:search`, `coderabbit:autofix`, etc.) | Phase E0 input access skill tier | Available-skills list at session start | CLI tier; user-fallback |
| `TaskCreate` / `TaskUpdate` (host task API) | Plan progress tracking when `N > 5` portions | Tool presence check | Emit progress as inline telemetry log lines instead (`- [storytelling]: Portion 3/5 emitted`) — same information, no persistent task list |
| `mkdir -p` (filesystem) | Cache directory creation at wrap-time, package directory creation in export mode | (basic shell — almost always present) | If directory create fails (permission, disk full): warn user with the exact filesystem error; emit wrap output normally; flag in Session block that persistence failed; omit `Resume this session` / file-save next-steps from Suggested Next Steps |

At Phase E0 entry, methodology probes each capability (cheap probes only — `command -v X`, tool-list scan, no network calls during the probe). The result is held in working memory as `{capability_map}` and consulted whenever an input access tier is selected (Phase E0), an artifact disposition is offered (Artifact Disposition section above — the `post-to-resource` availability-status is computed from this map), or a progress-tracking decision is made (TaskCreate Progress Tracking below). The capability matrix is NOT user-visible by default; it surfaces in chat only when (a) the user-fallback prompt fires (showing what was tried and what's missing), or (b) the disposition prompt's `post-to-resource` availability-status is shown.

## Page Size

Resolution at every portion-emission decision (priority order):
1. **Mid-session override**: `change page size to {soft}` (auto-derives hard as `round({soft} × 1.75)`) or `change page size to {soft}/{hard}` for explicit values
2. **Project preference**: `page_size_soft` / `page_size_hard` from `preferences.json`
3. **Defaults**: soft 200, hard 350

The resolved values feed: Phase E2 portion-shape size invariant, proactive sub-portion decomposition trigger, hard-cap recovery, first-portion shape, Recap sub-portion size budget. Methodology never auto-asks for page size — defaults cover most users.

`remember new page size` persists current values to `preferences.json`.

## Artifact Language

Persisted artifacts (open-questions file, diagrams file, key-takeaways file) MUST be written in a language **explicitly chosen by the user**, NOT inferred from chat language. This preserves portability — artifacts may be shared with the artifact's author, archived, or read by people whose first language differs.

Resolution at every artifact-write event (priority order):
1. **Mid-session override**: `change artifact language to {X}` / `set artifact language to {X}`
2. **Session choice**: if asked this session and user picked but chose NOT to remember, use that value
3. **Project preference**: `artifact_language` from `preferences.json`
4. **Ask** — at the first artifact-write event of the session (Phase E4 Mermaid creation, Phase E5 open-questions save, or Phase E5 key-takeaways save):
   ```text
   I'm about to save artifacts in this session. What language for saved files
   (open questions, diagrams, key takeaways)?
     1. English (most portable)
     2. {detected-chat-language} — your prompt language
     3. Other — specify in your reply
   Remember this choice for all future explain sessions in this project? (yes / no)
   → suggested: 1, remember=yes
   ```
   On `remember=yes` write `{"artifact_language": "{value}"}` to `preferences.json` (mkdir -p if missing). On `remember=no` hold value in working memory for the rest of the session only.

**Scope**: artifact language affects free-prose surfaces (file headers, section titles, question text, takeaway text, captions). Does NOT change technical surfaces (IDs, Mermaid node identifiers, code snippets). Source quotes are NOT translated — they stay in the artifact's original language.

**Buffer translation at save time**: methodology MAY hold buffer entries (open-questions / takeaways / glossary) in chat language during the session; at save time, translate prose surfaces to chosen artifact language before writing. Source quotes never translated.

`change artifact language to {X}` switches subsequent writes; `remember new language` persists.

## Artifact Disposition

Some artifacts accumulate during a session and need an explicit handling decision: where the user wants the methodology to put each accumulated artifact at the end. Affected artifact types:

- **Review comments** (review mode only — line-anchored review notes drafted via the Comment slot in challenge portions)
- **Open questions** (any mode — entries pushed when the user asks a question the input cannot answer)
- **Key takeaways / bookmarks** (any mode — items the user marked with `bookmark` / `mark` plus auto-selected key points)

Other artifacts have their own dispositions or are inline-only:
- Diagrams → format chosen via Phase E4 lazy-ask (ASCII / Mermaid file / Both)
- Glossary → always inline in the wrap output (no separate disposition)
- Mode-specific extras (decision recommendation, change-impact map, onboarding reading roadmap, socratic scorecard) → follow the disposition picked for the session's primary artifact (`save-to-file` writes them as additional sections in the wrap file; `chat-only` shows them in the wrap response; `post-to-resource` posts them as a summary comment when supported)

All three disposition options take effect **immediately on each artifact-create event** (Comment-slot use in review, push to the open-questions buffer, bookmark mark) — NOT deferred to wrap. This matters because wrap ends the session: deferring to wrap would force the user to choose between continuing the review and saving comments, which is broken UX. The session continues normally after each artifact is persisted.

1. **`chat-only` (draft)** — methodology surfaces the artifact **right now in chat** as a ready-to-copy fenced block, with a one-line note like `📋 drafted comment Q-3 (chat-only — copy this now or it's gone at session end)`. Artifact is held in working memory only; the wrap output re-shows all `chat-only` drafts as a final consolidated block for last-chance copy. The user copies, pastes, or discards manually.

2. **`save-to-file`** — methodology **appends** the artifact to its file **immediately** on the create event (with mkdir -p on first append):
   - `{cypilot_path}/.cache/explain/review-comments-{slug}-{date}.md` (review mode only)
   - `{cypilot_path}/.cache/explain/open-questions-{slug}-{date}.md`
   - `{cypilot_path}/.cache/explain/key-takeaways-{slug}-{date}.md`

   On first append in a session, methodology writes a session header (`## Session {ISO-timestamp} — {role} for {audience}, mode={mode}`) so multiple intra-day sessions on the same target accumulate without overwriting. Each artifact entry is appended under that header. Methodology emits a one-line confirmation in chat per append: `📝 Q-3 appended to {path} (line 42)`. The session continues immediately — wrap does NOT re-prompt for save (already saved). Wrap output reports the cumulative path + entry count.

3. **`post-to-resource`** — methodology **posts** the artifact directly to the target **right now** via the same access tier that fetched the input (MCP / skill / CLI). Availability check at session start:
   - GitHub PR (target_is_pr=true) — review comments via `gh pr review {N} --comment-file ...` or `mcp__github__create_review_comment`; open-questions / takeaways as a single summary comment via `gh pr comment` or equivalent
   - GitLab MR — `glab mr note` or MCP equivalent
   - Notion page — MCP `mcp__plugin_Notion_notion__*` comment-create
   - Jira ticket — MCP Jira add-comment
   - Other — post unavailable; methodology MUST tell the user during the disposition prompt and fall back to `save-to-file`

   Each post is **confirmed immediately on the artifact-create event**, not at wrap. Methodology shows the post payload (file:line + comment body for review comments; question text + author tag for open-questions) and asks:
   ```text
   Post this draft now to {target}?
     1. Post — send to {target} via {handler}
     2. Save instead — append to {save-to-file path} for this item only
     3. Discard — drop this artifact, don't save or post
     4. Skip rest — switch disposition to save-to-file for ALL remaining items in this session
   → suggested: 1
   ```
   On `Post`: methodology calls the handler; on success, emits one-line confirmation `📤 Q-3 posted to PR #25 ({URL})`; on failure (network / permissions / rate limit), reports the exact error AND falls back to save-to-file for that item with `📝 Q-3 post failed ({error}) — saved to {path} instead`. The session continues immediately. Wrap output reports cumulative post count + any failures.

**Crucial: deferring artifact persistence to wrap is FORBIDDEN** for `save-to-file` and `post-to-resource` dispositions. Saying "I'll save this at wrap" when the user picked save-to-file is broken UX (wrap ends the session, so user can't both continue and save). Persistence happens immediately; the session continues uninterrupted; wrap merely reports the cumulative results. See Anti-Pattern #28d.

**Resolution at session start** (Phase E1, after mode resolution and before role/audience confirmation):

```text
This {mode} session may produce accumulating artifacts:
{conditional list per mode — review comments / open questions / bookmarks}

How should they be handled at session end?
  1. chat-only — draft in chat, you copy/paste manually
  2. save-to-file — write to {cypilot_path}/.cache/explain/{...}-{slug}-{date}.md at wrap
  3. post-to-resource — try to post directly to {target} ({availability-status}); fall back to save-to-file when post fails or unavailable; each post confirmed individually
  4. mixed — pick per artifact type (secondary prompt)

→ suggested: {S} ({why-suggested})

Remember this choice for all future explain sessions in this project? (yes / no)
```

`{S}` is computed in priority order: project preference (`artifact_disposition` from `preferences.json`) → `save-to-file` (default; preserves history; reliable). `{availability-status}` shows what's posting-available for the resolved target (e.g. `posting available via MCP github tool` / `posting available via gh CLI` / `posting NOT available — falls back to save-to-file`).

On `remember=yes`, write `{"artifact_disposition": "{value}"}` to `preferences.json`. The disposition prompt always emits at session start (like the mode prompt) — preferences.json informs the suggested default but does NOT bypass the prompt. Methodology MUST NOT proceed past the prompt without an explicit user response.

**Override mid-session**: `change disposition to {X}` switches subsequent artifact handling. `remember new disposition` persists. `mixed` mode triggers a per-type prompt (review-comments? open-questions? bookmarks?) at first use of each artifact type.

**Explicit drafting requirement** (applies to all dispositions): every time the methodology drafts an artifact (Comment slot in review, push to open-questions, bookmark), it MUST surface a one-line note in chat indicating disposition status, e.g.:
- `📋 drafted comment Q-3 (chat-only — copy at wrap)` /
- `📝 added Q-3 to open-questions buffer (save-to-file at wrap → {path})` /
- `📤 posting comment Q-3 to PR... [yes / no / skip-rest]?`

Silent drafting (artifact created but nothing emitted in chat) is forbidden — see Anti-Patterns.

## Path Conventions (Portability)

All explain-generated artifacts and references **inside** them MUST use **relative paths**, never absolute paths. This makes the artifacts portable across machines, repo clones, container mounts, and CI workspaces. Hardcoding `/Users/viator/...` or `/Volumes/...` into a comments file or a checkpoint breaks immediately when the file is shared or the project is cloned to a different location.

**Scope** (covers every artifact the methodology can write to disk):

| Artifact / surface | Relative-path requirement |
|---|---|
| Per-portion files inside an export package | Internal links to other portion files: relative within the package (`portion-002-data-model.md`). External refs to source artifacts: relative from the package directory (e.g. `../../../requirements/auth-prd.md#anchor`) — NEVER absolute |
| `index.md` in an export package | All file refs in plan list, navigation graph, and wrap-up: relative (same rules as above). Mermaid graph node hrefs: relative |
| `review-comments-{slug}-{date}.md` (loose artifact under `{cypilot_path}/.cache/explain/`) | File:line references inside comments: relative path from project root (e.g. `requirements/auth.md:42`), NEVER absolute. When `target_is_pr`: PR-view URL form per Phase E3 (those URLs are already canonical/portable) |
| `open-questions-{slug}-{date}.md` | Same as comments file — source-path refs are relative-from-project-root or PR-view URLs |
| `key-takeaways-{slug}-{date}.md` | Same |
| `diagrams-{slug}-{date}.md` (Mermaid file) | Diagram body uses identifiers (no paths). Source-ref captions use relative paths |
| `session-{slug}-{ISO-timestamp}.json` (checkpoint) | `input_path` field: relative from project root (so a resumed session works after `git clone` to a different directory). `path` fields in any buffer entry: relative |
| Chat-displayed paths (artifact-create confirmations, wrap output Session block, save-to-file confirmations) | Display as relative from project root when emitting in chat (e.g. `📝 Q-3 appended to .bootstrap/.cache/explain/review-comments-...md`); the underlying filesystem call MAY use the absolute resolved form, but the user-visible string is relative |

**Resolution rule**: convert `{cypilot_path}` and `{project_root}` template variables to relative-from-project-root form before writing to artifact content or displaying in chat. The resolved-absolute form is held in working memory only for filesystem syscalls; never persisted into artifact bytes.

**`{project_root}` reference rule**: when a path goes outside the package or cache directory (e.g. an export package's portion file refs the source `requirements/auth-prd.md`), express it relative-from-project-root with explicit `../` prefixes so the package can be opened from any location and a Markdown renderer resolves the link correctly. Example: from `{cypilot_path}/.cache/explain/packages/{slug}/portion-002-data-model.md`, the relative ref to `requirements/auth-prd.md` is `../../../../requirements/auth-prd.md` (three `../` to escape `.cache/explain/packages/{slug}/` plus one to escape `{cypilot_path}` if cypilot_path is one level deep like `.bootstrap`). Compute the depth from the actual artifact location, not a hardcoded count.

**Anti-pattern** (also see router Anti-Patterns): writing `/Users/...` or `/Volumes/...` or `/home/...` into any explain-generated artifact body. The methodology MUST detect such absolute paths in any string about to be written and convert them to relative form first.

## Output Language (chat)

Chat output (the live narrative) follows different rules from artifact language:
- **Match user prompt language** (auto-detected on first user message)
- **Source quotes** remain in the **original artifact language** (never translated)
- If audience and source language differ, methodology MAY add parenthesised translation when audience-helpful (e.g. RU artifact + EN audience: `"{quote ru}" (≈ "{translation en}")`)

**Language complexity** (global Cypilot rule): both chat output and persisted artifacts also respect the project's resolved `language_complexity` level (`low` / `middle` / `high`, default `middle`) per `{cypilot_path}/.core/requirements/language-complexity.md`. The methodology MUST self-check every chat message and every artifact write against the resolved level — no rare/archaic words at `middle`, no long sentences at `low`, etc. Override commands (`change language complexity to {X}` / `remember new language complexity` / `show language complexity`) work mid-session. Source quotes are exempt (quoted verbatim).

## Checkpoint and Resume

- **File**: `{cypilot_path}/.cache/explain/session-{slug}-{ISO-timestamp}.json` (resolves `{cypilot_path}` from project config; do NOT hardcode `.cypilot/`)
- **Directory**: if `{cypilot_path}/.cache/explain/` does not exist, methodology MUST create it (mkdir -p) at the moment of the wrap-time write. Same applies to diagrams / open-questions / key-takeaways files.
- **`{slug}` derivation**: basename without extension, lowercased, non-alphanumeric → hyphens. `requirements/my-prd.md` → `my-prd`. External resources: `gh-{owner}-{repo}-pr-{N}`, `jira-{key}`, `notion-{slugified-title}`, `url-{domain}-{path}`. Same `{slug}` flows through `session-`, `diagrams-`, `open-questions-`, `key-takeaways-`, package-directory.
- **Trigger** (the ONLY trigger): user accepts the checkpoint prompt during a mid-session Wrap (Phase E5 trigger 2, plan-not-complete branch). Auto-checkpointing during the session is **forbidden** — no periodic writes, no Phase-transition writes, no pivot writes. State is held in working memory and persisted only at the natural stopping point if the user opts in.
- **State persisted**: `mode, role, audience, plan, current_position, open_questions_buffer, takeaways_buffer, diagram_format, glossary_buffer, telemetry_log, input_hash, target_is_pr`
- **Resume invocation**: write `explain --resume {session-id}` (or `resume explain session {session-id}`) in any chat where `{session-id}` is the ISO-timestamp suffix. The `analyze.md` WHEN-rule recognises the resume intent verb and routes here; the methodology then loads the checkpoint at Phase E0 invocation handling. There is no dedicated `cypilot explain` CLI subcommand — resume is a methodology-level intent-routed action, not a CLI entrypoint
- **On resume**:
  - Load state from JSON
  - If the input file at the stored path is missing or unreadable, abort with `Input '{path}' no longer exists or is unreadable; cannot resume session.` and do NOT proceed
  - Re-read input; verify unchanged via stored `input_hash`; warn if changed and require user confirmation to continue
  - Print 1-line resume header: `Resuming session {id}, role={role}, audience={audience}, mode={mode}, at portion {X}/{N}`
  - Continue from `current_position`

**Cleanup at completion**: when user picks Wrap-up at plan exhaustion AND a resume checkpoint exists for THIS session, methodology asks `Delete it? (yes / no)` with default `yes`. On `yes` → delete file, log telemetry, omit `Resume this session` from Suggested Next Steps. On `no` → keep file; entry MAY appear as a courtesy reference.

## Bookmark Export

On wrap, after open-questions save prompt:
```text
Save bookmarks ({B} items) to {cypilot_path}/.cache/explain/key-takeaways-{slug}-{YYYY-MM-DD}.md? (yes / no / path)
```
File contains: header (input, role, audience, mode, date), numbered takeaways with clickable source refs, glossary section if non-empty. Written in resolved artifact language.

## TaskCreate Progress Tracking

For plans with `N > 5` portions (note: review-mode `2 × N` may push this), after E1 plan approval:
- Call `TaskCreate` once with one task per plan item
- Mark each task `in_progress` when entering its portion (presentation portion in review)
- Mark `completed` after navigation block emitted (challenge portion in review)

For `N ≤ 5`, no TaskCreate (overhead not justified).

## Telemetry / Execution Logging

Inherits cypilot-skill execution logging style:
- `- [storytelling]: Entering Phase E1 — discovery (audience known: false)`
- `- [storytelling]: Mode resolved — {mode} ({why-suggested})`
- `- [storytelling]: External input resolved via {tier} {handler}`
- `- [storytelling]: Completed Phase E1 — role: Software Architect, audience: engineers, plan: 5 portions`
- `- [storytelling]: Portion 3/5 emitted (size: 187 words, open-questions delta: +1)`
- `- [storytelling]: Wrap-checkpoint written to {path} (user accepted at mid-session wrap)`
- `- [storytelling]: Resume checkpoint deleted ({path})`
- `- [storytelling]: User pivot — Lateral to ADR-0042`

## Failure Modes

| Condition | Behavior |
|---|---|
| Input not readable | Stop with suggestion (inherit `analyze.md` Phase 1) |
| External resource — all fetch tiers (MCP / skill / CLI) failed or unavailable | User-fallback prompt with paste / local-path / cancel options (NO arbitrary shell-command option) |
| Input registered, parent ID broken in registry | Warn, continue without that lateral candidate |
| User asks question requiring external knowledge | Polite refuse + push to open-questions: `this requires knowledge beyond `{path}`, added to open questions` |
| Methodology output exceeds soft cap (default 200 words) | Auto-trim with ack `trimmed to keep within format`; exceeds hard cap (default 350) → split into two portions sharing the plan-item index with letter suffixes (`3a`, `3b`) |
| All 6 nav slots vacuous | Mark End-of-thread; offer Wrap or `/cypilot-analyze` as next step |
| Diagram opportunity check fires but content has ≤2 entities and no structural relationships | Decline diagram in the `🎨 visualization:` marker with reason; continue with prose |
| Glossary term has no clear definition in input | **Skip the inline gloss silently**. Do NOT invent a definition; do NOT push to open-questions on methodology's own initiative — open-questions are user-driven only. The first-mention term is used as-is without a parenthetical |
| Wrap-time checkpoint write fails (permission, disk full) | Warn with the exact filesystem error; emit wrap output normally but flag in the Session block that checkpoint was NOT persisted; do NOT include `Resume this session` in Suggested Next Steps |
| User mid-portion override (role / audience / format / mode / page-size / artifact-language) | Acknowledge, finish current portion under old settings, apply new from next portion |
| Both `EXPLAIN_MODE` and `PROMPT_REVIEW` intent detected | Ask user to disambiguate before loading either methodology |
