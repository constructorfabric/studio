---
cf: true
type: requirement
name: Storytelling Shared Cross-Cutting Rules
version: 1.0
purpose: Shared cross-cutting rules loaded once by the storytelling router; portion shape, navigation, source-grounding, language-complexity defaults
description: "Cross-cutting storytelling rules — portion shape (Body + Mode-lens + deeper/lateral topic menus + 7-slot nav), Source-Grounding (clickable links per AP-#16/17), Path Conventions (per AP-#28e), language-complexity defer rule. Loaded once by the storytelling.md router as a prefix block; not registered in agents.toml."
---

# Storytelling Shared Cross-Cutting Rules

<!-- toc -->

- [Portion Shape (E2)](#portion-shape-e2)
- [7-Slot Navigation Block](#7-slot-navigation-block)
- [Source-Grounding Rules](#source-grounding-rules)
- [Path Conventions (Portability)](#path-conventions-portability)
- [Language Complexity](#language-complexity)

<!-- /toc -->

## Portion Shape (E2)

Non-socratic modes deliver:

```pdsl
UNIT portion_shape_e2
PURPOSE: Define the mandatory output shape for every non-socratic mode portion.
DO:
  - EMIT opening_paragraph
  - EMIT body: text ≤ resolved page_size_soft words (default 200)
  - EMIT mode_lens_section: per-mode rhythm per storytelling-modes.md
  - EMIT next_candidates: upcoming plan items plus completed/revisitable topics; each with short label + 1-line preview
  - EMIT deeper_candidates: drill-down candidates for current topic; each with short label + 1-line preview
  - EMIT lateral_candidates: related-topic candidates at same depth; each with short label + 1-line preview
  - EMIT source_refs: clickable Markdown links
  - EMIT visualization_marker: 🎨 visualization: decision marker
  - EMIT progress_marker: 📍 {idx}/{N}
  - EMIT nav_block: 7-slot navigation block, Next-first order (see §7-Slot Navigation Block)
RULES:
  - NEVER dump candidate lists inside the portion body
  - ALWAYS open a numbered topic-pick menu on bare Next / Deeper / Lateral input
  - ALWAYS execute a candidate immediately on direct shortcuts Next N / Deeper N / Lateral N
```

## 7-Slot Navigation Block

Next-first order (slot 1 always first):

```pdsl
UNIT seven_slot_nav_block
PURPOSE: Emit the 7-slot navigation block at the end of every non-socratic portion.
DO:
  - EMIT_MENU nav_block:
      TITLE: navigation
      OPTIONS:
        1. Next — open numbered menu of upcoming/revisit plan topics (keyword: Next; shortcut: Next {N})
        2. Deeper — open numbered menu of drill-down candidates (keyword: Deeper; shortcut: Deeper {N})
        3. Lateral — open numbered menu of related-topic candidates (keyword: Lateral; shortcut: Lateral {N})
        4. Recap — summary so far (keyword: Recap)
        5. Ask — free-form question (keyword: Ask)
        6. Wrap — end session (keyword: Wrap)
        7. Back — return to previous portion or previous menu (keyword: Back)
  - EMIT → suggested: {S}
RULES:
  - ALWAYS render slots in Next-first order (1 through 7)
  - ALWAYS include exactly one → suggested: N line per portion
  - ALWAYS execute suggested slot when user inputs go or Enter alone
  - ALWAYS open the Next topics menu when user inputs bare next
```

bare `Next` / `Deeper` / `Lateral` opens a numbered topic-pick menu; a shortcut like `Next 2` executes immediately without a menu.

When slot 1, 2, or 3 is selected, render the matching topic menu then STOP_TURN before delivering a new portion:

```pdsl
UNIT topic_menu_dispatch
PURPOSE: Render a numbered topic-pick menu and stop the turn when slot 1, 2, or 3 is selected.
WHEN:
  - REQUIRE user selects slot 1 (Next), 2 (Deeper), or 3 (Lateral)
DO:
  - DISPATCH slot 1 ->
      EMIT_MENU:
        TITLE: Next topics
        OPTIONS:
          1. Continue — {next plan item label} — {one-line preview}
          2. Skip ahead — {later plan item label} — {one-line preview}
          3. Revisit — {completed/current topic label} — {one-line preview}
          N. Custom — tell me which planned topic to jump to or revisit
          N+1. Back — return to the main navigation
  - DISPATCH slot 2 ->
      EMIT_MENU:
        TITLE: Deeper topics
        OPTIONS:
          1. {candidate label} — {one-line preview}
          N. Custom — tell me what to drill into
          N+1. Back — return to the main navigation
  - DISPATCH slot 3 ->
      EMIT_MENU:
        TITLE: Lateral topics
        OPTIONS:
          1. {candidate label} — {one-line preview}
          N. Custom — tell me where to go sideways
          N+1. Back — return to the main navigation
  - EMIT → suggested: {S}
  - STOP_TURN
RULES:
  - NEVER deliver a new portion before the user picks from the topic menu
  - ALWAYS ask for one free-text topic when user picks Custom
ON_ERROR:
  no_candidates -> EMIT_MENU with "1. Custom" and "2. Back to the main navigation"
```

## Source-Grounding Rules

Per Anti-Patterns #16, #17, #19, #20:

```pdsl
UNIT source_grounding
PURPOSE: Enforce clickable source references and prevent ungrounded claims.
RULES:
  - ALWAYS attach a clickable Markdown link source ref to every non-trivial claim
  - NEVER use plain-text citations (e.g. (DESIGN.md §4.2))
  - ALWAYS use PR-view inline-diff URLs for files in diff (/pull/{N}/files#diff-{hash}R{a}-R{b}); use blob/SHA for files not in diff
  - NEVER fabricate ungrounded claims; omit rather than invent; no [?] markers; no agent-initiated open-questions
  - ALWAYS use original artifact language for source quotes; follow user prompt language for chat replies
  - ALWAYS create a user-driven open-question entry when the user directly asks for information the input does not cover
```

## Path Conventions (Portability)

Per Anti-Pattern #28e; see `{cf-studio-path}/.core/requirements/storytelling-preferences.md` §Path Conventions for full scope.

```pdsl
UNIT path_conventions
PURPOSE: Enforce relative-path portability for all written artifacts and cross-references.
RULES:
  - ALWAYS use relative paths from project root in all written artifacts and internal cross-references
  - NEVER write absolute prefixes: /Users/..., /Volumes/..., /home/..., C:\...
  - ALWAYS convert template variables (e.g. cf-path, project_root) to relative-from-project-root before write or chat-display
  - ALWAYS compute ../ prefixes per artifact location for relative-within-package references and exports
```

## Language Complexity

```pdsl
UNIT language_complexity_check
PURPOSE: Self-check every output against the resolved language_complexity setting.
WHEN:
  - REQUIRE resolved language_complexity (low / middle / high; default middle)
DO:
  - RUN self-check against language_complexity on every chat message
  - RUN self-check against language_complexity on every artifact write
RULES:
  - NEVER apply language_complexity to source quotes (verbatim exempt)
NOTES:
  Full rule: {cf-studio-path}/.core/requirements/language-complexity.md
```
