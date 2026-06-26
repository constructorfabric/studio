# UX Fix Plan — All Workflow Findings (branch: reorg-core-skills)

**Date:** 2026-06-26
**Branch:** reorg-core-skills
**Source:** UX review `.bootstrap/.cache/reviews/ux-review-reorg-core-skills-2026-06-26.md`
**Total findings:** 86 (8 CRITICAL / 44 MAJOR / 34 MINOR)
**Skill:** cf-prompting-planning → cf-planning
**Domain:** skills

---

## Phase-DoD (all phases)

| Requirement | Detail |
|---|---|
| authoring | All scoped files edited per checklist; no out-of-scope edits |
| deterministic-validation | `cf-prompting-ci` passes on all changed files; zero new errors |
| semantic-review | `cf-prompting-review` run; no new CRITICAL/MAJOR findings introduced |
| git | `commit-intent` prepared; preflight satisfied; message references finding IDs |
| phase-close | Phase status marked; checklist items checked; findings resolved count updated |

---

## Phase 1 — Cross-cutting shared modules

**Status:** pending

**goal:** Fix the 5 shared modules whose UX problems affect every workflow. Highest-leverage
changes — fixing once resolves findings across all 47 workflows simultaneously.

**prerequisites:**
- UX review report (available)
- Read current state of each target file before editing

**target files:**
- `skills/studio/modules/gates/simple-mode.md`
- `skills/studio/modules/subagents/dispatch.md`
- `skills/studio/modules/ui/next-actions.md`
- `skills/studio/modules/routing/companion-skills.md`
- `skills/studio/modules/review/fix-approval.md`

**findings addressed:** F-X-001, F-X-002, F-X-009, F-X-024, F-X-025, F-X-039, F-X-046, F-X-047, F-X-057
(3 CRITICAL, 6 MAJOR)

**skill_sequence:** cf-prompting-fix → cf-prompting-ci → cf-prompting-review

**checklist:**
- [ ] `simple-mode.md`: default to normal; skip gate when SIMPLE_MODE already set; remove debug from non-debug flows; mark "normal" `(suggested)`; add "type 'change mode' to switch" note
- [ ] `subagents/dispatch.md`: rewrite `SubAgentApprovalRequest` title to plain language; rename options to "native (this time) / native (always) / inline (this time) / inline (always) / cancel"; allow workflows to declare `approve-session` upfront for action intents
- [ ] `ui/next-actions.md`: fix back/done numbering to N+1/N+2; resolve `back` destination before emitting; suppress cf-explain suggestion when planning artifacts produced
- [ ] `routing/companion-skills.md`: name actual companion workflows in option 1 label; replace "launch list" / "host/user" jargon with user-facing language; make STOP_TURN consequence explicit
- [ ] `review/fix-approval.md`: `ReviewFixPartialIdsPrompt` — emit available IDs + format + `back`→browser; retry mini-menu; `ReviewFixScope` — inject live counts + plain language + `(suggested)` + one-line why per option; `ReviewFindingsNavigation` — group options, add explicit `exit` label

**expected_outputs:** skill-changes (5 files), deterministic-report, review-findings, commit-intent, phase-status

**completion_signal:** All checklist items done; CI passes; review findings ≤ MINOR; commit-intent prepared

---

## Phase 2 — Router menus + analyze/generate routing

**Status:** pending
**depends_on:** Phase 1

**goal:** Fix analyze/generate routing menus: opaque "most-relevant" token, unexplained
describe-intent prompts, "other" label, redundant double-LOAD, load-offer with no suggested option.

**prerequisites:**
- Phase 1 complete (companion-skills.md fixed)

**target files:**
- `skills/studio/modules/analyze-routing-menus.md`
- `skills/studio/modules/generate-routing-menus.md`
- `skills/studio/modules/analyze-skill-fallbacks.md`
- `skills/studio/modules/generate-skill-fallbacks.md`
- `workflows/analyze.md` (double-LOAD collapse)
- `workflows/generate.md` (double-LOAD collapse)

