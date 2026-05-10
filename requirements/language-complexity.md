---
cf-constructor: true
type: requirement
name: Language Complexity (global UX rule)
version: 1.0
purpose: Configurable language-complexity level for all Cypilot user-facing output (chat + artifacts/documentation)
---

# Language Complexity


<!-- toc -->

- [Rule](#rule)
- [Levels](#levels)
- [Resolution](#resolution)
- [Override commands](#override-commands)

<!-- /toc -->

## Rule

All Cypilot user-facing output — chat messages from any workflow / methodology / skill, AND any user-facing artifact body (explain portions, review comments, open questions, key takeaways, generated guides, READMEs, validation reports, summaries) — MUST respect the project's `language_complexity` setting. Default is `middle`. Source quotes from input artifacts are exempt (quoted verbatim per existing strict-context rules); spec/normative files (workflows, requirements, kits, agent definitions) are exempt (those are agent-facing instructions, not user-facing prose).

## Levels

| Level | Sentence length | Vocabulary | Audience |
|---|---|---|---|
| `low` | short, ≤15 words avg | common words only (~top 3000 English / equivalent in user-prompt language); no idioms; jargon defined inline on every use; direct subject-verb-object; minimal passive voice | non-native A2-B1; quick scanners |
| `middle` (default) | short-to-medium, 15-25 words avg | everyday vocabulary; technical terms allowed with brief gloss on first mention; simple compound sentences OK; light passive voice OK; no archaic / rare / academic register | non-native B2 / intermediate; broad mixed audiences |
| `high` | any length OK | full register: technical jargon assumed; idioms / metaphors / academic vocabulary fine | native or C1+; specialist audiences |

Methodology MUST self-check the resolved level on every chat message and every artifact write — if a draft sentence would breach the level (long sentence at `low` / rare word at `middle` / etc.), rewrite before emitting. The check is an active routine, not best-effort.

## Resolution

Priority order:
1. **Mid-session override**: `change language complexity to {low|middle|high}` (in chat) — session-only
2. **Project config**: `[language] complexity = "{level}"` in `{cf-constructor-path}/config/core.toml`
3. **Default**: `middle`

`remember new language complexity` persists the current value to `core.toml` (writes the `[language]` table if absent; preserves unrelated keys).

## Override commands

| Command | Effect |
|---|---|
| `change language complexity to {low|middle|high}` | Session-level override; applies to subsequent chat output and artifact writes; project config NOT updated |
| `remember new language complexity` | Persist current session value to `core.toml` `[language] complexity = "{value}"` |
| `show language complexity` | Display the resolved level + source (override / config / default) |
