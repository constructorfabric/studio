# Auto-Config Docs

```pdsl
UNIT AutoConfigDocs
PURPOSE: Discover project documentation, offer TOCs, and confirm doc navigation rules.
WHEN:
  REQUIRE the scan summary is confirmed
DO:
  RUN build a documentation inventory from resource_context (path, title, has-TOC, key headings, WHEN condition)
  RUN for each doc missing a TOC, EMIT a non-blocking suggestion "To add a TOC, run `{cfs_cmd} toc <doc>`"; never run the command or block discovery on it
  EMIT the Documentation Map and proposed navigation rules checkpoint
  LOAD {cf-studio-path}/.core/skills/studio/modules/auto-config-detect.md
  EMIT_MENU DocsConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS present the documentation map and proposed navigation rules before detection
  NEVER add TOCs without confirmation
MENU DocsConfirmMenu
TITLE: Documentation map — proceed to system and topic detection?
OPTIONS:
  1 proceed -> CONTINUE AutoConfigDetect
  2 adjust -> re-emit the documentation map, then EMIT_MENU DocsConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the documentation map checkpoint" and next_action="re-run auto-config to continue from the scan" and STOP_TURN
  INVALID -> EMIT_MENU DocsConfirmMenu
```
