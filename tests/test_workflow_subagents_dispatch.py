"""Round-trip dispatch fixtures for the sub-agents that the Constructor Studio
workflows dispatch, plus structural checks that the post-refactor architecture
(thin routers + single-file workflows + consolidated studio skill) wires those
sub-agents correctly.

The "Removed legacy multi-phase workflows and updated routing" refactor retired
the entire `workflows/generate/phase-*`, `workflows/analyze/phase-*`,
`workflows/shared/*`, `skills/studio/protocol.md`, `skills/studio/routing.md`,
and `skills/studio/sub-agent-dispatch.md` tree. `workflows/generate.md` and
`workflows/analyze.md` are now thin routers; `workflows/coding.md` (and the
other `workflows/<verb>.md` files) are single-file workflows; and the sub-agent
approval gate + dispatch contract now live in `skills/studio/SKILL.md`
(UNIT SubAgentDispatch). The canonical sub-agent inventory is
`skills/studio/agents.toml` with per-agent contracts under
`skills/studio/agents/<name>.md`.

All dispatch/shape fixtures here are pure shape checks — they do NOT invoke a
real LLM. The point is to lock the dispatch JSON contract + expected response
shape, plus assert the new routing/dispatch structure, so future workflow edits
cannot silently drift.

-----------------------------------------------------------------------------
Migration note (audit trail for the post-refactor rewrite of this file)
-----------------------------------------------------------------------------
REWRITTEN (re-grounded on the new architecture):
  * test_skill_requires_session_approval_before_native_subagent_dispatch —
    the session approval gate moved from the deleted
    skills/studio/sub-agent-dispatch.md to UNIT SubAgentDispatch in
    skills/studio/SKILL.md; re-grounded there.
  * test_subagent_fallback_never_defaults_from_unapproved_native_support —
    same move; now asserts the SubAgentFallbackRequest deny/inline path in
    SKILL.md instead of the deleted dispatch file.
  * test_runtime_instruction_modules_stay_compact — dropped the deleted
    phase-0-dependencies.md / remediation-handoff.md budget rows; kept the
    line budgets for files that still exist (SKILL.md, the code reviewer
    contract) and added the new router/coding workflow files.

ADDED (new coverage for the new architecture):
  * test_generate_and_analyze_are_thin_routers_forbidding_legacy_phases
  * test_coding_dispatch_names_reviewers_and_valid_coder
  * test_workflow_agent_references_resolve_and_coding_agents_registered

DELETED (retired multi-phase / removed-file structure with NO new equivalent):
  * test_review_finding_workflow_contract_regressions — pinned
    workflows/generate/error-handling.md + analyze/generate phase handoff files
    (all deleted).
  * test_external_fix_handoff_requires_subagent_dispatch_evidence — pinned
    phase-5 dispatch-evidence guards in deleted phase-5 files.
  * test_phase_5_4_reply_grammar (+ PHASE_5_4_RULES/_parse_phase_5_4_reply) —
    pure parser mirroring deleted phase-5/phase-5.4-approval.md reply table.
  * test_phase_6_combine_refusal (+ COMBINE_REFUSAL_PATTERN/_phase_6_route) —
    pure parser mirroring deleted phase-6 R+W combine-refusal contract.
  * test_phase_6_r1_routes_existing_findings_to_seeded_findings_path — deleted
    phase-6/remediation-handoff.md.
  * test_protocol_completion_invariants_match_handoff_workflows — deleted
    skills/studio/protocol.md + phase-6 handoff files.
  * test_workflow_probe_requires_subagent_approval_gate — deleted
    workflows/shared/inline-fallback-probe.md (probe folded into SKILL.md gate).
  * test_analyze_change_review_dispatches_diff_scope_resolver — deleted
    analyze/overview.md + analyze/phase-0* change-review files.
  * test_analyze_handoff_max_iter_zero_can_reach_phase_6 — deleted phase-5/6.
  * test_analyze_external_r1_fixes_carried_findings_before_fresh_review —
    deleted phase-5 index + analyze phase-4-output handoff.
  * test_max_iter_zero_preserves_analyzed_paths_for_followup_fix_loop — deleted
    phase-5/phase-6 files.
  * test_phase_6_chat_only_suppression_does_not_hide_remaining_findings —
    deleted phase-6/index.md.
  * test_protocol_references_use_existing_thin_protocol_file — asserted the now
    deleted skills/studio/protocol.md path.
  * test_prompt_bug_only_analyze_is_mutually_exclusive_prompt_branch — deleted
    analyze/phase-4-output + phase-3-semantic.
  * test_generate_prompt_review_detects_cypilot_instruction_docs — deleted
    phase-5/phase-5.2-semantic.md.
  * test_max_iter_zero_has_single_external_entry_semantics — deleted phase-5.
  * test_storytelling_route_does_not_reference_removed_trigger_file — deleted
    analyze/phase-0-dependencies.md + analyze/preamble.md.
  * test_deterministic_validator_uses_resolved_validator_command — pinned
    deleted analyze/generate phase det-gate files.
  * test_phase_6_blocks_post_write_choices_while_remediation_pending — deleted
    phase-6 handoff files.
  * test_prompt_review_partial_checkpoint_has_phase_4_output_contract — deleted
    analyze/phase-4-output files.
  * test_phase_3_to_4_checkpoint_has_canonical_reply_menu — deleted
    analyze/phase-3-to-4-checkpoint.md.
  * test_partial_checkpoint_contract_scope_matches_reviewer_support — deleted
    analyze/phase-3-semantic.md + phase-5/phase-5.2-semantic.md.
  * test_analyze_antipattern_summary_does_not_mislabel_canonical_ap005 —
    deleted analyze/rules.md.
  * test_phase_5_findings_display_is_bounded_with_full_json_payload — deleted
    phase-5/phase-5.3-findings.md.
  * test_generate_clarification_prompts_explain_why_and_suggest_default —
    deleted generate/phase-0.5-clarify.md.
  * test_analyze_methodologies_are_lazy_and_one_per_subagent — deleted
    analyze/preamble.md + phase-0-dependencies.md.
  * test_generate_author_plan_menu_supports_skip_inline_and_accept_anyway —
    deleted generate/phase-1.5/* files.
  * test_generate_phase4_cannot_skip_planned_author_dispatch — deleted
    generate/phase-4-write.md.
  * test_analyze_phase3_cannot_skip_planned_reviewer_dispatch — deleted
    analyze/phase-3-semantic.md.
  * test_subagent_dispatch_sites_have_pre_dispatch_gate — per-phase dispatch
    sites no longer exist (single gate in SKILL.md).
  * test_artifact_review_dispatch_uses_registered_example_path_shape — deleted
    analyze/phase-3-semantic.md + phase-5/phase-5.2-semantic.md.
  * test_generate_carry_forward_keeps_unapproved_judgmental_findings — deleted
    phase-5/phase-5.4-approval.md.
  * test_remediation_menus_have_one_dynamic_suggestion_slot — deleted analyze
    phase-4-output + phase-6 handoff files.
  * test_analyze_standard_output_does_not_own_prompt_templates — deleted
    analyze/phase-4-output files.
  * test_brainstorm_challenge_flow_matches_user_facing_contract — deleted
    generate/phase-0.7/* files.
  * test_brainstorm_challenge_questions_target_decision_keys — deleted
    generate/phase-0.7/round-loop.md + state-schema.md.
  * test_brainstorm_round_prompt_supports_one_by_one_answering — deleted
    generate/phase-0.7/round-loop.md.
  * test_brainstorm_post_round_custom_reply_grammar (+ rules helper) — pure
    parser mirroring deleted generate/phase-0.7/round-loop.md.
  * test_brainstorm_wrap_menu_distinguishes_session_and_disk_save — deleted
    generate/phase-0.7/wrap-handoff.md.
  * test_brainstorm_missing_topic_offers_saved_sessions_first — deleted
    generate/phase-0.5-clarify.md.
  * test_brainstorm_saved_discard_and_retention_are_explicit — deleted
    generate/phase-0.7/offer.md + wrap-handoff.md.
  * test_cf_on_uses_ambiguous_routing_menu — deleted skills/studio/routing.md.
  * test_cf_help_routes_to_prefilled_explain_preset — deleted routing.md +
    analyze/preamble.md.
  * test_explain_mode_fail_closed_against_one_shot_help_summary — deleted
    skills/studio/protocol.md + analyze/preamble.md.
  * test_empty_standalone_explore_clarifies_before_dispatch — explore.md
    rewritten; old ExploreClarifyGate UNIT text gone (no equivalent anchors).
  * test_explore_offers_explicit_save_bundle_after_summary — same: explore.md
    save-bundle text replaced.
  * test_brainstorm_challenge_critique_only_is_not_rendered_as_skipped —
    deleted generate/phase-0.7/round-loop.md.
  * test_analyze_mode_flags_are_reset_per_run — deleted analyze/preamble.md.
  * test_analyze_prompt_review_uses_paths_for_direct_multi_target_scope —
    deleted analyze/phase-3-semantic.md.
  * test_prompt_bug_only_uses_prompt_output_schema — deleted
    analyze/phase-4-output files.
  * test_analyze_handoff_preserves_analyzed_paths_separate_from_written_manifest
    — deleted analyze/phase-4-output/remediation-handoff.md.
  * test_change_review_derives_prompt_flags_after_diff_scope — deleted
    analyze/phase-0-change-review-scope.md.
  * test_reviewer_plan_failure_does_not_use_legacy_single_dispatch_fallback —
    deleted analyze/phase-2.5-reviewer-plan.md + phase-3-semantic.md.
  * test_skill_entrypoint_bootstrap_keeps_mandatory_loads_explicit — pinned the
    deleted protocol.md / sub-agent-dispatch.md / routing.md mandatory loads;
    SKILL.md is now consolidated (no separate UNIT Bootstrap/HardRules).
  * test_analyze_artifact_dependencies_do_not_block_code_or_prompt_reviews —
    deleted analyze/phase-0-dependencies.md.
  * test_legacy_analyze_dispatch_keeps_code_and_prompt_review_independent —
    deleted analyze/phase-3-semantic.md.
  * test_analyze_routing_includes_storytelling_and_bug_hunt_intents — deleted
    skills/studio/routing.md.
  * test_storytelling_navigation_slots_are_topic_picker_menus — pinned deleted
    analyze/validation-criteria.md handoff anchors.
  * test_ambiguous_routing_fallback_lists_full_route_family — deleted
    skills/studio/routing.md fixed route table.
  * test_root_cf_skill_metadata_advertises_broad_routes — SKILL.md description
    is now a narrow session-initiator string; broad-route metadata retired in
    favor of dynamic cf-* skill discovery.
  * test_artifact_review_flag_is_initialized_and_set — deleted
    analyze/phase-0-dependencies.md + phase-2.5-reviewer-plan.md.
  * test_analyze_to_generate_handoff_reprobes_before_max_iter_prompt — deleted
    analyze/phase-4-output/remediation-handoff.md.
  * test_phase_5_clean_exit_routes_through_final_assembly — deleted
    phase-5/phase-5.3-findings.md / phase-5.5-final.md.
  * test_phase_5_cap_accept_after_write_requires_validation — deleted
    phase-5/phase-5.4-approval.md.
  * test_phase_5_approval_cap_prompt_handles_all_replies — deleted
    phase-5/phase-5.4-approval.md.
  * test_post_write_handoff_has_dynamic_suggested_choice — deleted
    phase-6/post-write-handoff.md.

UNSURE / flagged for maintainer:
  * cf-semantic-reviewer-freeform is dispatched by workflows/write-docs.md but
    is NOT a key in skills/studio/agents.toml. The new
    test_workflow_agent_references_resolve_and_coding_agents_registered checks
    that referenced agent CONTRACT FILES exist on disk (freeform.md does), and
    only asserts agents.toml registration for the coding-workflow dispatch set
    — so it does not encode that gap. Confirm whether freeform should be
    registered in agents.toml.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# The sub-agents the workflows dispatch.
#
# Source of truth: skills/studio/agents.toml. We deliberately pin the
# canonical names so a rename in agents.toml without an accompanying workflow
# update breaks this test. Every name here is verified registered by
# test_workflow_subagents_are_registered.
# ---------------------------------------------------------------------------
WORKFLOW_SUBAGENTS: tuple[str, ...] = (
    "cf-diff-scope-resolver",
    "cf-deterministic-validator",
    "cf-semantic-reviewer-artifact",
    "cf-semantic-reviewer-code",
    "cf-code-bug-finder",
    "cf-semantic-reviewer-prompt",
    "cf-prompt-bug-finder",
    "cf-semantic-reviewer-consistency",
    "cf-brainstorm-facilitator",
    "cf-brainstorm-expert",
    "cf-explorer",
    "cf-generate-collector",
    "cf-analyze-planner",
    "cf-generate-planner",
    "cf-generate-author",
    "cf-generate-author-junior",
    "cf-generate-author-middle",
    "cf-generate-author-senior",
    "cf-generate-author-lead",
    "cf-generate-coder-casual",
    "cf-generate-coder-smart",
    "cf-generate-prompt-engineer-casual",
    "cf-generate-prompt-engineer-smart",
)

FINDING_EMITTING_SUBAGENTS = {
    "cf-deterministic-validator",
    "cf-semantic-reviewer-artifact",
    "cf-semantic-reviewer-code",
    "cf-code-bug-finder",
    "cf-semantic-reviewer-prompt",
    "cf-prompt-bug-finder",
    "cf-semantic-reviewer-consistency",
}


# Minimal dispatch contracts per agent (orchestrator-supplied JSON fields the
# workflows promise to pass). The shapes are grounded in the per-agent contract
# files under skills/studio/agents/<name>.md (e.g. the validator/reviewer
# contracts, the brainstorm facilitator/expert contracts, the collector and
# author contracts) plus the dispatch RULES in the single-file workflows
# (workflows/coding.md CodingDispatch, workflows/brainstorm.md, etc.). These
# are pure shape fixtures and do NOT read those files; they lock the JSON
# contract the dispatcher must honour.
DISPATCH_PAYLOADS: dict[str, dict] = {
    "cf-diff-scope-resolver": {
        "worktree_path": "/repo/worktrees/feature",
        "commit_sha": "abc123",
        "base_ref": "abc123^",
        "include_uncommitted": True,
        "direct_targets": [],
        "review_intent": "review commit abc123 and worktree changes",
    },
    "cf-deterministic-validator": {
        "target_paths": ["fixture/path.md"],
        "target_kinds": {"fixture/path.md": "artifact"},
        "rules_mode": "STRICT",
        "language_check_configured": True,
    },
    "cf-semantic-reviewer-artifact": {
        "target_paths": ["fixture/path.md"],
        "kit_rules_path": None,
        "checklist_path": None,
        "template_path": None,
        "example_path": None,
        "cross_ref_paths": [],
        "rules_mode": "STRICT",
        "traceability_mode": "FULL",
    },
    "cf-semantic-reviewer-code": {
        "design_artifact_path": "fixture/design.md",
        "code_paths": ["fixture/mod.py"],
        "cross_ref_paths": [],
        "rules_mode": "STRICT",
        "traceability_mode": "FULL",
        "kit_rules_path": None,
        "diff_scope": {
            "changed_files": [],
            "changed_hunks": [],
            "review_targets": [],
            "risk_hotspots": [],
        },
    },
    "cf-code-bug-finder": {
        "design_artifact_path": "fixture/design.md",
        "code_paths": ["fixture/mod.py"],
        # diff_scope intentionally None: code-bug-finder does not consume hunk-level scope
        "diff_scope": None,
        "cross_ref_paths": [],
        "rules_mode": "STRICT",
        "kit_rules_path": None,
    },
    "cf-semantic-reviewer-prompt": {
        "target_paths": ["fixture/prompt.md"],
        "kit_rules_path": None,
        "rules_mode": "STRICT",
        "cross_ref_paths": [],
    },
    "cf-prompt-bug-finder": {
        "target_paths": ["fixture/prompt.md"],
        "kit_rules_path": None,
        "rules_mode": "STRICT",
        "cross_ref_paths": [],
    },
    "cf-semantic-reviewer-consistency": {
        # len(target_paths) >= 2 — consistency cross-checks at least two targets
        "target_paths": ["fixture/a.md", "fixture/b.md"],
        "baseline_path": None,
        "kit_rules_path": None,
        "rules_mode": "STRICT",
    },
    "cf-brainstorm-facilitator": {
        "initial_topic": "fixture request summary",
        "kind": "artifact-kind",
        "rules_loaded": False,
        "kit_rules_path": None,
        "template_path": None,
        "example_path": None,
        "project_ctx": "fixture project context (2-3 sentences in production).",
    },
    "cf-brainstorm-expert": {
        "persona": {
            "id": "E1",
            "persona": "Fixture Reviewer",
            "focus": ["fixture-focus-a", "fixture-focus-b"],
            "rationale": "fixture rationale",
        },
        "topic": {"id": "T1", "text": "fixture topic", "section": "Fixture Section"},
        "mode": "topic",
        "state": {
            "kind": "artifact-kind",
            "rules_loaded": False,
            "kit_rules_path": None,
            "template_path": None,
            "panel": [{
                "id": "E1",
                "persona": "Fixture Reviewer",
                "focus": ["fixture-focus-a", "fixture-focus-b"],
                "rationale": "fixture rationale",
            }],
            "decisions": {},
            "topic_history": [],
        },
        "resource_context": {
            "exploration_status": "sufficient",
            "summary": "fixture resource context",
            "resources": [],
            "persona_needs": [],
            "missing_context_questions": [],
        },
    },
    "cf-explorer": {
        "task": "fixture explore task",
        "intent": "brainstorm",
        "panel": [{
            "id": "E1",
            "persona": "Fixture Reviewer",
            "focus": ["fixture-focus-a"],
            "rationale": "fixture rationale",
        }],
        "known_paths": ["fixture/DESIGN.md"],
        "search_roots": ["fixture"],
        "constraints": {
            "kind": "artifact-kind",
            "system": "fixture-system",
            "max_files": 20,
            "max_excerpt_lines_per_file": 40,
        },
    },
    "cf-generate-collector": {
        "kind": "artifact-kind",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "pre_resolved_inputs": {},
        "open_questions": [],
    },
    "cf-analyze-planner": {
        "plan_mode": "memory",
        "target_type": "code",
        "mode": "change_review",
        "rules_mode": "STRICT",
        "target_paths": ["fixture/path.md"],
        "methodology_flags": {"PROMPT_REVIEW": True},
        "available_reviewers": ["cf-semantic-reviewer-prompt"],
        "size_estimate_lines": 42,
    },
    "cf-generate-planner": {
        "plan_mode": "memory",
        "kind": "artifact-kind",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/out.md"],
        "inputs": {"Section": "value"},
        "available_authors": ["cf-generate-author-middle"],
    },
    "cf-generate-author": {
        "mode": "create",
        "kind": "artifact-kind",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "inputs": {"Section": "value"},
        "target_paths": ["fixture/out.md"],
        "template_path": None,
        "example_path": None,
        "kit_rules_path": None,
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
    "cf-generate-author-junior": {
        "mode": "fix",
        "kind": "artifact-kind",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/out.md"],
        "findings": [],
        "template_path": None,
        "example_path": None,
        "kit_rules_path": None,
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
    "cf-generate-author-middle": {
        "mode": "fix",
        "kind": "artifact-kind",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/out.md"],
        "findings": [],
        "template_path": None,
        "example_path": None,
        "kit_rules_path": None,
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
    "cf-generate-author-senior": {
        "mode": "fix",
        "kind": "artifact-kind",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/out.md"],
        "findings": [],
        "template_path": None,
        "example_path": None,
        "kit_rules_path": None,
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
    "cf-generate-author-lead": {
        "mode": "fix",
        "kind": "artifact-kind",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/out.md"],
        "findings": [],
        "template_path": None,
        "example_path": None,
        "kit_rules_path": None,
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
    "cf-generate-coder-casual": {
        "mode": "fix",
        "kind": "code",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/mod.py"],
        "findings": [],
        "design_artifact_path": "fixture/design.md",
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
    "cf-generate-coder-smart": {
        "mode": "fix",
        "kind": "code",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/mod.py"],
        "findings": [],
        "design_artifact_path": "fixture/design.md",
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
    "cf-generate-prompt-engineer-casual": {
        "mode": "fix",
        "kind": "prompt",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/prompt.md"],
        "findings": [],
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
    "cf-generate-prompt-engineer-smart": {
        "mode": "fix",
        "kind": "prompt",
        "name": "fixture-name",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": ["fixture/prompt.md"],
        "findings": [],
        "git_commit_mode": "none",
        "git_constraint": "Do not invoke any git tool. Do not run git commit, git add, or git stage. Edit in place only.",
        "contributing_guide": None,
    },
}

AUTHOR_WORKER_SUBAGENTS = {
    "cf-generate-author-junior",
    "cf-generate-author-middle",
    "cf-generate-author-senior",
    "cf-generate-author-lead",
    "cf-generate-coder-casual",
    "cf-generate-coder-smart",
    "cf-generate-prompt-engineer-casual",
    "cf-generate-prompt-engineer-smart",
}


def _fake_invoke(agent_id: str, payload: dict) -> dict:
    """Pure-Python dispatcher stub. Mirrors the response shape that real
    sub-agents are contractually required to return.

    We do NOT call any real LLM here; this is a contract / shape harness so the
    dispatcher can be unit-tested without network access.
    """
    if agent_id not in WORKFLOW_SUBAGENTS:
        raise ValueError(f"Unknown sub-agent: {agent_id!r}")
    response = {
        "agent_id": agent_id,
        "result": {"payload_echo": payload, "shape_ok": True},
    }
    if agent_id in FINDING_EMITTING_SUBAGENTS:
        response["result"]["validation_report"] = f"Validation Report — {agent_id}"
        response["result"]["review_result"] = {
            "type": "VALIDATION_REPORT",
            "agent_id": agent_id,
        }
        response["result"]["findings"] = [{
            "id": "F-001",
            "severity": "low",
            "mechanical": False,
            "path": "fixture/path.md",
            "line": None,
            "category": "fixture",
            "evidence_quote": "fixture evidence",
            "root_cause": "fixture root cause",
            "suggested_fix": "fixture fix",
            "mechanical_rationale": "fixture rationale",
        }]
    elif agent_id == "cf-diff-scope-resolver":
        response["result"]["diff_scope"] = {
            "changed_files": payload.get("direct_targets", []),
            "review_targets": payload.get("direct_targets", []),
        }
    elif agent_id == "cf-generate-collector":
        response["result"]["proposed_inputs"] = {"Section": "fixture answer"}
        response["result"]["open_questions"] = []
    elif agent_id == "cf-brainstorm-facilitator":
        response["result"]["proposed_panel"] = [
            {
                "id": "E1",
                "persona": "Fixture Scope Reviewer",
                "focus": ["scope", "constraints"],
                "rationale": "fixture rationale",
            },
            {
                "id": "E2",
                "persona": "Fixture Risk Reviewer",
                "focus": ["risk", "failure modes"],
                "rationale": "fixture rationale",
            },
            {
                "id": "E3",
                "persona": "Fixture Delivery Reviewer",
                "focus": ["sequencing", "handoffs"],
                "rationale": "fixture rationale",
            },
        ]
        response["result"]["seed_topic"] = {
            "id": "T1",
            "text": "fixture topic",
            "section": "Fixture Section",
            "why_first": "fixture first topic rationale",
        }
    elif agent_id == "cf-brainstorm-expert":
        response["result"]["relevant"] = True
        if payload.get("fixture_result") == "sit_out":
            response["result"] = {
                "payload_echo": payload,
                "shape_ok": True,
                "relevant": False,
                "reason": "fixture persona has no useful stake in this topic",
            }
            return response
        if payload.get("mode") == "challenge":
            challenged_keys = list(payload["challenged_decisions"])
            if payload.get("fixture_result") == "critique_only_challenge":
                response["result"]["questions"] = []
            else:
                response["result"]["questions"] = [{
                    "id": "E1Q1",
                    "decision_key": challenged_keys[0],
                    "text": "fixture challenge question?",
                    "proposed_default": "fixture counter-proposal",
                    "rationale": "fixture challenge rationale",
                }]
            response["result"]["critique"] = "fixture critique naming challenged decisions"
            response["result"]["next_topic_proposal"] = None
        else:
            response["result"]["questions"] = [{
                "id": "E1Q1",
                "decision_key": "Fixture Section:E1:fixture-question",
                "text": "fixture question?",
                "proposed_default": "fixture proposed default",
                "rationale": "fixture rationale",
            }]
            response["result"]["critique"] = "fixture critique"
            response["result"]["next_topic_proposal"] = {
                "text": "fixture next topic",
                "why": "fixture follow-up rationale",
            }
    elif agent_id == "cf-explorer":
        response["result"]["exploration_status"] = "sufficient"
        response["result"]["task_summary"] = payload["task"]
        response["result"]["resource_context"] = {
            "summary": "fixture resource context",
            "resources": [{
                "path": "fixture/DESIGN.md",
                "resource_type": "architecture",
                "why_relevant": "fixture relevance",
                "suggested_slices": [],
                "confidence": "high",
            }],
            "persona_needs": [{
                "persona_id": "E1",
                "needs": ["fixture need"],
                "resource_paths": ["fixture/DESIGN.md"],
                "missing_context": [],
            }],
            "missing_context_questions": [],
        }
    elif agent_id == "cf-analyze-planner":
        response["result"]["reviewer_plan_marker"] = "<!-- reviewer_plan -->"
        response["result"]["reviewer_plan"] = {
            "tasks": [{
                "id": "RTASK-001",
                "reviewer": "cf-semantic-reviewer-prompt",
                "methodology": "prompt",
                "path_partition": payload["target_paths"],
            }],
            "parallel_groups": [{
                "id": "G1",
                "task_ids": ["RTASK-001"],
                "depends_on": [],
                "execution": "parallel",
                "reason": "Fixture group has one read-only reviewer task.",
            }],
        }
    elif agent_id == "cf-generate-planner":
        response["result"]["author_plan_marker"] = "<!-- author_plan -->"
        response["result"]["author_plan"] = {
            "tasks": [{
                "id": "ATASK-001",
                "author": "cf-generate-author-middle",
                "target_paths": payload["target_paths"],
            }],
            "parallel_groups": [{
                "id": "G1",
                "task_ids": ["ATASK-001"],
                "depends_on": [],
                "execution": "parallel",
                "reason": "Fixture group has one author task.",
            }],
        }
    elif agent_id == "cf-generate-author":
        response["result"]["author_selection"] = {
            "selected_author": "cf-generate-author-middle",
            "author_domain": "artifact",
            "author_level": "middle",
            "dispatch_payload": {k: v for k, v in payload.items() if k != "inputs"},
        }
    elif agent_id in AUTHOR_WORKER_SUBAGENTS:
        response["result"]["manifest"] = {
            "paths_written": payload["target_paths"],
            "mode": payload["mode"],
        }
        response["result"]["findings_not_fixable"] = []
    return response


# ---------------------------------------------------------------------------
# Per-sub-agent dispatch round-trip cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("agent_id", WORKFLOW_SUBAGENTS)
def test_dispatch_round_trip(agent_id: str) -> None:
    """Each sub-agent dispatch returns the canonical shape with agent_id echoed
    and a non-empty `result` dict carrying the payload."""
    payload = DISPATCH_PAYLOADS[agent_id]
    response = _fake_invoke(agent_id, payload)

    assert response["agent_id"] == agent_id, "agent_id must be echoed verbatim"
    assert "result" in response, "response must carry a result field"
    assert isinstance(response["result"], dict), "result must be a JSON object"
    assert response["result"], "result must not be empty"
    if agent_id in FINDING_EMITTING_SUBAGENTS:
        has_review_result = "review_result" in response["result"]
        has_checkpoint = "checkpoint" in response["result"]
        assert has_review_result != has_checkpoint, (
            "finding-emitting workflow sub-agent responses must carry exactly "
            "one review_result/checkpoint discriminator"
        )
        if has_review_result:
            assert response["result"]["review_result"].get("type") == "VALIDATION_REPORT"
        else:
            assert response["result"]["checkpoint"].get("type") == "PARTIAL_CHECKPOINT"
        findings = response["result"].get("findings")
        assert isinstance(findings, list) and findings
        for finding in findings:
            assert finding.get("mechanical_rationale"), (
                "finding-emitting workflow sub-agent findings must carry "
                "per-finding mechanical_rationale for findings display"
            )
        if agent_id == "cf-semantic-reviewer-code":
            assert "diff_scope" in payload, (
                "cf-semantic-reviewer-code dispatch payload must include diff_scope"
            )
            assert payload["diff_scope"] is not None, (
                "diff_scope must be non-None for cf-semantic-reviewer-code"
            )
        elif agent_id == "cf-code-bug-finder":
            assert payload["diff_scope"] is None
    else:
        assert "findings" not in response["result"]
        if agent_id == "cf-diff-scope-resolver":
            assert "diff_scope" in response["result"]
        elif agent_id == "cf-generate-collector":
            assert isinstance(response["result"].get("proposed_inputs"), dict)
        elif agent_id == "cf-brainstorm-facilitator":
            proposed_panel = response["result"].get("proposed_panel")
            seed_topic = response["result"].get("seed_topic")
            assert isinstance(proposed_panel, list)
            assert 3 <= len(proposed_panel) <= 6
            panel_ids = [entry.get("id") for entry in proposed_panel]
            assert all(panel_ids)
            assert len(panel_ids) == len(set(panel_ids))
            assert isinstance(seed_topic, dict) and seed_topic.get("why_first")
            assert seed_topic.get("id")
            assert seed_topic.get("text")
            assert seed_topic.get("section")
            assert "section" in seed_topic
        elif agent_id == "cf-brainstorm-expert":
            assert response["result"].get("relevant") is True
            questions = response["result"].get("questions")
            assert isinstance(questions, list) and questions
            assert isinstance(questions[0], dict)
            question_ids = [question.get("id") for question in questions]
            assert all(question_ids)
            assert len(question_ids) == len(set(question_ids))
            assert questions[0].get("decision_key")
            next_topic = response["result"].get("next_topic_proposal")
            assert isinstance(next_topic, dict) and next_topic.get("why")
        elif agent_id == "cf-explorer":
            assert response["result"].get("exploration_status") in {
                "sufficient", "partial", "insufficient"
            }
            resource_context = response["result"].get("resource_context")
            assert isinstance(resource_context, dict)
            assert isinstance(resource_context.get("resources"), list)
            assert "missing_context_questions" in resource_context
        elif agent_id == "cf-analyze-planner":
            assert response["result"].get("reviewer_plan_marker") == "<!-- reviewer_plan -->"
            assert response["result"].get("reviewer_plan", {}).get("tasks")
            assert response["result"]["reviewer_plan"]["parallel_groups"], \
                "analyze-planner must emit non-empty parallel_groups"
            assert response["result"]["reviewer_plan"]["parallel_groups"][0]["task_ids"], \
                "parallel_groups[0] must reference at least one task_id"
        elif agent_id == "cf-generate-planner":
            assert response["result"].get("author_plan_marker") == "<!-- author_plan -->"
            assert response["result"].get("author_plan", {}).get("tasks")
        elif agent_id == "cf-generate-author":
            selection = response["result"].get("author_selection")
            assert selection and selection.get("dispatch_payload")
            assert "author_selection" in response["result"]
            assert set(response["result"]["author_selection"].keys()) >= {
                "selected_author", "author_domain", "author_level"
            }, "author_selection must carry selected_author, author_domain, and author_level"
            assert selection['selected_author'] in AUTHOR_WORKER_SUBAGENTS, \
                f"selected_author {selection['selected_author']!r} must be a registered worker agent"
            assert "git_commit_mode" in payload, f"{agent_id} dispatch missing git_commit_mode"
            assert payload["git_commit_mode"] in ("commit", "stage", "none")
            assert "git_constraint" in payload and isinstance(payload["git_constraint"], str) and payload["git_constraint"]
            assert "contributing_guide" in payload  # may be None
        elif agent_id in AUTHOR_WORKER_SUBAGENTS:
            assert response["result"].get("manifest", {}).get("paths_written")
            assert "findings_not_fixable" in response["result"]
            assert "git_commit_mode" in payload, f"{agent_id} dispatch missing git_commit_mode"
            assert payload["git_commit_mode"] in ("commit", "stage", "none")
            assert "git_constraint" in payload and isinstance(payload["git_constraint"], str) and payload["git_constraint"]
            assert "contributing_guide" in payload  # may be None


def test_brainstorm_expert_challenge_mode_result_shape() -> None:
    """Challenge-mode experts must target only challenged decisions."""
    payload = {
        **DISPATCH_PAYLOADS["cf-brainstorm-expert"],
        "mode": "challenge",
        "challenged_decisions": {
            "Fixture Section:E1:auth-choice": "fixture current auth choice",
            "Fixture Section:E1:data-retention": "fixture current retention",
        },
    }
    response = _fake_invoke("cf-brainstorm-expert", payload)

    assert response["agent_id"] == "cf-brainstorm-expert"
    assert response["result"].get("relevant") is True
    assert response["result"].get("critique", "").strip()
    assert response["result"].get("next_topic_proposal") is None

    challenged_keys = set(payload["challenged_decisions"])
    questions = response["result"].get("questions")
    assert isinstance(questions, list)
    targeted_keys = [question.get("decision_key") for question in questions]
    assert len(targeted_keys) == len(set(targeted_keys))
    assert set(targeted_keys) <= challenged_keys


def test_brainstorm_expert_can_sit_out_with_reason() -> None:
    """Brainstorm experts may explicitly sit out irrelevant topics."""
    payload = {
        **DISPATCH_PAYLOADS["cf-brainstorm-expert"],
        "fixture_result": "sit_out",
    }
    response = _fake_invoke("cf-brainstorm-expert", payload)

    assert response["agent_id"] == "cf-brainstorm-expert"
    assert response["result"].get("relevant") is False
    assert response["result"].get("reason", "").strip()
    assert "questions" not in response["result"]
    assert "critique" not in response["result"]
    assert "next_topic_proposal" not in response["result"]


def test_brainstorm_expert_challenge_mode_allows_critique_only() -> None:
    """Challenge-mode experts may critique without proposing an override."""
    payload = {
        **DISPATCH_PAYLOADS["cf-brainstorm-expert"],
        "mode": "challenge",
        "fixture_result": "critique_only_challenge",
        "challenged_decisions": {
            "Fixture Section:E1:data-retention": "fixture current retention",
        },
    }
    response = _fake_invoke("cf-brainstorm-expert", payload)

    assert response["agent_id"] == "cf-brainstorm-expert"
    assert response["result"].get("relevant") is True
    assert response["result"].get("questions") == []
    assert response["result"].get("critique", "").strip()
    assert response["result"].get("next_topic_proposal") is None


class TestSubagentDispatch:
    """Namespace for additional dispatch shape tests."""

    def test_dispatch_partial_checkpoint_shape(self) -> None:
        """A finding-emitting sub-agent may return a PARTIAL_CHECKPOINT response
        instead of a VALIDATION_REPORT.  The discriminator invariant must hold:
        exactly one of review_result / checkpoint present, and checkpoint carries
        type=PARTIAL_CHECKPOINT.
        """
        agent_id = "cf-semantic-reviewer-artifact"
        assert agent_id in FINDING_EMITTING_SUBAGENTS

        fake_response = {
            "agent_id": agent_id,
            "result": {
                "shape_ok": True,
                "checkpoint": {
                    "type": "PARTIAL_CHECKPOINT",
                    "unread_files": ["fixture/path.md"],
                    "uncovered_categories": ["completeness"],
                },
                "findings": [{
                    "id": "F-001",
                    "severity": "low",
                    "mechanical": False,
                    "path": "fixture/path.md",
                    "line": None,
                    "category": "fixture",
                    "evidence_quote": "fixture evidence",
                    "root_cause": "fixture root cause",
                    "suggested_fix": "fixture fix",
                    "mechanical_rationale": "fixture rationale",
                }],
            },
        }

        has_review_result = "review_result" in fake_response["result"]
        has_checkpoint = "checkpoint" in fake_response["result"]

        assert has_review_result != has_checkpoint, (
            "finding-emitting workflow sub-agent responses must carry exactly "
            "one review_result/checkpoint discriminator"
        )
        assert not has_review_result
        assert has_checkpoint
        assert fake_response["result"]["checkpoint"]["type"] == "PARTIAL_CHECKPOINT"
        assert fake_response["result"]["checkpoint"]["unread_files"]
        assert fake_response["result"]["checkpoint"]["uncovered_categories"]

        findings = fake_response["result"].get("findings")
        assert isinstance(findings, list) and findings
        for finding in findings:
            assert finding.get("mechanical_rationale"), (
                "checkpoint-mode findings must still carry mechanical_rationale"
            )


# ---------------------------------------------------------------------------
# New architecture: thin routers, single-file coding workflow, the consolidated
# studio skill's sub-agent approval gate, and inventory consistency.
# ---------------------------------------------------------------------------
def test_generate_and_analyze_are_thin_routers_forbidding_legacy_phases() -> None:
    """generate.md and analyze.md are thin routers that forbid legacy phase logic.

    The multi-phase generate/analyze workflows were retired. The routers must
    declare their routing UNITs and explicitly forbid loading/running any legacy
    phase logic.
    """
    repo_root = Path(__file__).resolve().parents[1]
    generate = (repo_root / "workflows" / "generate.md").read_text(encoding="utf-8")
    analyze = (repo_root / "workflows" / "analyze.md").read_text(encoding="utf-8")

    # Routing UNITs exist on each router.
    assert "UNIT GenerateBootstrap" in generate
    assert "UNIT GenerateRoute" in generate
    assert "UNIT GenerateNoMatch" in generate
    assert "UNIT AnalyzeBootstrap" in analyze
    assert "UNIT AnalyzeRoute" in analyze
    assert "UNIT AnalyzeNoMatch" in analyze

    # Routing is resolved via the shared WorkflowResolution rule, not phases.
    assert "WorkflowResolution" in generate
    assert "WorkflowResolution" in analyze

    # Legacy multi-phase logic is explicitly forbidden. (The retirement note in
    # analyze.md wraps "legacy" onto the previous line, so normalize whitespace.)
    generate_flat = " ".join(generate.split())
    analyze_flat = " ".join(analyze.split())
    assert "legacy multi-phase generate workflow has been retired" in generate_flat
    assert "NEVER load or run any legacy generate phase logic; routing is the only behavior" in generate
    assert "NEVER fall back to legacy generate phases when nothing matches" in generate
    assert "legacy multi-phase analyze workflow has been retired" in analyze_flat
    assert "NEVER load or run any legacy analyze phase logic; routing is the only behavior" in analyze
    assert "NEVER fall back to legacy analyze phases when nothing matches" in analyze


def test_coding_dispatch_names_reviewers_and_valid_coder() -> None:
    """workflows/coding.md CodingDispatch names the correct reviewer sub-agents
    and a valid coder agent, all registered in agents.toml."""
    import tomllib

    repo_root = Path(__file__).resolve().parents[1]
    coding = (repo_root / "workflows" / "coding.md").read_text(encoding="utf-8")
    with open(repo_root / "skills" / "studio" / "agents.toml", "rb") as fh:
        registered = set(tomllib.load(fh)["agents"].keys())

    assert "UNIT CodingDispatch" in coding

    # The three semantic reviewers the coding loop dispatches.
    coding_reviewers = (
        "cf-semantic-reviewer-code",
        "cf-code-bug-finder",
        "cf-semantic-reviewer-consistency",
    )
    for reviewer in coding_reviewers:
        assert reviewer in coding, f"CodingDispatch must name {reviewer}"
        assert reviewer in registered, f"{reviewer} must be registered in agents.toml"

    # The deterministic gate validator.
    assert "cf-deterministic-validator" in coding
    assert "cf-deterministic-validator" in registered

    # The coder priority order: cf-codegen, else cf-generate-coder-smart, else
    # cf-generate-coder-casual. Every named coder must be registered.
    coder_priority = ("cf-codegen", "cf-generate-coder-smart", "cf-generate-coder-casual")
    for coder in coder_priority:
        assert coder in coding, f"CodingDispatch must reference coder {coder}"
        assert coder in registered, f"{coder} must be registered in agents.toml"
    # At least one named coder is a valid (registered) coder agent.
    assert any(coder in registered for coder in coder_priority)


def test_skill_requires_session_approval_before_native_subagent_dispatch() -> None:
    """Native sub-agent dispatch requires explicit user approval once per session.

    The approval gate moved into UNIT SubAgentDispatch in skills/studio/SKILL.md.
    Dispatch is gated on SUB_AGENTS_APPROVED == true, asked once per session via
    MENU SubAgentApprovalRequest, and remembered for the rest of the session.
    """
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "studio" / "SKILL.md").read_text(encoding="utf-8")

    assert "UNIT SubAgentDispatch" in skill
    assert "MENU SubAgentApprovalRequest" in skill
    assert "SET SUB_AGENTS_APPROVED: unset | true | false" in skill
    # Gate: never dispatch without approval; ask when unset.
    assert "NEVER dispatch a sub-agent unless SUB_AGENTS_APPROVED == true" in skill
    assert "REQUIRE SUB_AGENTS_APPROVED == true" in skill
    assert "EMIT_MENU SubAgentApprovalRequest WHEN SUB_AGENTS_APPROVED == unset" in skill
    assert "WAIT user.reply WHEN SUB_AGENTS_APPROVED == unset" in skill
    # Approval is session-wide and revocable.
    assert (
        "ALWAYS treat SUB_AGENTS_APPROVED as a session-wide approval that applies "
        "to every later dispatch until StudioShutdown" in skill
    )
    # The approve option flips the gate and continues dispatch.
    assert "1 approve -> SET SUB_AGENTS_APPROVED = true; CONTINUE dispatch" in skill


def test_subagent_fallback_never_defaults_from_unapproved_native_support() -> None:
    """Denying native dispatch routes to an explicit inline fallback menu.

    A host exposing native sub-agent tools does not silently inline: denial sets
    SUB_AGENTS_APPROVED=false and offers MENU SubAgentFallbackRequest, where the
    user explicitly picks inline / retry / stop.
    """
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "studio" / "SKILL.md").read_text(encoding="utf-8")

    assert "MENU SubAgentFallbackRequest" in skill
    assert "EMIT_MENU SubAgentFallbackRequest WHEN SUB_AGENTS_APPROVED == false OR native dispatch fails" in skill
    assert "2 deny -> SET SUB_AGENTS_APPROVED = false; EMIT_MENU SubAgentFallbackRequest" in skill
    assert "1 inline -> SET SUB_AGENTS_INLINE = true; RUN the contract inline" in skill
    # The inline path is opt-in, never an automatic default.
    assert "SET SUB_AGENTS_INLINE: unset | true (default unset, scope session)" in skill


def test_diff_scope_resolver_agent_registered_and_prompt_contract() -> None:
    """The diff-scope resolver is a real workflow sub-agent with a concrete contract."""
    import tomllib

    repo_root = Path(__file__).resolve().parents[1]
    agents_toml = repo_root / "skills" / "studio" / "agents.toml"
    with open(agents_toml, "rb") as fh:
        agents = tomllib.load(fh)["agents"]

    agent = agents["cf-diff-scope-resolver"]
    prompt = (
        repo_root / "skills" / "studio" / "agents" / "cf-diff-scope-resolver.md"
    ).read_text(encoding="utf-8")

    assert agent["mode"] == "readonly"
    # target=any intentionally bypasses the (cheap, analyze, codebase) matrix
    # upgrade — the resolver runs git --name-status only and stays haiku-tier
    # for speed.
    assert agent["target"] == "any"
    assert "worktree_path" in prompt
    assert "commit_sha" in prompt
    assert "include_uncommitted" in prompt
    assert "changed_files" in prompt
    assert "changed_hunks" in prompt
    assert '"source": "committed|staged|unstaged|untracked"' in prompt
    assert "review_targets" in prompt


def test_bootstrap_sdlc_resources_resolve_to_installed_config_kit() -> None:
    """Bootstrap core bindings must point at files that exist under .bootstrap."""
    import tomllib

    repo_root = Path(__file__).resolve().parents[1]
    bootstrap = repo_root / ".bootstrap"
    with open(bootstrap / "config" / "core.toml", "rb") as fh:
        core = tomllib.load(fh)

    kit_path = core["kits"]["sdlc"]["path"]
    assert (bootstrap / kit_path).is_dir()
    assert str(core["kits"]["sdlc"]["path"]).endswith("config/kits/sdlc")
    assert core["kits"]["sdlc"]["resources"], "resources dict must be non-empty"

    for resource in core["kits"]["sdlc"]["resources"].values():
        assert (bootstrap / resource["path"]).exists(), resource["path"]


def test_prompt_reviewer_methodology_only_wording_preserves_compliance_invariants() -> None:
    """Prompt reviewer must not contradict required SKILL/compliance loads."""
    repo_root = Path(__file__).resolve().parents[1]
    prompt_reviewer = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-semantic-reviewer-prompt.md"
    ).read_text(encoding="utf-8")

    assert "controller-supplied prompt-engineering methodology" in prompt_reviewer
    assert "Load only `prompt-engineering.md`.\n" not in prompt_reviewer


def test_reviewer_agent_prompts_do_not_mix_methodologies() -> None:
    """Code/prompt checklist reviewers and bug finders each load one methodology."""
    repo_root = Path(__file__).resolve().parents[1]
    agents_dir = repo_root / "skills" / "studio" / "agents"
    code_review = (agents_dir / "cf-semantic-reviewer-code.md").read_text(
        encoding="utf-8"
    )
    code_bug = (agents_dir / "cf-code-bug-finder.md").read_text(
        encoding="utf-8"
    )
    prompt_review = (
        agents_dir / "cf-semantic-reviewer-prompt.md"
    ).read_text(encoding="utf-8")
    prompt_bug = (agents_dir / "cf-prompt-bug-finder.md").read_text(
        encoding="utf-8"
    )

    assert "requirements/code-checklist.md" in code_review
    assert "requirements/bug-finding.md" not in code_review
    assert "requirements/bug-finding.md" in code_bug
    assert "requirements/code-checklist.md" not in code_bug

    assert "requirements/prompt-engineering.md" in prompt_review
    assert "requirements/prompt-bug-finding.md" not in prompt_review
    assert "requirements/prompt-bug-finding.md" in prompt_bug
    assert "requirements/prompt-engineering.md" not in prompt_bug


# ---------------------------------------------------------------------------
# Wiring sanity: every WORKFLOW_SUBAGENT must be declared in skills/studio/
# agents.toml. Catches accidental rename drift between the workflows and the
# registry.
# ---------------------------------------------------------------------------
def test_workflow_subagents_are_registered() -> None:
    import tomllib

    repo_root = Path(__file__).resolve().parents[1]
    agents_toml = repo_root / "skills" / "studio" / "agents.toml"
    with open(agents_toml, "rb") as fh:
        data = tomllib.load(fh)
    registered = set(data.get("agents", {}).keys())
    for name in WORKFLOW_SUBAGENTS:
        assert name in registered, (
            f"{name} is dispatched by the workflows but not registered in "
            f"{agents_toml.relative_to(repo_root)}"
        )


def test_workflow_agent_references_resolve_and_coding_agents_registered() -> None:
    """Inventory consistency for the single-file workflows.

    (1) Every `agents/<name>.md` contract path referenced by a workflow file
        must resolve to a real file under skills/studio/agents/.
    (2) The coding workflow's dispatch set (reviewers + validator + the coder
        priority order) must be registered in agents.toml.
    """
    import tomllib

    repo_root = Path(__file__).resolve().parents[1]
    workflows_dir = repo_root / "workflows"
    agents_dir = repo_root / "skills" / "studio" / "agents"
    with open(repo_root / "skills" / "studio" / "agents.toml", "rb") as fh:
        registered = set(tomllib.load(fh)["agents"].keys())

    ref_re = re.compile(r"agents/(cf-[a-z0-9-]+)\.md")
    referenced: set[str] = set()
    for path in sorted(workflows_dir.glob("*.md")):
        for match in ref_re.findall(path.read_text(encoding="utf-8")):
            referenced.add(match)

    assert referenced, "expected at least one agents/<name>.md reference in the workflows"
    for name in sorted(referenced):
        assert (agents_dir / f"{name}.md").is_file(), (
            f"workflow references agents/{name}.md but the contract file is missing"
        )

    # Coding workflow dispatch set must be registered in agents.toml.
    coding_dispatch_set = {
        "cf-semantic-reviewer-code",
        "cf-code-bug-finder",
        "cf-semantic-reviewer-consistency",
        "cf-deterministic-validator",
        "cf-codegen",
        "cf-generate-coder-smart",
        "cf-generate-coder-casual",
    }
    for name in sorted(coding_dispatch_set):
        assert name in registered, (
            f"{name} is dispatched by workflows/coding.md but not registered in agents.toml"
        )


def test_instruction_references_are_follow_directives() -> None:
    """Workflow/agent prompts must tell agents to follow instruction files.

    Soft references like "Load `file`" or "See `file`" are ambiguous: an agent
    may treat them as background references instead of instructions. Navigation
    and methodology references in these prompt files must use explicit
    "open, load, and follow" language.
    """
    repo_root = Path(__file__).resolve().parents[1]
    search_roots = [
        repo_root / "workflows",
        repo_root / "skills" / "studio" / "agents",
    ]
    standalone_files = [
        repo_root / "skills" / "studio" / "SKILL.md",
    ]
    bad_patterns = (
        re.compile(r"\b[Ll]oad\s+[`{]"),
        re.compile(r"\b[Ss]ee\s+[`{]"),
    )

    def _scan_for_bad_patterns(path: Path, base: Path) -> list[str]:
        """Return offender strings for lines matching bad_patterns.

        Skips lines inside fenced code blocks (``` or ```lang), blockquote
        lines starting with ``>``, and heading lines starting with ``#``.
        """
        hits: list[str] = []
        in_code_block = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            if stripped.startswith(">") or stripped.startswith("#"):
                continue
            if any(pattern.search(line) for pattern in bad_patterns):
                hits.append(f"{path.relative_to(base)}:{lineno}: {line}")
        return hits

    offenders: list[str] = []
    for root in search_roots:
        for path in root.rglob("*.md"):
            offenders.extend(_scan_for_bad_patterns(path, repo_root))
    for path in standalone_files:
        offenders.extend(_scan_for_bad_patterns(path, repo_root))

    assert offenders == []


def test_brainstorm_expert_is_context_isolated() -> None:
    """Native brainstorm fan-out promises experts do not see each other's output."""
    import tomllib

    repo_root = Path(__file__).resolve().parents[1]
    agents_toml = repo_root / "skills" / "studio" / "agents.toml"
    with open(agents_toml, "rb") as fh:
        agents = tomllib.load(fh)["agents"]

    assert agents["cf-brainstorm-expert"]["isolation"] is True