**findings addressed:** F-X-003, F-X-019, F-X-033, F-X-048, F-ROU-012, F-ROU-013
(2 CRITICAL, 4 MAJOR/MINOR)

**skill_sequence:** cf-prompting-fix → cf-prompting-ci → cf-prompting-review

**checklist:**
- [ ] Expand option 1 in `AnalyzeIntentOffer` / `GenerateIntentOffer` to actual resolved skill name + description; add enforcement RULE
- [ ] Add one-line example to `AnalyzeDescribeIntent` / `GenerateDescribeIntent` prompts
- [ ] Mark `describe-intent` as `(suggested)` in `AnalyzeLoadOffer` / `GenerateLoadOffer` when ORIGINAL_INTENT == unset
- [ ] Rename `"other"` option to `"browse all [analyze/generate] workflows"`
- [ ] Collapse double-LOAD of routing-menus into single LOAD + two conditional CONTINUEs in `analyze.md` and `generate.md`

**expected_outputs:** skill-changes (6 files), deterministic-report, review-findings, commit-intent, phase-status

**completion_signal:** All checklist items done; CI passes; no CRITICAL/MAJOR findings remain for these files

---

## Phase 3 — Gate modules + prep gates + workspace menus

**Status:** pending
**depends_on:** Phase 1

**goal:** Fix unconditional prep gates (explore + brainstorm), plan-first gate, workflow-prep
repeat gate, and workspace menus that defer to "see loaded reference."

**prerequisites:**
- Phase 1 complete

**target files:**
- `skills/studio/modules/write-docs-prep-gates.md`
- `skills/studio/modules/write-skills-prep-gates.md`
- `skills/studio/modules/gates/plan-first.md`
- `skills/studio/modules/gates/workflow-prep.md`
- `skills/studio/modules/workspace-discover.md`
- `skills/studio/modules/workspace-configure.md`
- `skills/studio/modules/workspace-next-dispatch.md`

**findings addressed:** F-X-005, F-X-008, F-X-010, F-X-011, F-X-012, F-X-016, F-X-034, F-X-036, F-X-038, F-X-050
(1 CRITICAL, 9 MAJOR/MINOR)

**skill_sequence:** cf-prompting-fix → cf-prompting-ci → cf-prompting-review

**checklist:**
- [ ] `write-docs-prep-gates.md` + `write-skills-prep-gates.md`: auto-skip when target is clear; collapse explore + brainstorm into one "prep" gate; mark `skip` `(suggested)` for clear targets; explain what cf-explore returns
- [ ] `gates/plan-first.md`: add `3 stop`; suggested option conditional on task scope; "Choosing no-plan will start the task immediately"; `PlanStorageChoice` dynamic `(suggested)` based on plan complexity
- [ ] `gates/workflow-prep.md`: auto-continue when RESOURCE_CONTEXT matches task key; inject RESOURCE_CONTEXT_TASK_KEY + provenance into menu title
- [ ] `workspace-discover.md`: emit suggested selection inline; remove "see loaded reference"; pre-remove unavailable options
- [ ] `workspace-configure.md`: one-line description of `cross_repo` / `resolve_remote_ids`; "primary source is always cwd" note before confirm
- [ ] `workspace-next-dispatch.md`: collapse options 3/4; mark option 1 `(suggested)` inline

**expected_outputs:** skill-changes (7 files), deterministic-report, review-findings, commit-intent, phase-status

**completion_signal:** All checklist items done; CI passes; no CRITICAL/MAJOR findings remain for these files

---

## Phase 4 — Planning / brainstorm / explain flows

**Status:** pending
**depends_on:** Phase 1

**goal:** Fix BrainstormOffer mini-language, dead-end cancelled paths, ExplainE1Gates interrupt
density and AP#0 boundary risk, DecompositionConfirmMenu no-path dead end, PlanningBlocked
without recovery menu.

