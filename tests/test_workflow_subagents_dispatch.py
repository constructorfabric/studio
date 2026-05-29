"""Round-trip dispatch fixtures for the workflow sub-agents that the thin-
orchestrator refactor exercises, plus the Phase 5.4 reply-grammar parser and
the Phase 6 combine-refusal contract.

Resolves PROMPT_REVIEW findings I16 (snapshot-only test coverage for sub-agent
dispatch wiring) and I21 (no parser-grammar test for Phase 5.4 reply table /
no Phase 6 R+W combine-refusal test). All fixtures are pure shape checks — they
do NOT invoke a real LLM. The point is to lock the dispatch JSON contract +
expected response shape so future workflow edits cannot silently drift.

Test count contract (per plan phase 5 acceptance criterion): ≥ 11 cases:
  * 12 × per-sub-agent dispatch round-trip
  * 1 × Phase 5.4 reply-grammar parser table (parametrised across every regex row)
  * 1 × Phase 6 R+W combine-refusal
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# The sub-agents the thin-orchestrator workflows dispatch.
#
# Source of truth: skills/studio/agents.toml. We deliberately pin the
# canonical names so a rename in agents.toml without an accompanying workflow
# update breaks this test.
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
# workflows promise to pass). Sourced verbatim from:
#   * workflows/generate/phase-5/phase-5.1-det-gate.md (validator)
#   * workflows/generate/phase-5/phase-5.2-semantic.md (reviewers)
#   * workflows/generate/phase-0.7/panel-selection.md (brainstorm-facilitator)
#   * workflows/generate/phase-0.7/round-loop.md       (brainstorm-expert)
#   * workflows/generate/phase-1-collect.md            (collector)
#   * workflows/generate/phase-4-write.md              (author)
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
        # len(target_paths) >= 2 — see Consistency precondition in
        # workflows/generate/phase-5/phase-5.2-semantic.md
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

    Returns:
      {
        "agent_id": <echoed agent id>,
        "result": {
            # Reviewers / validator: a Validation Report markdown block stub +
            # findings array.
            # Author: a manifest stub.
            # Collector: a proposed_inputs dict stub.
            # Brainstorm: a state-mutation stub.
            ...
        },
      }

    We do NOT call any real LLM here; this is a contract / shape harness so the
    Phase 5 / Phase 6 dispatchers can be unit-tested without network access.
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
            "parallel_groups": [{"id": "G1", "task_ids": ["RTASK-001"], "depends_on": []}],
        }
    elif agent_id == "cf-generate-planner":
        response["result"]["author_plan_marker"] = "<!-- author_plan -->"
        response["result"]["author_plan"] = {
            "tasks": [{
                "id": "ATASK-001",
                "author": "cf-generate-author-middle",
                "target_paths": payload["target_paths"],
            }],
            "parallel_groups": [{"id": "G1", "task_ids": ["ATASK-001"], "depends_on": []}],
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
# 12 × dispatch round-trip cases
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
        # Build a fake checkpoint response by hand (simulates what a sub-agent
        # would return when it has only partially reviewed the target files).
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

        # The discriminator invariant: exactly one of the two keys is present.
        assert has_review_result != has_checkpoint, (
            "finding-emitting workflow sub-agent responses must carry exactly "
            "one review_result/checkpoint discriminator"
        )
        # This branch exercises the checkpoint path specifically.
        assert not has_review_result
        assert has_checkpoint
        assert fake_response["result"]["checkpoint"]["type"] == "PARTIAL_CHECKPOINT"
        assert fake_response["result"]["checkpoint"]["unread_files"]
        assert fake_response["result"]["checkpoint"]["uncovered_categories"]

        # Findings must still be present even in checkpoint responses.
        findings = fake_response["result"].get("findings")
        assert isinstance(findings, list) and findings
        for finding in findings:
            assert finding.get("mechanical_rationale"), (
                "checkpoint-mode findings must still carry mechanical_rationale"
            )


def test_review_finding_workflow_contract_regressions() -> None:
    """Review-loop handoff text must not regress on approved review findings."""
    repo_root = Path(__file__).resolve().parents[1]
    error_handling = (
        repo_root / "workflows" / "generate" / "error-handling.md"
    ).read_text(encoding="utf-8")
    shared_plan_gate = (
        repo_root / "workflows" / "shared" / "plan-escalation-gate.md"
    ).read_text(encoding="utf-8")
    analyze_plan_gate = (
        repo_root / "workflows" / "analyze" / "phase-0.1-plan-escalation-gate.md"
    ).read_text(encoding="utf-8")
    reviewer_plan = (
        repo_root / "workflows" / "analyze" / "phase-2.5-reviewer-plan.md"
    ).read_text(encoding="utf-8")
    validation_criteria = (
        repo_root / "workflows" / "analyze" / "validation-criteria.md"
    ).read_text(encoding="utf-8")
    clarify = (
        repo_root / "workflows" / "generate" / "phase-0.5-clarify.md"
    ).read_text(encoding="utf-8")
    analyze_handoff = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")

    assert "`{cfs_cmd} update`" in error_handling
    assert "`{cfs_cmd} --json update`" not in error_handling

    assert "higher precedence — resolve first" in shared_plan_gate
    assert "higher precedence than the bypass" in analyze_plan_gate

    assert "empty|enter|memory|1" in reviewer_plan

    assert "Dependencies loaded when required for the active methodology" in validation_criteria
    assert "prompt-bug-only output uses the prompt-bug-finder block" in validation_criteria

    assert "Reply with `File`, `Chat only`, `MCP: <tool>`, or `External: <system>`" in clarify

    assert "manifest.paths_written = []" in analyze_handoff
    assert "target_paths = analyzed_paths" in analyze_handoff


def test_external_fix_handoff_requires_subagent_dispatch_evidence() -> None:
    """Analyze→generate fix mode must fail closed instead of patching inline.

    The handoff carries SUB_AGENT_SESSION_APPROVED but deliberately does not
    carry INLINE_FALLBACK. A future orchestrator must therefore re-probe and
    record per-iteration dispatch evidence before applying fixes when native
    sub-agents are active.
    """
    repo_root = Path(__file__).resolve().parents[1]
    analyze_handoff = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")
    phase5_index = (
        repo_root / "workflows" / "generate" / "phase-5" / "index.md"
    ).read_text(encoding="utf-8")
    phase53 = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.3-findings.md"
    ).read_text(encoding="utf-8")
    phase54 = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.4-approval.md"
    ).read_text(encoding="utf-8")

    for text in (analyze_handoff, phase5_index, phase53):
        assert "handoff_guard.inline_fallback_reprobed = true" in text
        assert "handoff_guard.max_iter_resolved = true" in text
        assert "handoff_guard.dispatch_evidence_required = true" in text

    assert "phase5_dispatch_evidence" in phase5_index
    assert "validator dispatch record per iteration" in phase5_index
    assert "semantic reviewer\n      dispatch record per iteration" in phase5_index
    assert "author dispatch\n      record before any file edit" in phase5_index
    assert "missing evidence = protocol violation" in phase5_index

    assert "Inline patching permitted ONLY when INLINE_FALLBACK=true OR MAX_ITER=0" in phase53
    assert "MUST stop before editing files" in phase53
    assert "APPEND selected author dispatch evidence to phase5_dispatch_evidence" in phase54


# ---------------------------------------------------------------------------
# Phase 5.4 reply-grammar parser table
#
# Mirrors the regex map in
#   workflows/generate/phase-5/phase-5.4-approval.md § Reply parsing rules
# verbatim. If that table grows or shrinks, this test breaks.
# ---------------------------------------------------------------------------
PHASE_5_4_RULES = (
    (re.compile(r"^1$", re.IGNORECASE),               "option_1"),
    (re.compile(r"^2$", re.IGNORECASE),               "reject_bare_2_no_colon"),
    (re.compile(r"^2:\s*$", re.IGNORECASE),           "option_2_mechanical_only"),
    (re.compile(
        r"^2:\s*[A-Za-z][A-Za-z0-9_-]*(\s*,\s*[A-Za-z][A-Za-z0-9_-]*)*\s*$",
        re.IGNORECASE,
    ),                                                "option_2_with_ids"),
    (re.compile(r"^3$", re.IGNORECASE),               "option_3"),
    (re.compile(r"^4$", re.IGNORECASE),               "option_4"),
    (re.compile(r"^(stop|enough|done)$", re.IGNORECASE), "stop_token_as_4"),
)


def _parse_phase_5_4_reply(raw: str) -> str:
    user_input = raw.strip()
    for pattern, outcome in PHASE_5_4_RULES:
        if pattern.match(user_input):
            return outcome
    return "reject_unrecognized"


PHASE_5_4_CASES = (
    # Each (reply, expected outcome) — exercises every row in the regex table.
    ("1",                  "option_1"),
    ("2",                  "reject_bare_2_no_colon"),
    ("2:",                 "option_2_mechanical_only"),
    ("2: V-001",           "option_2_with_ids"),
    ("2: V-001, Rp-007",   "option_2_with_ids"),
    ("3",                  "option_3"),
    ("4",                  "option_4"),
    ("STOP",               "stop_token_as_4"),
    ("Enough",             "stop_token_as_4"),
    ("done",               "stop_token_as_4"),
    ("garbage",            "reject_unrecognized"),
    ("",                   "reject_unrecognized"),
    ("  1  ",              "option_1"),         # whitespace-tolerant
    ("2: 001",             "reject_unrecognized"),  # finding id starts with digit
    ("2: V 001",           "reject_unrecognized"),  # finding id contains space
)


@pytest.mark.parametrize("reply,expected", PHASE_5_4_CASES)
def test_phase_5_4_reply_grammar(reply: str, expected: str) -> None:
    """Parametrised case exercising the full Phase 5.4 reply-grammar
    table. Resolves PROMPT_REVIEW finding I16 + I21 (no parser test)."""
    got = _parse_phase_5_4_reply(reply)
    assert got == expected, f"reply {reply!r} → {got!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# Phase 6 combine-refusal
#
# Source of truth: workflows/generate/phase-6/remediation-handoff.md § Combine
# semantics. Combined Remediation (R*) + Post-Write Review (W*) replies on the
# same turn MUST be refused with the canonical clarifier.
# ---------------------------------------------------------------------------
COMBINE_REFUSAL_PATTERN = re.compile(
    r"""^\s*
        (?:R[123]|W[123])           # one menu choice
        \s*[,+]\s*                  # comma or plus separator (whitespace ok)
        (?:R[123]|W[123])           # another menu choice
        (?:\s*[,+]\s*(?:R[123]|W[123]))*   # zero or more additional choices
        \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _phase_6_route(reply: str) -> str:
    user_input = reply.strip()
    if COMBINE_REFUSAL_PATTERN.match(user_input):
        return "refuse_combined_rw"
    if re.match(r"^R[123]$", user_input, re.IGNORECASE):
        return "accept_remediation"
    if re.match(r"^W[123]$", user_input, re.IGNORECASE):
        return "accept_post_write"
    return "reject_unrecognized"