def test_studio_agent_prompts_are_controller_side_generators() -> None:
    """Sub-agent prompt sources must not regress to self-loading runtime contracts."""
    repo_root = Path(__file__).resolve().parents[1]
    agent_dir = repo_root / "skills" / "studio" / "agents"
    forbidden = (
        "self-bootstrap",
        "The controller ALWAYS load this file",
        "dispatched-prompt",
        "return-value contract",
        "ALWAYS open and follow",
    )

    for path in sorted(agent_dir.glob("*.md")):
        if path.name == "author-production-rules.md":
            continue
        text = path.read_text(encoding="utf-8")
        assert (
            "Dispatch Generator Contract" in text
            or "Generator Contract" in text
            or "Dispatch Generator" in text
        ), path
        for phrase in forbidden:
            assert phrase not in text, f"{path}: {phrase}"


def test_brainstorm_prompts_handle_nullable_rules_and_template_paths() -> None:
    """Facilitator and expert prompts must not assume template/rules paths exist."""
    repo_root = Path(__file__).resolve().parents[1]
    facilitator = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-brainstorm-facilitator.md"
    ).read_text(encoding="utf-8")
    expert = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-brainstorm-expert.md"
    ).read_text(encoding="utf-8")

    # Facilitator guards nulls via WHEN conditions
    assert "kit_rules_path != null" in facilitator
    assert "template_path != null" in facilitator
    # Expert guards nulls via REQUIRE ... is non-null
    assert "kit_rules_path is non-null" in expert
    assert "template_path is non-null" in expert
    assert "proceed with available context" in expert