**prerequisites:**
- Phase 1 complete (companion-skills.md, next-actions.md fixed)

**target files:**
- `skills/studio/modules/brainstorm-offer.md`
- `skills/studio/modules/brainstorm-offer-outcomes.md`
- `skills/studio/modules/brainstorm-wrap.md`
- `skills/studio/modules/brainstorm-panel-render.md`
- `skills/studio/modules/plan-assess-decompose.md`
- `skills/studio/modules/plan-discovery.md`
- `skills/studio/modules/planning-runtime.md`
- `skills/studio/modules/explain-gates.md`
- `skills/studio/modules/explain-intent-explore.md`
- `workflows/planning.md`

**findings addressed:** F-X-004, F-X-006, F-X-015, F-X-020, F-X-021, F-X-029, F-X-030, F-X-034, F-X-035, F-X-040, F-X-041
(2 CRITICAL, 9 MAJOR/MINOR)

**skill_sequence:** cf-prompting-fix → cf-prompting-ci → cf-prompting-review

**checklist:**
- [ ] `brainstorm-offer.md`: split into two turns (yes/no/save first; modifiers second); hide `save` when writes blocked; remove "needs native parallelism" from user text; add example topic to `BrainstormTopicCapture` + mirror on retry
- [ ] `brainstorm-offer-outcomes.md`: `BrainstormOfferCancelled` — add 2–3 context-grounded next steps from ORIGINAL_INTENT
- [ ] `brainstorm-wrap.md`: `WrapMenu` disk option — pre-check writes before rendering; fix spec/NOTES ordering conflict
- [ ] `brainstorm-panel-render.md`: `PanelEditMenu` — remove "one thing" wording
- [ ] `plan-assess-decompose.md`: `DecompositionConfirmMenu` — add `3 revise` option with loop back
- [ ] `plan-discovery.md`: `PlanExploreBrainstormGate` — infer suggested option from ORIGINAL_INTENT; mark dynamically
- [ ] `planning-runtime.md`: `PlanSaveGateMenu` — mark option 1 `(suggested)` with why
- [ ] `explain-gates.md`: add explicit STOP_TURN before `CONTINUE ExplainE2Deliver`; add multi-gate fast-path parsing
- [ ] `explain-intent-explore.md`: add `cancel` escape; add one-sentence preview; mark `(suggested)` dynamically in `ExplainExploreMenu`
- [ ] `workflows/planning.md`: `PlanningBlocked` — numbered recovery menu + WAIT; `PlanningCompletion` — suppress cf-explain for planning artifacts

**expected_outputs:** skill-changes (10 files), deterministic-report, review-findings, commit-intent, phase-status

**completion_signal:** All checklist items done; CI passes; no CRITICAL/MAJOR findings remain for these files

---

## Phase 5 — Coding / documenting / skills workflows + dead ends

**Status:** pending
**depends_on:** Phase 1

**goal:** Fix dead-end states in coding/documenting/prompting workflows, missing prerequisite
gates in `-fix` workflows, hardcoded empty `suggested_next_skills`, silent intent overwrite,
review-fix-outcome without NextActionsOffer.

**prerequisites:**
- Phase 1 complete (fix-approval.md, next-actions.md, blocked-next-actions.md fixed)

**target files:**
- `workflows/coding-fix.md`
- `workflows/coding-gen.md`
- `workflows/coding-review.md`
- `workflows/coding-tests.md`
- `workflows/prompting-fix.md`
- `workflows/documenting-fix.md`
- `skills/studio/modules/write-docs-write-policy-fix.md`
- `skills/studio/modules/write-docs-author-dispatch.md`
- `skills/studio/modules/write-docs-review-setup.md`
- `skills/studio/modules/runtime/blocked-report.md`
- `skills/studio/modules/runtime/blocked-next-actions.md`