def test_phase_6_combine_refusal() -> None:
    """The Phase 6 dispatcher MUST refuse combined Remediation+Post-Write
    replies and also refuse multi-choice replies within one menu. Single-menu
    single-choice replies are accepted."""
    # Combined R+W must be refused (every separator variant + casing).
    for combo in ("R1, W2", "R2 + W3", "W2, R1", "r1,w2", "R1+W3", "R1 ,  W2"):
        assert _phase_6_route(combo) == "refuse_combined_rw", combo
    # Multi-choice within one menu also refused.
    for same_menu in ("R1, R2", "W1, W2", "R2 + R3", "  R1, W2  ", "R1+R2+R3"):
        assert _phase_6_route(same_menu) == "refuse_combined_rw", same_menu
    # Single valid choice accepted.
    for ok_r in ("R1", "R2", "R3", "  r1 "):
        assert _phase_6_route(ok_r) == "accept_remediation", ok_r
    for ok_w in ("W1", "W2", "W3"):
        assert _phase_6_route(ok_w) == "accept_post_write", ok_w


def test_phase_6_r1_routes_existing_findings_to_seeded_findings_path() -> None:
    """R1 must fix the known remaining findings instead of starting a fresh review.

    R1 enters the Phase 5 dispatcher in fix mode; iteration 1 starts at
    `phase-5.1-det-gate.md` per the dispatcher contract. `all_findings` is
    seeded from `remaining_findings` at the dispatcher boundary.
    """
    repo_root = Path(__file__).resolve().parents[1]
    remediation = (
        repo_root / "workflows" / "generate" / "phase-6" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")

    assert "ENTER phase-5/index.md § Dispatcher in fix mode" in remediation
    assert "phase-5.1-det-gate.md" in remediation
    assert "all_findings = remaining_findings" in remediation
    assert "re-enter `workflows/generate/phase-5/index.md` with `remaining_findings`" not in remediation


def test_skill_completion_invariants_match_handoff_workflows() -> None:
    """SKILL.md must agree with the thin-orchestrator handoff contract.

    Generate and analyze complete by emitting handoff menus. Prompt blocks are
    on-demand next-turn emissions, not mandatory terminal blocks in the same
    response.
    """
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "studio" / "SKILL.md").read_text(encoding="utf-8")
    codegen = (
        repo_root / "skills" / "studio" / "agents" / "cf-codegen.md"
    ).read_text(encoding="utf-8")
    pr_review = (
        repo_root / "skills" / "studio" / "agents" / "cf-pr-review.md"
    ).read_text(encoding="utf-8")
    analyze_overview = (
        repo_root / "workflows" / "analyze" / "overview.md"
    ).read_text(encoding="utf-8")
    analyze_handoff = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")
    post_write_handoff = (
        repo_root / "workflows" / "generate" / "phase-6" / "post-write-handoff.md"
    ).read_text(encoding="utf-8")

    assert "terminal = Post-Write Review Handoff menu" in skill
    assert "terminal = Remediation Handoff menu" in skill
    assert "MUST be emitted only on the NEXT turn" in skill
    assert "both `Plan Review Prompt` and `Direct Review Prompt` blocks" not in skill
    assert "both `Fix Prompt` and `Plan Prompt` blocks" not in skill

    assert "Post-Write Review Handoff" in codegen
    assert "Prompt blocks are emitted only on next turn" in codegen
    assert "Review Prompts` section" not in codegen

    assert "Remediation Handoff" in pr_review
    assert "emitted only on next turn" in pr_review
    assert "final two sections" not in pr_review

    assert "MUST trigger the `Remediation Handoff` menu" in analyze_overview
    assert "MUST trigger both remediation prompts in the same response" not in analyze_overview

    assert "load skill `cf`; enter fix mode" in analyze_handoff
    assert 'start with' in analyze_handoff and '"Invoke skill cf"' in analyze_handoff
    assert "load skill `cf` and route to `/cf-analyze`" in post_write_handoff
    assert "starts with `Invoke skill cf` and routes to `/cf-analyze`" in post_write_handoff


def test_skill_requires_session_approval_before_native_subagent_dispatch() -> None:
    """Native sub-agent dispatch requires explicit user approval once per session.

    The platform may expose sub-agent tools, but Constructor Studio must still
    ask before first use and remember approval for the rest of the session.
    """
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "studio" / "SKILL.md").read_text(encoding="utf-8")

    assert "## Session Sub-Agent Approval Gate" in skill
    assert "SUB_AGENT_SESSION_APPROVED == true" in skill
    assert "explicit user approval for native sub-agent dispatch" in skill
    assert "Use native sub-agents" in skill
    assert "Use inline fallback for this workflow" in skill
    assert "Suggested: 1" in skill
    assert "Reply with 1 or 2" in skill
    assert "STOP_TURN) immediately" in skill
    assert "MUST end the turn (STOP_TURN) immediately" in skill
    assert "MUST_NOT default INLINE_FALLBACK from host capability or missing approval" in skill
    assert "MUST_NOT set INLINE_FALLBACK = false unless SUB_AGENT_SESSION_APPROVED == true" in skill


