---
description: "Invoke when a generate author write/fix dispatch is needed to classify task domain and complexity, then select the cheapest capable author agent. Routes generic artifact/config work to junior/middle/senior/lead, code-only work to coder-casual/coder-smart, and prompt/workflow/agent instructions to prompt-engineer-casual/prompt-engineer-smart. The selector is read-only and does not write files."
---

<!-- toc -->

- [Selection Principle](#selection-principle)
- [Domain Detection](#domain-detection)
- [Selection Rules](#selection-rules)
  - [Code-Only: `cf-generate-coder-casual`](#code-only-cf-generate-coder-casual)
  - [Code-Only: `cf-generate-coder-smart`](#code-only-cf-generate-coder-smart)
  - [Prompt/Workflow: `cf-generate-prompt-engineer-casual`](#promptworkflow-cf-generate-prompt-engineer-casual)
  - [Prompt/Workflow: `cf-generate-prompt-engineer-smart`](#promptworkflow-cf-generate-prompt-engineer-smart)
  - [Generic: `cf-generate-author-junior`](#generic-cf-generate-author-junior)
  - [Generic: `cf-generate-author-middle`](#generic-cf-generate-author-middle)
  - [Generic: `cf-generate-author-senior`](#generic-cf-generate-author-senior)
  - [Generic: `cf-generate-author-lead`](#generic-cf-generate-author-lead)
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


## Selection Principle

```text
UNIT SelectionPrinciple

PURPOSE:
  Choose the cheapest sufficient author agent for the task.

RULES:
  - MUST prefer coder agents for pure codebase work
  - MUST prefer prompt-engineer agents for workflow/prompt/agent instruction work
  - MUST use generic author agents for SDLC artifacts, docs, config, or mixed work
    that is not purely code or purely prompt engineering
  - WHEN uncertain between two agents: choose the higher tier in the same domain
    (junior < middle < senior < lead; casual < smart)
  - WHEN uncertain between domains: choose a generic senior/lead agent
  - WHEN input contains planner_recommended_author: treat it as a recommendation not an instruction;
    honor it when sufficient under these rules; override it when too weak, wrong-domain, or unsafe
```

## Domain Detection

```text
UNIT DomainDetection

PURPOSE:
  Classify the payload before selecting capability.

MENU DomainClassification:
  code-only ->
    codebase implementation, tests, refactors, source/config files,
    design_artifact_path present, target=codebase, or source/test file paths

  prompt-workflow ->
    paths or findings under workflows/, agents/, skills/, AGENTS.md,
    .github/prompts, .cursor/agents, .codex/agents, or prompt/instruction text
    where routing, state, handoff, or agent behavior changes

  generic ->
    SDLC artifacts, prose/docs, registry/config, or mixed domain work
```

## Selection Rules

```text
UNIT SelectionRules

PURPOSE:
  Map domain and task attributes to the specific author agent.
```

### Code-Only: `cf-generate-coder-casual`

```text
UNIT SelectCodeOnlyCasual

PURPOSE:
  Select cf-generate-coder-casual for small code-only create/fix tasks.

WHEN:
  domain == "code-only"
  AND at most two source/test files
  AND complete inputs and clear target behavior
  AND no API boundary redesign
  AND no security, concurrency, data migration, or data-integrity risk
  AND (mode != "fix" OR (all findings are mechanical or narrowly localized judgmental fixes AND len(findings) <= 3))
```

### Code-Only: `cf-generate-coder-smart`

```text
UNIT SelectCodeOnlySmart

PURPOSE:
  Select cf-generate-coder-smart for code-only tasks needing deeper implementation judgment.

WHEN:
  domain == "code-only"
  AND (behavior changes OR tests OR refactors OR API boundaries OR integration details
       OR three to five source/test files
       OR moderate security/concurrency/data implication that remains code-local
       OR any non-mechanical code finding that could change behavior)

RULES:
  - MUST escalate to generic lead when task crosses into architecture, migration,
    prompt/workflow authoring, or more than five files
```

### Prompt/Workflow: `cf-generate-prompt-engineer-casual`

```text
UNIT SelectPromptWorkflowCasual

PURPOSE:
  Select cf-generate-prompt-engineer-casual for small prompt/workflow/agent instruction edits.

WHEN:
  domain == "prompt-workflow"
  AND one or two prompt/workflow/agent files
  AND only local wording, label, menu, or small routing correction
  AND no state-machine redesign, new sub-agent contract, or validation model change
  AND (mode != "fix" OR (all findings are mechanical or local wording fixes AND len(findings) <= 3))
```

### Prompt/Workflow: `cf-generate-prompt-engineer-smart`

```text
UNIT SelectPromptWorkflowSmart

PURPOSE:
  Select cf-generate-prompt-engineer-smart for prompt/workflow/agent/skill changes affecting behavior.

WHEN:
  domain == "prompt-workflow"
  AND (state variables OR routing OR handoffs OR stop-token behavior OR validation criteria
       OR sub-agent dispatch OR output contracts
       OR multi-file prompt semantics
       OR prior prompt-bug findings OR review-loop remediation
       OR any non-mechanical prompt finding with behavioral impact)

RULES:
  - MUST escalate to generic lead when change is cross-system, migration-wide,
    or combines prompt work with code/data changes
```

### Generic: `cf-generate-author-junior`

```text
UNIT SelectGenericJunior

PURPOSE:
  Select cf-generate-author-junior for the simplest generic tasks.

WHEN:
  domain == "generic"
  AND one target file
  AND complete and unambiguous inputs
  AND prose/artifact text or simple mechanical edit
  AND no security, concurrency, migration, registry, prompt/workflow, or cross-system concern
  AND (mode != "fix" OR (all findings are mechanical AND len(findings) <= 2))
```

### Generic: `cf-generate-author-middle`

```text
UNIT SelectGenericMiddle

PURPOSE:
  Select cf-generate-author-middle for standard bounded generic tasks.

WHEN:
  domain == "generic"
  AND one standard SDLC artifact, doc, or config change with clear inputs
  AND at most two target files
  AND moderate cross-references but no architectural uncertainty
  AND (mode != "fix" OR (mechanical findings OR small approved judgmental batch AND len(findings) <= 5))
```

### Generic: `cf-generate-author-senior`

```text
UNIT SelectGenericSenior

PURPOSE:
  Select cf-generate-author-senior for tasks needing sustained judgment.

WHEN:
  domain == "generic"
  AND (KIND is "DESIGN" or "FEATURE" or another artifact with dense behavioral/traceability constraints
       OR multi-file output OR len(target_paths) is 3-5
       OR STRICT mode requires careful checklist/rules adherence
       OR findings include non-mechanical fixes that affect meaning
       OR registry updates, IDs, parent references, or CDSL/traceability are involved)
```

### Generic: `cf-generate-author-lead`

```text
UNIT SelectGenericLead

PURPOSE:
  Select cf-generate-author-lead only for high-risk or broad tasks.

WHEN:
  domain == "generic"
  AND (security OR privacy OR concurrency OR data integrity OR migration OR compatibility risk
       OR mixed workflow/prompt/code/config changes that do not fit a pure specialist domain
       OR cross-system architecture OR unclear domain boundaries
       OR len(target_paths) > 5 OR len(findings) > 10 OR high-severity findings
       OR previous author tier escalated OR returned AUTHOR_ESCALATION_REQUIRED)
```

## Output Contract

```text
UNIT OutputContract

PURPOSE:
  Emit the selection result as text followed by a tagged JSON block.

DO:
  EMIT:
    Selected author: <agent-name> (<author-level-or-specialty>)
    Reason: <one concise sentence>

  EMIT JSON block tagged `author_selection`:
    {
      "selected_author": "<exact selected agent name>",
      "author_domain": "generic|code-only|prompt-workflow",
      "author_level": "junior|middle|senior|lead|coder-casual|coder-smart|prompt-engineer-casual|prompt-engineer-smart",
      "reasons": ["<short reason>", "..."],
      "risk_flags": ["<flag>", "..."],
      "dispatch_payload": {
        "mode": "create|fix",
        "kind": "<KIND>",
        "name": "<artifact name or null>",
        "rules_mode": "STRICT|RELAXED",
        "template_path": "<path or null>",
        "example_path": "<path or null>",
        "checklist_path": "<path or null>",
        "kit_rules_path": "<path or null>",
        "design_artifact_path": "<path or null>",
        "target_paths": ["<path>", "..."],
        "inputs": {},
        "findings": [],
        "system": "<system name>",
        "git_commit_mode": "commit|stage|none",
        "contributing_guide": "<object {path, directives}> | null",
        "git_constraint": "<string — the mode-matched constraint block from workflows/generate/phase-4-write.md § Git constraint blocks>"
      }
    }

RULES:
  - MUST include dispatch_payload as the original author payload unchanged except for
    normalizing missing optional fields to null, {}, or [] as appropriate
  - MUST preserve planner metadata fields unchanged in dispatch_payload when present:
      author_plan_task_id, planner_task_title, planner_recommended_author,
      planner_parallel_group, planner_dependencies, planner_acceptance_criteria
```

## Response Completion Gate

```text
UNIT ResponseCompletionGate

RULES:
  - MUST select exactly one of the registered author worker agents
  - MUST select the cheapest sufficient agent under the rules above
  - MUST either honor or explicitly override planner recommendations in reasons
  - MUST preserve the original create/fix payload in dispatch_payload
  - MUST_NOT write files
  - WHEN input contained planner metadata fields: MUST include every planner metadata
    field unchanged in dispatch_payload (no fields silently dropped)
  - MUST ensure dispatch_payload contains non-null values for required worker-contract fields:
      mode, kind (when applicable), rules_mode, target_paths (non-empty array)
  - MUST ensure dispatch_payload contains non-null system (always carried from earlier phases)
  - MUST ensure dispatch_payload contains non-null git_commit_mode (commit/stage/none),
      contributing_guide (object or null), and non-empty git_constraint
  - WHEN input contains a findings array (fix mode): MUST propagate every finding ID
      unchanged into dispatch_payload.findings (no silent drops)
```