**findings addressed:** F-X-022, F-X-023, F-X-042, F-X-043, F-X-044, F-X-045, F-X-051, F-X-066, F-X-068, F-X-072, F-X-073, F-X-075
(12 MAJOR/MINOR)

**skill_sequence:** cf-prompting-fix → cf-prompting-ci → cf-prompting-review

**checklist:**
- [ ] `coding-fix.md` + `prompting-fix.md` + `documenting-fix.md`: early gate — check REVIEW_FINDINGS_REMAINING > 0; emit "run *-review first" + STOP_TURN + suggested_producers when missing
- [ ] `coding-gen.md`: `CodingValidate` — derive `suggested_next_skills` from context; differentiate `override_summary` per artifact
- [ ] `coding-review.md`: explicit branch for 0 findings with "review passed cleanly"; remove double NextActionsOffer call
- [ ] `coding-tests.md`: preserve verbatim ORIGINAL_INTENT; use separate TESTS_SCOPE preset
- [ ] `write-docs-write-policy-fix.md`: `WriteDocsReviewFixOutcome` — run NextActionsOffer before STOP_TURN; mark cf-documenting-fix `(suggested)`
- [ ] `write-docs-author-dispatch.md`: add path format example + cf-documenting-planning as numbered option
- [ ] `write-docs-review-setup.md`: remove "declared content slices" jargon; plain-language + example + back/escape
- [ ] `runtime/blocked-report.md`: add RULE for `primary_suggested_producer` derivation
- [ ] `runtime/blocked-next-actions.md`: fix expanded entry numbering; mark first entry `(suggested)`

**expected_outputs:** skill-changes (11 files), deterministic-report, review-findings, commit-intent, phase-status

**completion_signal:** All checklist items done; CI passes; no CRITICAL/MAJOR findings remain for these files

---

## Phase 6 — Git / debug / BNW / navigation workflows

**Status:** pending
**depends_on:** Phase 1

**goal:** Fix git-commit hidden consequence (no preview before write, blocked dead end, empty
failure next-actions), debug-prompts undisclosed side-effects, brave-new-world undisclosed
autonomy, cf-help silent handoff, cf-map premature CompanionSkillOffer.

**prerequisites:**
- Phase 1 complete

**target files:**
- `workflows/git-commit.md`
- `workflows/brave-new-world.md`
- `workflows/debug-prompts.md`
- `workflows/help.md`
- `workflows/map.md`
- `skills/studio/modules/session/shutdown.md`

**findings addressed:** F-X-007 (partial), F-X-014, F-X-026, F-X-027, F-X-028, F-X-031, F-X-042, F-X-043, F-X-060, F-X-061
(1 CRITICAL, 9 MAJOR/MINOR)

**skill_sequence:** cf-prompting-fix → cf-prompting-ci → cf-prompting-review

**checklist:**
- [ ] `git-commit.md`: `GitCommitExecute` — EMIT planned message + trailers + scope; WAIT confirmation; `GitCommitBlocked` — prompt for missing paths + loop back; `GitCommitFailed` — derive `suggested_next_skills`; call NextActionsOffer
- [ ] `brave-new-world.md`: emit activation summary (allowed / excluded); on disable emit log summary if non-empty; resolve equivalent trigger phrases
- [ ] `debug-prompts.md`: `DebugSessionConsoleOpen` — EMIT one sentence per active constraint (commit routing, debug-target behavior)
- [ ] `workflows/help.md`: emit one-sentence preview + opt-out before invoking cf-explain
- [ ] `workflows/map.md`: move CompanionSkillOffer to after MapIntentRouter resolves scope
- [ ] `session/shutdown.md`: add option 3 "what will be forgotten?"; replace "content and rules" with plain-language asset list

**expected_outputs:** skill-changes (6 files), deterministic-report, review-findings, commit-intent, phase-status