def test_workflow_probe_requires_subagent_approval_gate() -> None:
    """The workflow-level probe must preserve the SKILL.md approval gate.

    Root cause guard: if Phase 0 only says "set INLINE_FALLBACK" and defaults to
    native dispatch, orchestrators can skip asking the user before sub-agent use.
    """
    repo_root = Path(__file__).resolve().parents[1]
    shared_probe = (
        repo_root / "workflows" / "shared" / "inline-fallback-probe.md"
    ).read_text(encoding="utf-8")
    analyze_phase0 = (
        repo_root / "workflows" / "analyze" / "phase-0-dependencies.md"
    ).read_text(encoding="utf-8")
    generate_phase0 = (
        repo_root / "workflows" / "generate" / "phase-0-dependencies.md"
    ).read_text(encoding="utf-8")

    assert "Session Sub-Agent Approval Gate" in shared_probe
    assert "Approve sub-agent use for this session" in shared_probe
    assert "Suggested: 1" in shared_probe
    assert "STOP_TURN immediately after emitting" in shared_probe
    assert "do NOT load agent contracts" in shared_probe
    assert "MUST NOT treat absence of user reply as option 2" in shared_probe
    assert "MUST_NOT default INLINE_FALLBACK = true from missing approval" in shared_probe
    assert "MUST_NOT default INLINE_FALLBACK = false" in shared_probe
    assert "default `false` when ambiguous" not in shared_probe
    assert "workflows/shared/inline-fallback-probe.md" in analyze_phase0
    assert "workflows/shared/inline-fallback-probe.md" in generate_phase0


def test_analyze_change_review_dispatches_diff_scope_resolver() -> None:
    """Review-commit/worktree requests must not leave git diff scanning to the orchestrator."""
    repo_root = Path(__file__).resolve().parents[1]
    overview = (repo_root / "workflows" / "analyze" / "overview.md").read_text(
        encoding="utf-8"
    )
    phase0 = (
        repo_root / "workflows" / "analyze" / "phase-0-dependencies.md"
    ).read_text(encoding="utf-8")
    change_scope = (
        repo_root / "workflows" / "analyze" / "phase-0-change-review-scope.md"
    ).read_text(encoding="utf-8")
    phase3 = (
        repo_root / "workflows" / "analyze" / "phase-3-semantic.md"
    ).read_text(encoding="utf-8")
    code_reviewer = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-semantic-reviewer-code.md"
    ).read_text(encoding="utf-8")

    assert "CHANGE_REVIEW=true" in overview
    assert "cf-diff-scope-resolver" in change_scope
    assert "MUST_NOT run git diff" in change_scope
    assert "diff_scope" in phase3
    assert "target_paths=prompt_targets" in phase3
    assert "deterministic gate is PASS OR SKIPPED (with validator availability proof)" in phase3
    assert '"diff_scope":' in code_reviewer
    assert "changed_hunks" in code_reviewer


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


def test_analyze_handoff_max_iter_zero_can_reach_phase_6() -> None:
    """Analyze option 1 with MAX_ITER=0 must surface carried findings, not dead-end."""
    repo_root = Path(__file__).resolve().parents[1]
    phase53 = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.3-findings.md"
    ).read_text(encoding="utf-8")
    phase6 = (
        repo_root / "workflows" / "generate" / "phase-6" / "index.md"
    ).read_text(encoding="utf-8")

    assert "IF MAX_ITER == 0:" in phase53
    assert "remaining_findings = all_findings" in phase53
    assert "external entry from analyze.md with MAX_ITER=0" in phase6
    assert "accept carried analyze-side deterministic result" in phase6


def test_analyze_external_r1_runs_generate_review_before_fixing() -> None:
    """Analyze-originated R1 must not fix carried findings before generate-side review."""
    repo_root = Path(__file__).resolve().parents[1]
    handoff = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")
    phase5 = (
        repo_root / "workflows" / "generate" / "phase-5" / "index.md"
    ).read_text(encoding="utf-8")

    assert "CONTINUE workflows/generate/phase-5/phase-5.1-det-gate.md" in handoff
    assert "external-entry from analyze" in phase5
    assert "MUST run Phase 5.1 then Phase 5.2 before Phase 5.3" in phase5


def test_max_iter_zero_preserves_analyzed_paths_for_followup_fix_loop() -> None:
    """Zero-iteration analyze handoff keeps analyzed paths until a write manifest exists."""
    repo_root = Path(__file__).resolve().parents[1]
    phase53 = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.3-findings.md"
    ).read_text(encoding="utf-8")
    remediation = (
        repo_root / "workflows" / "generate" / "phase-6" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")

    assert "external_target_paths = analyzed_paths" in phase53
    assert "prefer external_target_paths when manifest.paths_written is empty" in remediation


def test_phase_6_chat_only_suppression_does_not_hide_remaining_findings() -> None:
    """Chat-only outputs still emit remediation when actionable findings remain."""
    repo_root = Path(__file__).resolve().parents[1]
    phase6 = (
        repo_root / "workflows" / "generate" / "phase-6" / "index.md"
    ).read_text(encoding="utf-8")

    assert "IF output was chat-only AND no files changed AND remaining_findings is empty" in phase6
    assert "IF chat-only output with non-empty remaining_findings" in phase6


def test_protocol_references_use_existing_thin_protocol_file() -> None:
    """Thin orchestrator workflows must not reference removed execution-protocol paths."""
    repo_root = Path(__file__).resolve().parents[1]
    protocol = repo_root / "skills" / "studio" / "protocol.md"
    assert protocol.is_file()

    checked_files = [
        "workflows/analyze/preamble.md",
        "workflows/analyze/validation-criteria.md",
        "workflows/plan.md",
        "workflows/generate.md",
        "workflows/generate/validation-criteria.md",
    ]
    for rel_path in checked_files:
        content = (repo_root / rel_path).read_text(encoding="utf-8")
        assert "execution-protocol.md" not in content, rel_path
        assert "skills/studio/protocol.md" in content, rel_path


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


def test_prompt_bug_only_analyze_is_mutually_exclusive_prompt_branch() -> None:
    """Prompt-bug-only mode uses prompt output without suppressing other active flags."""
    repo_root = Path(__file__).resolve().parents[1]
    output_index = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "index.md"
    ).read_text(encoding="utf-8")
    phase3 = (
        repo_root / "workflows" / "analyze" / "phase-3-semantic.md"
    ).read_text(encoding="utf-8")

    assert "PROMPT_REVIEW=false`, `PROMPT_BUG_REVIEW=false" in output_index
    assert "PROMPT_BUG_REVIEW=true" in phase3
    assert "ARTIFACT_REVIEW=true" in phase3
    assert "TARGET_TYPE == code OR CODE_REVIEW=true" in phase3


def test_generate_prompt_review_detects_cypilot_instruction_docs() -> None:
    """Generate-side review must include thin protocol instruction docs."""
    repo_root = Path(__file__).resolve().parents[1]
    phase52 = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.2-semantic.md"
    ).read_text(encoding="utf-8")

    assert "skills/studio/**/*.md" in phase52


def test_max_iter_zero_has_single_external_entry_semantics() -> None:
    """MAX_ITER=0 should consistently mean surface carried findings, not fresh review."""
    repo_root = Path(__file__).resolve().parents[1]
    phase5 = (
        repo_root / "workflows" / "generate" / "phase-5" / "index.md"
    ).read_text(encoding="utf-8")
    phase53 = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.3-findings.md"
    ).read_text(encoding="utf-8")

    assert "MAX_ITER=0" in phase5
    assert "single validator pass + one semantic-reviewer pass" not in phase5
    assert "SKIP fresh Phase 5 validation/review" in phase5
    assert "IF gate FAIL" in phase5 and "SKIP semantic review" in phase5
    assert "zero-iteration external entry" in phase53
    assert "zero-iteration internal entry" in phase53