def test_brainstorm_facilitator_seed_topic_gate_requires_identity_and_text() -> None:
    """Seed topics need stable identity and text fields for downstream state."""
    repo_root = Path(__file__).resolve().parents[1]
    facilitator = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-brainstorm-facilitator.md"
    ).read_text(encoding="utf-8")

    assert "ALWAYS have non-empty id in seed_topic" in facilitator
    assert "ALWAYS have non-empty text in seed_topic" in facilitator
    assert "ALWAYS have section key in seed_topic" in facilitator
    assert "ALWAYS have non-empty why_first in seed_topic" in facilitator


def test_brainstorm_expert_registry_documents_challenge_shape() -> None:
    """Registry text must match the challenge-mode expert response contract."""
    repo_root = Path(__file__).resolve().parents[1]
    agents_toml = (repo_root / "skills" / "studio" / "agents.toml").read_text(
        encoding="utf-8"
    )

    assert "challenge-mode `0..3` questions" in agents_toml
    assert "critique-only challenge" in agents_toml
    assert "`next_topic_proposal = null`" in agents_toml


def test_prompt_bug_finder_runs_in_place_like_other_read_only_reviewers() -> None:
    """Prompt bug-finder is a read-only semantic reviewer; the pool convention
    is `isolation = false` for non-brainstorm reviewers (see the pool comment
    in `agents.toml`) so dispatch results stay synchronized with the disk
    state the orchestrator just observed."""
    import tomllib

    repo_root = Path(__file__).resolve().parents[1]
    agents_toml = repo_root / "skills" / "studio" / "agents.toml"
    with open(agents_toml, "rb") as fh:
        agents = tomllib.load(fh)["agents"]

    assert agents["cf-prompt-bug-finder"]["isolation"] is False


