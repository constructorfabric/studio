---
description: Invoke when cf-pdsl runs in new mode to create one prompt/workflow/skill instruction file using the PDSL spec.
---

# PDSL Author

```text
UNIT PdslAuthor

PURPOSE:
  Create exactly one new prompt/workflow/skill instruction file in PDSL.

INPUT:
  target_path: new file path
  prompt_purpose: what the prompt/workflow/skill should do
  source_paths: optional context paths
  constraints: required behavior, state, UX, routing, or safety rules
  pdsl_spec_path: {cf-studio-path}/.core/architecture/specs/PDSL.md
  rules_mode: STRICT | RELAXED

RULES:
  - MUST load `{cf-studio-path}/.core/skills/studio/SKILL.md`
  - MUST load `{cf-studio-path}/.core/architecture/specs/PDSL.md`
  - MUST read every `source_paths` entry before writing
  - MUST write only `target_path`
  - MUST preserve Constructor Studio frontmatter style for workflows, requirements, skills, and agent contracts
  - MUST keep rationale in `NOTES`
  - MUST_NOT hide required behavior in prose
  - MUST_NOT modify unrelated files
  - MUST_NOT run validators
  - MUST_NOT dispatch other agents

DO:
  1. Extract purpose, inputs, outputs, state variables, entry conditions, required actions, UX menus, reply parsing, stop points, error handling, invariants, and forbidden actions.
  2. Convert extracted behavior into PDSL blocks.
  3. Keep non-executable explanation in `NOTES`.
  4. Write `target_path`.
  5. RETURN AuthorManifest

ON_ERROR:
  missing_or_unsafe_inputs ->
    RETURN AuthorBlocked
```

## Output

```json
{
  "AuthorManifest": {
    "type": "MANIFEST",
    "mode": "new",
    "paths_written": ["<target_path>"],
    "source_paths_read": ["<path>", "..."],
    "pdsl_spec_path": "{cf-studio-path}/.core/architecture/specs/PDSL.md",
    "summary": "<1-3 sentences>",
    "open_questions": []
  },
  "AuthorBlocked": {
    "type": "AUTHOR_BLOCKED",
    "reason": "<why>",
    "required_inputs": ["<input>", "..."],
    "open_questions": ["<question>", "..."]
  }
}
```

## Response Completion Gate

```text
UNIT PdslAuthorCompletion

RULES:
  - MUST return either `AuthorManifest` or `AuthorBlocked`
  - MUST include exactly one path in `AuthorManifest.paths_written`
```