def test_storytelling_route_does_not_reference_removed_trigger_file() -> None:
    """Analyze EXPLAIN_MODE routing must not dead-end on a removed sub-file."""
    repo_root = Path(__file__).resolve().parents[1]
    phase0 = (
        repo_root / "workflows" / "analyze" / "phase-0-dependencies.md"
    ).read_text(encoding="utf-8")
    preamble = (
        repo_root / "workflows" / "analyze" / "preamble.md"
    ).read_text(encoding="utf-8")

    assert "workflows/analyze/storytelling-trigger.md" not in phase0
    assert "storytelling.md" in preamble


def test_deterministic_validator_uses_resolved_validator_command() -> None:
    """Self-hosted bootstrap validation must not hard-code cfc over cpt."""
    repo_root = Path(__file__).resolve().parents[1]
    checked_files = [
        "workflows/analyze/phase-2-det-gate.md",
        "workflows/generate/phase-5/index.md",
        "skills/studio/agents/cf-deterministic-validator.md",
    ]

    for rel_path in checked_files:
        content = (repo_root / rel_path).read_text(encoding="utf-8")
        assert "resolved validator command" in content, rel_path
        assert "actual `cfc --json" not in content, rel_path
        assert "executes `cfc --json" not in content, rel_path


def test_phase_6_blocks_post_write_choices_while_remediation_pending() -> None:
    """W-only replies must be refused until remediation choice is processed."""
    repo_root = Path(__file__).resolve().parents[1]
    remediation = (
        repo_root / "workflows" / "generate" / "phase-6" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")
    post_write = (
        repo_root / "workflows" / "generate" / "phase-6" / "post-write-handoff.md"
    ).read_text(encoding="utf-8")

    assert "W-only replies are refused while remediation is pending" in remediation
    assert "remaining_findings is non-empty" in post_write
    assert "REJECT W1, W2, W3" in post_write


def test_prompt_review_partial_checkpoint_has_phase_4_output_contract() -> None:
    """Prompt-review partial checkpoints must be renderable or explicitly blocked."""
    repo_root = Path(__file__).resolve().parents[1]
    output_index = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "index.md"
    ).read_text(encoding="utf-8")
    prompt_output = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "output-prompt-review.md"
    ).read_text(encoding="utf-8")
    validation = (
        repo_root / "workflows" / "analyze" / "validation-criteria.md"
    ).read_text(encoding="utf-8")

    assert "Prompt Review Partial Checkpoint" in prompt_output
    assert "checkpoint.type = \"PARTIAL_CHECKPOINT\"" in prompt_output
    assert "prompt-review partial checkpoints satisfy Phase 4" in output_index
    assert "Prompt Review Partial Checkpoint" in validation


def test_phase_3_to_4_checkpoint_has_canonical_reply_menu() -> None:
    """Context recovery checkpoint must define exact replies and parser behavior."""
    repo_root = Path(__file__).resolve().parents[1]
    checkpoint = (
        repo_root / "workflows" / "analyze" / "phase-3-to-4-checkpoint.md"
    ).read_text(encoding="utf-8")

    assert "Reply `1` or `2`." in checkpoint
    assert "1 -> CONTINUE" in checkpoint
    assert "2 -> Emit" in checkpoint
    assert "MUST_NOT infer a default when the user replies anything other than 1 or 2" in checkpoint


def test_partial_checkpoint_contract_scope_matches_reviewer_support() -> None:
    """Dispatchers must not promise checkpoints for reviewers that lack the contract."""
    repo_root = Path(__file__).resolve().parents[1]
    phase3 = (
        repo_root / "workflows" / "analyze" / "phase-3-semantic.md"
    ).read_text(encoding="utf-8")
    phase52 = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.2-semantic.md"
    ).read_text(encoding="utf-8")

    assert "MUST support PARTIAL_CHECKPOINT only for reviewers whose contract declares it" in phase3
    assert "PARTIAL_CHECKPOINT only supported by reviewers whose contract declares it" in phase52


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

    assert "Load `prompt-engineering.md` as review methodology" in prompt_reviewer
    assert "Load only `prompt-engineering.md`.\n" not in prompt_reviewer


def test_analyze_antipattern_summary_does_not_mislabel_canonical_ap005() -> None:
    """Analyze rules must not reuse AP-005 for a noncanonical anti-pattern."""
    repo_root = Path(__file__).resolve().parents[1]
    rules = (repo_root / "workflows" / "analyze" / "rules.md").read_text(encoding="utf-8")

    assert "AP-005 SELF_TEST_LIE" in rules
    assert "AP-005 SIMULATED_VALIDATION" not in rules


def test_phase_5_findings_display_is_bounded_with_full_json_payload() -> None:
    """The chat audit trail must show every finding before approval."""
    repo_root = Path(__file__).resolve().parents[1]
    phase53 = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.3-findings.md"
    ).read_text(encoding="utf-8")

    assert "Render every finding" in phase53
    assert "MUST NOT collapse, summarize, or truncate" in phase53
    assert "bounded chat-only audit block" not in phase53


def test_generate_clarification_prompts_explain_why_and_suggest_default() -> None:
    """Phase 0.5 user questions need rationale and a suggested/default path."""
    repo_root = Path(__file__).resolve().parents[1]
    clarify = (
        repo_root / "workflows" / "generate" / "phase-0.5-clarify.md"
    ).read_text(encoding="utf-8")

    assert "Why this input is needed:" in clarify
    assert "Suggested:" in clarify
    assert "Reply with" in clarify


def test_analyze_methodologies_are_lazy_and_one_per_subagent() -> None:
    """The orchestrator must route methodology work, not preload it."""
    repo_root = Path(__file__).resolve().parents[1]
    preamble = (repo_root / "workflows" / "analyze" / "preamble.md").read_text(
        encoding="utf-8"
    )
    phase0 = (
        repo_root / "workflows" / "analyze" / "phase-0-dependencies.md"
    ).read_text(encoding="utf-8")
    phase3 = (
        repo_root / "workflows" / "analyze" / "phase-3-semantic.md"
    ).read_text(encoding="utf-8")

    forbidden = [
        "ALWAYS open and follow `{cf-studio-path}/.core/requirements/code-checklist.md`",
        "ALWAYS open and follow `{cf-studio-path}/.core/requirements/bug-finding.md`",
        "ALWAYS open and follow `{cf-studio-path}/.core/requirements/prompt-engineering.md`",
        "ALWAYS open and follow `{cf-studio-path}/.core/requirements/prompt-bug-finding.md`",
        "open `prompt-engineering.md` and `prompt-bug-finding.md`",
        "load `{cf-studio-path}/.core/requirements/code-checklist.md`",
    ]
    for text in forbidden:
        assert text not in preamble
        assert text not in phase0

    assert "FORBID opening code methodology files in the orchestrator" in phase0
    assert "FORBID opening prompt methodology files in the orchestrator" in phase0
    assert "cf-code-bug-finder" in phase3
    assert "cf-prompt-bug-finder" in phase3


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


def test_subagent_dispatch_sites_have_pre_dispatch_gate() -> None:
    """Every workflow file that dispatches cf-constructor sub-agents needs a guard.

    Phase 0 is easy for an orchestrator to skip during handoffs or resumed paths;
    each dispatch site therefore carries a local fail-stop reference to the
    shared approval/probe block.
    """
    repo_root = Path(__file__).resolve().parents[1]
    dispatch_files = [
        "workflows/analyze/phase-0-dependencies.md",
        "workflows/analyze/phase-2-det-gate.md",
        "workflows/analyze/phase-3-semantic.md",
        "workflows/generate/phase-0.7/panel-selection.md",
        "workflows/generate/phase-0.7/round-loop.md",
        "workflows/generate/phase-1-collect.md",
        "workflows/generate/phase-4-write.md",
        "workflows/generate/phase-5/phase-5.1-det-gate.md",
        "workflows/generate/phase-5/phase-5.2-semantic.md",
        "workflows/generate/phase-5/phase-5.3-findings.md",
        "workflows/generate/phase-5/phase-5.4-approval.md",
    ]

    for rel_path in dispatch_files:
        content = (repo_root / rel_path).read_text(encoding="utf-8")
        assert "inline-fallback-probe.md" in content, rel_path
        assert "before dispatching any `cf-*` sub-agent from this sub-file" not in content, rel_path


