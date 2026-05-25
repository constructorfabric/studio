---
cf: true
type: requirement
name: Storytelling Shared Cross-Cutting Rules
version: 1.0
purpose: Shared cross-cutting rules loaded once by the storytelling router; portion shape, navigation, source-grounding, language-complexity defaults
description: "Cross-cutting storytelling rules — portion shape (Body + Mode-lens + ≥2 deep-candidates + 6-slot nav), Source-Grounding (clickable links per AP-#16/17), Path Conventions (per AP-#28e), language-complexity defer rule. Loaded once by the storytelling.md router as a prefix block; not registered in agents.toml."
---

# Storytelling Shared Cross-Cutting Rules

<!-- toc -->

- [Portion Shape (E2)](#portion-shape-e2)
- [6-Slot Navigation Block](#6-slot-navigation-block)
- [Source-Grounding Rules](#source-grounding-rules)
- [Path Conventions (Portability)](#path-conventions-portability)
- [Language Complexity](#language-complexity)

<!-- /toc -->

## Portion Shape (E2)

Non-socratic modes deliver:

1. Opening paragraph
2. **Body** (text, ≤ resolved `page_size_soft` words, default 200)
3. Mode-lens mid-section (per-mode rhythm per `storytelling-modes.md`)
4. **Deeper candidates**: numbered list of ≥2 sub-topics. Each: short label + 1-line preview. Renders under Deeper nav as `Deeper: pick 1-N` (parse keyword: `Deeper N`); bare `Deeper` is rejected with re-prompt
5. Source refs (clickable Markdown links)
6. `🎨 visualization:` decision marker
7. Progress marker (`📍 {idx}/{N}`)
8. 6-slot navigation block — Next / Deeper / Lateral / Recap / Ask / Wrap, Next-first order (see §6-Slot Navigation Block below)

## 6-Slot Navigation Block

Next-first order (slot 1 always first):

1. **Next** — advance to next plan item (keyword: `next` unambiguous)
2. **Deeper** — drill into ≥2 candidates per portion (keyword: `Deeper {N}`)
3. **Lateral** — related-topic same depth (keyword: `Lateral`)
4. **Recap** — summary so far (keyword: `Recap`)
5. **Ask** — free-form question (keyword: `Ask`)
6. **Wrap** — end session (keyword: `Wrap`)

One mandatory `→ suggested: N` line per portion (current best-fit slot). `go` or Enter alone executes suggested slot; `next` = slot 1 unambiguous per Anti-Pattern #27.

## Source-Grounding Rules

Per Anti-Patterns #16, #17, #19, #20:

- Every non-trivial claim: **clickable Markdown link** source ref (NOT plain-text `(DESIGN.md §4.2)`)
- PR/MR analysis: files-in-diff use PR-view inline-diff URLs (`/pull/{N}/files#diff-{hash}R{a}-R{b}`); files NOT in diff use blob/SHA
- Ungrounded claims: **silently skipped** — no `[?]` markers; no agent-initiated open-questions
- Source quotes: original artifact language; chat replies follow user prompt language

## Path Conventions (Portability)

Per Anti-Pattern #28e; see `storytelling-preferences.md` §Path Conventions for full scope.

- ALL written artifacts and internal cross-references: **relative paths** from project root
- Forbidden absolute prefixes: `/Users/...`, `/Volumes/...`, `/home/...`, `C:\...`
- Template variables (e.g. `cf-path`, `project_root`): convert to relative-from-project-root before write or chat-display
- Relative-within-package: `../` prefixes computed per artifact location; same for exports

## Language Complexity

Every chat message AND every artifact write self-checks against resolved `language_complexity` (low/middle/high; default middle).

Source quotes exempt (verbatim). See `.bootstrap/.core/requirements/language-complexity.md` for full rule.