**completion_signal:** All checklist items done; CI passes; no CRITICAL/MAJOR findings remain for these files

---

## Phase 7 — Kit family + minor + alias redirects

**Status:** pending
**depends_on:** Phases 1–6 complete

**goal:** Fix kit workflow UX issues, kit-gen dead state variable, kit-planning undisclosed
lifecycle. Fix all silent alias redirects and remaining MINOR findings.

**prerequisites:**
- Phases 1–6 complete

**target files:**
- `skills/studio/modules/kit-entry-router.md`
- `skills/studio/modules/kit-existing-manifest.md`
- `skills/studio/modules/kit-legacy-preview-menus.md`
- `skills/studio/modules/kit-thin-domain-routing.md`
- `workflows/kit-gen.md`
- `workflows/kit-planning.md`
- `workflows/write-skills.md`
- `workflows/testing.md`
- `workflows/skills-ci.md`
- `workflows/skills-review.md`
- `workflows/docs-ci.md`
- `workflows/docs-planning.md`
- `workflows/docs-review.md`
- `skills/studio/modules/routing/companion-skills.md` (CompanionSkillRouting unnamed menu)
- `skills/studio/modules/debug-prompts-locators.md`
- `workflows/auto-config.md`
- `workflows/explore.md`
- `workflows/coding-ci.md`

**findings addressed:** F-X-032, F-X-049, F-X-052, F-X-053–056, F-X-058–075, F-X-076–086
(~35 MINOR + 5 MAJOR)

**skill_sequence:** cf-prompting-fix → cf-prompting-ci → cf-prompting-review

**checklist:**
- [ ] `kit-entry-router.md`: move CompanionSkillOffer after preflight
- [ ] `kit-existing-manifest.md`: add edit option
- [ ] `kit-legacy-preview-menus.md`: guided edit flow with `done` escape; rename approve/show-preview; differentiate failure menu by PREVIEW_STATUS
- [ ] `kit-thin-domain-routing.md`: single recommended next step per block domain + one-line description
- [ ] `kit-gen.md`: remove or implement `REVIEW_LOOP_REQUESTED`
- [ ] `kit-planning.md`: disclose 5-step phase lifecycle before plan approval; allow opt-out for lightweight iterations
- [ ] Alias redirects: add one-line EMIT before CONTINUE in write-skills, testing, skills-ci, skills-review, docs-ci, docs-planning, docs-review
- [ ] `routing/companion-skills.md` `CompanionSkillRouting`: define named MENU with INVALID handler + cancel
- [ ] `debug-prompts-locators.md`: add `(line unknown)` fallback RULE
- [ ] `workflows/auto-config.md`: add explicit EMIT before STOP_TURN on methodology-not-found
- [ ] `workflows/explore.md`: add orientation EMIT before ExploreEntry
- [ ] `workflows/coding-ci.md`: audit/align SimpleModeGate; document deliberate omission
- [ ] Remaining MINOR: brainstorm-panel-render PanelEditMenu title; plan.md disambiguation note; planning.md cf-explain suppression; documenting-ci GATE_FAILURE_CATEGORIES; write-docs-review-setup final polish

**expected_outputs:** skill-changes (18+ files), deterministic-report, review-findings, commit-intent, phase-status

**completion_signal:** All checklist items done; CI passes; review findings ≤ MINOR cosmetic; all 86 original findings resolved or deferred with rationale; commit-intent prepared

---

## Execution notes

- Phases 2–6 are independent of each other and can run in parallel (they share no target files)
- Phase 1 must complete first (shared modules depended on by all other phases)
- Phase 7 depends on all prior phases to avoid re-introducing fixed patterns
- Use `cf-prompting-fix` for all authoring; `cf-prompting-ci` for validation; `cf-prompting-review` for semantic review
- Each phase commit should reference the finding IDs it resolves

---

*Generated by cf-prompting-planning, branch reorg-core-skills, 2026-06-26*
