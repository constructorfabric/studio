# Explain Gates

```pdsl
UNIT ExplainE0Preflight
PURPOSE: Resolve the explanation target and input access via preflight before any portion content (Phase E0).
DO:
  RUN ExplainExecutionContextPrep
  RUN SubAgentDispatch for the storytelling-preflight dispatch group before launching preflight
  DISPATCH storytelling-preflight with the raw target/path, user prompt, cf_studio_path, project_root, and RESOURCE_CONTEXT when provided to resolve the input-access tier, run the session-discovery scan, and enforce size guards (returns a lightweight handle, no bulk extraction)
  INVOKE skill `cf-explore` with intent=analyze and return_context=true to discover targets WHEN the explanation target is not explicit
  CONTINUE ExplainE1Gates
RULES:
  ALWAYS run the E0 input-access chain (preflight) for non-local targets before reporting any "not found"
  ALWAYS pass ExplainExploreGate-resolved RESOURCE_CONTEXT to storytelling-preflight as read-only context references, never as a gate verdict or inline bulk prompt text
  NEVER emit portion content in E0
```

```pdsl
UNIT ExplainE1Gates
PURPOSE: Resolve the four Discovery gates as separate user-interaction boundaries via storytelling-gate, advancing one gate per turn (Phase E1).
STATE:
  SET E1_GATE: mode | disposition | audience | plan | done (default mode, scope workflow_run)
DO:
  RUN ExplainStorytellingReferenceLoad
  LOAD {cf-studio-path}/.core/skills/studio/modules/explain-deliver-wrap.md
  RUN resolve mode/disposition/audience/plan from the STORYTELLING_* presets, represent those preset answers in the E0/E1 opener, SET E1_GATE = done, and CONTINUE ExplainE2Deliver WHEN CF_HELP_PRESET == true AND STORYTELLING_PLAN_APPROVED == true
  RUN SubAgentDispatch for the storytelling-gate dispatch group before launching each E1 gate WHEN CF_HELP_PRESET != true OR STORYTELLING_PLAN_APPROVED != true
  DISPATCH storytelling-gate gate_id=mode to render the numbered always-ask mode menu, WAIT user.reply, SET E1_GATE = disposition, STOP_TURN WHEN E1_GATE == mode
  DISPATCH storytelling-gate gate_id=artifact-disposition, WAIT user.reply, SET E1_GATE = audience, STOP_TURN WHEN E1_GATE == disposition
  DISPATCH storytelling-gate gate_id=audience, WAIT user.reply, SET E1_GATE = plan, STOP_TURN WHEN E1_GATE == audience
  DISPATCH storytelling-gate gate_id=plan to render the 4-option plan-approval menu (handle Edit/Pivot/Cancel per storytelling-gate), WAIT user.reply, STOP_TURN WHEN E1_GATE == plan AND the plan is NOT yet approved
  SET E1_GATE = done WHEN E1_GATE == plan AND the plan is approved
  CONTINUE ExplainE2Deliver WHEN E1_GATE == done
RULES:
  ALWAYS under CF_HELP_PRESET == true, resolve the four gates from the STORYTELLING_* presets instead of prompting (preset resolution skips the prompts, not the phases) and NEVER emit a one-shot overview/command list — the next output is the E0/E1 opener, then E2 delivery
  ALWAYS run the gates in order mode -> disposition -> audience -> plan and keep each a separate user-interaction boundary
  ALWAYS resolve mode always-ask (intent/default only suggest, never auto-select)
  ALWAYS advance E1_GATE only after the current gate's user reply is received; NEVER re-ask an already-resolved gate
  ALWAYS parse a single user reply that contains enough information to resolve multiple gates (e.g. "tutorial, chat only, developer") in one pass; prompt only for remaining unresolved gates rather than emitting each gate as a separate mandatory turn
  ALWAYS handle Edit/Pivot/Cancel from the plan gate per storytelling-gate
  ALWAYS on a plan-gate Cancel, RETURN an EXPLAIN_RESULT envelope with status="cancelled" and STOP_TURN
  NEVER enter E2 before the plan-approval gate resolves
  NEVER emit portion content or inline explanation text after plan approval — ALWAYS hand control to ExplainE2Deliver, which owns the portion-delivery loop; emitting all plan portions in one response from ExplainE1Gates is an AP#0 violation equivalent to skipping E2 entirely
```
