# Brainstorm Panel Render

```pdsl
UNIT BrainstormPanelRender
PURPOSE: Present the proposed panel and wait for one edit or start command.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-rounds.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/brainstorm-wrap.md
  EMIT the rendered panel (E1..E6: persona, focus, why) and the seed topic
  EMIT_MENU PanelEditMenu
  WAIT user.reply
  STOP_TURN
MENU PanelEditMenu
TITLE: Panel setup — reply `start` to begin, or refine the panel with one command at a time (drop, swap, add, or change seed topic).
OPTIONS:
  1 start -> INVOKE skill `cf-explore` with intent=brainstorm and return_context=true (it returns resource_context and skips its save offer and NextActionsOffer handoff), SET resource_context, then CONTINUE BrainstormRounds
  2 seed:<topic> -> set the seed topic, re-render the panel, and EMIT_MENU PanelEditMenu
  3 drop E{N} -> REQUIRE min 3 remain, re-render the panel, and EMIT_MENU PanelEditMenu
  4 swap E{N}:<persona>(<focus>) -> replace the persona, re-render the panel, and EMIT_MENU PanelEditMenu
  5 add:<persona>(<focus>) -> REQUIRE panel size < 6, re-render the panel, and EMIT_MENU PanelEditMenu
  6 W | wrap -> CONTINUE BrainstormWrap
  INVALID -> EMIT one-line clarifier and EMIT_MENU PanelEditMenu
```
