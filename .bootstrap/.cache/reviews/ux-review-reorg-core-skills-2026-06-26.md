# UX Review — All Workflows (branch: reorg-core-skills)

**Date:** 2026-06-26  
**Branch:** reorg-core-skills  
**Scope:** All 47 workflow files + supporting modules changed/added in branch  
**Review type:** Combo — UX-freeform + PDSL L5/L8/L9 + prompt-bug-finding  
**Granularity:** Per-layer (8 parallel reviewer groups)

---

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 8 |
| MAJOR | 44 |
| MINOR | 34 |
| **Total** | **86** |

---

## CRITICAL Findings (8)

### F-X-001 — SimpleModeGate fires as first question before any task context
**Files:** `gates/simple-mode.md`  
**Merged from:** F-ROU-007, F-WRK-001, F-DOC-001  
**Evidence:** "Choose workflow interaction mode for this session. Assistant mode acts like a visible guide in chat… Debug loads the existing debugger overlay in run mode… Reply with a number."  
**Root cause:** AP-UNEXPLAINED-ASK + AP-NO-SUGGESTED-OPTION. Gate fires before user sees any task context. Wall-of-prose descriptions. Debug mode exposed to non-developer flows. No option marked suggested. No "change later" hint.  
**Impact:** Every user on every non-exempt workflow is blocked by a meta-question before doing anything. First impression is friction.  
**Fix:** (1) Default to "normal", skip gate unless user requests mode change. (2) If gate must fire, move it after intent capture. (3) Remove debug option from non-debugging flows. (4) Mark "normal" as `(suggested)`. (5) Add "type 'change mode' at any time to switch."

---

### F-X-002 — SubAgentDispatchApprovalGate: technical infrastructure question blocks every dispatch
**Files:** `subagents/dispatch.md`  
**Evidence:** "Approve this cf-* sub-agent dispatch group? Native sub-agents are preferred for this work; inline keeps execution in this chat."  
**Root cause:** AP-HIDDEN-CONSEQUENCE + AP-AMBIGUOUS-OPTIONS. User must choose "native vs inline" without knowing what either means in practice. Options "approve-once" vs "approve-session" differ only in persistence — not stated. Gate fires on every dispatch group.  
**Impact:** Technical infrastructure decision interrupts task flow repeatedly. Users guess or accidentally hit "stop."  
**Fix:** (1) Rewrite title: "Ready to run a background task. Native = faster, isolated process. Inline = stays in this chat. [Recommended: native]." (2) Rename options: "native (this time)" / "native (always)" / "inline (this time)" / "inline (always)" / "cancel". (3) Allow workflows to declare SUB_AGENT_DISPATCH_MODE = approve-session upfront when user's message is clearly an action request.

---

### F-X-003 — AnalyzeIntentOffer / GenerateIntentOffer: opaque "most-relevant" token as option 1
**Files:** `analyze-routing-menus.md`, `generate-routing-menus.md`  
**Evidence:** Option 1 renders as `"most-relevant (suggested)"` — never shows the actual matched skill name before user confirms.  
**Root cause:** AP-HIDDEN-CONSEQUENCE. User commits to routing a skill without seeing which skill that is. Mis-routing is invisible at confirmation time.  
**Fix:** Expand option 1 to the actual resolved skill name + description before emitting: `"1 cf-coding-gen — write or update production code (suggested)"`. Add enforcement RULE: "ALWAYS expand option 1 with actual resolved skill name; never emit the token 'most-relevant' as visible text."

---

