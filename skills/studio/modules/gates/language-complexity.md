# Language Complexity Gate

```pdsl
UNIT LanguageComplexityLoad
PURPOSE: Always load and apply the language-complexity rule when the intent is creating documents, guides, or reports.
WHEN:
  REQUIRE the prompt intent is creating or writing documents, guides, reports, READMEs, documentation, onboarding/training material, or explanatory write-ups
DO:
  LOAD {cf-studio-path}/.core/requirements/language-complexity.md and follow it
RULES:
  ALWAYS load {cf-studio-path}/.core/requirements/language-complexity.md before producing any document, guide, or report content
  ALWAYS self-check every chat message and artifact write against the resolved language-complexity level and rewrite before emitting when a draft breaches it
  ALWAYS keep source quotes verbatim (exempt from the complexity rewrite)
```
