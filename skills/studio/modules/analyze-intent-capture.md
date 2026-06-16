# Analyze Intent Capture

```pdsl
UNIT AnalyzeDescribeIntent
PURPOSE: Capture an analyze intent as a separate turn before routing.
STATE:
  SET ANALYZE_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
DO:
  EMIT "Describe what you want to analyze, review, validate, or compare. I will match the relevant cf-* workflow(s), including companions when needed."
  SET ANALYZE_INTENT_CAPTURE_STATE = resume
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS stop the turn after prompting so analyze intent routing resumes in an explicit unit
```

```pdsl
UNIT AnalyzeDescribeIntentResume
PURPOSE: Route the resumed analyze intent after the prompt turn completes.
STATE:
  SET ANALYZE_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE ANALYZE_INTENT_CAPTURE_STATE == resume
DO:
  SET ORIGINAL_INTENT = user.reply
  SET ANALYZE_INTENT_CAPTURE_STATE = unset
  CONTINUE AnalyzeRoute
```