### F-X-004 — BrainstormOffer: modifier mini-language exposed to users
**Files:** `brainstorm-offer.md`  
**Evidence:** NOTES BrainstormOfferText exposes `:N`, `mode=inline`, `mode=single-agent`, `mode=fan-out`, "needs native parallelism", silent `save` precondition all in one message.  
**Root cause:** AP-OPTION-OVERLOAD + AP-HIDDEN-CONSEQUENCE. Engineering concepts ("needs native parallelism") exposed directly. `save` silently fails if writes blocked — only discovered after selection via BrainstormOfferSaveRejected.  
**Fix:** Split into two turns. Turn 1: present only `yes / no / save` (hide save when writes blocked). Turn 2 (only after yes/save): present round-cap and mode modifiers with human-readable outcome per mode. Remove "needs native parallelism" from user-facing text.

---

### F-X-005 — WriteDocsExploreGate fires unconditionally before every doc-writing run
**Files:** `write-docs-prep-gates.md`  
**Evidence:** Gate fires on every invocation with "Before writing or reviewing docs, discover task-relevant project context… — or skip?"  
**Root cause:** AP-UNEXPLAINED-ASK + AP-NO-SUGGESTED-OPTION. No auto-skip when target is clear. "cf-explore" unexplained. Delegates "is context clear?" decision entirely to user. Same pattern in `WriteDocsBrainstormGate` — two consecutive skip-gates before writing begins.  
**Fix:** Pre-condition: auto-skip when ORIGINAL_INTENT resolves to a single known file with no ambiguity (emit single-line note "Skipping context discovery — target is clear"). Gate only fires for ambiguous/cross-cutting tasks. When it fires, mark `skip` as `(suggested)` with a one-sentence explanation of what cf-explore returns. Collapse explore + brainstorm into one "prep" gate to reduce turn count.

---

### F-X-006 — ExplainE1Gates: AP#0 violation risk — E1→E2 boundary not flow-enforced
**Files:** `explain-gates.md`  
**Evidence:** RULES block: "NEVER emit portion content or inline explanation text after plan approval — ALWAYS hand control to ExplainE2Deliver… emitting all plan portions in one response from ExplainE1Gates is an AP#0 violation equivalent to skipping E2 entirely"  
**Root cause:** The guard exists only as a RULES annotation. An implementing agent reading only the DO block can legally emit all content in one turn. Boundary not structurally enforced.  
**Fix:** Add explicit `STOP_TURN` before `CONTINUE ExplainE2Deliver` so the boundary is enforced at flow-control level: "STOP_TURN; CONTINUE ExploreE2Deliver WHEN E1_GATE == plan AND the plan is approved (deliver starts in the next turn)."

---

### F-X-007 — debug-prompts.md is a pure dispatch shell with no reviewable UX surface
**Files:** `workflows/debug-prompts.md`  
**Evidence:** All 15 non-activate units have PURPOSE of the form "Load X module and route to XRun." No WHEN, no RULES, no user-visible output. All user-facing interaction is in unreviewed modules.  
**Root cause:** Zero structural UX guarantees. Any regression in modules silently breaks all debugger user interaction.  
**Fix:** Each dispatch unit should carry a RULES block stating what the user sees when it executes (e.g. "ALWAYS emit the step-gate frame before waiting for a command") and a reference to the menu/prompt shape. Alternatively consolidate dispatch shells into modules so full interaction path is readable without cross-file traversal.

---

### F-X-008 — "See loaded reference" deferred suggestions across workspace menus
**Files:** `workspace-discover.md`, `workspace-configure.md`  
**Evidence:** `RepoSelectionMenu`: "see loaded reference for the suggested default"; `StorageModeMenu`: "see loaded reference; inline is unavailable with Git URL sources"; `SourceConfirmMenu`: "fields + suggested defaults in the loaded reference."  
**Root cause:** Three decision points defer the recommended option to a file the user cannot see. System has the information and withholds it at the exact moment of decision.  
**Fix:** Emit the suggested selection and reason inline: "Suggested: all 3 repos (adapters detected in each)." Remove all "see loaded reference" deferrals. Preemptively remove unavailable options (e.g. inline when Git URL sources selected) rather than showing then rejecting.

---

## MAJOR Findings (44)

