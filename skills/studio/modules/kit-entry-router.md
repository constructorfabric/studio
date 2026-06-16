# Kit Entry Router
```pdsl
UNIT KitInitEntryRoute
PURPOSE: Capture the target folder from the user request or ask for it before any discovery or write logic.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET TARGET_DIR: string (default unset, scope workflow_run)
  SET CANONICAL_MANIFEST: string (default unset, scope workflow_run)
  SET LEGACY_MANIFEST: string (default unset, scope workflow_run)
  SET LEGACY_CONF: string (default unset, scope workflow_run)
  SET TARGET_SOURCE: unset | canonical | legacy_manifest | legacy_layout | discovery (default unset, scope workflow_run)
  SET NORMALIZE_SOURCE_HINT: unset | manifest | layout (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT: unset | provided (default unset, scope workflow_run)
  SET DISCOVERY_STATUS: unset | provided | empty | error (default unset, scope workflow_run)
  SET PREVIEW_STATUS: unset | pass | fail | error (default unset, scope workflow_run)
  SET PENDING_EDIT_BRANCH: unset | legacy_manifest | discovery (default unset, scope workflow_run)
  SET PENDING_MANUAL_GUIDANCE: unset | true (default unset, scope workflow_run)
  SET CURRENT_PREVIEW_TOML: string (default unset, scope workflow_run)
  SET CURRENT_PREVIEW_REPORT: string (default unset, scope workflow_run)
  SET APPROVED_PREVIEW: string (default unset, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering request (verbatim or shortest faithful summary)
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-edit-flow.md WHEN PENDING_EDIT_BRANCH != unset AND the user reply contains requested manifest edits
  CONTINUE KitInitApplyUserEditsStart WHEN PENDING_EDIT_BRANCH != unset AND the user reply contains requested manifest edits
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-manual-guidance-flow.md WHEN PENDING_MANUAL_GUIDANCE == true AND the user reply contains manual resource guidance
  CONTINUE KitInitManualGuidanceProposalStart WHEN PENDING_MANUAL_GUIDANCE == true AND the user reply contains manual resource guidance
  SET TARGET_DIR = the target folder path from the user request WHEN the request already names a concrete folder
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-target-entry.md WHEN TARGET_DIR == unset
  CONTINUE KitInitAskTarget WHEN TARGET_DIR == unset
  SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer WHEN TARGET_DIR != unset
RULES:
  ALWAYS capture the original intent before routing any cf-kit branch
  ALWAYS resolve the target folder before discovery, preview, validation, or write work
  NEVER guess a target folder from vague intent alone
```
