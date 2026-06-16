# Generate Intent Capture

```pdsl
UNIT GenerateDescribeIntent
PURPOSE: Capture a generate intent as a separate turn before routing.
STATE:
  SET GENERATE_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
DO:
  EMIT "Describe what you want to generate, change, or fix. I will match the relevant cf-* workflow(s), including companions when needed."
  SET GENERATE_INTENT_CAPTURE_STATE = resume
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS stop the turn after prompting so generate intent routing resumes in an explicit unit
```

```pdsl
UNIT GenerateDescribeIntentResume
PURPOSE: Route the resumed generate intent after the prompt turn completes.
STATE:
  SET GENERATE_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE GENERATE_INTENT_CAPTURE_STATE == resume
DO:
  SET ORIGINAL_INTENT = user.reply
  SET GENERATE_INTENT_CAPTURE_STATE = unset
  CONTINUE GenerateRoute
```
