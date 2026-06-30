# Plan Validate

```pdsl
UNIT PlanPhase3Validate
PURPOSE: Verify produced phase files match their briefs and cover all rules (Phase 3.4).
WHEN:
  REQUIRE phase files were produced this run (option 1 or 3)
DO:
  RUN verify every brief exists, each phase file matches its brief's load instructions, no unresolved {...} vars outside code fences, each phase file <= 1000 lines (split if oversized), and the union of all phase Rules sections covers 100% of applicable rules (re-split rather than drop rules)
  CONTINUE PlanPhase4Finalize
ON_ERROR:
  each phase file <= 1000 lines (split if oversized) check fails -> RUN auto-split the oversized phase file into ordered phase-NN-*.md parts (re-split rather than drop rules), update plan.toml [[phases]], then re-run the verify step; WHEN it still exceeds 1000 lines after the auto-split: EMIT the oversized file path with explicit split instructions, EMIT_MENU OversizedPhaseRecoveryMenu, WAIT user.reply, STOP_TURN
MENU OversizedPhaseRecoveryMenu
TITLE: Phase file still exceeds 1000 lines after auto-split. How would you like to proceed?
OPTIONS:
  1 re-verify — I have made manual edits to the file, re-run the verify step -> CONTINUE PlanPhase3Validate
  2 stop — keep the current files and return to free mode -> LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded; RUN NextActionsOffer
  INVALID -> EMIT_MENU OversizedPhaseRecoveryMenu
RULES:
  NEVER drop rules to meet budget
```

```pdsl
UNIT PlanPhase4Finalize
PURPOSE: Self-validate the plan against the checklist and offer next steps (Phase 4).
WHEN:
  REQUIRE phase files were produced this run (brief-checkpoint option 1 or 3)
DO:
  LOAD {cf-studio-path}/.core/requirements/plan-checklist.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/plan-native-dispatch.md
  RUN self-validate against the 7 checklist categories (structural, interactive questions, rules coverage, context completeness, phase independence, budget, lifecycle & handoff) and update plan.toml status fields
  EMIT the self-validation table and offer to fix any FAIL
  EMIT "Plan created: {cf-studio-path}/.plans/{task-slug}/ (phases, files, lifecycle)" WHEN all categories PASS
  EMIT_MENU Phase4NextStepsMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS run self-validation before any handoff or startup prompt
  ALWAYS emit "Plan created" only after validation PASS confirms plan.toml + every brief + every phase file exist on disk
  ALWAYS wrap the startup prompt in a single fenced code block with no other text
  ALWAYS keep option 2 execute safe — when sub-agents are unavailable it falls back to the handoff prompt rather than failing
MENU Phase4NextStepsMenu
TITLE: Plan passed self-validation — what next? Option 1 (analyze) is the suggested default before execution. Reply with a number.
OPTIONS:
  1 analyze -> CONTINUE {cf-studio-path}/.core/workflows/analyze.md with ORIGINAL_INTENT="analyze the generated plan at {cf-studio-path}/.plans/{task-slug}/ for validation issues"
  2 execute -> CONTINUE PlanNativeExecute (native same-chat execution; if sub-agents are unavailable it falls back to the handoff prompt)
  3 handoff -> EMIT the new-chat startup prompt in a single fenced code block (read plan.toml, execute Phase 1, then report and prompt for Phase 2), EMIT "Paste the above prompt into a new chat to begin execution. Return here to continue with Phase 2.", then EMIT_MENU Phase4NextStepsMenu
  4 review -> EMIT the plan file paths to inspect, then EMIT_MENU Phase4NextStepsMenu
  5 modify -> WAIT the user's plan changes (add/remove phases, adjust scope, update files), then EMIT_MENU Phase4NextStepsMenu
  6 done -> LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded; RUN NextActionsOffer
  INVALID -> EMIT_MENU Phase4NextStepsMenu
```