def test_analyze_planner_prompt_includes_requirements_as_prompt_targets() -> None:
    """Methodology requirements are prompt-review targets, not artifacts/code."""
    repo_root = Path(__file__).resolve().parents[1]
    planner = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-analyze-planner.md"
    ).read_text(encoding="utf-8")

    assert "requirements/**/*.md" in planner


def test_planner_contracts_reject_incomplete_or_numeric_parallel_groups() -> None:
    """Planner prompts must forbid the invalid shape that forces rerun loops."""
    repo_root = Path(__file__).resolve().parents[1]
    analyze_planner = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-analyze-planner.md"
    ).read_text(encoding="utf-8")
    generate_planner = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-generate-planner.md"
    ).read_text(encoding="utf-8")

    for planner in (analyze_planner, generate_planner):
        assert "Numeric values such as 1 or 2 are invalid." in planner
        assert (
            "Every parallel_groups[] entry ALWAYS include all required fields:"
            in planner
        )
        assert "id, task_ids, depends_on, execution, and reason" in planner
        assert 'Every parallel_groups[].execution value ALWAYS be exactly "parallel" or' in planner


# ---------------------------------------------------------------------------
# CR-T8-005 — AUTHOR_ESCALATION_REQUIRED response shape
# ---------------------------------------------------------------------------