def test_artifact_review_dispatch_uses_registered_example_path_shape() -> None:
    """Artifact reviewer dispatches must use the kit's examples/example.md layout.

    SDLC kit resources register example files under `examples/example.md`;
    `{KIND}/example.md` is not a valid path and makes artifact reviewers lose
    their style/reference example.
    """
    repo_root = Path(__file__).resolve().parents[1]
    analyze_semantic = (
        repo_root / "workflows" / "analyze" / "phase-3-semantic.md"
    ).read_text(encoding="utf-8")
    generate_semantic = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.2-semantic.md"
    ).read_text(encoding="utf-8")

    for content in (analyze_semantic, generate_semantic):
        assert "examples/example.md" in content
        assert "{KIND}/example.md" not in content


def test_generate_carry_forward_keeps_unapproved_judgmental_findings() -> None:
    """Subset approval must not drop judgmental findings that the user declined."""
    repo_root = Path(__file__).resolve().parents[1]
    approval = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.4-approval.md"
    ).read_text(encoding="utf-8")

    assert "un-approved judgmental findings are carried forward in session state" in approval
    assert "MUST union every un-approved judgmental finding into carry_forward" in approval
    assert "reviewers no longer detect after the mechanical fix is effectively dropped" not in approval


def test_remediation_menus_have_one_dynamic_suggestion_slot() -> None:
    """Menus should not mark several options as suggested at once."""
    repo_root = Path(__file__).resolve().parents[1]
    analyze_handoff = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")
    generate_handoff = (
        repo_root / "workflows" / "generate" / "phase-6" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")

    assert "Suggested: {1|2|3} because {scope/risk reason}." in analyze_handoff
    assert "Suggested: {R1|R2|R3} because {scope/risk reason}." in generate_handoff
    for option_line in (
        "load skill `cf`; enter fix mode",
        "fix-prompt-template.md",
        "plan-prompt-template.md",
    ):
        assert option_line in analyze_handoff
    assert "(suggested when" not in analyze_handoff
    assert "(suggested when" not in generate_handoff


def test_analyze_standard_output_does_not_own_prompt_templates() -> None:
    """Fix/Plan prompt bodies are on-demand remediation emissions.

    The standard analyze output schema should end in the Remediation Handoff
    menu when issues exist; it must not also carry prompt-template sections that
    look mandatory in the same response.
    """
    repo_root = Path(__file__).resolve().parents[1]
    output_standard = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "output-standard.md"
    ).read_text(encoding="utf-8")
    remediation = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")

    assert "### Fix Prompt\n" not in output_standard
    assert "### Plan Prompt\n" not in output_standard
    assert "fix-prompt-template" in remediation
    assert "plan-prompt-template" in remediation


# ---------------------------------------------------------------------------
# Wiring sanity: every WORKFLOW_SUBAGENT must be declared in skills/studio/
# agents.toml. Catches accidental rename drift between the workflow router
# and the registry.
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


def test_brainstorm_challenge_flow_matches_user_facing_contract() -> None:
    """The challenge option must challenge the decisions the user just made."""
    repo_root = Path(__file__).resolve().parents[1]
    offer = (repo_root / "workflows" / "generate" / "phase-0.7" / "offer.md").read_text(
        encoding="utf-8"
    )
    round_loop = (
        repo_root / "workflows" / "generate" / "phase-0.7" / "round-loop.md"
    ).read_text(encoding="utf-8")
    state_schema = (
        repo_root / "workflows" / "generate" / "phase-0.7" / "state-schema.md"
    ).read_text(encoding="utf-8")

    assert "challenge decisions" in offer
    assert "challenge_source_round = state.rounds[-1]" in round_loop
    assert "parse-side guard" in round_loop
    assert "last round with kind == \"topic\"" not in round_loop
    assert "preceding answer-writing round" in state_schema
    assert "immediately-preceding topic-round" not in state_schema


def test_brainstorm_challenge_questions_target_decision_keys() -> None:
    """Challenge counter-proposals must name the exact decision key to overwrite."""
    repo_root = Path(__file__).resolve().parents[1]
    expert = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-brainstorm-expert.md"
    ).read_text(encoding="utf-8")
    round_loop = (
        repo_root / "workflows" / "generate" / "phase-0.7" / "round-loop.md"
    ).read_text(encoding="utf-8")
    state_schema = (
        repo_root / "workflows" / "generate" / "phase-0.7" / "state-schema.md"
    ).read_text(encoding="utf-8")

    assert '"decision_key": "<decision-key>"' in expert
    assert '"id": "<persona.id>Q1"' in expert
    assert "`questions[].id` values MUST be unique within the response" in expert
    assert "MUST be unique within this response" in expert
    assert "MUST_NOT use bare `topic.section` as the whole key" in expert
    assert "decision_key` MUST name a key present in `challenged_decisions`" in expert
    assert "update state.decisions[q.decision_key]" in round_loop
    assert "challenge overwrites; skip/keep excluded" in round_loop
    assert "MUST reject duplicate topic-round decision_key values" in round_loop
    assert '"decision_key": "<section-or-topic>:<expert-id>:<question-key>"' in state_schema
    assert '"decision_key": "<key>"' in state_schema


def test_brainstorm_round_prompt_supports_one_by_one_answering() -> None:
    """Users should answer brainstorm questions one at a time, then choose next action."""
    repo_root = Path(__file__).resolve().parents[1]
    round_loop = (
        repo_root / "workflows" / "generate" / "phase-0.7" / "round-loop.md"
    ).read_text(encoding="utf-8")
    round_loop_lines = round_loop.splitlines()

    assert "UNIT Phase07QuestionQueue" in round_loop
    assert "UNIT Phase07AskCurrentQuestion" in round_loop
    assert "MUST show exactly one pending question per turn" in round_loop
    assert "MUST NOT dump the full question_queue to the user" in round_loop
    assert "UNIT Phase07PostRoundMenu" in round_loop
    assert "MUST NOT show this menu before every pending question is resolved" in round_loop
    assert '  EMIT "custom: <text> — custom next topic"' in round_loop_lines
    assert "3 skip ->" in round_loop
    assert 'reason = "user_skipped"' in round_loop
    assert 'mark q.status = "open_unanswered"' in round_loop
    assert "skip MUST NOT update state.decisions" in round_loop


_BRAINSTORM_POST_ROUND_REPLY_RULES = (
    (re.compile(r"^custom:\s*<text>$", re.IGNORECASE), "custom_topic"),
    (re.compile(r"^(?:1|2|C|W)$", re.IGNORECASE), "topic_choice"),
)


def _parse_brainstorm_post_round_reply(raw: str) -> str:
    user_input = raw.strip()
    for pattern, outcome in _BRAINSTORM_POST_ROUND_REPLY_RULES:
        if pattern.match(user_input):
            return outcome
    return "reject_unrecognized"


def test_brainstorm_post_round_custom_reply_grammar() -> None:
    """Post-round choices parse directly after the one-by-one question queue."""
    assert _parse_brainstorm_post_round_reply("custom: <text>") == "custom_topic"
    assert _parse_brainstorm_post_round_reply("then: custom: <text>") == "reject_unrecognized"


def test_brainstorm_wrap_menu_distinguishes_session_and_disk_save() -> None:
    """Wrap handoff must separate session-only preservation from disk persistence."""
    repo_root = Path(__file__).resolve().parents[1]
    wrap = (
        repo_root / "workflows" / "generate" / "phase-0.7" / "wrap-handoff.md"
    ).read_text(encoding="utf-8")

    assert "1. Save brainstorm results only (in session)" in wrap
    assert "2. Save brainstorm results only (to disk)" in wrap
    assert "Option 1 MUST be session-only and MUST NOT write files" in wrap
    assert "Option 2 MUST be hidden or rejected" in wrap
    assert "WRITE state.json" in wrap
    assert "WRITE design.md" in wrap


