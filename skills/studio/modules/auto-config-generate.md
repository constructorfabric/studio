# Auto-Config Generate

```pdsl
UNIT AutoConfigGenerate
PURPOSE: Generate per-topic rule files from scan evidence and write them only after explicit confirmation.
WHEN:
  REQUIRE the topic map is confirmed
DO:
  RUN generate per-topic rule files from scan evidence — each rule grounded in `file:line` evidence, activity-based, passing prompt-engineering L2 clarity (no vague qualifiers, explicit activity-based WHEN) and L5 anti-pattern checks (no AP-VAGUE, AP-CONTEXT-BLOAT, AP-HALLUCINATION-PRONE), under 120 lines, no overlap, no boilerplate; one topic file includes a Critical Files table
  EMIT the generated rule-file batch for review
  LOAD {cf-studio-path}/.core/skills/studio/modules/auto-config-integrate-validate.md
  EMIT_MENU GenerateConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS present generated rule files before writing any file
  NEVER write without explicit confirmation
  ALWAYS restrict rule-file writes to {cf-studio-path}/config/rules/
MENU GenerateConfirmMenu
TITLE: Generated rule files — write them and proceed to integration?
OPTIONS:
  1 proceed -> WRITE the rule files to {cf-studio-path}/config/rules/{topic}.md, RUN `{cfs_cmd} toc` on each, then CONTINUE AutoConfigIntegrate
  2 adjust -> revise the rule files per feedback and EMIT_MENU GenerateConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the rule-file review checkpoint; no files written" and next_action="re-run auto-config to regenerate and review the rule files" and STOP_TURN
  INVALID -> EMIT_MENU GenerateConfirmMenu
```