### Pattern A — Over-confirmation / unconditional gates

**F-X-009** `subagents/dispatch.md` — SubAgentDispatch stops on every dispatch group even for read-only operations; no intent-based auto-approve. Fix: allow workflows to declare `SUB_AGENT_DISPATCH_MODE = approve-session` upfront for action-intent requests.

**F-X-010** `write-docs-prep-gates.md`, `write-skills-prep-gates.md` — Two consecutive "skip by default" gates (explore + brainstorm) before writing begins. Fix: collapse to one "prep" gate; auto-skip when target is clear.

**F-X-011** `gates/workflow-prep.md` — `WorkflowPrepExploreRepeatGate` stops to confirm "skip/reuse" when context already matches. Fix: auto-continue with single-line status note; gate only when stale-context evidence exists.

**F-X-012** `gates/plan-first.md` — `PlanFirstConfirm` has no `stop` option, no suggested option conditional on task scope, "no-plan = start immediately" consequence hidden. Fix: add `3 stop`; mark suggested based on task complexity; add "Choosing no-plan will start the task immediately."

**F-X-013** `review/semantic-loop-skeleton.md` — `ReviewGranularityMenu` uses internal terms ("per-methodology", "per-layer") as user-facing labels. Fix: rename to "quick / standard / thorough"; embed explanation in menu title, not deferred to RULE.

**F-X-014** `workflows/map.md` — cf-map triggers `CompanionSkillOffer` before map scope is captured. Fix: gate CompanionSkillOffer after MapIntentRouter resolves scope.

**F-X-015** `explain-gates.md` — Four mandatory sequential turns (mode → disposition → audience → plan) with no multi-gate fast path; no back option for wrong answers. Fix: parse multi-gate replies in one pass; only prompt for unresolved gates.

**F-X-016** `workflows/workspace.md` — "intent router first, not menu-first wizard" declared but full sequential wizard loaded with no fast-path for fully-specified intents. Fix: add fast-path decision unit that skips wizard when ORIGINAL_INTENT names complete inputs.

---

### Pattern B — AP-UNEXPLAINED-ASK at key prompt boundaries

**F-X-017** `write-skills-review-targets.md` — Asks for "declared content slice(s)" with no explanation. Fix: remove jargon; "reply with file path(s), e.g. `.bootstrap/.core/workflows/prompting-gen.md`; full file is default."

**F-X-018** `write-skills-intent-routing.md` — Intent capture exposes internal "before cf-explore or brainstorm" reasoning. Fix: replace with example-grounded prompt.

**F-X-019** `analyze-routing-menus.md`, `generate-routing-menus.md` — Describe-intent prompts give no examples or specificity guidance. Fix: add one-line example ("e.g. 'review PDSL compliance of all workflow files'").

**F-X-020** `brainstorm-offer.md` — `BrainstormTopicCapture` has no examples; retry strips all context. Fix: add example topic + mirror examples on retry.

**F-X-021** `explain-intent-explore.md` — `ExplainIntentCapture` has no cancel escape, no preview of what cf-explain produces. Fix: add `cancel` escape; add one-sentence preview.

**F-X-022** `write-docs-author-dispatch.md` — `WriteDocsAuthorTargetMissing` is a bare dead-end EMIT with no example or recovery. Fix: provide path format example + offer cf-documenting-planning as numbered option.

**F-X-023** `write-docs-review-setup.md` — "declared content slices" jargon in dead-end EMIT. Fix: replace with plain-language + example; add back/escape.

---

### Pattern C — AP-HIDDEN-CONSEQUENCE at decision points

**F-X-024** `routing/companion-skills.md` — `CompanionSkillOffer` option 1 returns a "launch list" and STOP_TURNs; consequence (session ends, run manually) not stated; "host/user" jargon visible; companions not named in menu. Fix: name the actual companion workflows in option 1 label; replace "launch list" with user-facing outcome; explain what happens next.

