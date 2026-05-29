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

1. Opening paragraph
2. **Body** (text, ≤ resolved `page_size_soft` words, default 200)
3. Mode-lens mid-section (per-mode rhythm per `storytelling-modes.md`)
4. **Navigation topic candidates**: maintain Next, Deeper, and Lateral candidate lists. Next candidates include upcoming plan items plus completed topics that can be revisited. Deeper/Lateral candidates each have a short label + 1-line preview. Do not dump candidate lists inside every portion; bare `Next` / `Deeper` / `Lateral` opens a numbered topic-pick menu. Direct shortcuts `Next N` / `Deeper N` / `Lateral N` may execute a candidate immediately.
5. Source refs (clickable Markdown links)
6. `🎨 visualization:` decision marker
7. Progress marker (`📍 {idx}/{N}`)
8. 7-slot navigation block — Next / Deeper / Lateral / Recap / Ask / Wrap / Back, Next-first order (see §7-Slot Navigation Block below)

## 7-Slot Navigation Block

Next-first order (slot 1 always first):

1. **Next** — open a numbered menu of upcoming/revisit plan topics (keyword: `Next`; shortcut: `Next {N}`)
2. **Deeper** — open a numbered menu of drill-down candidates for the current topic (keyword: `Deeper`; shortcut: `Deeper {N}`)
3. **Lateral** — open a numbered menu of related-topic candidates at the same depth (keyword: `Lateral`; shortcut: `Lateral {N}`)
4. **Recap** — summary so far (keyword: `Recap`)
5. **Ask** — free-form question (keyword: `Ask`)
6. **Wrap** — end session (keyword: `Wrap`)
7. **Back** — return to the previous portion or previous menu (keyword: `Back`)

One mandatory `→ suggested: N` line per portion (current best-fit slot). `go` or Enter alone executes suggested slot; bare `next` opens the Next topics menu.

When the user picks slot 1, 2, or 3, render the matching topic menu and STOP_TURN
before delivering a new portion:

```text
Next topics:
  1. Continue — {next plan item label} — {one-line preview}
  2. Skip ahead — {later plan item label} — {one-line preview}
  3. Revisit — {completed/current topic label} — {one-line preview}
  ...
  N. Custom — tell me which planned topic to jump to or revisit
  N+1. Back — return to the main navigation
→ suggested: {S}
```

```text
Deeper topics:
  1. {candidate label} — {one-line preview}
  2. {candidate label} — {one-line preview}
  ...
  N. Custom — tell me what to drill into
  N+1. Back — return to the main navigation
→ suggested: {S}
```

```text
Lateral topics:
  1. {candidate label} — {one-line preview}
  2. {candidate label} — {one-line preview}
  ...
  N. Custom — tell me where to go sideways
  N+1. Back — return to the main navigation
→ suggested: {S}
```

If the user picks `Custom`, ask for one free-text topic. If no candidate list can
be generated, still render a menu with `1. Custom ...` and `2. Back to the main
navigation`.

## Source-Grounding Rules

Per Anti-Patterns #16, #17, #19, #20:

- Every non-trivial claim: **clickable Markdown link** source ref (NOT plain-text `(DESIGN.md §4.2)`)
- PR/MR analysis: files-in-diff use PR-view inline-diff URLs (`/pull/{N}/files#diff-{hash}R{a}-R{b}`); files NOT in diff use blob/SHA
- Ungrounded claims: **silently skipped** — no `[?]` markers; no agent-initiated open-questions
- Source quotes: original artifact language; chat replies follow user prompt language

## Path Conventions (Portability)

Per Anti-Pattern #28e; see `{cf-studio-path}/.core/requirements/storytelling-preferences.md` §Path Conventions for full scope.

- ALL written artifacts and internal cross-references: **relative paths** from project root
- Forbidden absolute prefixes: `/Users/...`, `/Volumes/...`, `/home/...`, `C:\...`
- Template variables (e.g. `cf-path`, `project_root`): convert to relative-from-project-root before write or chat-display
- Relative-within-package: `../` prefixes computed per artifact location; same for exports

## Language Complexity

Every chat message AND every artifact write self-checks against resolved `language_complexity` (low/middle/high; default middle).

Source quotes exempt (verbatim). See `{cf-studio-path}/.core/requirements/language-complexity.md` for the full rule.