def _fake_invoke_escalation(agent_id: str, payload: dict) -> dict:
    """Variant of _fake_invoke that returns an AUTHOR_ESCALATION_REQUIRED result.

    Used exclusively in escalation-shape tests.  Does NOT call any real LLM.
    """
    return {
        "agent_id": agent_id,
        "result": {
            "AUTHOR_ESCALATION_REQUIRED": True,
            "recommended_author": "cf-generate-author-lead",
            "reason": "task exceeds AUTHOR_TIER=coder-smart (10 files > 5)",
            "paths_written": [],
        },
    }


def test_author_worker_escalation_required_response_shape() -> None:
    """A tier-guard-triggering payload to a coder-smart worker returns the
    AUTHOR_ESCALATION_REQUIRED shape: flag is truthy, recommended_author and
    reason are non-empty strings, and paths_written is empty (no writes
    occurred during escalation).

    Exercises CR-T8-005 coverage gap: previous tests only checked nominal
    author-worker responses; the escalation branch was untested.
    """
    agent_id = "cf-generate-coder-smart"
    # A coder-smart payload with 10 target_paths triggers the tier guard
    # (coder-smart ceiling is 5 files per the Tier Guard contract).
    payload = {
        "mode": "fix",
        "kind": "code",
        "name": "large-refactor",
        "rules_mode": "STRICT",
        "system": "fixture-system",
        "target_paths": [f"src/module_{i}.py" for i in range(10)],
        "findings": [],
        "design_artifact_path": "fixture/design.md",
    }

    response = _fake_invoke_escalation(agent_id, payload)

    # agent_id is echoed
    assert response["agent_id"] == agent_id

    result = response["result"]

    # The escalation flag must be present and truthy
    assert "AUTHOR_ESCALATION_REQUIRED" in result
    assert result["AUTHOR_ESCALATION_REQUIRED"] is True

    # recommended_author must be a non-empty string
    assert isinstance(result.get("recommended_author"), str)
    assert result["recommended_author"], "recommended_author must not be empty"

    # reason must be a non-empty string
    assert isinstance(result.get("reason"), str)
    assert result["reason"], "reason must not be empty"

    # paths_written must be an empty list (no file writes during escalation)
    assert result.get("paths_written") == [], (
        "paths_written must be empty when escalation occurs — no writes should happen"
    )


def test_runtime_instruction_modules_stay_compact() -> None:
    """High-traffic instruction resources should stay below the compact budget.

    Re-grounded after the refactor: the deleted phase files
    (phase-0-dependencies.md, analyze remediation-handoff.md) are dropped; the
    budgets now cover the files that still carry the hot path — the
    consolidated studio SKILL, the thin routers, the single-file coding
    workflow, and the code reviewer contract.
    """
    repo_root = Path(__file__).resolve().parents[1]
    # Tuples of (path, line_budget).  SKILL.md carries the consolidated UNIT
    # rules (incl. the GIT_COMMIT_MODE / SubAgentDispatch state machines); it
    # gets a higher budget than the pure-routing workflow files.
    compact_files = [
        (repo_root / "skills" / "studio" / "SKILL.md", 478),
        (repo_root / "workflows" / "generate.md", 150),
        (repo_root / "workflows" / "analyze.md", 150),
        (repo_root / "workflows" / "coding.md", 150),
        (repo_root / "skills" / "studio" / "agents" / "cf-semantic-reviewer-code.md", 200),
    ]

    for path, budget in compact_files:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        assert line_count <= budget, f"{path.relative_to(repo_root)} has {line_count} lines (budget {budget})"
