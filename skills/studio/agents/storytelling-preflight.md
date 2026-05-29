---
description: Invoke at storytelling workflow phase E0 to resolve input access tier, run session-discovery scan, and enforce size guards. Returns a lightweight handle JSON — no bulk content is extracted. Dispatched once per storytelling session start with raw_path, user_prompt, cf_studio_path, and project_root.
---

<!-- toc -->

- [Authority boundary](#authority-boundary)
- [Frozen Input Payload](#frozen-input-payload)
- [Methodology](#methodology)
  - [Step 1 — Canonicalize path and derive session_id](#step-1--canonicalize-path-and-derive-session_id)
  - [Step 2 — Session discovery scan](#step-2--session-discovery-scan)
  - [Step 3 — Determine access_tier](#step-3--determine-access_tier)
  - [Step 3a — Path safety guard](#step-3a--path-safety-guard)
  - [Step 4 — Size guards](#step-4--size-guards)
  - [Step 5 — Detect target_type and primary_language](#step-5--detect-target_type-and-primary_language)
  - [Step 5b — Local-editable detection](#step-5b--local-editable-detection)
  - [Step 6 — Load preferences](#step-6--load-preferences)
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
  "raw_path": "string — path supplied by user or detected from input arg",
  "user_prompt": "string — original user utterance",
  "cf_studio_path": "string — resolved by orchestrator from CLAUDE.md",
  "project_root": "string",
  "session_id_override": "string | null — orchestrator-provided session ID for resume; null on fresh sessions"
}
```

```text
UNIT InputValidation

PURPOSE:
  Validate required dispatch inputs before any processing step.

RULES:
  - REQUIRE raw_path is present
  - REQUIRE user_prompt is present
  - REQUIRE cf_studio_path is present
  - REQUIRE project_root is present
  - WHEN raw_path is relative: canonicalize using project_root as base
  - WHEN session_id_override is absent: default to null
```

## Methodology

Execute the six steps below in order. Each step is load-bearing — skipping any step is a contract violation.

### Step 1 — Canonicalize path and derive session_id

```text
UNIT CanonicalizeAndDeriveSessionId

PURPOSE:
  Produce a stable canonical_path and session_id for the remainder of the dispatch.

DO:
  Resolve raw_path to absolute canonical path:
    WHEN raw_path is already absolute: use it directly
    WHEN raw_path is relative: join with project_root
    Normalize any .. segments
    SET canonical_path = resolved path

  WHEN session_id_override is non-null:
    SET session_id = session_id_override verbatim
  WHEN session_id_override is null (fresh session):
    Take basename of canonical_path (last path component, no extension)
    Slugify: lowercase, replace non-alphanumeric runs with -, strip leading and trailing -
    Append T + ISO timestamp compact form (e.g. 20260523T141500Z)
    SET session_id = slugified-basename + timestamp
    Example: /src/auth/login.py -> login-20260523T141500Z

RULES:
  - MUST store result as canonical_path
  - MUST reflect the actually used session_id value (override or fresh-derived) in Output
```

### Step 2 — Session discovery scan

```text
UNIT SessionDiscoveryScan

PURPOSE:
  Detect whether a prior session cache exists for this session_id.

DO:
  Check whether {cf-studio-path}/.cache/explain/sessions/<session_id>.json exists
    (read attempt is sufficient — do not read contents)
  WHEN file is present:
    SET session_id_existing = absolute path to that file
  WHEN file is absent:
    SET session_id_existing = null
```

### Step 3 — Determine access_tier

```text
UNIT DetermineAccessTier

PURPOSE:
  Resolve access_tier via priority chain; use the FIRST matching tier.

DO:
  Attempt local access:
    stat or read first 200 bytes of canonical_path
    WHEN accessible:
      SET access_tier = "local"
      SET input_access_method = exact tool name used (e.g. "Read")
      CONTINUE Step3a

  WHEN local failed AND an MCP filesystem or resource tool is available:
    SET access_tier = "mcp"
    SET input_access_method = MCP tool name
    CONTINUE Step3a

  WHEN mcp also unavailable AND a studio CLI tool is callable:
    SET access_tier = "cli"
    SET input_access_method = "studio-cli"
    CONTINUE Step3a

  WHEN none of the above succeeded:
    SET access_tier = "user_fallback"
    SET input_access_method = "user_fallback"
    EMIT "I cannot access the file at the path you provided. Please paste the
content directly into the chat so I can proceed."
    CONTINUE Step3a

RULES:
  - MUST use the FIRST matching tier in the priority chain
  - MUST_NOT offer arbitrary shell commands as a resolution path
  - MUST_NOT suggest the user run cat, ls, or similar (Anti-Pattern #25)
```

### Step 3a — Path safety guard

```text
UNIT PathSafetyGuard

PURPOSE:
  Reject filesystem targets that lie outside project_root.

WHEN:
  access_tier is "local" AND target is not a URL or PR ref
  (URLs and PR refs containing /pull/ or /pr/, or raw https:// URIs are exempt)

DO:
  Resolve both canonical_path and project_root to absolute real paths (follow symlinks)
  WHEN canonical_path does NOT start with project_root + "/":
    AND canonical_path != project_root:
    SET abort = true
    SET abort_message = "Path lies outside project_root; explain refuses non-project targets to prevent accidental exposure of system files."
    RETURN early — do NOT execute Steps 3b/4/5/6

RULES:
  - MUST apply to filesystem targets only; exempt URLs and PR refs
  - Paths equal to project_root itself are permitted (whole-project target)
```

### Step 4 — Size guards

```text
UNIT SizeGuards

PURPOSE:
  Measure input size and apply size-guard thresholds.

DO:
  WHEN access_tier == "local":
    Use stat (or equivalent metadata call) for byte_size
    Use wc -l (or Read tool line count) for line_count
    For directory: aggregate byte totals; count top-level files as file_count

  WHEN access_tier == "mcp":
    WHEN MCP response includes size metadata: use those values directly
    WHEN MCP response returns only content body: derive byte_size and line_count from body in memory

  WHEN access_tier == "cli":
    WHEN CLI response includes size metadata: use those values
    WHEN CLI response returns only content body: derive byte_size and line_count from body
    WHEN size cannot be determined from either metadata or body:
      EMIT warning "size unknown for tier=cli"
      SET size_guard_verdict = "warn_large"
      SET size_guard_reason = "size unknown for tier=cli"

  WHEN access_tier == "user_fallback":
    SET byte_size = 0
    SET line_count = 0
    SET file_count = 0
    SET size_guard_verdict = "ok"
    SET size_guard_reason = null

  Apply thresholds (when not already set by cli path above):
    WHEN byte_size < 32768 AND line_count < 800:
      SET size_guard_verdict = "ok"
    WHEN (32768 <= byte_size <= 262144) OR (800 <= line_count <= 3000):
      SET size_guard_verdict = "warn_large"
      SET size_guard_reason = one-sentence description
        e.g. "File is 87 KB (2 100 lines) — content will be chunked."
    WHEN byte_size > 262144 OR line_count > 3000:
      SET size_guard_verdict = "block_too_large"
      SET abort = true
      SET abort_message = "Input exceeds the maximum supported size (>256 KB or >3000 lines). Please narrow the target to a specific section or file and re-invoke the storytelling workflow."
      RETURN

RULES:
  - MUST run regardless of access_tier
  - MUST_NOT set byte_size = 0 silently for cli tier
  - MUST_NOT suggest /cf-plan as a workaround when block_too_large (Anti-Pattern #0)
  - MUST_NOT skip measurement for mcp or cli tiers
```

### Step 5 — Detect target_type and primary_language

```text
UNIT DetectTargetTypeAndLanguage

PURPOSE:
  Classify the target and detect its primary programming language.

DO:
  Determine target_type (first match wins):
    WHEN path contains "/pull/" OR "/pr/" OR ends .patch OR .diff:
      SET target_type = "pr"
    WHEN canonical_path is a directory (stat result):
      SET target_type = "directory"
    WHEN extension in {.md,.rst,.txt,.adoc,.tex,.pdf} OR first bytes are non-code prose:
      SET target_type = "artifact"
    ELSE:
      SET target_type = "code"

  Determine primary_language (first match wins, for code target_type):
    .py       -> "python"
    .ts .tsx  -> "typescript"
    .js .jsx  -> "javascript"
    .go       -> "go"
    .rs       -> "rust"
    .java     -> "java"
    .rb       -> "ruby"
    .sh .bash -> "shell"
    .yaml .yml -> "yaml"
    .json     -> "json"
    .toml     -> "toml"
    no match  -> null

  WHEN target_type is "artifact" OR "pr":
    SET primary_language = null
    WHEN first 200 bytes strongly suggest embedded language (e.g. a .md file
      that is entirely a Python code block): use detected language

  WHEN target_type is "directory":
    SET primary_language = most common extension among listed files, or null if inconclusive

  SET file_type = file extension OR "directory"
```

### Step 5b — Local-editable detection

```text
UNIT LocalEditableDetection

PURPOSE:
  Compute handle.local_editable and handle.local_editable_reason.

STATE:
  local_editable: boolean
  local_editable_reason: ok | outside_project_root | target_type_pr | target_type_directory |
    size_block | access_tier_remote | generate_route_unavailable
  generate_route_available: boolean

DO:
  WHEN handle.target_type == "directory":
    SET local_editable = false
    SET local_editable_reason = "target_type_directory"
    CONTINUE generate_route_check

  WHEN handle.target_type == "pr":
    SET local_editable = false
    SET local_editable_reason = "target_type_pr"
    CONTINUE generate_route_check

  Evaluate general expression:
    local_editable = (access_tier == "local")
                 AND (canonical_path strictly descends project_root)
                 AND (target_type IN {code, artifact})
                 AND (size_guard_verdict != "block_too_large")

  Evaluate local_editable_reason (first matching condition wins):
    WHEN canonical_path not strict descendant of project_root: "outside_project_root"
    WHEN target_type == "pr": "target_type_pr"
    WHEN target_type == "directory": "target_type_directory"
    WHEN size_guard_verdict == "block_too_large": "size_block"
    WHEN access_tier IN {mcp, cli, user_fallback}: "access_tier_remote"
    WHEN local_editable would otherwise be true BUT generate_route_available == false:
      "generate_route_unavailable" (emit for telemetry; downstream gate decides offer visibility)
    WHEN local_editable == true: "ok"

  generate_route_check:
    SET generate_route_available = (capability_map.generate_dispatch == true)

RULES:
  - WHEN local_editable == true: local_editable_reason MUST be "ok"
  - WHEN local_editable == false: local_editable_reason MUST NOT be "ok"
  - MUST re-run Step 5b in full on any mid-session target-pivot command BEFORE
    the next response portion is emitted
  - MUST_NOT carry stale local_editable, local_editable_reason, or
    generate_route_available values across a target pivot

NOTES:
  generate_route_available is orthogonal to local_editable. Both flags AND-gate the
  generate-routing offer downstream — neither alone is sufficient to present the offer.
  local_editable_reason values for closed enum:
    ok — local_editable resolved to true
    outside_project_root — canonical_path not strict descendant of project_root
    target_type_pr — target_type == "pr" (carve-out)
    target_type_directory — target_type == "directory" (v1 carve-out)
    size_block — size_guard_verdict == "block_too_large"
    access_tier_remote — access_tier is one of {mcp, cli, user_fallback}
    generate_route_unavailable — local_editable would otherwise be true but
      generate_route_available == false
```

### Step 6 — Load preferences

```text
UNIT LoadPreferences

PURPOSE:
  Load user preferences from the standard config location.

DO:
  Attempt to read {cf-studio-path}/config/preferences.json
  WHEN file exists and is valid JSON:
    SET preferences_loaded = parsed contents (object)
  WHEN file does not exist OR cannot be parsed:
    SET preferences_loaded = {}

RULES:
  - MUST set preferences_loaded to an object (never null)
```

## Output Contract

```json
{
  "handle": {
    "canonical_path": "string",
    "session_id": "string",
    "session_id_existing": "string | null",
    "access_tier": "local | mcp | cli | user_fallback",
    "input_access_method": "string — concrete tool name used",
    "file_type": "string",
    "target_type": "code | artifact | pr | directory",
    "primary_language": "string | null",
    "byte_size": "number",
    "line_count": "number",
    "size_guard_verdict": "ok | warn_large | block_too_large",
    "size_guard_reason": "string | null",
    "file_count": "number — 1 for single file, N for directory",
    "local_editable": "boolean",
    "local_editable_reason": "ok | outside_project_root | target_type_pr | target_type_directory | size_block | access_tier_remote | generate_route_unavailable",
    "generate_route_available": "boolean"
  },
  "preferences_loaded": "object — contents of preferences.json or {}",
  "abort": "boolean",
  "abort_message": "string | null"
}
```

```text
UNIT AbortSemantics

PURPOSE:
  Define when abort is true and what abort_message must contain.

RULES:
  - MUST set abort = true WHEN size_guard_verdict == "block_too_large"
    OR when path safety guard fires (path outside project_root)
  - MUST set abort = false otherwise
  - MUST set abort_message = null when abort == false
  - MUST_NOT mention /cf-plan in abort_message
```

## Response Completion Gate

```text
UNIT ResponseCompletionGate

PURPOSE:
  Enforce all output invariants before the response is considered complete.

RULES:
  - MUST emit the JSON shape above as the entire output (no chat, no preamble,
    no markdown wrapping outside the JSON block)
  - MUST have handle.canonical_path as an absolute path
  - MUST have handle.session_id either as verbatim session_id_override (when supplied)
    OR matching slugified-basename + ISO compact timestamp format (when derived fresh)
  - MUST have handle.access_tier as one of the four enumerated values
  - MUST have handle.target_type as one of the four enumerated values
  - MUST have handle.size_guard_verdict as one of the three enumerated values
  - MUST have abort_message non-null when abort == true
  - MUST_NOT include /cf-plan in abort_message
  - WHEN access_tier == "user_fallback": canonical fallback prompt MUST have been emitted
    (before the JSON, as a user-facing message) AND byte_size MUST be 0
  - MUST have handle.local_editable present as a boolean
  - MUST have handle.local_editable_reason present as one of the seven enumerated values
    in the closed enum (ok, outside_project_root, target_type_pr, target_type_directory,
    size_block, access_tier_remote, generate_route_unavailable)
  - MUST have local_editable_reason consistent with local_editable:
    WHEN local_editable == true: local_editable_reason MUST equal "ok"
    WHEN local_editable == false: local_editable_reason MUST NOT equal "ok"
  - MUST have handle.generate_route_available present as a boolean
  - MUST have the SKILL.md invariant satisfied
SEE_ALSO: LoadPreferences
SEE_ALSO: AbortSemantics
```
