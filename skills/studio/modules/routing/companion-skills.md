# Companion Skill Routing

```pdsl
UNIT CompanionSkillRouting
PURPOSE: Let routers and workflows offer multiple compatible cf-* companion skills for cross-domain tasks without weakening each selected skill's protocol.
WHEN:
  REQUIRE a task intent clearly spans more than one cf-* skill domain
DO:
  RUN identify compatible companion skills from the resolved cf-* skill list by matching the task domains, required artifacts, and requested operations against each skill name and description
  RUN rank companion groups by relevance, protocol compatibility, and minimal necessary scope
  EMIT a menu that includes the best single skill and the best companion group, marking exactly one suggested option
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS prefer the smallest companion group that covers the task domains
  ALWAYS include write-docs/write-skills/coding/analyze/generate companions when the user request explicitly spans documentation, prompt/workflow authoring, source code, review, or implementation
  ALWAYS invoke selected companion skills sequentially, not as a merged prompt, so each skill entry loads and follows its own prerequisites
  NEVER load a companion skill silently; companion loading is always visible in a numbered menu or explicit user reply
  NEVER let companion routing skip or reorder hard gates emitted by any selected skill
```