**F-X-025** `review/fix-approval.md` — `ReviewFindingsNavigation` option "8 none" permanently exits fix path; labeled ambiguously. Fix: rename to "skip fixes (exit without fixing)"; add consequence description; or move to fix-scope menu only.

**F-X-026** `workflows/brave-new-world.md` — No disclosure at activation of what is autonomous vs still gated; decision log never surfaced on disable. Fix: emit activation summary listing allowed/excluded decision categories; on disable emit log summary if non-empty.

**F-X-027** `workflows/git-commit.md` — No preview-and-confirm gate before actual commit write; trailers applied silently. Fix: EMIT planned commit message + trailers + scope; WAIT confirmation before committing.

**F-X-028** `workflows/debug-prompts.md` — Enabling debugger also modifies commit routing and treats loaded skills as debug targets — neither disclosed. Fix: DebugSessionConsoleOpen emits one sentence per active constraint.

**F-X-029** `plan-assess-decompose.md` — `DecompositionConfirmMenu` `no` path terminates session; no in-session boundary edit path. Fix: add `3 revise` option that loops back into decomposition with user-described changes.

**F-X-030** `brainstorm-wrap.md` — `WrapMenu` disk option shown when writes blocked; silently fails. Fix: conditionally hide disk option or emit pre-check failure with re-menu.

**F-X-031** `workflows/help.md` — cf-help silently presets and invokes cf-explain with no transition preview or opt-out. Fix: emit one-sentence preview + implicit opt-out before INVOKE.

**F-X-032** `kit-entry-router.md` — User supplies target folder → immediately hits CompanionSkillOffer before preflight. Fix: move CompanionSkillOffer to after first substantive output.

---

### Pattern D — AP-NO-SUGGESTED-OPTION

**F-X-033** `analyze-routing-menus.md`, `generate-routing-menus.md` — `AnalyzeLoadOffer` / `GenerateLoadOffer` no suggested option when user has no intent; describe-intent should be marked suggested. Fix: RULE: "ALWAYS mark describe-intent as (suggested) when ORIGINAL_INTENT == unset."

**F-X-034** `plan-discovery.md` — `PlanExploreBrainstormGate` heuristic in prose, no (suggested) derived from ORIGINAL_INTENT. Fix: infer suggestion from ORIGINAL_INTENT; mark in menu.

**F-X-035** `planning-runtime.md` — `PlanSaveGateMenu` save is safer but not marked suggested. Fix: mark option 1 `(suggested)`; add one-sentence why.

**F-X-036** `gates/plan-first.md` — `PlanStorageChoice` disk/memory suggestion lives in RULES only, not reflected in rendered options. Fix: dynamically annotate `(suggested)` based on plan complexity.

**F-X-037** `explain-intent-explore.md` — `ExplainExploreMenu` passive prose heuristic; no (suggested) derived from EXPLAIN_TARGET. Fix: apply heuristic to resolved target; mark suggested option.

**F-X-038** `gates/workflow-prep.md` — `WorkflowPrepExploreRepeatMenu` shows stored task key in RULE but not in MENU title. Fix: inject RESOURCE_CONTEXT_TASK_KEY + provenance into menu title text.

---

### Pattern E — Dead ends without recovery

**F-X-039** `review/fix-approval.md` — `ReviewFixPartialIdsPrompt`: bare "reply with finding IDs", no format, no browser escape, retry repeats same message. Fix: emit available IDs with format example; add `back` → browser escape; update retry with mini-menu (retry / table / back).

**F-X-040** `brainstorm-offer-outcomes.md` — `BrainstormOfferCancelled` terminal with no onward path despite ORIGINAL_INTENT being live. Fix: offer 2–3 context-grounded next steps using ORIGINAL_INTENT.