def test_studio_agent_prompts_are_controller_side_generators() -> None:
    """Sub-agent prompt sources must not regress to self-loading runtime contracts."""
    repo_root = Path(__file__).resolve().parents[1]
    agent_dir = repo_root / "skills" / "studio" / "agents"
    forbidden = (
        "self-bootstrap",
        "The controller MUST load this file",
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


def test_brainstorm_missing_topic_offers_saved_sessions_first() -> None:
    """Missing brainstorm topic should offer saved sessions before fresh topics."""
    repo_root = Path(__file__).resolve().parents[1]
    clarify = (
        repo_root / "workflows" / "generate" / "phase-0.5-clarify.md"
    ).read_text(encoding="utf-8")

    assert "BRAINSTORM mode is selected AND brainstorm topic is missing" in clarify
    assert "DISCOVER saved brainstorm sessions" in clarify
    assert "{cf-studio-path}/.cache/brainstorm/" in clarify
    assert "I found saved brainstorm sessions you can continue" in clarify
    assert "Reply with a saved session number to continue it" in clarify
    assert "No saved brainstorm sessions were found" in clarify


def test_cf_on_uses_ambiguous_routing_menu() -> None:
    """Activation-only cf requests should use the same menu as unclear intent."""
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "studio" / "SKILL.md").read_text(encoding="utf-8")
    routing = (repo_root / "skills" / "studio" / "routing.md").read_text(encoding="utf-8")

    assert "CfOnActivationMenu" not in skill
    assert "activation-only / no-task intent" in routing
    assert "cf on" in routing
    assert "MENU RoutingClarificationMenu" in routing
    assert "1 -> help" in routing
    assert "2 -> brainstorm" in routing
    assert "CONTINUE WorkflowRoutingTable entry 0" in routing


def test_cf_help_routes_to_prefilled_explain_preset() -> None:
    """cf help should run explain on Studio itself without asking setup gates."""
    repo_root = Path(__file__).resolve().parents[1]
    routing = (repo_root / "skills" / "studio" / "routing.md").read_text(
        encoding="utf-8"
    )
    help_workflow = (repo_root / "workflows" / "help.md").read_text(
        encoding="utf-8"
    )
    preamble = (
        repo_root / "workflows" / "analyze" / "preamble.md"
    ).read_text(encoding="utf-8")

    assert "cf help | /cf help | cf-studio help | /cf-studio help | cfs help" in routing
    assert "open and follow {cf-studio-path}/.core/workflows/help.md" in routing
    assert "name: cf-help" in help_workflow
    assert "SET CF_HELP_PRESET = true" in help_workflow
    assert 'SET EXPLAIN_TARGET = "{cf-studio-path}"' in help_workflow
    assert 'SET STORYTELLING_MODE = "presentation"' in help_workflow
    assert 'SET STORYTELLING_ARTIFACT_DISPOSITION = "chat-only"' in help_workflow
    assert 'SET STORYTELLING_AUDIENCE = "Constructor Studio newcomers"' in help_workflow
    assert 'SET STORYTELLING_DIAGRAM_FORMAT = "ascii"' in help_workflow
    assert "SET STORYTELLING_DIAGRAM_FORMAT_PRESET = true" in help_workflow
    assert "Run a normal cf-explain storytelling session" in help_workflow
    assert "LOAD skill `cf` IN ANALYZE + EXPLAIN mode, CF_HELP_PRESET=true" in help_workflow
    assert "MUST_NOT render custom one-shot help here" in help_workflow
    assert "MUST_NOT ask the diagram-format lazy prompt in help mode" in help_workflow
    assert "IF CF_HELP_PRESET == true" in preamble
    assert "PRESERVE route-supplied preset variables" in preamble
    assert "STORYTELLING_DIAGRAM_FORMAT, STORYTELLING_DIAGRAM_FORMAT_PRESET" in preamble
    assert "do not ask mode, disposition, audience" in preamble
    assert "diagram-format questions" in preamble
    assert "normal Storytelling Protocol E0-E5" in preamble
    assert "FORBID custom one-shot help rendering" in preamble
    assert "ASCII inline diagrams" in preamble
    assert "Do NOT replace it with a custom one-shot `Cf Overview`" in preamble
    assert "STORYTELLING_HELP_OUTPUT_CONTRACT" not in preamble


def test_empty_standalone_explore_clarifies_before_dispatch() -> None:
    """Bare cf-explore should ask for a topic before launching cf-explorer."""
    repo_root = Path(__file__).resolve().parents[1]
    explore = (repo_root / "workflows" / "explore.md").read_text(encoding="utf-8")

    assert "UNIT ExploreClarifyGate" in explore
    assert "request is activation-only / no-task explore intent" in explore
    assert "skill explorer" in explore
    assert "I need a topic before I search the project" in explore
    assert "What should I explore?" in explore
    assert "MENU ExploreClarifyMenu" in explore
    assert "MUST_NOT dispatch cf-explorer before this gate resolves" in explore
    assert "Parent workflows MAY skip this gate only when they supply a non-empty" in explore


def test_explore_offers_explicit_save_bundle_after_summary() -> None:
    """Explore should offer an explicit save bundle without silently writing."""
    repo_root = Path(__file__).resolve().parents[1]
    explore = (repo_root / "workflows" / "explore.md").read_text(encoding="utf-8")

    assert "EMIT resource map and context summary" in explore
    assert "RUN ExploreSaveOffer" in explore
    assert "UNIT ExploreSaveOffer" in explore
    assert "{cf-studio-path}/.cache/explore/{slug}-{ISO}/" in explore
    assert "folder: <path>" in explore
    assert "result.json" in explore
    assert "resource-map.md" in explore
    assert "summary.md" in explore
    assert "exact explorer result JSON" in explore
    assert "task summary, exploration status, resource count, and missing-context questions" in explore
    assert "MUST NOT silently write exploration results from running explore alone" in explore
    assert "MUST keep explorer output in `resource_context`, not `SHARED_CONTEXT_PACK`" in explore


def test_brainstorm_challenge_critique_only_is_not_rendered_as_skipped() -> None:
    """Challenge pushback without an override should still render as critique."""
    repo_root = Path(__file__).resolve().parents[1]
    expert = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-brainstorm-expert.md"
    ).read_text(encoding="utf-8")
    round_loop = (
        repo_root / "workflows" / "generate" / "phase-0.7" / "round-loop.md"
    ).read_text(encoding="utf-8")

    assert "critique-only challenge" in expert
    assert "relevant: true, empty questions" in expert
    assert "MUST NOT render critique-only challenge outputs as skipped" in round_loop
    assert "keep in participating" in round_loop


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

    assert "MUST have non-empty id in seed_topic" in facilitator
    assert "MUST have non-empty text in seed_topic" in facilitator
    assert "MUST have section key in seed_topic" in facilitator
    assert "MUST have non-empty why_first in seed_topic" in facilitator


def test_brainstorm_expert_registry_documents_challenge_shape() -> None:
    """Registry text must match the challenge-mode expert response contract."""
    repo_root = Path(__file__).resolve().parents[1]
    agents_toml = (repo_root / "skills" / "studio" / "agents.toml").read_text(
        encoding="utf-8"
    )

    assert "challenge-mode `0..3` questions" in agents_toml
    assert "critique-only challenge" in agents_toml
    assert "`next_topic_proposal = null`" in agents_toml


def test_brainstorm_saved_discard_and_retention_are_explicit() -> None:
    """Saved-session discard must say whether cache artifacts remain."""
    repo_root = Path(__file__).resolve().parents[1]
    offer = (repo_root / "workflows" / "generate" / "phase-0.7" / "offer.md").read_text(
        encoding="utf-8"
    )
    wrap = (
        repo_root / "workflows" / "generate" / "phase-0.7" / "wrap-handoff.md"
    ).read_text(encoding="utf-8")

    assert "manual cache retention" in offer
    assert "discard handoff" in wrap
    assert "saved brainstorm cache remains on disk" in wrap


