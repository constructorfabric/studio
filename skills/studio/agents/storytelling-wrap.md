---
description: Invoke at storytelling workflow phase E5 (wrap) to synthesize the final session summary from accumulated session state — produces key takeaways, carries forward open questions verbatim, emits glossary and bookmarks export prompt when present, and proposes 2-3 contextual next steps.
---

<!-- toc -->

- [Authority boundary](#authority-boundary)
- [Frozen Input Payload](#frozen-input-payload)
- [Methodology](#methodology)
  - [Step 1 — Key takeaways](#step-1--key-takeaways)
  - [Step 2 — Open questions carry-forward](#step-2--open-questions-carry-forward)
  - [Step 3 — Glossary emit](#step-3--glossary-emit)
  - [Step 4 — Bookmarks export prompt](#step-4--bookmarks-export-prompt)
  - [Step 5 — Next steps](#step-5--next-steps)
  - [Step 6 — Session block](#step-6--session-block)
  - [Step 7 — Path normalization](#step-7--path-normalization)
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
  "mode": "string",
  "audience": "string",
  "plan": {
    "items": [{"index": 0, "title": "string"}],
    "item_count": "number"
  },
  "e2_segments": [
    {
      "plan_item_index": "number",
      "title": "string",
      "narrative_text": "string",
      "source_refs": ["string"]
    }
  ],
  "content_pack_strategy": "snippets | anchors | hybrid",
  "user_prompt": "string",
  "open_questions_buffer": [{"id": "string", "text": "string"}],
  "glossary_buffer": [{"term": "string", "definition": "string"}],
  "bookmarked_takeaways": [{"anchor_id": "string", "note": "string"}],
  "session_ended_early": "boolean — defaults to false when absent in input",
  "handle": "preflight.output.handle — provides canonical_path used to populate session.input as relative-from-project-root path"
}
```

```pdsl
UNIT StorytellingWrapInputConstraints

RULES:
  - ALWAYS treat all fields except session_ended_early and handle as required
  - ALWAYS accept empty arrays for open_questions_buffer, glossary_buffer, and bookmarked_takeaways
  - ALWAYS default session_ended_early to false when absent
  - ALWAYS set session.input to "(path not provided)" when handle is absent
```

## Methodology

```pdsl
UNIT WrapMethodology

PURPOSE:
  Execute the seven steps in order to produce the wrap output.

DO:
  - CONTINUE Step1_KeyTakeaways
  - CONTINUE Step2_OpenQuestionsCarryForward
  - CONTINUE Step3_GlossaryEmit
  - CONTINUE Step4_BookmarksExportPrompt
  - CONTINUE Step5_NextSteps
  - CONTINUE Step6_SessionBlock
  - CONTINUE Step7_PathNormalization
```

### Step 1 — Key takeaways

```pdsl
UNIT Step1_KeyTakeaways

PURPOSE:
  Produce 3-5 key_takeaways grounded exclusively in e2_segments or bookmarked_takeaways.

DO:
  - RUN Produce 3-5 key_takeaways bullets. For each:
    - RUN Write a concise one-sentence `text` field capturing the insight.
    - Set `source_ref` to a clickable markdown link:
        if takeaway originates from e2_segments: use first non-empty entry in
          source_refs as link URL and segment title as link text.
          Format: `[title](source_ref_url)`
        if takeaway originates from bookmarked_takeaways:
          Format: `[Bookmark: <anchor_id>](#<anchor_id>)`
        if source has no URL (empty source_refs):
          Format: `[<title>](#plan-item-<index>)`

RULES:
  - NEVER invent takeaways from general knowledge; only e2_segments or bookmarked_takeaways
  - NEVER produce two takeaways that paraphrase the same e2_segments entry
  - ALWAYS prefer takeaways that span multiple segments when the narrative supports it
```

### Step 2 — Open questions carry-forward

```pdsl
UNIT Step2_OpenQuestionsCarryForward

PURPOSE:
  Copy open_questions_buffer into open_questions verbatim.

DO:
  - SET open_questions = open_questions_buffer verbatim
  - RUN WHEN open_questions_buffer is empty: SET open_questions = []

RULES:
  - NEVER add, remove, reorder, rephrase, auto-fill, or resolve any item (AP-#21)
  - NEVER generate agent-generated entries (AP-#21)
```

### Step 3 — Glossary emit

```pdsl
UNIT Step3_GlossaryEmit

DO:
  - RUN WHEN glossary_buffer is non-empty: SET glossary = glossary_buffer verbatim
  - RUN WHEN glossary_buffer is empty:     SET glossary = null
```

### Step 4 — Bookmarks export prompt

```pdsl
UNIT Step4_BookmarksExportPrompt

DO:
  - RUN WHEN bookmarked_takeaways is non-empty: SET bookmarks_export_prompt = true
  - RUN WHEN bookmarked_takeaways is empty:     SET bookmarks_export_prompt = false
```

### Step 5 — Next steps

```pdsl
UNIT Step5_NextSteps

PURPOSE:
  Suggest 2-3 contextual next_steps as plain strings.

DO:
  - RUN WHEN session_ended_early == true:
    Prepend one entry:
      "Resume this session from plan item <N> — <title of first unprocessed plan item>"
    where N is the index of the first plan item with no corresponding e2_segment.
    This resumption entry counts toward the 2-3 total.
  - RUN SELECT 2-3 contextually most-relevant next steps derived from session content,
    mode, audience, or unresolved open questions.

RULES:
  - ALWAYS produce 2-3 entries total; NEVER exceed 3 entries regardless of session_ended_early
  - NEVER enumerate all four possible candidate categories mechanically
  - NEVER propose steps that contradict mode
    (e.g. do not propose a decision record step when mode is onboarding)
```

### Step 6 — Session block

```pdsl
UNIT Step6_SessionBlock

PURPOSE:
  Populate the session object.

DO:
  - SET session.role = storytelling role derived from mode
    (e.g. "presentation" for mode presentation, "review" for mode review)
  - SET session.audience = input audience
  - SET session.input = handle.canonical_path converted to relative-from-project-root path (AP-#28e)
    WHEN handle is absent: SET session.input = "(path not provided)"
  - SET session.progress = "{len(e2_segments)}/{plan.item_count} plan items"
  - SET session.diagrams = count of e2_segments entries whose narrative_text contains a
    fenced Mermaid block (```mermaid); 0 if none
  - SET session.open_questions_count = len(open_questions_buffer)
  - SET session.bookmarks_count = len(bookmarked_takeaways)
  - SET session.glossary_count = len(glossary_buffer)
```

### Step 7 — Path normalization

```pdsl
UNIT Step7_PathNormalization

PURPOSE:
  Ensure all file paths in output are relative-from-project-root (AP-#28e).

DO:
  - RUN Audit every string value in the output that contains a file path.
  - RUN Replace any absolute paths beginning with /Users/, /Volumes/, /home/, or any
    other absolute root with their relative-from-project-root equivalent.

RULES:
  - ALWAYS ensure save_prompt_default_path is relative
    (e.g. ".bootstrap/.cache/explain/sessions/<session_id>.json")
  - NEVER emit absolute paths in any output string value (AP-#28e)
```

## Output Contract

```json
{
  "wrap": {
    "header": "Storytelling Wrap-up",
    "session": {
      "role": "string",
      "audience": "string",
      "input": "string — relative path",
      "progress": "string — e.g. '6/6 plan items'",
      "diagrams": "number",
      "open_questions_count": "number",
      "bookmarks_count": "number",
      "glossary_count": "number"
    },
    "key_takeaways": [
      {"text": "string", "source_ref": "string — clickable markdown link"}
    ],
    "open_questions": [{"id": "string", "text": "string"}],
    "save_prompt_default_path": "string — relative",
    "glossary": [{"term": "string", "definition": "string"}],
    "bookmarks_export_prompt": "boolean",
    "next_steps": ["string"]
  }
}
```

```pdsl
NOTES:
  wrap.header is the literal string "Storytelling Wrap-up" — do not localize or alter it.
  The JSON block is the entire response — no preamble, no trailing commentary.
  glossary is null when glossary_buffer was empty; otherwise a verbatim copy.
```

## Response Completion Gate

```pdsl
UNIT StorytellingWrapResponseCompletionGate

RULES:
  - ALWAYS return the JSON shape above as the entire output (no chat, no preamble, no markdown wrapping outside the JSON block)
  - ALWAYS set wrap.header to exactly "Storytelling Wrap-up"
  - ALWAYS ensure every key_takeaways[].source_ref is a valid clickable markdown link
  - ALWAYS ensure open_questions is a verbatim copy of open_questions_buffer — no additions, removals, reorderings, or rephrasing (AP-#21)
  - ALWAYS set glossary to null when glossary_buffer was empty; otherwise verbatim copy
  - ALWAYS set bookmarks_export_prompt to true if and only if bookmarked_takeaways was non-empty
  - ALWAYS produce 2-3 next_steps entries; ALWAYS include a "Resume this session" entry as first element if and only if session_ended_early=true
  - ALWAYS ensure all file paths in output are relative-from-project-root (AP-#28e)
  - ALWAYS satisfy the SKILL.md invariant
- ALWAYS SEE_ALSO: Step1_KeyTakeaways
- ALWAYS SEE_ALSO: Step5_NextSteps
- ALWAYS SEE_ALSO: Step7_PathNormalization
```