**F-X-041** `workflows/planning.md` — `PlanningBlocked` delegates to BlockedReportContract but has no interactive recovery menu. Fix: after BlockedReportContract, emit numbered recovery menu from suggested_next_skills + explicit WAIT.

**F-X-042** `workflows/git-commit.md` — `GitCommitBlocked` when paths unset: no prompt to supply missing paths. Fix: emit "Which files should be committed?" and loop back to GitCommitResolve on reply.

**F-X-043** `workflows/git-commit.md` — `GitCommitFailed`: `suggested_next_skills = []` hardcoded; NextActionsOffer not called. Fix: derive suggested_next_skills from failure reason; call NextActionsOffer.

**F-X-044** `write-docs-write-policy-fix.md` — `WriteDocsReviewFixOutcome` when no fixes applied: STOP_TURN without NextActionsOffer. Fix: run NextActionsOffer; mark cf-documenting-fix as (suggested).

**F-X-045** `workflows/coding-fix.md`, `workflows/prompting-fix.md` — Invoked without prior review findings: RULES says required but no early gate; silent failure. Fix: add PrerequisiteCheckContract or explicit EMIT + STOP_TURN with suggested_producers.

---

### Pattern F — AP-OPTION-OVERLOAD / ambiguous labels

**F-X-046** `review/fix-approval.md` — `ReviewFixScope` menu: no finding counts, no consequence per option, no suggested marker, "crit-major" jargon. Fix: inject live counts; rename to plain language; mark (suggested) based on severity distribution; add one-line why per option.

**F-X-047** `review/fix-approval.md` — `ReviewFindingsNavigation` 8 options, ungrouped, no clearly-labeled exit. Fix: group into Navigation / View / Selection / Continue sections; add explicit `exit` option.

**F-X-048** `analyze-routing-menus.md`, `generate-routing-menus.md` — `"other"` option label opaque. Fix: rename to "browse all [analyze/generate] workflows."

**F-X-049** `kit-legacy-preview-menus.md` — `KitInitLegacyApprovalMenu` edit branch: raw command-syntax dump with no context, no `done` escape. Fix: guided multi-step edit flow with examples; emit updated preview; return to approval menu.

**F-X-050** `workspace-next-dispatch.md` — `WorkspaceNextStepsMenu` options 3 and 4 are functionally identical open-ended prompts. Fix: collapse to one "other (describe what you want)" entry; replace option 4 with concrete action from workspace state.

**F-X-051** `runtime/blocked-next-actions.md` — `BlockedNextActionsMenu`: suggested-skill expander renders unnumbered entries; no (suggested) marker. Fix: each suggested_next_skills entry gets own integer; first entry marked (suggested).

**F-X-052** `kit-thin-domain-routing.md` — `KitThinRouteBlocked`: 4–6 skill names emitted flat. Fix: single primary recommendation per block domain + one-line description.

---

## MINOR Findings (34)

### Silent alias redirects (no disclosure before CONTINUE)
- **F-X-053** `write-skills.md` → `prompting-gen` — add "Note: write-skills is now an alias for prompting-gen."
- **F-X-054** `testing.md` → `coding-tests` — add one-line transparency disclosure
- **F-X-055** `skills-ci.md` → `prompting-ci`
- **F-X-056** `docs-ci.md` / `docs-planning.md` / `docs-review.md` → documenting-* equivalents

### NextActionsMenu numbering conflict (F-X-057)
`ui/next-actions.md` — OPTIONS block hardcodes "2 back / 3 done" conflicting with 3–5 synthesized items. Fix: replace with `N+1 back` / `N+2 done` relative positions, or anchor back/done explicitly as final two entries.

### CompanionSkillRouting unnamed menu (F-X-058)
`routing/companion-skills.md` — unnamed MENU, no INVALID handler, no cancel. Fix: define named MENU schema aligned with CompanionSkillOfferMenu.

