---
cf: true
type: requirement
name: Language Complexity (global UX rule)
version: 1.0
purpose: Configurable language-complexity level for all Studio user-facing output (chat + artifacts/documentation)
---

# Language Complexity


<!-- toc -->

- [Rule](#rule)
- [Levels](#levels)
- [Resolution](#resolution)
- [Override commands](#override-commands)

<!-- /toc -->

## Rule

```pdsl
UNIT LANGUAGE_COMPLEXITY_APPLY
PURPOSE: Enforce the resolved language_complexity level on every piece of user-facing Studio output.
WHEN:
  - REQUIRE output target is user-facing (chat message or artifact body)
DO:
  - LOAD resolved_level from LANGUAGE_COMPLEXITY_RESOLVE
  - RUN self-check on every draft sentence against resolved_level
  - EMIT rewritten sentence if self-check detects a breach; never emit the breaching draft
RULES:
  - ALWAYS apply to all chat messages from any workflow, methodology, or skill
  - ALWAYS apply to all user-facing artifact bodies (explain portions, review comments, open questions, key takeaways, generated guides, READMEs, validation reports, summaries)
  - NEVER apply to source quotes from input artifacts (quoted verbatim per strict-context rules)
  - NEVER apply to spec/normative files (workflows, requirements, kits, agent definitions — agent-facing instructions, not user-facing prose)
  - ALWAYS treat the self-check as an active routine, not best-effort
```

## Levels

| Level | Sentence length | Vocabulary | Audience |
|---|---|---|---|
| `low` | short, ≤15 words avg | common words only (~top 3000 English / equivalent in user-prompt language); no idioms; jargon defined inline on every use; direct subject-verb-object; minimal passive voice | non-native A2-B1; quick scanners |
| `middle` (default) | short-to-medium, 15-25 words avg | everyday vocabulary; technical terms allowed with brief gloss on first mention; simple compound sentences OK; light passive voice OK; no archaic / rare / academic register | non-native B2 / intermediate; broad mixed audiences |
| `high` | any length OK | full register: technical jargon assumed; idioms / metaphors / academic vocabulary fine | native or C1+; specialist audiences |

## Resolution

```pdsl
UNIT LANGUAGE_COMPLEXITY_RESOLVE
PURPOSE: Determine the active language_complexity level using priority-ordered sources.
STATE:
  - SET levels: [low, middle, high]
  - SET default_level: middle
  - SET config_path: {cf-studio-path}/config/core.toml
DO:
  - LOAD session_override if set by the user this session
  - LOAD config_level from config_path [language] complexity if session_override is absent
  - SET resolved_level = first of: session_override, config_level, default_level
  - RETURN resolved_level
RULES:
  - ALWAYS apply priority order: session override > project config > default
NOTES:
  Session override is session-only and does not update project config.
```

## Override commands

```pdsl
UNIT LANGUAGE_COMPLEXITY_OVERRIDE
PURPOSE: Process user commands that change or persist the active language_complexity level.
WHEN:
  - REQUIRE user issues a registered language-complexity command
DO:
  - DISPATCH "change language complexity to {low|middle|high}":
      SET session_override = {level}
      EMIT confirmation of new level; note that project config is NOT updated
  - DISPATCH "remember new language complexity":
      RUN WHEN session_override is set:
        SET current_override = session_override
      RUN WHEN session_override is not set:
        LOAD resolved_level via LANGUAGE_COMPLEXITY_RESOLVE
        SET current_override = resolved_level
      REQUIRE current_override in [low, middle, high]
      LOAD [language] table from config_path (create table if absent; preserve all unrelated keys)
      SET [language] complexity = current_override in config_path
      EMIT confirmation of persisted value
  - DISPATCH "show language complexity":
      LOAD resolved_level and its source via LANGUAGE_COMPLEXITY_RESOLVE
      EMIT resolved_level and source (override / config / default)
RULES:
  - NEVER update project config when processing "change language complexity to {level}"
  - ALWAYS preserve unrelated keys in core.toml when writing [language] complexity
ON_ERROR:
  config_write_fails -> RETURN error; NEVER emit success confirmation
```
