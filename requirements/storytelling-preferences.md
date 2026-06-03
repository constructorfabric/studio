---
cf: true
type: requirement
name: Storytelling Preferences
version: 1.0
purpose: Page size, artifact language, checkpoint, telemetry, failure modes for the storytelling methodology
---

# Storytelling Preferences


<!-- toc -->

- [Host Capability Matrix](#host-capability-matrix)
  - [Context-pack reuse for generate routing](#context-pack-reuse-for-generate-routing)
- [Page Size](#page-size)
- [Artifact Language](#artifact-language)
- [Artifact Disposition](#artifact-disposition)
- [Dispatch-Failure Audit Log](#dispatch-failure-audit-log)
- [Path Conventions (Portability)](#path-conventions-portability)
- [Output Language (chat)](#output-language-chat)
- [Checkpoint and Resume](#checkpoint-and-resume)
- [Bookmark Export](#bookmark-export)
- [TaskCreate Progress Tracking](#taskcreate-progress-tracking)
- [Telemetry / Execution Logging](#telemetry--execution-logging)
- [Failure Modes](#failure-modes)

<!-- /toc -->

Loaded by `requirements/storytelling.md` (router) for preference resolution and runtime state behavior. Project preferences live in `{cf-studio-path}/.cache/explain/preferences.json` with keys: `default_mode`, `artifact_language`, `artifact_disposition`, `page_size_soft`, `page_size_hard`.

```pdsl
UNIT StorytellingPreferencesFile

PURPOSE:
  Enforce safe read/write behavior for the preferences.json file.

RULES:
  - ALWAYS preserve unrelated keys when writing preferences.json
```

## Host Capability Matrix

The methodology assumes some host-runtime tools that may not be present in every Studio host.

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
| `generate_dispatch` | Phase E0 input access — derives `handle.generate_route_available` for the generate-routing sub-prompt gate | tool list at session start includes `cf-generate` skill OR `Skill` tool can invoke `cf-generate` | `generate_route_available=false`; sub-prompt suppressed entirely (no "unavailable" message) |

Cross-reference: the preflight Step 5b sub-rule (see `{cf-studio-path}/.core/skills/studio/agents/storytelling-preflight.md` § Step 5b).

```pdsl
UNIT HostCapabilityProbe

PURPOSE:
  Probe for host capabilities at session start and record availability for runtime decisions.

WHEN:
  - REQUIRE Phase E0 entry

DO:
  - RUN cheap probes for each capability: command -v X, tool-list scan; no network calls during probe
  - SET capability_map: record availability of each capability in working memory
  - CONTINUE with capability_map consulted for input access tier selection, artifact disposition post-to-resource availability, and progress-tracking decisions

RULES:
  - ALWAYS probe each capability at session start (Phase E0)
  - NEVER silently fail when a capability is absent; fall back gracefully
  - NEVER surface capability_map to the user by default; only surface when user-fallback prompt fires or disposition prompt post-to-resource availability-status is shown
  - NEVER run without basic file IO (Read/Write/Edit); abort with explicit error if absent
```

### Context-pack reuse for generate routing

When dispatching generate-routing (Mode A / B / C), the orchestrator passes a `pack_handle` instead of inlining the full pack body:
```
pack_handle = {
  session_id: <string>,
  kit_path: <string>,         // path to the persisted content_pack.json
  anchor_ids: [<string>, ...] // ordered by line_range.start; primary = largest overlap
}
```

```pdsl
UNIT ContextPackReuse

PURPOSE:
  Define how consumers load and verify context packs passed by the generate-routing orchestrator.

WHEN:
  - REQUIRE generate-routing dispatch occurs (Mode A / B / C)

DO:
  - LOAD persisted content_pack from kit_path
  - REQUIRE etag field matches; re-dispatch storytelling-context-pack on etag mismatch, unreadable kit_path, or kit_path == null

RULES:
  - NEVER branch reasoning on content_pack.strategy
  - ALWAYS use resolved_section_text verbatim when target anchor has resolved_section_text != null
  - ALWAYS issue a narrow Read against canonical_path for the anchor's line_range when resolved_section_text is null
  - ALWAYS select Mode B inline dispatch when target file is < 50 KB; use Mode C paste-handoff above that
```

## Page Size

Resolution at every portion-emission decision (priority order):
1. **Mid-session override**: `change page size to {soft}` (auto-derives hard as `round({soft} × 1.75)`) or `change page size to {soft}/{hard}` for explicit values
2. **Project preference**: `page_size_soft` / `page_size_hard` from `preferences.json`
3. **Defaults**: soft 200, hard 350

```pdsl
UNIT PageSizeResolution

PURPOSE:
  Resolve page size at every portion-emission decision.

STATE:
  - SET page_size_soft: integer
    default: 200
  - SET page_size_hard: integer
    default: 350

WHEN:
  - REQUIRE portion-emission decision occurs

DO:
  - SET page_size_soft: mid-session override value when provided
  - SET page_size_hard: round(soft × 1.75) when only soft is overridden; explicit value when provided
  - SET page_size_soft: preferences.json page_size_soft when no mid-session override
  - SET page_size_hard: preferences.json page_size_hard when no mid-session override
  - SET page_size_soft: 200 when no preference and no override
  - SET page_size_hard: 350 when no preference and no override

RULES:
  - NEVER auto-ask for page size; defaults cover most users
  - ALWAYS persist current values to preferences.json when user says remember new page size
```

## Artifact Language

Persisted artifacts (open-questions file, diagrams file, key-takeaways file) MUST be written in a language **explicitly chosen by the user**, NOT inferred from chat language. This preserves portability — artifacts may be shared with the artifact's author, archived, or read by people whose first language differs.

Resolution at every artifact-write event (priority order):
1. **Mid-session override**: `change artifact language to {X}` / `set artifact language to {X}`
2. **Session choice**: if asked this session and user picked but chose NOT to remember, use that value
3. **Project preference**: `artifact_language` from `preferences.json`
4. **Ask** — at the first artifact-write event of the session

```pdsl
UNIT ArtifactLanguageResolution

PURPOSE:
  Resolve artifact language at every artifact-write event using explicit user choice, never inference.

STATE:
  - SET artifact_language: string
    default: unset

WHEN:
  - REQUIRE an artifact-write event occurs (Phase E4 Mermaid creation, Phase E5 open-questions save, or Phase E5 key-takeaways save)

DO:
  - SET artifact_language: mid-session override value when provided
  - SET artifact_language: session choice when user chose this session without remembering
  - SET artifact_language: preferences.json artifact_language when no session override
  - EMIT language choice prompt at the first artifact-write event of the session when no preference or session choice exists:
    "I'm about to save artifacts in this session. What language for saved files (open questions, diagrams, key takeaways)? 1. English (most portable) 2. {detected-chat-language} — your prompt language 3. Other — specify in your reply"
  - WAIT user.reply for language choice
  - EMIT "Remember this choice for all future explain sessions in this project? (yes / no) → suggested: yes"
  - WAIT user.reply for persistence decision
  - SET artifact_language in preferences.json with mkdir -p when remember = yes

RULES:
  - NEVER infer artifact language from chat language
  - ALWAYS apply artifact language to free-prose surfaces: file headers, section titles, question text, takeaway text, captions
  - NEVER change technical surfaces: IDs, Mermaid node identifiers, code snippets
  - NEVER translate source quotes; keep them in the artifact's original language
  - ALWAYS hold buffer entries in chat language during session; translate prose surfaces to chosen artifact language at save time
  - ALWAYS persist to preferences.json when user says remember new language
```

## Artifact Disposition

Some artifacts accumulate during a session and need an explicit handling decision. Affected artifact types:

- **Review comments** (review mode only — line-anchored review notes drafted via the Comment slot in challenge portions)
- **Open questions** (any mode — entries pushed when the user asks a question the input cannot answer)
- **Key takeaways / bookmarks** (any mode — items the user marked with `bookmark` / `mark` plus auto-selected key points)

Other artifacts have their own dispositions or are inline-only:
- Diagrams → format chosen via Phase E4 lazy-ask (ASCII / Mermaid file / Both)
- Glossary → always inline in the wrap output (no separate disposition)
- Mode-specific extras → follow the disposition picked for the session's primary artifact

**Option 1 — `chat-only` (draft)**: methodology surfaces the artifact right now in chat as a ready-to-copy fenced block with a one-line note. Artifact is held in working memory only; the wrap output re-shows all `chat-only` drafts as a final consolidated block for last-chance copy.

**Option 2 — `save-to-file`**: methodology appends the artifact to its file immediately on the create event (with mkdir -p on first append):
- `{cf-studio-path}/.cache/explain/review-comments-{slug}-{date}.md` (review mode only)
- `{cf-studio-path}/.cache/explain/open-questions-{slug}-{date}.md`
- `{cf-studio-path}/.cache/explain/key-takeaways-{slug}-{date}.md`

On first append in a session, methodology writes a session header (`## Session {ISO-timestamp} — {role} for {audience}, mode={mode}`).

**Option 3 — `post-to-resource`**: methodology posts or routes the artifact to the resolved target right now via the same access tier that fetched the input (MCP / skill / CLI), or via generate-routing for a local editable file. Branch priority: GitHub PR → GitLab MR → Notion page → Jira ticket → Local file (when `handle.local_editable == true` AND `handle.generate_route_available == true`) → fallback to `save-to-file`.

```pdsl
UNIT ArtifactDisposition

PURPOSE:
  Define timing, resolution, and persistence rules for artifact disposition.

STATE:
  - SET disposition: chat-only | save-to-file | post-to-resource | mixed
    default: save-to-file

WHEN:
  - REQUIRE Phase E1 begins, after mode resolution and before role/audience confirmation

DO:
  - EMIT disposition prompt with conditional artifact list per mode and four options
  - WAIT user.reply for disposition choice
  - EMIT "Remember this choice for all future explain sessions in this project? Reply yes or no."
  - WAIT user.reply for persistence decision
  - SET disposition in preferences.json when remember = yes
  - CONTINUE with resolved disposition applied immediately on each artifact-create event

RULES:
  - ALWAYS emit disposition prompt at session start; preferences.json informs suggested default but does NOT bypass the prompt
  - NEVER proceed past the disposition prompt without an explicit user response to both the disposition prompt and the persistence prompt
  - ALWAYS apply chosen disposition immediately on each artifact-create event; never defer to wrap
  - ALWAYS emit one-line note in chat for every artifact draft (e.g. "📋 drafted comment Q-3 (chat-only — copy from chat; wrap will repeat drafts)" / "📝 appended Q-3 to {path} (save-to-file; persisted now)" / "📤 posting comment Q-3 to PR... [yes / no / skip-rest]?")
  - NEVER silently draft an artifact; every artifact creation must produce a chat notification
  - ALWAYS compute {S} suggested option: project preference -> save-to-file (default)
  - ALWAYS fall back to save-to-file when post-to-resource is unavailable; tell user the concrete reason
  - NEVER show the legacy "posting NOT available — falls back to save-to-file" line when the local-file branch applies
  - ALWAYS allow mid-session override: change disposition to {X} switches subsequent artifact handling
  - ALWAYS persist on remember new disposition

NOTES:
  post-to-resource confirmation prompt shape:
  "Confirm what to do with this draft.
  Action: {post_action_label}
  Target: {target}
  Effect:
    - Reply 1: {post_action_effect}
    - Reply 2: append this item to {save-to-file path} and do not post or route it
    - Reply 3: discard this item and persist nothing
    - Reply 4: switch all remaining items in this session to save-to-file
  Reply with exactly one number from 1-4."
  post_action_label and post_action_effect MUST be branch-specific (see Artifact Disposition section prose).
```

```pdsl
UNIT ArtifactPersistenceRules

PURPOSE:
  Prohibit deferred artifact persistence and enforce immediate-on-create behavior.

RULES:
  - NEVER defer artifact persistence to wrap for save-to-file or post-to-resource dispositions
  - ALWAYS persist immediately when save-to-file disposition is active; wrap reports cumulative results only
  - ALWAYS confirm each post or route action immediately on the artifact-create event; show exact payload, resolved target, and fallback path
  - ALWAYS fall back to save-to-file on post failure; report the exact error
  - ALWAYS emit one-line confirmation per append for save-to-file: "📝 Q-3 appended to {path} (line 42)"
```

## Dispatch-Failure Audit Log

When a generate-routing dispatch fails (any of the five locked failure classes `{write_conflict, transient_io, cfc_invocation_error, validation_rejected, unknown}`), methodology appends one NDJSON record to:

```
{cf-studio-path}/.cache/explain/dispatch-failures-{slug}-{ISO-date}.jsonl
```

Per-failure record schema:
```json
{
  "dispatch_key": "<sha1>",
  "class": "write_conflict | transient_io | cfc_invocation_error | validation_rejected | unknown",
  "attempt": "<int, 1 or 2>",
  "ts": "<ISO timestamp>",
  "etag_at_dispatch": "<sha or null>",
  "line_range_hash_at_dispatch": "<sha or null>",
  "payload_excerpt": "<first 280 chars of the comment text + breadcrumb>",
  "draft_path": "<relative path of preserved draft when auto-save fired, else null>"
}
```

Per-retry-success record schema (appended when a retry of `dispatch_key` completes successfully):
```json
{
  "dispatch_key": "<same sha1>",
  "status": "resolved",
  "ts": "<ISO timestamp>"
}
```

```pdsl
UNIT DispatchFailureLog

PURPOSE:
  Record generate-routing dispatch failures and successes for session-restart resilience.

WHEN:
  - REQUIRE a generate-routing dispatch fails

DO:
  - EMIT one NDJSON record to {cf-studio-path}/.cache/explain/dispatch-failures-{slug}-{ISO-date}.jsonl

RULES:
  - ALWAYS append-only; never truncate or delete in-session
  - ALWAYS write one record per failure, one record per resolved retry
  - ALWAYS reconstruct session_state.pending_retries from NDJSON records on session resume (skipping any dispatch_key whose latest record is status=resolved)
  - NEVER use subdirectories; write directly to the flat NDJSON file
```

## Path Conventions (Portability)

All explain-generated artifacts and references **inside** them MUST use **relative paths**, never absolute paths.

| Artifact / surface | Relative-path requirement |
|---|---|
| Per-portion files inside an export package | Internal links: relative within the package. External refs to source artifacts: relative from the package directory — NEVER absolute |
| `index.md` in an export package | All file refs: relative. Mermaid graph node hrefs: relative |
| `review-comments-{slug}-{date}.md` | File:line references: relative path from project root (e.g. `requirements/auth.md:42`), NEVER absolute |
| `open-questions-{slug}-{date}.md` | Same as comments file |
| `key-takeaways-{slug}-{date}.md` | Same |
| `diagrams-{slug}-{date}.md` | Source-ref captions use relative paths |
| `session-{slug}-{ISO-timestamp}.json` | `input_path` field: relative from project root |
| Chat-displayed paths | Display as relative from project root when emitting in chat |

```pdsl
UNIT PathConventions

PURPOSE:
  Enforce relative-path usage in all explain-generated artifacts.

RULES:
  - ALWAYS use relative paths in all explain-generated artifact content; never use absolute paths
  - ALWAYS convert {cf-studio-path} and {project_root} template variables to relative-from-project-root form before writing to artifact content or displaying in chat
  - ALWAYS hold the resolved-absolute form in working memory only for filesystem syscalls; never persist absolute paths into artifact bytes
  - ALWAYS compute relative depth from the actual artifact location when using ../ prefixes in cross-directory references; never hardcode a count
  - NEVER write /Users/..., /Volumes/..., or /home/... absolute paths into any explain-generated artifact body; detect and convert to relative form before writing
```

## Output Language (chat)

Chat output (the live narrative) follows different rules from artifact language.

```pdsl
UNIT OutputLanguage

PURPOSE:
  Define language rules for chat output and language complexity enforcement.

RULES:
  - ALWAYS match chat output language to the user prompt language (auto-detected on first user message)
  - ALWAYS keep source quotes in the original artifact language; never translate them
  - ALWAYS respect the project's resolved language_complexity level (low/middle/high, default middle) per {cf-studio-path}/.core/requirements/language-complexity.md for both chat output and persisted artifacts
  - ALWAYS self-check every chat message and every artifact write against the resolved language_complexity level
  - ALWAYS allow mid-session override: change language complexity to {X} / remember new language complexity / show language complexity
  - NEVER apply language complexity rules to source quotes; quoted verbatim
```

## Checkpoint and Resume

```pdsl
UNIT CheckpointAndResume

PURPOSE:
  Define checkpoint trigger, state persistence, and resume behavior for storytelling sessions.

STATE:
  - SET checkpoint_path: {cf-studio-path}/.cache/explain/session-{slug}-{ISO-timestamp}.json

WHEN:
  - REQUIRE user accepts the checkpoint prompt during a mid-session Wrap (Phase E5 trigger 2, plan-not-complete branch)

DO:
  - SET slug: basename without extension, lowercased, non-alphanumeric -> hyphens
  - RUN mkdir -p {cf-studio-path}/.cache/explain/ if it does not exist
  - SET checkpoint_state: mode, role, audience, plan, current_position, open_questions_buffer, takeaways_buffer, diagram_format, glossary_buffer, telemetry_log, input_hash, target_is_pr, handle fields, session_state fields
  - EMIT checkpoint saved confirmation

RULES:
  - NEVER auto-checkpoint during the session; never use periodic writes, phase-transition writes, or pivot writes
  - ALWAYS write state only at the natural stopping point when user opts in via checkpoint prompt
  - ALWAYS make the NDJSON dispatch-failures file the ONLY surface that writes on every failure event (append-only audit log, not a checkpoint)
  - ALWAYS resolve {cf-studio-path} from project config; do NOT hardcode .cf-studio/
  - ALWAYS use resume intent verb explain --resume {session-id} or resume explain session {session-id}; no dedicated CLI subcommand

ON_ERROR:
  input file missing or unreadable on resume -> EMIT "Input '{path}' no longer exists or is unreadable; cannot resume session." and STOP_TURN
  input hash changed on resume -> EMIT warning and require user confirmation to continue

NOTES:
  On resume:
  1. Load state from JSON
  2. Re-read input; verify unchanged via input_hash; warn if changed and require user confirmation
  3. Print 1-line resume header: "Resuming session {id}, role={role}, audience={audience}, mode={mode}, at portion {X}/{N}"
  4. Continue from current_position

  Cleanup at completion: when user picks Wrap-up at plan exhaustion AND resume checkpoint exists for THIS session, ask "Delete it? (yes / no)" default yes. On yes -> delete file, log telemetry. On no -> keep file.

  Slug derivation: basename without extension, lowercased, non-alphanumeric -> hyphens. External resources: gh-{owner}-{repo}-pr-{N}, jira-{key}, notion-{slugified-title}, url-{domain}-{path}.
```

## Bookmark Export

```pdsl
UNIT BookmarkExport

PURPOSE:
  Define bookmark export prompt and file structure at session wrap.

WHEN:
  - REQUIRE session wrap occurs and bookmarks exist

DO:
  - EMIT "Save bookmarks ({B} items) to {cf-studio-path}/.cache/explain/key-takeaways-{slug}-{YYYY-MM-DD}.md? (yes / no / path)"
  - WAIT user.reply

RULES:
  - ALWAYS write bookmark file in resolved artifact language
  - ALWAYS include in bookmark file: header (input, role, audience, mode, date), numbered takeaways with clickable source refs, glossary section if non-empty
```

## TaskCreate Progress Tracking

```pdsl
UNIT TaskCreateTracking

PURPOSE:
  Define when and how to use TaskCreate for plan progress tracking.

WHEN:
  - REQUIRE plan has more than 5 portions
  - AND Phase E1 plan approval is received

DO:
  - RUN TaskCreate once with one task per plan item
  - SET task status: in_progress when entering a portion (presentation portion in review)
  - SET task status: completed after navigation block is emitted (challenge portion in review)

RULES:
  - NEVER call TaskCreate for plans with 5 or fewer portions; overhead not justified
  - ALWAYS emit progress as inline telemetry log lines when TaskCreate is unavailable: "- [storytelling]: Portion 3/5 emitted"
```

## Telemetry / Execution Logging

Inherits studio-skill execution logging style:
- `- [storytelling]: Entering Phase E1 — discovery (audience known: false)`
- `- [storytelling]: Mode resolved — {mode} ({why-suggested})`
- `- [storytelling]: External input resolved via {tier} {handler}`
- `- [storytelling]: Completed Phase E1 — role: Software Architect, audience: engineers, plan: 5 portions`
- `- [storytelling]: Portion 3/5 emitted (size: 187 words, open-questions delta: +1)`
- `- [storytelling]: Wrap-checkpoint written to {path} (user accepted at mid-session wrap)`
- `- [storytelling]: Resume checkpoint deleted ({path})`
- `- [storytelling]: User pivot — Lateral to ADR-0042`

## Failure Modes

```pdsl
UNIT StorytellingFailureModes

PURPOSE:
  Define behavior for each known failure condition in the storytelling methodology.

ON_ERROR:
  input not readable -> EMIT stop with suggestion (inherit analyze.md Phase 1)
  all fetch tiers failed or unavailable -> EMIT user-fallback prompt with paste / local-path / cancel options; NEVER include arbitrary shell-command option
  input registered but parent ID broken in registry -> EMIT warning; continue without that lateral candidate
  user asks question requiring external knowledge -> EMIT "this requires knowledge beyond {path}, added to open questions" and push to open-questions
  output exceeds soft cap (default 200 words) -> auto-trim with EMIT "trimmed to keep within format"
  output exceeds hard cap (default 350 words) -> split into two portions sharing the plan-item index with letter suffixes (3a, 3b)
  all forward nav slots vacuous -> mark End-of-thread; EMIT_MENU offering Wrap / Back / Invoke skill cf-analyze
  diagram opportunity fires but content has <=2 entities and no structural relationships -> decline diagram in visualization marker with reason; continue with prose
  glossary term has no clear definition in input -> skip inline gloss silently; NEVER invent a definition; NEVER push to open-questions on methodology's own initiative
  wrap-time checkpoint write fails -> EMIT warning with exact filesystem error; emit wrap output normally; flag in Session block that checkpoint was NOT persisted; NEVER include Resume this session in Suggested Next Steps
  user mid-portion override -> acknowledge; finish current portion under old settings; apply new settings from next portion
```
