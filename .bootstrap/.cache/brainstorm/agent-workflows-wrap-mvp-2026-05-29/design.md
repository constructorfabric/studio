# Brainstorm: Agent Workflows Wrap MVP

Date: 2026-05-29

## Topic

Improve Constructor Studio agent workflows by focusing the first MVP on
`cf-brainstorm -> wrap`.

The accepted slice makes brainstorm completion more trustworthy without
expanding every workflow at once.

## Panel

- Workflow State Architect
- Prompt Context Boundary Reviewer
- Agent UX Designer
- Deterministic Guardrails Engineer
- Workflow Adoption Strategist

## Core Decisions

- Feature direction: improve `cf-brainstorm -> wrap` as a thin MVP slice.
- Recovery: use conservative adaptive resume. Resume is allowed only after a
  deterministic state integrity check. Otherwise rewind to the last valid
  checkpoint, then offer workflow switch.
- Context policy: hard fail for boundary, security, or contract violations.
  Reduced mode or user choice is allowed only for non-critical gaps.
- Workflow navigation: recommend one path when intent is confident; show
  2-3 outcome-based paths when ambiguous.
- Phase handoff visibility: always show a compact ledger line; require
  confirmation only for risk, ambiguity, or fallback.
- Brainstorm handoff: provide one recommended primary handoff. Secondary
  handoff is available only on request or high ambiguity.
- Menu labels: outcome label first, workflow name secondary.
- Validator visibility: hard failures immediately; warnings at checkpoints or
  wrap.
- Trust preview: compact line with next action, fallback behavior, and rough
  cost/time.
- Adaptive defaults: scoped to repo/workspace plus task type.
- Learning signal: bounded hybrid learning from choices and optional feedback;
  never changes safety or contract rules.
- Context provenance: compact by default, expandable in verbose/on request.
- Context reuse: lease-based in later slices.
- Save behavior: allow saving the full brainstorm session without starting any
  downstream workflow.

## MVP Boundary

The MVP is not the full workflow-navigation system. It is one vertical slice:

- workflow: `cf-brainstorm -> wrap`
- compact phase ledger line
- hard context validation before primary handoff
- one recommended primary handoff path
- explicit full-session save outcome

Deferred:

- full context lease reuse
- adaptive menus across all workflows
- expanded repair menus
- contract patch proposal generation

## Accepted Wrap Menu

```text
Outcome: direction selected.
Context: verified - 3 anchors - next step ~5-10 min - fallback: return to the valid checkpoint.

Recommended next step:
1. Create an implementation plan (cf-plan)

Save or finish:
2. Save the full brainstorm session
3. Finish without saving

Other actions:
4. Clarify scope (cf-explore / cf-analyze)
5. Show context details
```

## Open Questions

- What exact compact ledger fields are required for the
  `cf-brainstorm -> wrap` MVP?
- What deterministic state/context checks define a valid primary handoff from
  `cf-brainstorm` to `cf-plan`?

## Recommended Next Step

Create a small implementation plan for the `cf-brainstorm -> wrap` MVP. The
first implementation should avoid broad workflow redesign and prove only the
accepted vertical slice.
