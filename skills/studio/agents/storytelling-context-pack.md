---
description: "Invoke at E1.5 of a storytelling workflow — reads the input once (file, directory, or PR descriptor) and emits a content_pack JSON parametrized by strategy: snippets (α) extracts all text up-front, anchors (β) emits line-range pointers only, hybrid (γ) extracts hot sections and leaves the rest as pointers. Downstream portion-delivery agents consume the pack without any further reads in anchors mode."
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
- [Methodology](#methodology)
  - [Step 1 — Read input](#step-1--read-input)
  - [Step 2 — Build anchor list](#step-2--build-anchor-list)
  - [Step 3 — Apply strategy](#step-3--apply-strategy)
  - [Step 4 — Compute depth_mode_flags](#step-4--compute-depth_mode_flags)
  - [Step 5 — Build plan_anchor_map](#step-5--build-plan_anchor_map)
  - [Step 6 — Persist pack (informational)](#step-6--persist-pack-informational)
  - [Step 7 — Return content_pack](#step-7--return-content_pack)
- [Strategy Reference](#strategy-reference)
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
  "strategy": "snippets | anchors | hybrid",
  "handle": {
    "canonical_path": "<absolute path — file, directory root, or PR descriptor path>",
    "byte_size": "<number>",
    "line_count": "<number>",
    "target_type": "code | artifact | pr | directory",
    "primary_language": "<string or null>"
  },
  "plan": {
    "items": [
      {
        "index": 0,
        "title": "<string>",
        "description": "<string>",
        "anchor_hint": "<string | null>"
      }
    ],
    "item_count": "<number>"
  },
  "mode": "<string — e.g. onboarding | review | presentation | change-impact | socratic | decision>",
  "audience": "<string — e.g. new-hire | senior-engineer | external-reviewer>",
  "hot_threshold_bytes": "<number | null — orchestrator hint for hybrid; default 8192>",
  "session_id": "<string — used for cache file naming>"
}
```

```text
UNIT InputValidation

PURPOSE:
  Validate required dispatch inputs before any processing step.

RULES:
  - REQUIRE strategy is present
  - REQUIRE handle.canonical_path is an absolute path
  - REQUIRE plan.items is non-empty
  - REQUIRE every plan item has a unique index with values 0..N-1 where N = plan.item_count
  - WHEN session_id is absent: skip Step 6 persistence and record warning
    "session_id absent or cf_studio_path unresolvable — pack not persisted"
```

## Methodology

### Step 1 — Read input

```text
UNIT ReadInput

PURPOSE:
  Load raw_text and total_lines from the dispatch target.

DO:
  WHEN handle.target_type == "code" OR handle.target_type == "artifact":
    Read file at handle.canonical_path using Read tool with no offset (all lines)
    SET raw_text = file contents
    SET total_lines = line count

  WHEN handle.target_type == "directory":
    REQUIRE Bash tool OR Glob tool is available
    WHEN Bash tool is available (preferred):
      run ls <canonical_path> to enumerate entries
    WHEN Bash tool is unavailable AND Glob tool is available (fallback):
      use Glob pattern <canonical_path>/* for top-level entries
      use Glob pattern <canonical_path>/**/*.{py,ts,js,go,rs,java,rb,sh,yaml,yml,json,toml,md,txt}
        for sub-directory code files
      skip entries that are sub-directories (retain files only)
    WHEN neither Bash nor Glob is available:
      SET abort = true
      EMIT "Cannot enumerate directory: neither Bash nor Glob tool is available in this dispatch context."
      RETURN
    After listing:
      Read each top-level file (not recursive sub-directories unless Glob enumeration is in use)
      Skip binary files (detected by file -b returning non-text MIME or by extension:
        .png .jpg .gif .pdf .zip .tar .gz .bin .exe .whl .jar)
      Concatenate content with file-boundary markers <<FILE: relative/path>> at each transition
      SET total_lines = running sum of line counts

  WHEN handle.target_type == "pr":
    Read file at handle.canonical_path (structured PR descriptor JSON with fields:
      title, body, diff_summary, changed_files, comments)
    Treat as a single logical document
    SET raw_text = file contents
    SET total_lines = line count

RULES:
  - MUST record raw_text and total_lines for use in Steps 2-3
```

### Step 2 — Build anchor list

```text
UNIT BuildAnchorList

PURPOSE:
  Derive a structured anchor index from raw_text using language-appropriate rules.

DO:
  WHEN handle.primary_language is "markdown" OR anchors cannot be determined by code rules:
    Derive one anchor per heading matching ^#{1,3} :
      id: h-<slugified-heading> (lowercase, spaces/punctuation to -, truncated at 60 chars)
      title: heading text without leading # characters
      line_range.start: heading line number (1-indexed)
      line_range.end: line before next same-or-higher heading OR total_lines for last anchor

  WHEN handle.primary_language is one of (python, javascript, typescript, go, java, rust,
      c, cpp, ruby, php, swift, kotlin, scala):
    Derive one anchor per top-level function or class boundary:
      Detect with language-appropriate patterns (^def , ^class , ^func , ^function ,
        ^public class, ^impl , ^fn )
      id: func-<name> OR class-<name> (lowercase, truncated at 60 chars)
      title: <kind> <name> (e.g. function parse_args)
      line_range.start: boundary line
      line_range.end: last line of logical block (next same-or-higher boundary, or total_lines)

  WHEN no headings and no top-level code boundaries found (fallback):
    Derive anchors from plan.items directly:
      For each plan item:
        WHEN anchor_hint is non-null: grep raw_text for first line matching anchor_hint
          SET line_range.start = matched line (1-indexed) OR 1 if not found
        id: plan-item-<index>
        title: plan item title
        line_range.end: start of next anchor OR total_lines

  WHEN derived anchor count < plan.item_count:
    Append synthetic fallback anchors (one per remaining un-mapped plan item) using fallback rule
    Flag each with synthetic: true

  WHEN anchor slug collides with previously assigned id:
    Append -2, -3, etc. to make id stable and unique

RULES:
  - MUST produce at least plan.item_count anchors (using synthetic anchors if needed)
  - MUST assign each anchor a unique id within the anchors array
```

### Step 3 — Apply strategy

```text
UNIT ApplyStrategy

PURPOSE:
  Resolve hot_threshold_bytes and populate resolved_section_text and is_hot per anchor.

DO:
  SET hot_threshold_bytes = dispatch value when non-null, else 8192
  For each anchor:
    Compute byte_count = approximate byte length of lines in line_range
      (1 byte per ASCII char, 3 bytes per non-ASCII char)

  WHEN strategy == "snippets":
    For every anchor:
      Slice raw_text lines from line_range.start to line_range.end (inclusive, 1-indexed)
      Prefix extracted slice with <<L{line_range.start}>> on its own line before first content line
      SET is_hot = true
      SET resolved_section_text = extracted slice
    SET total_extracted_bytes = sum of all byte_count values

  WHEN strategy == "anchors":
    For every anchor:
      SET resolved_section_text = null
      SET is_hot = false
    SET total_extracted_bytes = 0

  WHEN strategy == "hybrid":
    For each anchor:
      SET is_hot = true WHEN ANY of:
        1. anchor index == 0
        2. anchor is referenced by >= 2 plan items in plan_anchor_map
        3. anchor.byte_count > hot_threshold_bytes
        4. mode == "change-impact" AND depth_mode_flags.diff_summary == true
           AND anchor is among the first 3 anchors in the diff_summary set
      Otherwise SET is_hot = false
      WHEN is_hot == true:
        Extract resolved_section_text with line markers as in snippets strategy
      WHEN is_hot == false:
        SET resolved_section_text = null
    SET total_extracted_bytes = sum of byte_count for hot anchors only

RULES:
  - MUST echo the input strategy verbatim in content_pack.strategy
```

### Step 4 — Compute depth_mode_flags

```text
UNIT ComputeDepthModeFlags

PURPOSE:
  Map mode and audience inputs to boolean flags for downstream consumers.

DO:
  Initialize all flags to false: surface_only, risk_map, diff_summary, inline_code

  SET surface_only = true WHEN:
    mode == "onboarding" OR audience contains "new-hire" OR audience contains "beginner"

  SET risk_map = true WHEN:
    mode == "review" OR mode == "change-impact"

  SET diff_summary = true WHEN:
    mode == "review" OR mode == "change-impact" OR handle.target_type == "pr"

  SET inline_code = true WHEN:
    mode == "presentation" OR audience contains "engineer" OR primary_language is non-null

INVARIANTS:
  - MUST set depth_mode_flags.risk_map = true when mode == "review"; this is a hard
    invariant checked by the orchestrator — apply it even if the table mapping
    above would yield false through some code path
```

### Step 5 — Build plan_anchor_map

```text
UNIT BuildPlanAnchorMap

PURPOSE:
  Map every plan item index (0..N-1) to exactly one anchor id.

DO:
  WHEN ALL plan items have anchor_hint == null (all-null edge case):
    Use distribution strategy:
      WHEN structural anchor count >= plan.item_count (N):
        Map plan item i -> anchor at position i in anchors array (1:1 in index order)
      WHEN structural anchor count M < N:
        Distribute plan items proportionally across M anchors:
          Divide items into M groups of size ceil(N/M) or floor(N/M) (standard integer partitioning)
          Assign all items in group g to anchor index g
          Example: 5 plan items, 3 anchors -> items 0,1 -> anchor 0; items 2,3 -> anchor 1; item 4 -> anchor 2
      WHEN no structural anchors exist (M == 0):
        Split input into N equal byte-range chunks where N = plan.item_count
        Generate synthetic anchor ids chunk-0 through chunk-<N-1>
        Each chunk spans an equal portion of total_lines
        Map plan item i -> chunk-<i>
        Add synthetic anchors to anchors array with synthetic: true

  WHEN at least one anchor_hint is non-null (standard per-item rules):
    For each plan item i:
      WHEN plan.items[i].anchor_hint is non-null:
        Find first anchor whose title contains hint (case-insensitive substring match)
          OR whose line_range contains hint's first occurrence in raw_text
        WHEN matched: assign that anchor's id
      WHEN unmatched by hint:
        Compute expected_line = round((i / N) * total_lines) + 1
        Assign anchor with smallest abs(anchor.line_range.start - expected_line)
        Break ties by lower anchor index

  Emit plan_anchor_map as {"0": "<anchor_id>", "1": "<anchor_id>", ...}

RULES:
  - MUST map every plan item to exactly one anchor
  - MUST NOT collapse all items onto anchor at line 1 when all-null edge case detected
```

### Step 6 — Persist pack (informational)

```text
UNIT PersistPack

PURPOSE:
  Write the content_pack JSON to a cache file for consumer re-use.

DO:
  Construct cache path: {cf-studio-path}/.cache/explain/packs/<session_id>.json
  Resolve {cf-studio-path} from CLAUDE.md / SKILL.md context (cf_studio_path variable)
  WHEN resolution fails OR session_id is absent:
    SET kit_path = null
    Record warning: "session_id absent or cf_studio_path unresolvable — pack not persisted"
    CONTINUE Step7
  WHEN both are available:
    Use Bash to create directory: mkdir -p <cache-dir>
    Write content_pack JSON using Write tool
    SET kit_path = absolute path of written file
  Include etag field in persisted JSON:
    etag = sha256(canonical_path + ":" + byte_size + ":" + line_count)

RULES:
  - MUST_NOT abort the agent run on persistence failure
  - MUST add a warning and continue to Step 7 on any persistence failure

NOTES:
  etag captures source-file identity; consumers MUST re-dispatch this agent on etag
  mismatch (file moved or changed since pack was written).
  Persistence is informational only.
```

### Step 7 — Return content_pack

```text
UNIT ReturnContentPack

PURPOSE:
  Emit the final content_pack JSON as the entire response.

DO:
  Build output JSON per the Output contract
  RETURN content_pack JSON

RULES:
  - MUST_NOT emit preamble or trailing commentary
  - MUST emit the JSON block as the entire response
```

## Strategy Reference

| Strategy | Read passes | `resolved_section_text` | `is_hot` | Best for |
|---|---|---|---|---|
| α snippets | 1 (full read up-front) | Populated for all anchors | All true | Small inputs (< ~50 KB), offline portion delivery, no orchestrator re-reads |
| β anchors | 1 (structural scan only) | `null` for all anchors | All false | Large inputs (> 200 KB), portion-by-portion narrow Read() calls at delivery |
| γ hybrid | 1 + narrow re-reads for non-hot (optional) | Populated for hot anchors only | Selective | Medium inputs; overview + diff body always pre-extracted, long tail anchors on-demand |

```text
UNIT ConsumerContract

PURPOSE:
  Define how downstream agents MUST use the content_pack.

RULES:
  - MUST_NOT branch reasoning on content_pack.strategy (it is an implementation detail)
  - MUST use anchors[] array and resolved_section_text field uniformly regardless of strategy
  - MUST reject (in Response Completion Gate) any reasoning that explicitly cites strategy value

NOTES:
  The orchestrator selects the strategy before dispatch. The strategy field is an
  implementation detail of how the pack was built, not a behavioral signal for consumers.
```

## Output Contract

Schema version of the content_pack JSON; consumers MAY refuse a mismatched major.

```json
{
  "content_pack": {
    "version": "1.0",
    "strategy": "snippets | anchors | hybrid",
    "anchors": [
      {
        "id": "<string — stable slug e.g. h-introduction or func-parse_args>",
        "title": "<string>",
        "resolved_section_text": "<string | null — null for anchors strategy>",
        "line_range": {"start": "<number>", "end": "<number>"},
        "byte_count": "<number>",
        "is_hot": "<boolean — meaningful for hybrid; always true for snippets, always false for anchors>"
      }
    ],
    "plan_anchor_map": {
      "<plan_item_index_as_string>": "<anchor.id>"
    },
    "depth_mode_flags": {
      "surface_only": "<boolean>",
      "risk_map": "<boolean>",
      "diff_summary": "<boolean>",
      "inline_code": "<boolean>"
    },
    "overview": "<string — non-empty 2-3 sentence orientation verbatim-used by portion 1>",
    "total_extracted_bytes": "<number>",
    "kit_path": "<string | null — absolute path to persisted pack JSON>"
  },
  "warnings": ["<string>"]
}
```

```text
UNIT OverviewConstruction

PURPOSE:
  Define the required content and constraints for the overview field.

RULES:
  - MUST be non-empty
  - MUST NOT exceed three sentences
  - MUST state: what the input is (file name/type/purpose inferred from first anchor titles
    and plan item descriptions), what the plan covers (summary of item titles), and the
    strategy in use (one clause)

NOTES:
  Example: "This file implements the CLI argument parser for studio (230 lines, Python).
  The storytelling plan walks through four sections: overview, core flag handling,
  subcommand dispatch, and error paths. Content has been pre-extracted using the
  snippets strategy for low-latency delivery."
```

## Response Completion Gate

```text
UNIT ResponseCompletionGate

PURPOSE:
  Enforce all invariants before the response is considered complete.

RULES:
  - MUST have anchors array non-empty
  - MUST have every anchors[].id unique within the array
  - MUST have every anchors[].line_range non-null with start <= end
  - MUST have plan_anchor_map containing exactly one key per plan item index (0..N-1
    where N = plan.item_count); every value MUST resolve to a key in anchors[].id
  - MUST have overview non-empty
  - MUST have all anchors[].resolved_section_text non-null for strategy α
  - MUST have all anchors[].resolved_section_text null for strategy β
  - MUST have at least the first anchor with resolved_section_text non-null and
    is_hot: true for strategy γ
  - MUST have total_extracted_bytes equal to the sum of byte_count for all anchors
    with non-null resolved_section_text
  - MUST have the SKILL.md invariant satisfied
SEE_ALSO: ApplyStrategy
SEE_ALSO: ComputeDepthModeFlags
SEE_ALSO: ReturnContentPack

ON_ERROR:
  mode_review_risk_map_unresolvable ->
    MUST_NOT emit a partially-valid content_pack
    RETURN:
      {
        "abort": true,
        "abort_message": "risk_map invariant failed for review mode: <one-line cause>",
        "content_pack": null
      }

  any_other_completion_gate_violation ->
    RETURN abort-with-message using the same pattern as above

NOTES:
  The orchestrator surfaces abort_message to the user and aborts the storytelling session.
  mode=review cannot proceed without a risk_map.
```