### DebugLocators no fallback format (F-X-059)
`debug-prompts-locators.md` — no fallback when line resolution fails. Fix: add RULES: "ALWAYS emit '(line unknown)' with warning when real line resolution fails."

### BraveNewWorld narrow trigger surface (F-X-060)
`workflows/brave-new-world.md` — "stop asking me", "auto mode" won't match. Fix: resolve semantically equivalent phrases as BNW activation.

### StudioShutdown "content and rules" jargon (F-X-061)
`session/shutdown.md` — no "tell me more" option. Fix: add option 3 "what will be forgotten?" + plain-language description of loaded assets.

### KitExistingManifestMenu no edit path (F-X-062)
`kit-existing-manifest.md` — only validate/cancel. Fix: add option 3 "edit — open existing manifest for review and edit."

### KitLegacyApproval "show-preview" redundant (F-X-063)
`kit-legacy-preview-menus.md` — option 2 re-shows already-visible content; option 1 label ambiguous. Fix: rename to "approve — write the manifest shown above" / "re-show manifest."

### KitPreviewFailureMenu non-specific error (F-X-064)
`kit-legacy-preview-menus.md` — identical menu for parse error vs validation failure. Fix: differentiate by PREVIEW_STATUS; show source file path; split retry behaviour.

### KitPlanningPreset undisclosed 5-step lifecycle (F-X-065)
`workflows/kit-planning.md` — mandatory authoring/CI/review/git/close per phase not disclosed before plan approval. Fix: surface lifecycle before plan approval; allow opt-out for lightweight iterations.

### CodingGenPrerequisites identical override summaries (F-X-066)
`workflows/coding-gen.md` — four override_summary strings are identical boilerplate. Fix: differentiate to communicate differential risk per artifact.

### coding-ci missing SimpleModeGate (F-X-067)
`workflows/coding-ci.md` — inconsistent bootstrap vs sibling workflows. Fix: audit and align or document deliberate omission.

### CodingReviewFixGate double NextActionsOffer (F-X-068)
`workflows/coding-review.md` — NextActionsOffer called twice; zero-findings path silent. Fix: explicit branch for 0 findings with "review passed cleanly" message.

### REVIEW_LOOP_REQUESTED dead state variable (F-X-069)
`workflows/kit-gen.md`, `kit-review.md`, `kit-fix.md` — declared but never consumed. Fix: implement review-loop logic or remove variable and document.

### BrainstormWrap WrapMenu spec/NOTES conflict (F-X-070)
`brainstorm-wrap.md` — OPTIONS block numbering conflicts with NOTES rendering order. Fix: canonical ordered rendering spec; routes enumerated 4..N after fixed header.

### cf-plan vs cf-planning disambiguation (F-X-071)
`workflows/plan.md` — difference never explained to user. Fix: single-sentence disambiguation at start of plan work.

### coding-tests ORIGINAL_INTENT silent overwrite (F-X-072)
`workflows/coding-tests.md` — ORIGINAL_INTENT normalised before blocked reports; shows generic string. Fix: preserve verbatim intent; use separate TESTS_SCOPE preset.

### coding-gen hardcoded empty suggested_next_skills (F-X-073)
`workflows/coding-gen.md` — `CodingValidate` emits `suggested_next_skills = []`. Fix: derive from context; default to [cf-coding-ci, cf-coding-review].

### documenting-ci generic next actions on failure (F-X-074)
`workflows/documenting-ci.md` — no structured failure categories passed to NextActionsOffer. Fix: SET GATE_FAILURE_CATEGORIES before NextActionsOffer.

### blocked-report no primary_suggested_producer rule (F-X-075)
`runtime/blocked-report.md` — no rule for single top-level recommendation when multiple artifacts missing. Fix: add RULE to derive primary_suggested_producer that resolves most artifacts in one step.

