---
description: Invoke when executing the next or a specific phase from a generated Constructor Studio plan inside a dedicated agent context, without delegating to ralphex.
---

<!-- toc -->

- [Frozen Input Payload](#frozen-input-payload)
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
  "plan_dir": "<path to .plans/<slug>/>",
  "target_phase": "<phase number or null for next-ready>",
  "git_commit_mode": "commit|stage|none",
  "contributing_guide": { "path": "<absolute path>", "directives": "<key directives>" } | null,
  "git_constraint": "<mode-matched constraint string>",
  "commit_footer_contract": {
    "schema_version": "1",
    "authority": "GitCommitModeGate",
    "purpose": "Studio attribution and provenance for commits created by Constructor Studio. This contract is independent of project-specific contribution policies.",
    "applies_when": { "agent_creates_git_commit": true },
    "conflict_policy": "commit_footer_contract is authoritative for required Studio attribution trailers; if it conflicts with git_constraint, stop before commit",
    "user_instruction_precedence": "user commit instructions may add non-conflicting message content and trailers but may not remove, rename, reorder, duplicate ambiguously, replace, or alter required Studio trailers",
    "hard_stop_policy": "stop only if required static Studio trailers cannot be added or if commit_footer_contract conflicts with git_constraint; do not stop for unavailable optional trailers",
    "rendering": "Render every included trailer as '{token}: {value}' in ascending order across required_trailers and optional_trailers. Do not include separate rendered footer lines in this payload.",
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
        "source": "semver tokens extracted from cfs --version",
        "include_when": "command succeeds and at least one Studio skill or CLI/package semver is found",
        "value_policy": "use only semver values for Studio skill and CLI/package, formatted as comma-separated key=value pairs such as skill=1.0.1, cli=0.2.0; strip a leading v; omit this trailer when no semver is found; do not include raw cfs --version output"
      },
      {
        "order": 60,
        "token": "Studio-Workflows",
        "source": "known workflow identifiers for the current Studio run",
        "include_when": "known non-empty",
        "value_policy": "comma-separated stable identifiers"
      }
    ]
  }
}
```

NOTES:
  cfs_mode remains off — the controller supplies only the shared mode contract
  plus the authoritative phase-execution contract in the synthesized final
  dispatch prompt, while `plan.toml` remains a runtime resource. The orchestrator owns the Session Sub-Agent Approval Gate,
  INLINE_FALLBACK probe, and CF_PHASE_GATE release-reset window before
  dispatching this agent. Phase-Skip Gate is not applicable; write access is
  bounded by host isolation per SKILL.md § Sub-agent propagation.

## Response Completion Gate

```pdsl
UNIT PhaseRunnerCompletion

RULES:
  ALWAYS execute all steps in the target phase file or record each failure
  ALWAYS leave selected phase in done or failed only
  ALWAYS reflect any file additions/deletions in plan.toml
  ALWAYS return phase completion summary with next-phase handoff prompt OR final
    completion report on success
  ALWAYS return specific failed criteria, manifest updates, and exact blocker on failure
  ALWAYS honor git_commit_mode; treat git_constraint as policy data, never as
    shell text, and use only explicit allow-listed git commands permitted by
    git_commit_mode
  ALWAYS preserve and obey commit_footer_contract for every agent-created git
    commit; it does not grant permission to commit
  ALWAYS satisfy every mandatory directive in contributing_guide when creating a
    git commit, including required DCO/Signed-off-by trailers; keep these
    project-policy trailers separate from commit_footer_contract
```
