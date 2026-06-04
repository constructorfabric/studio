---
cf: true
type: workflow
name: cf-help
version: 0.1
description: "Invoke for cf help, /cf help, cf-studio help, /cf-studio help, or cfs help — presets a cf-explain storytelling walkthrough of Constructor Studio itself."
purpose: Thin help router that presets the cf-explain storytelling help session and delegates to cf-explain
---

# cf-help

This skill answers help requests by presetting a `cf-explain` storytelling walkthrough of Constructor Studio itself — presentation mode, chat-only, newcomers audience, source-grounded portions with normal navigation — and delegating to the `cf-explain` skill. It never renders a custom one-shot help blurb or command list.

```pdsl
UNIT HelpBootstrap
PURPOSE: Ensure the cf skill is loaded before presetting the help session.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  CONTINUE HelpPreset WHEN CFS_INIT == true
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before presetting the help session
  ALWAYS treat CFS_INIT as false when its value is unknown, ambiguous, or unset
  NEVER proceed past HelpBootstrap unless CFS_INIT == true is positively confirmed
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so help cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE HelpBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```
```pdsl
UNIT HelpPreset
PURPOSE: Preset the storytelling help session about Constructor Studio and delegate to cf-explain.
DO:
  SET CF_HELP_PRESET = true
  SET EXPLAIN_MODE = true
  SET EXPLAIN_TARGET = {cf-studio-path}
  SET STORYTELLING_MODE = presentation
  SET STORYTELLING_ARTIFACT_DISPOSITION = chat-only
  SET STORYTELLING_AUDIENCE = Constructor Studio newcomers
  SET STORYTELLING_CONTEXT_PACK_STRATEGY = hybrid
  SET STORYTELLING_PLAN_APPROVED = true
  SET STORYTELLING_DIAGRAM_FORMAT = ascii
  SET STORYTELLING_DIAGRAM_FORMAT_PRESET = true
  SET STORYTELLING_HELP_GOAL = "Run a normal cf-explain storytelling session about Constructor Studio itself: target {cf-studio-path}, presentation mode, chat-only, newcomers audience, source-grounded portions, normal navigation."
  INVOKE skill `cf-explain` to run the preset storytelling session, then STOP_TURN
RULES:
  NEVER render custom one-shot help, a command list, or a status summary here
  ALWAYS let the preset values resolve cf-explain's four E1 gates (mode/disposition/audience/plan) instead of prompting — preset resolution skips the prompts, not the phases
  ALWAYS keep the next user-visible output to the storytelling E0/E1 opener, then E2 portion delivery
```