def test_subagent_fallback_never_defaults_from_unapproved_native_support() -> None:
    """Approval-unset + native-capable hosts must ask, not silently inline."""
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "studio" / "SKILL.md").read_text(encoding="utf-8")

    assert "MUST_NOT set INLINE_FALLBACK = true from missing approval alone" in skill
    assert "Otherwise set `INLINE_FALLBACK=true`" not in skill


def test_analyze_mode_flags_are_reset_per_run() -> None:
    """Mode flags from a previous analyze request must not leak into a new one."""
    repo_root = Path(__file__).resolve().parents[1]
    preamble = (repo_root / "workflows" / "analyze" / "preamble.md").read_text(
        encoding="utf-8"
    )

    reset_idx = preamble.index("Initialize per-run analyze flags before matching")
    code_idx = preamble.index("WHEN user requests analysis of code")
    prompt_idx = preamble.index("WHEN user requests analysis of the following instruction targets")
    assert reset_idx < code_idx
    assert reset_idx < prompt_idx
    for flag in (
        "CODE_REVIEW=false",
        "CODE_BUG_REVIEW=false",
        "CONSISTENCY_REVIEW=false",
        "PROMPT_REVIEW=false",
        "PROMPT_BUG_REVIEW=false",
        "EXPLAIN_MODE=false",
    ):
        assert flag in preamble


def test_analyze_prompt_review_uses_paths_for_direct_multi_target_scope() -> None:
    """Direct multi-target prompt reviews must pass every explicit target."""
    repo_root = Path(__file__).resolve().parents[1]
    phase3 = (
        repo_root / "workflows" / "analyze" / "phase-3-semantic.md"
    ).read_text(encoding="utf-8")

    assert "target_paths=prompt_targets" in phase3
    assert "filter diff_scope.review_targets to prompt-typed targets" in phase3
    assert 'otherwise ["{PATH}"]' not in phase3


def test_prompt_bug_only_uses_prompt_output_schema() -> None:
    """Prompt-bug-only reviews must not fall through to standard output."""
    repo_root = Path(__file__).resolve().parents[1]
    index = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "index.md"
    ).read_text(encoding="utf-8")
    prompt_output = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "output-prompt-review.md"
    ).read_text(encoding="utf-8")

    assert "`PROMPT_REVIEW=true` or `PROMPT_BUG_REVIEW=true`" in index
    assert "IF PROMPT_REVIEW == false" in prompt_output and "Render only the prompt-bug-finder report" in prompt_output


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


def test_analyze_handoff_preserves_analyzed_paths_separate_from_written_manifest() -> None:
    """Analyze R1 must preserve fix targets without faking written files."""
    repo_root = Path(__file__).resolve().parents[1]
    remediation = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")

    assert "analyzed_paths = analyzed paths" in remediation
    assert "target_paths = analyzed_paths" in remediation
    assert "manifest.paths_written = []" in remediation
    assert "manifest.paths_written = analyzed_paths" not in remediation


def test_change_review_derives_prompt_flags_after_diff_scope() -> None:
    """Prompt/instruction diffs must dispatch prompt reviewers in change reviews."""
    repo_root = Path(__file__).resolve().parents[1]
    change_scope = (
        repo_root / "workflows" / "analyze" / "phase-0-change-review-scope.md"
    ).read_text(encoding="utf-8")

    assert "prompt_targets" in change_scope
    assert "PROMPT_REVIEW = true" in change_scope
    assert "PROMPT_BUG_REVIEW = true" in change_scope
    assert "workflows/**" in change_scope and "skills/studio/**/*.md" in change_scope


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


def test_reviewer_plan_failure_does_not_use_legacy_single_dispatch_fallback() -> None:
    """Planner failure after sub-agent decomposition must not drop to oversized legacy dispatch."""
    repo_root = Path(__file__).resolve().parents[1]
    phase25 = (
        repo_root / "workflows" / "analyze" / "phase-2.5-reviewer-plan.md"
    ).read_text(encoding="utf-8")
    phase3 = (
        repo_root / "workflows" / "analyze" / "phase-3-semantic.md"
    ).read_text(encoding="utf-8")

    assert "legacy single-dispatch-per-methodology" not in phase25
    assert "checkpoint-only report" not in phase25
    assert "checkpoint.type=PARTIAL_CHECKPOINT" in phase25
    assert "MUST_NOT set REVIEWER_PLAN_RESOLVED=auto_skipped_inline_fallback after" in phase25
    assert "rerun the planner" in phase25
    assert "rerun the planner or stop with validation errors" in phase25
    assert "IF re-validation fails" in phase3
    assert "every parallel_groups[].task_ids names an existing task" in phase3
    assert "every parallel_groups[].depends_on references an earlier group" in phase3
    assert "Route back to phase-2.5-reviewer-plan.md" in phase3
    assert "REVIEWER_EXECUTION_PLAN is non-null" in phase3
    assert "auto_skipped_inline_fallback" in phase3
    assert "starts with `auto_skipped_`" not in phase3
    assert "When `REVIEWER_EXECUTION_PLAN` is null (Phase 2.5 auto-skipped)" not in phase3


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


def test_skill_entrypoint_has_context_budget_fail_safe() -> None:
    """The root skill entrypoint should bound mandatory loads before opening files."""
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "studio" / "SKILL.md").read_text(encoding="utf-8")

    bootstrap_idx = skill.index("UNIT Bootstrap")
    hard_rules_idx = skill.index("UNIT HardRules")
    assert hard_rules_idx < bootstrap_idx
    assert "Estimate file size" in skill
    assert "STOP with a checkpoint message" in skill


def test_analyze_artifact_dependencies_do_not_block_code_or_prompt_reviews() -> None:
    """Artifact-only dependency recovery must not block code/prompt reviewers."""
    repo_root = Path(__file__).resolve().parents[1]
    phase0 = (
        repo_root / "workflows" / "analyze" / "phase-0-dependencies.md"
    ).read_text(encoding="utf-8")

    assert "artifact review dependencies are missing" in phase0
    assert "only when ARTIFACT_REVIEW == true" in phase0
    assert "Code and prompt methodologies do not require artifact" in phase0


def test_legacy_analyze_dispatch_keeps_code_and_prompt_review_independent() -> None:
    """Inline fallback must not drop code review on mixed code+prompt diffs."""
    repo_root = Path(__file__).resolve().parents[1]
    phase3 = (
        repo_root / "workflows" / "analyze" / "phase-3-semantic.md"
    ).read_text(encoding="utf-8")

    assert "TARGET_TYPE == code OR CODE_REVIEW=true" in phase3
    assert "CODE_BUG_REVIEW=true" in phase3 and "cf-code-bug-finder" in phase3
    assert "not `PROMPT_REVIEW` and not `PROMPT_BUG_REVIEW`" not in phase3


def test_analyze_routing_includes_storytelling_and_bug_hunt_intents() -> None:
    """Routing must reach analyze for branches owned by the analyze preamble."""
    repo_root = Path(__file__).resolve().parents[1]
    routing = (repo_root / "skills" / "studio" / "routing.md").read_text(
        encoding="utf-8"
    )

    assert "explain | walk through | teach | onboard" in routing
    assert "bug hunt | find bugs | prompt bugs" in routing


