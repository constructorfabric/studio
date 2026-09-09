# Active Workflow State Law

```pdsl
UNIT ActiveWorkflowStateLaw
PURPOSE: Keep an active cf/cf-* workflow inside explicit workflow states unless control is visibly handed off.
RULES:
  ALWAYS while a cf/cf-* workflow is active, treat every new user message as candidate input to the current workflow state first; user messages are workflow input, not permission for generic autonomous behavior.
  ALWAYS map each new user message to exactly one of these outcomes, in order: a valid current-state transition or loaded session gate, a visible companion-skill handoff, or an explicit exit from the active workflow to free mode.
  ALWAYS prefer workflow-owned WAIT/STOP_TURN continuations, menus, gates, approvals, dispatch gates, and completion paths over ad-hoc interpretation; resolving a gate by its declared type is workflow-owned behaviour, not ad-hoc interpretation.
  ALWAYS use visible companion-skill routing and return a launch list for current user messages that no longer fit the active workflow's reachable states but clearly span another cf-* domain; NEVER switch workflows silently.
  ALWAYS say that the current workflow is being exited and that control is returning to free mode before handling any request outside the workflow; requests outside the workflow are allowed only after no valid current-state transition or companion workflow remains.
  NEVER treat an off-protocol follow-up as authority to skip the active
    workflow's states, menus, approvals, validation, dispatch gates, or
    completion criteria. A skip is bypassing a gate without a resolution
    permitted by its statically declared type and the deterministic gate
    semantics that apply to it; a gate resolved within those is not a skip.
  ALWAYS produce the required audit record for every permitted autonomous
    resolution.
  NEVER continue the active workflow and free mode in the same turn.
  NEVER treat a reply as a mode reset; mode and typed-gate semantics persist
    across cancels, re-plans, and workflow transitions and change only on
    an explicit request matched against the declared trigger set in
    SimpleModeChoice.
```
