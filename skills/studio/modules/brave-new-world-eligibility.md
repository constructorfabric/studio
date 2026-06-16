# Brave New World Eligibility

```pdsl
UNIT BraveNewWorldEligibilityChecklist
PURPOSE: Produce the classification result that permits autonomous selection unless a destructive or irreversible risk is present.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE a pending choice is being evaluated for autonomous selection
DO:
  - RUN inspect every original option's visible action path until the next fresh user input or terminal stop
  - RUN reject only options whose visible action path matches BraveNewWorldBlockedChoice or whose project-damage risk cannot be bounded from current context
  - RUN treat reversible, non-destructive options as eligible without requiring explicit autodefaultable marking
  - RUN prefer non-destructive progress options over terminal or no-op options
  - RUN set classification_status = eligible when at least one valid original option remains after blocked options are rejected
  - RUN set classification_status = ineligible when every option is blocked, every option's project-damage risk is unknown, or the menu/question requires fresh confidential, legal, financial, personal, or irreversible human judgment
RULES:
  - ALWAYS allow reversible, non-destructive workflow choices by default, including loading needed skills, selecting next steps, accepting default discovery/brainstorm/review scopes, answering brainstorm steering questions, choosing inline fallbacks, and continuing validation or review loops
  - ALWAYS require the selected option's visible action path to avoid data loss, destructive or irreversible file operations, unsafe git state changes, permission escalation, credential or secret exposure, deployment, publication, external commitments, payments, and security-impacting changes
  - ALWAYS require the choice to be reversible or correctable without losing user work, secrets, credentials, money, published state, deployment state, or git history
  - ALWAYS require the choice to be derived from visible current workflow state, not hidden user preference
  - ALWAYS require all original options and the chosen option action to be captured in the classification record before selection
  - NEVER require explicit autodefaultable marking for reversible, non-destructive options
  - NEVER prefer terminal or no-op options over non-destructive progress options
```

```pdsl
UNIT BraveNewWorldBlockedChoice
PURPOSE: Define prompts and options that this overlay must never answer.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE a pending choice is being evaluated for autonomous selection
INVARIANTS:
  - NEVER auto-answer destructive-operation prompts, deletion prompts, overwrite prompts, shutdown confirmations, history-rewrite prompts, publish prompts, deployment prompts, or irreversible-operation prompts
  - NEVER auto-answer debugger prompts, breakpoint controls, step/continue approvals, debug-gate prompts, or cf-debug-skill console choices
  - NEVER auto-answer credential, secret, token, authentication, authorization, privacy, security, payment, billing, network-access, external-service, filesystem-permission, sandbox-escalation, install, update, or setup prompts
  - NEVER auto-answer prompts that authorize external delegation, deployment, publication, payments, account changes, cross-repository changes, or actions outside the current workspace
  - NEVER auto-answer git mode, staging, committing, pushing, force-pushing, branch deletion, checkout over uncommitted work, history rewrite, or any git-related permission prompt
  - NEVER auto-answer prompts that authorize deleting files, overwriting user changes, broad mechanical rewrites, dependency upgrades, migrations, generated artifact replacement, or edits whose blast radius is unknown
  - NEVER auto-answer ReviewFindingsNavigation, ReviewFixScope, partial review-fix finding-ID capture, or any prompt that selects which review findings may be fixed
  - NEVER auto-answer prompts that forget, unload, disable, or shut down rules or session state
  - NEVER auto-answer missing prerequisites, unresolved template variables, unavailable required context, failed validation recovery that needs human judgment, validation-result acceptance, or final human-review prompts
  - NEVER auto-answer explicit approvals granting destructive, irreversible, external, permission-escalating, secret-bearing, financial, git-mutating, or unknown-blast-radius authority
  - NEVER weaken REQUIRE, ALWAYS, NEVER, WAIT, STOP_TURN, INVARIANTS, approvals, dispatch gates, or terminal output shapes
```
