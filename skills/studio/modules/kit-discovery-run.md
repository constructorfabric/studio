# Kit Discovery Run
```pdsl
UNIT KitInitDiscoveryRunStart
PURPOSE: Discover candidate kit resources read-only through cf-explore before proposing a new canonical manifest.
WHEN:
  REQUIRE TARGET_SOURCE == discovery
DO:
  INVOKE skill `cf-explore` with intent=discover candidate kit resources for a read-only manifest proposal and return_context=true, scoped to TARGET_DIR and known_paths = TARGET_DIR
  RUN KitInitDiscoveryRunClassifyResult
  CONTINUE KitInitDiscoveryProposal WHEN DISCOVERY_STATUS == provided
  CONTINUE KitInitDiscoveryRunFailure WHEN DISCOVERY_STATUS != provided
RULES:
  ALWAYS use cf-explore in return-context mode for discovery instead of direct filesystem prompt guessing
  ALWAYS keep discovery read-only
  NEVER synthesize a new manifest proposal without verified non-empty resource_context
UNIT KitInitDiscoveryRunClassifyResult
PURPOSE: Classify the discovery result and persist whether resource context is usable.
DO:
  SET DISCOVERY_STATUS = provided WHEN cf-explore returns resource_context with one or more candidate resource paths and evidence summaries
  SET DISCOVERY_STATUS = empty WHEN cf-explore returns no candidate resources
  SET DISCOVERY_STATUS = error WHEN cf-explore fails or returns no usable resource_context
  SET RESOURCE_CONTEXT = provided WHEN DISCOVERY_STATUS == provided
UNIT KitInitDiscoveryRunFailure
PURPOSE: Present the discovery failure menu and wait for the next choice.
DO:
  EMIT_MENU KitInitDiscoveryFailureMenu
  WAIT user.reply
  STOP_TURN
MENU KitInitDiscoveryFailureMenu
TITLE: Discovery did not return candidate kit resources. Retry, provide manual guidance, or cancel.
OPTIONS:
  1 retry -> CONTINUE KitInitDiscoveryRunStart
  2 guidance -> SET PENDING_MANUAL_GUIDANCE = true; EMIT "Reply with resource seed commands such as `add resource id=<id> kind=<kind> source=<path>`, `set metadata.name=<name>`, `set metadata.version=<semver>`, or `exclude source=<path>`."; WAIT user.reply; STOP_TURN
  3 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-3." and EMIT_MENU KitInitDiscoveryFailureMenu
```