### Additional MINOR (F-X-076–086)
- `kit-ci.md` — next-actions module loaded but never invoked (dead load)
- `git-commit.md` — trailer application never disclosed to user before commit
- `workflows/auto-config.md` — RETURN on methodology-not-found may not surface as readable text; add explicit EMIT before STOP_TURN
- `workflows/explore.md` — no orientation message before ExploreEntry; silent transition
- `debug-prompts-breakpoint-match.md` — breakpoint type/syntax documented only in NOTES, never surfaced in user-facing UI
- `brainstorm-wrap.md` WrapMenu — `disk` silently fails when writes blocked (no pre-check)
- `brainstorm-panel-render.md` — PanelEditMenu title says "edit one thing" but 4 operations available
- `workflows/planning.md` `PlanningCompletion` — cf-explain candidate dilutes execution suggestion in NextActionsOffer
- `workflows/coding-fix.md` `CodingValidate` — freeform prose instead of structured SKILL_RESULT envelope
- `kit-gen.md` `REVIEW_LOOP_REQUESTED` = false default, never set to true, never consumed
- `workspace-discover.md` `ZeroResultsMenu` — no diagnostic info about what was scanned or why zero results

---

## Cross-cutting Themes (affect 3+ files)

| Theme | Affected files | Findings |
|---|---|---|
| SimpleModeGate fires first, unconditionally | All non-exempt workflows | F-X-001 |
| SubAgentDispatch approval friction | All sub-agent workflows | F-X-002, F-X-009 |
| Unconditional explore+brainstorm prep gates | docs, skills, kit, planning | F-X-005, F-X-010 |
| "See loaded reference" deferred suggestions | workspace menus | F-X-008 |
| Dead ends without recovery/NextActionsOffer | 7 flows | F-X-039–045 |
| CompanionSkillOffer hidden consequence + jargon | analyze, generate, brainstorm, map, kit | F-X-024 |
| ReviewFixPartialIdsPrompt bare ask | coding, skills, documenting | F-X-039 |
| NextActionsMenu numbering conflict | every workflow using next-actions | F-X-057 |
| Silent alias redirects | write-skills, testing, skills-ci, docs-* | F-X-053–056 |
| AP-NO-SUGGESTED-OPTION in decision menus | 6 menus across planning/explain/analyze | F-X-033–038 |

---

## Recommended Fix Priority

### Tier 1 — Highest impact, cross-cutting (fix once, benefits all workflows)
1. **F-X-001** SimpleModeGate — default to normal, skip or defer gate
2. **F-X-002/009** SubAgentDispatch — rewrite title/labels; allow intent-based auto-approve
3. **F-X-003** AnalyzeIntentOffer/GenerateIntentOffer — expand option 1 to actual skill name
4. **F-X-057** NextActionsMenu numbering — fix N+1/N+2 positioning
5. **F-X-024** CompanionSkillOffer — name companions, explain session-stop consequence
6. **F-X-039** ReviewFixPartialIdsPrompt — format + browser escape + mini-menu retry

### Tier 2 — High impact, per-workflow
7. **F-X-004** BrainstormOffer mini-language — split into two turns
8. **F-X-005/010** Unconditional prep gates — auto-skip + collapse
9. **F-X-006** ExplainE1Gates AP#0 boundary — add STOP_TURN
10. **F-X-008** Workspace "see loaded reference" — emit suggestions inline
11. **F-X-046** ReviewFixScope menu — inject counts + rename options
12. **F-X-027** GitCommit no preview — add confirm gate

### Tier 3 — Medium impact
13. **F-X-015** ExplainE1Gates interrupt density — multi-gate fast path
14. **F-X-029** DecompositionConfirmMenu — add `3 revise` option
15. **F-X-040/041** Dead ends (brainstorm cancel, planning blocked)
16. **F-X-049** Kit legacy edit syntax — guided flow with `done` escape
17. **F-X-016** Workspace intent-router fast path

---

*Generated by cf-prompting-review, branch reorg-core-skills, 2026-06-26*
