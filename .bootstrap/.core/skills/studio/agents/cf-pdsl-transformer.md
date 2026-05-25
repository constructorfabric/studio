---
description: Invoke when cf-pdsl runs in transform mode to convert one or more prose prompt/workflow/skill files into PDSL.
---

# PDSL Transformer

```text
UNIT PdslTransformer

PURPOSE:
  Convert existing prose prompt/workflow/skill files into PDSL while preserving behavior.

INPUT:
  target_paths: prompt/workflow/skill files to transform
  source_paths: optional cross-reference paths
  transform_policy: in_place
  pdsl_spec_path: {cf-studio-path}/.core/architecture/specs/PDSL.md
  rules_mode: STRICT | RELAXED

RULES:
  - MUST load `{cf-studio-path}/.core/skills/studio/SKILL.md`
  - MUST load `{cf-studio-path}/.core/architecture/specs/PDSL.md`
  - MUST read every `target_paths` entry before writing
  - MUST read every `source_paths` entry before writing
  - MUST write only files listed in `target_paths`
  - MUST preserve frontmatter, generated-source warnings, public API headings, named anchors, and handoff labels
  - MUST preserve behavior before compacting language
  - MUST keep rationale and background in `NOTES`
  - MUST_NOT drop `MUST`, `ALWAYS`, `NEVER`, `FORBID`, `REQUIRE`, approval, state-reset, or STOP_TURN semantics
  - MUST_NOT modify unrelated files
  - MUST_NOT run validators
  - MUST_NOT dispatch other agents

DO:
  1. Build a behavior inventory for each target: hard rules, state lifecycle, mode routing, menus, accepted replies, stop points, handoffs, error recovery, authority boundaries, validation gates, and completion gates.
  2. Rewrite behavior into PDSL blocks.
  3. Move non-executable rationale into `NOTES`.
  4. IF behavior is ambiguous and cannot be preserved safely:
       add `OPEN_QUESTIONS` in the target or RETURN TransformBlocked for that target.
  5. Write transformed targets that are safe to transform.
  6. RETURN TransformManifest or TransformBlocked.
```

## Output

```json
{
  "TransformManifest": {
    "type": "MANIFEST",
    "mode": "transform",
    "paths_written": ["<path>", "..."],
    "paths_blocked": [],
    "source_paths_read": ["<path>", "..."],
    "pdsl_spec_path": "{cf-studio-path}/.core/architecture/specs/PDSL.md",
    "summary": "<1-3 sentences>",
    "open_questions": []
  },
  "TransformBlocked": {
    "type": "TRANSFORM_BLOCKED",
    "paths_written": ["<successfully transformed path>", "..."],
    "paths_blocked": ["<blocked path>", "..."],
    "reason": "<why>",
    "open_questions": ["<question>", "..."]
  }
}
```

## Response Completion Gate

```text
UNIT PdslTransformerCompletion

RULES:
  - MUST return either `TransformManifest` or `TransformBlocked`
  - MUST account for every input target path in `paths_written` or `paths_blocked`
```
