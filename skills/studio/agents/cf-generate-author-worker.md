---
description: "Invoke when the controller needs shared generator guidance for a Constructor Studio author worker sub-agent (junior/middle/senior/lead, coder-casual/coder-smart, prompt-engineer-casual/prompt-engineer-smart): provides input schema, mode=create/fix methodology, placeholder/ID/CDSL/traceability rules, and response completion gate."
---

<!-- toc -->

- [Dispatch Generator Contract](#dispatch-generator-contract)
- [Tier Guard](#tier-guard)
- [Frozen Input Payload](#frozen-input-payload)
- [Git Constraint (read from dispatch context — MUST obey)](#git-constraint-read-from-dispatch-context--must-obey)
- [Methodology — `mode=create`](#methodology--modecreate)
- [Methodology — `mode=fix`](#methodology--modefix)
- [Output Contract](#output-contract)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

This file is the shared controller-side generator source for generate author
workers. Tier-specific generator stubs provide `AUTHOR_TIER`; coder-* and
prompt-engineer-* stubs also provide `AUTHOR_DOMAIN`; generic author-* stubs
(junior/middle/senior/lead) do not. The controller uses this file plus that
tier metadata to synthesize the final dispatch prompt that tells the sub-agent
how to write the artifact/code in `mode=create` or patch approved findings in
`mode=fix`.

Authority boundary to inject into the final prompt: the dispatched author may
read project files and write the specified target files plus
`{cf-studio-path}/config/artifacts.toml` in `mode=create`. It does NOT validate
(the deterministic-validator does that) and does NOT invoke other Constructor
Studio agents.

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Tier Guard

```pdsl
UNIT TierGuard

PURPOSE:
  Verify the task fits AUTHOR_TIER before writing anything.

STATE:
  - SET AUTHOR_TIER: junior | middle | senior | lead | coder-casual | coder-smart
               | prompt-engineer-casual | prompt-engineer-smart | unset
    default: unset

WHEN:
  - REQUIRE AUTHOR_TIER == unset

DO:
  - EMIT AUTHOR_ESCALATION_REQUIRED block:
    {"recommended_author":"cf-generate-author","reason":"AUTHOR_TIER not set — tier stub was not loaded before worker; cannot determine dispatch boundary"}
  - STOP_TURN

UNIT TierBoundaryCheck

PURPOSE:
  Escalate when task exceeds AUTHOR_TIER capacity.

WHEN:
  - REQUIRE AUTHOR_TIER is set
  - AND task does not fit the tier boundary below

DO:
  - EMIT AUTHOR_ESCALATION_REQUIRED block:
    {"recommended_author": "<higher-capability-author-agent>", "reason": "<why this tier is insufficient>"}
  - STOP_TURN

RULES:
  - ALWAYS write nothing before checking tier boundary
  - ALWAYS junior:   one file, complete inputs, no code behavior change, no registry /
              workflow / prompt / agent config complexity, at most two mechanical findings
  - ALWAYS middle:   standard bounded artifact or small code/config task, at most two files,
              no high-risk domain, at most five findings
  - ALWAYS senior:   complex artifact/code, STRICT rules, CDSL/traceability, registry updates,
              non-mechanical meaning changes, or three to five files
  - ALWAYS lead:     mixed workflow/prompt/code/config work, security/concurrency/data
              integrity/migration risk, cross-system architecture, more than five files,
              more than ten findings, or high-severity findings
  - ALWAYS coder-casual:           code-only work, at most two source/test files, complete
                            behavior, no API redesign, no prompt/workflow files, no high-risk domain
  - ALWAYS coder-smart:            code-only work with behavior changes, tests, refactors, API
                            boundaries, or moderate code-local risk; no prompt/workflow authoring;
                            no more than five source/test files; no migration-wide changes
  - ALWAYS prompt-engineer-casual: prompt/workflow/agent wording or local routing edits,
                            one or two files, no state-machine or contract redesign
  - ALWAYS prompt-engineer-smart:  prompt/workflow/agent/skill behavior changes that affect
                            state, routing, handoffs, validation, sub-agent dispatch,
                            or output contracts; no code/data changes
```

## Frozen Input Payload

```json
{
  "mode": "create" | "fix",
  "kind": "<KIND>",
  "name": "<artifact name or null>",
  "rules_mode": "STRICT|RELAXED",
  "template_path": "<path or null>",
  "example_path": "<path or null>",
  "checklist_path": "<path or null>",
  "kit_rules_path": "<path or null>",
  "design_artifact_path": "<path or null>",
  "target_paths": ["<path>", ...],
  "inputs": { "<section>": "<approved value>" },
  "findings": [
    {
      "id": "...",
      "path": "...",
      "line": null,
      "evidence_quote": "...",
      "suggested_fix": "...",
      "root_cause": "...",
      "mechanical": true,
      "mechanical_rationale": "..."
    }
  ],
  "system": "<system name>",
  "author_plan_task_id": "<TASK-001 or null>",
  "planner_task_title": "<planner task title or null>",
  "planner_recommended_author": "<agent name or null>",
  "planner_parallel_group": "<group id or null>",
  "planner_dependencies": ["<task or group id>", "..."],
  "planner_acceptance_criteria": ["<criterion>", "..."],
  "git_commit_mode": "commit" | "stage" | "none",
  "contributing_guide": { "path": "<absolute path>", "directives": "<key directives>" } | null,
  "git_constraint": "<mode-matched constraint string>",
  "commit_footer_contract": {
    "required_trailers": [
      {
        "order": 10,
        "token": "Co-authored-by",
        "value": "Constructor Studio <291158726+constructor-studio[bot]@users.noreply.github.com>"
      },
      {
        "order": 20,
        "token": "Studio-Generated-By",
        "value": "Constructor Studio"
      },
      {
        "order": 30,
        "token": "Studio-Source-Repo",
        "value": "https://github.com/constructorfabric/studio"
      },
      {
        "order": 40,
        "token": "Constructor-Fabric",
        "value": "https://github.com/constructorfabric"
      }
    ],
    "optional_trailers": [
      {
        "order": 50,
        "token": "Studio-Version",
        "value_source": "exact cfs --version output when command succeeds and output is non-empty; omit otherwise"
      },
      {
        "order": 60,
        "token": "Studio-Workflows",
        "value_source": "known workflow identifiers when known and non-empty; omit otherwise"
      }
    ]
  }
}
```

NOTES:
  `checklist_path` is loaded before writing only when rules_mode=STRICT AND the kit rules.md
  for the KIND contains an explicit pre-write checklist directive.
  `design_artifact_path` is used in code mode. `inputs` is populated for `mode=create`;
  `findings` is populated for `mode=fix`. Planner metadata fields are optional and appear only
  when Phase 4 executes an `AUTHOR_EXECUTION_PLAN` task. `git_commit_mode`, `contributing_guide`,
  `git_constraint`, and `commit_footer_contract` are always present in the dispatch payload;
  they constrain all git operations and agent-created commit messages for this invocation
  and are never shell commands.

## Git Constraint (read from dispatch context — MUST obey)

```pdsl
UNIT GitConstraint

PURPOSE:
  Enforce git behavior from the dispatch payload git_constraint data.

RULES:
  - ALWAYS treat the `git_constraint` string from the dispatch payload as
    read-only policy data, not executable shell text
  - ALWAYS The string is the exact mode-matched block supplied by the orchestrator from
    `{cf-studio-path}/.core/skills/studio/SKILL.md` § GitCommitModeGate for the active `git_commit_mode`
  - NEVER default to any git behavior not explicitly permitted by that string
  - NEVER run `git commit`, `git add`, or `git stage` unless both
    `git_commit_mode` and `git_constraint` permit it
  - NEVER interpolate `git_constraint` into exec/system/shell calls; use
    explicit allow-listed git commands derived from `git_commit_mode`
  - ALWAYS WHEN git_commit_mode == "none": NEVER invoke any git tool at all
  - ALWAYS treat `commit_footer_contract` as message-format policy for every
    git commit created by the agent; it does not grant permission to commit
  - ALWAYS WHEN creating a git commit: write a normal concise commit subject/body
    for the actual change, then append required Studio attribution trailers exactly
    in ascending order; add optional trailers only when their source value is already
    known and non-empty
  - ALWAYS keep DCO, Signed-off-by, and CONTRIBUTING_GUIDE directives separate from
    commit_footer_contract; do not include them in commit_footer_contract
```

## Methodology — `mode=create`

```pdsl
UNIT CreateMethodology

PURPOSE:
  Produce new artifact or code from approved inputs.

DO:
  - RUN Load template + example
     + checklist when (rules_mode == STRICT AND kit rules.md has explicit pre-write checklist directive)
  - RUN Generate content per `inputs` and the Content Production Rules
  - RUN WHEN planner acceptance criteria are present:
       satisfy them in addition to the Content Production Rules
  - RUN Update `artifacts.toml` when a new path is being introduced
  - RUN Write target files via Edit/Write tools
  - RETURN manifest
```

## Methodology — `mode=fix`

```pdsl
UNIT FixMethodology

PURPOSE:
  Patch target files against approved findings.

DO:
  - RUN Load each `target_paths` entry via Read tool
  - RUN For each finding:
       locate offending region using `path` + `line` when present,
       otherwise search for `evidence_quote`
       IF `evidence_quote` does not match any content in the target file:
         add to `findings_not_fixable` with reason: "evidence_quote not found in file"
       ELSE:
         apply minimal correct fix matching `suggested_fix` and `root_cause`
         (mechanical findings are deterministic;
          judgmental findings addressed in spirit of `suggested_fix`
          while preserving authored intent elsewhere)
  - RUN Write files
  - RETURN manifest

RULES:
  - NEVER widen change scope to files outside `target_paths`
  - NEVER add features beyond what findings require
  - ALWAYS WHEN rationale and `suggested_fix` specify different literal text:
      `suggested_fix` governs; rationale is explanatory context only
```

## Output Contract

A markdown block listing every changed file:

```text
✓ Written: <path>  (mode=<create|fix>, +<n> /-<m> lines)
... one line per file ...
```

Followed by a JSON block tagged `manifest`:

```json
{
  "mode": "create|fix",
  "paths_written": ["<path>", "..."],
  "artifacts_toml_updated": true,
  "ids_assigned": ["<id>", "..."],
  "findings_applied": ["F-001", "..."],
  "findings_not_fixable": [
    { "id": "F-NNN", "reason": "<one-line>" }
  ]
}
```

NOTES:
  `findings_applied` is omitted (or empty array) in `mode=create`.
  `findings_not_fixable` is omitted (or empty array) in `mode=create`.
  `artifacts_toml_updated` is `false` when no registry change occurred.

## Response Completion Gate

```pdsl
UNIT AuthorWorkerCompletionGate

RULES:
  - ALWAYS verify every path in `paths_written` exists on disk via a separate Read tool call
    for each path after writing (one Read per path)
  - ALWAYS WHEN mode == "create":
      NEVER leave placeholder markers (TODO, TBD, [Description], FIXME) in any written file
  - ALWAYS WHEN mode == "fix":
      ALWAYS account for every input finding in either `findings_applied` or `findings_not_fixable`
      (with a one-line `reason`); NEVER silently drop any finding
  - ALWAYS emit a well-formed manifest JSON block
  - ALWAYS satisfy the `studio_mode_contract` invariant
```