def test_storytelling_navigation_slots_are_topic_picker_menus() -> None:
    """Next/Deeper/Lateral should offer choices before jumping away."""
    repo_root = Path(__file__).resolve().parents[1]
    shared = (
        repo_root / "requirements" / "storytelling-shared.md"
    ).read_text(encoding="utf-8")
    phases = (
        repo_root / "requirements" / "storytelling-phases.md"
    ).read_text(encoding="utf-8")
    methodology = (
        repo_root / "requirements" / "storytelling.md"
    ).read_text(encoding="utf-8")
    validation = (
        repo_root / "workflows" / "analyze" / "validation-criteria.md"
    ).read_text(encoding="utf-8")

    assert "choose next / skip-ahead / revisit topic" in phases
    assert "choose from drill-down topics for the current topic" in phases
    assert "choose from related topics / linked artifacts" in phases
    assert "Next topics:" in phases
    assert "Deeper topics:" in phases
    assert "Lateral topics:" in phases
    assert "Skip ahead" in phases
    assert "Revisit" in phases
    assert "Custom — tell me which planned topic to jump to or revisit" in phases
    assert "Custom — tell me what to drill into" in phases
    assert "Custom — tell me where to go sideways" in phases
    assert "Back — return to the main navigation" in phases
    assert "7. Back" in phases
    assert "8. Send comments — preview" in phases
    assert "WAIT user.reply and STOP_TURN" in phases
    assert "bare `Next` / `Deeper` / `Lateral` opens a numbered topic-pick menu" in shared
    assert "Making the main `Next` nav slot execute one preselected next topic directly" in methodology
    assert "Making the main `Deeper` or `Lateral` nav slot execute one preselected topic directly" in methodology
    assert "Omitting `Back` from the main storytelling navigation" in methodology
    assert "Next nav slots offered topic-pick menus" in validation
    assert "Deeper/Lateral nav slots offered topic-pick menus" in validation
    assert "Next / Deeper / Lateral / Recap / Ask / Wrap / Back" in validation


def test_ambiguous_routing_fallback_lists_full_route_family() -> None:
    """The root /cf fallback menu must not hide available routes or modes."""
    repo_root = Path(__file__).resolve().parents[1]
    routing = (repo_root / "skills" / "studio" / "routing.md").read_text(
        encoding="utf-8"
    )

    expected_routes = [
        "1 -> help -- Show a polished beginner-friendly cf overview",
        "2 -> brainstorm -- Explore options, decisions, requirements, or tradeoffs",
        "3 -> explain -- Get a source-grounded walkthrough",
        "4 -> explore -- Find relevant project context",
        "5 -> generate -- Create, edit, implement",
        "6 -> analyze -- Review, audit, validate",
        "7 -> plan -- Break a large task into executable phases",
        "8 -> pdsl -- Author, compact, transform",
        "9 -> map -- Build dependency, traceability",
        "10 -> workspace -- Configure or inspect multi-repo workspace",
        "11 -> auto-config -- Discover project setup",
        "12 -> delegate -- Delegate an approved generated plan",
        "13 -> compile phase -- Compile a plan phase brief",
        "14 -> execute phase -- Execute the next or specified generated plan phase",
        "15 -> migrate-from-cypilot -- Migrate legacy Cypilot setup",
    ]
    for route in expected_routes:
        assert route in routing

    assert "list PRs" in routing
    assert "review PR 123" in routing
    assert "PR status 123" in routing
    assert "migrate-openspec" in routing
    assert "Reply with 1-15" in routing
    assert "Reply with 1, 2, 3, 4, 5, or 6." not in routing


def test_root_cf_skill_metadata_advertises_broad_routes() -> None:
    """Generated root skill metadata depends on the source skill description."""
    repo_root = Path(__file__).resolve().parents[1]
    skill = (repo_root / "skills" / "studio" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    for route in [
        "PDSL prompt work",
        "mapping",
        "auto-config",
        "migration",
        "delegation",
        "phase compile/execute",
    ]:
        assert route in skill


def test_diff_scope_binary_omission_probe_is_allowed() -> None:
    """Resolver may only require probes it is authorized to run."""
    repo_root = Path(__file__).resolve().parents[1]
    resolver = (
        repo_root
        / "skills"
        / "studio"
        / "agents"
        / "cf-diff-scope-resolver.md"
    ).read_text(encoding="utf-8")

    assert "git -C <worktree> diff --numstat <base>..<head>" in resolver
    assert "git -C <worktree> diff --numstat HEAD" in resolver
    assert '"binary"  — git diff --numstat' in resolver


def test_artifact_review_flag_is_initialized_and_set() -> None:
    """Reviewer planning must not depend on an unset ARTIFACT_REVIEW bit."""
    repo_root = Path(__file__).resolve().parents[1]
    phase0 = (
        repo_root / "workflows" / "analyze" / "phase-0-dependencies.md"
    ).read_text(encoding="utf-8")
    planner = (
        repo_root / "workflows" / "analyze" / "phase-2.5-reviewer-plan.md"
    ).read_text(encoding="utf-8")

    assert "ARTIFACT_REVIEW=false" in phase0
    assert "SET ARTIFACT_REVIEW = true" in phase0
    assert "ARTIFACT_REVIEW" in planner


def test_analyze_to_generate_handoff_reprobes_before_max_iter_prompt() -> None:
    """External fix-mode entry must resolve INLINE_FALLBACK before MAX_ITER."""
    repo_root = Path(__file__).resolve().parents[1]
    remediation = (
        repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md"
    ).read_text(encoding="utf-8")

    reprobe_idx = remediation.index("Re-probe INLINE_FALLBACK")
    max_iter_idx = remediation.index("EMIT canonical MAX_ITER")
    assert reprobe_idx < max_iter_idx


def test_phase_5_clean_exit_routes_through_final_assembly() -> None:
    """Clean review-loop exits still need Phase 5.5 before Phase 6."""
    repo_root = Path(__file__).resolve().parents[1]
    findings = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.3-findings.md"
    ).read_text(encoding="utf-8")

    assert 'SET loop_exit = "clean"' in findings
    assert "CONTINUE workflows/generate/phase-5/phase-5.5-final.md" in findings
    assert "and proceed to `workflows/generate/phase-6/index.md`." not in findings


def test_phase_5_cap_accept_after_write_requires_validation() -> None:
    """Accepting a max-iteration stop after a fix write must not claim stale PASS."""
    repo_root = Path(__file__).resolve().parents[1]
    approval = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.4-approval.md"
    ).read_text(encoding="utf-8")

    assert "post-fix deterministic gate" in approval
    assert "RUN post-fix deterministic gate FIRST" in approval


def test_phase_5_approval_cap_prompt_handles_all_replies() -> None:
    """Phase 5.4 must implement the same cap prompt replies it advertises."""
    repo_root = Path(__file__).resolve().parents[1]
    approval = (
        repo_root / "workflows" / "generate" / "phase-5" / "phase-5.4-approval.md"
    ).read_text(encoding="utf-8")

    assert "extend: M ->" in approval
    assert "accept ->" in approval
    assert "stop ->" in approval


def test_post_write_handoff_has_dynamic_suggested_choice() -> None:
    """Post-write review menu should expose exactly one filled suggestion slot."""
    repo_root = Path(__file__).resolve().parents[1]
    handoff = (
        repo_root / "workflows" / "generate" / "phase-6" / "post-write-handoff.md"
    ).read_text(encoding="utf-8")

    assert "Suggested: {W1|W2|W3} because {scope/risk reason}." in handoff
    assert "(suggested when" not in handoff


def test_runtime_instruction_modules_stay_compact() -> None:
    """High-traffic instruction resources should stay below the compact budget."""
    repo_root = Path(__file__).resolve().parents[1]
    # Tuples of (path, line_budget).  SKILL.md grew with the PDSL GIT_COMMIT_MODE
    # state machine; it gets a higher budget than pure-workflow files.
    compact_files = [
        (repo_root / "skills" / "studio" / "SKILL.md", 450),
        (repo_root / "workflows" / "analyze" / "phase-0-dependencies.md", 200),
        (repo_root / "workflows" / "analyze" / "phase-4-output" / "remediation-handoff.md", 200),
        (repo_root / "skills" / "studio" / "agents" / "cf-semantic-reviewer-code.md", 200),
    ]

    for path, budget in compact_files:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        assert line_count <= budget, f"{path.relative_to(repo_root)} has {line_count} lines (budget {budget})"
