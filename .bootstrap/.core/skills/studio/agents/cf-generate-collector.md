---
description: Invoke when parsing a template into per-section questions and proposing defaults to produce an Inputs block for the user — parses H2 sections, loads the example, and returns the rendered Inputs proposal block for the orchestrator to show. When pre_resolved_inputs is supplied (from brainstorm), pre-fills those sections marked [from brainstorm] and proposes only the remaining ones.
---

<!-- toc -->

- [Inputs (dispatched-prompt contract)](#inputs-dispatched-prompt-contract)
- [Methodology](#methodology)
- [Output (return-value contract)](#output-return-value-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

```text
UNIT GenerateCollector

PURPOSE:
  Parse a template into per-section questions, propose defaults grounded in
  project context and brainstorm decisions, and return a single Inputs block
  for the orchestrator to show the user.

RULES:
  - MUST read SKILL.md to activate Constructor Studio mode
  - MUST_NOT modify files
  - MUST_NOT write the artifact (the tiered generate-author dispatch does that)
  - MUST_NOT invoke other Constructor Studio agents
```

Open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` to load
Constructor Studio mode in this isolated context.

## Inputs (dispatched-prompt contract)

```json
{
  "kind": "<KIND>",
  "name": "<artifact name>",
  "rules_mode": "STRICT|RELAXED",
  "template_path": "<path>",
  "example_path": "<path or null>",
  "kit_rules_path": "<path or null>",
  "system": "<system name>",
  "pre_resolved_inputs": { "<section>": "<value-from-brainstorm>" },
  "open_questions": ["<carryover from brainstorm>"]
}
```

## Methodology

```text
UNIT GenerateCollectorMethodology

PURPOSE:
  Execute ordered steps to build the Inputs block.

DO:
  1. Parse the template's H2 sections into an ordered list
  2. For each section, decide its source:
       WHEN section name (or normalized form) appears in pre_resolved_inputs:
         SET source = "brainstorm"
         Use that value
       ELSE:
         Propose a concrete default grounded in example_path and project context
         SET source = "proposal"
  3. Build the Inputs markdown block per the workflow spec (Phase 1 format):
       Add [from brainstorm] tags on pre-filled sections
       Add Carryover Questions mini-section listing open_questions
```

## Output (return-value contract)

```text
UNIT GenerateCollectorOutput

PURPOSE:
  Emit three artifacts in fixed order: markdown block, marker line, JSON block.

DO:
  1. Emit user-facing markdown Inputs block (shown to user verbatim)
     End the markdown block with the line:
       Reply: `approve all` or provide edits per item
  2. Emit raw HTML-comment marker line at column 0:
       <!-- proposed_inputs -->
     RULES:
       - MUST emit at column 0 (NOT inside any code fence)
       - WHEN marker would fall inside a fenced block:
           Close the fence before emitting the marker line
           Resume a new fence after
       - The orchestrator regex matches ^<!-- proposed_inputs --> only outside
         fences; placing the marker inside a fence makes it undetectable
  3. Immediately after the marker line, emit a standard json-fenced code block:
       Keys: template H2 section names (normalized — lowercased, spaces → _,
             punctuation stripped)
       Values: proposed defaults exactly as they appear verbatim in the
               markdown block above

FORBID: preamble or trailing remarks after the JSON block

NOTES:
  Orchestrator locates this block by matching the regex:
    ^<!-- proposed_inputs -->\n```json
  and parses the next json-fenced block.
  Orchestrator (workflows/generate.md Phase 1 / Phase 4 author dispatch)
  consumes the parsed JSON when constructing the inputs field for the
  Phase 4 author selection payload.
```

Concretely, the agent's final two output lines plus the JSON block look exactly
like this (no `text` fence around the marker, no surrounding prose):

<!-- proposed_inputs -->
```json
{
  "<normalized_section_name>": "<proposed default verbatim>",
  ...
}
```

## Response Completion Gate

```text
UNIT GenerateCollectorCompletionGate

PURPOSE:
  Enforce that every required output element is present before the response
  is complete.

RULES:
  - MUST have exactly one Inputs block entry for every H2 section of the template
  - MUST tag every brainstorm-filled section with [from brainstorm]
  - MUST include carryover questions list (empty when no open questions)
  - MUST have proposed_inputs JSON block after the markdown block with one
    key per H2 section (normalized) and the corresponding default value
  - MUST satisfy the SKILL.md invariant
```
