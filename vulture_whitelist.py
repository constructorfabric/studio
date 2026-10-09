# Vulture whitelist — false positives that should be ignored.
# Each entry is a dummy usage of the flagged name.
#
# RUNNING A "REMOVAL TRIGGER" GREP. Several entries below say to delete them once a real
# consumer appears, and name a grep for finding one. Run it like this, or it answers the
# wrong question:
#
#     grep -rn --include='*.py' NAME . | grep -v vulture_whitelist.py | grep -v '/tests/'
#
# **This file imports every name it whitelists**, so an unqualified grep always reports at
# least one hit and the instruction reads as already satisfied — which would have the entry
# deleted while the name is still genuinely unused, failing the dead-code gate. Two further
# kinds of hit are not consumers either: the defining module itself, and a mention in a
# docstring or comment (a module may name another in its own docstring, for instance, without
# importing anything from it). A consumer is production code that imports
# and calls the name. Tests do not count; vulture does not scan them, which is why the
# entry is needed at all. Raised in review, where the instructions were unqualified.

from studio.utils.ui import _UI
from studio.ralphex_export import (
    read_handoff_status,
    check_completed_plans,
    run_validation_commands,
    report_handoff,
)
from studio.commands.agents import _AgentEntry, _SkillEntry, _MergedComponents, _ProvenanceRecord
from studio.commands.kit import _read_conf_version
from studio.commands.resolve_vars import assemble_component
from studio.utils.context import LoadedKit
from studio.utils.doc_index import annotate_section_summary, diff_stale_sections
from studio.utils.eval_harness import ReferencePresenceScorer, Scenario, ScorerKind, run_suite
from studio.utils.eval_judge import Gold
from studio.utils.artifact_quality import (
    ArtifactFinding,
    finding_json_schema,
)
from studio.utils.manifest import ManifestLayerState
from studio.utils.okf import write_concept_file
from studio.utils.change_summary import (
    resolve_window,
    select_events,
    group_by_run,
    link_changed_files,
    ChangeWindow,
    EventSelection,
    LinkReport,
    RUN_UNATTRIBUTED,
)

is_json = _UI.is_json  # staticmethod alias exposed on the ui singleton

# Agent-facing handoff API: called by the cf-ralphex agent prompt,
# not by production code paths directly. See skills/studio/agents/cf-ralphex.md.
read_handoff_status
check_completed_plans
run_validation_commands
report_handoff

_AgentEntry  # used as string type hint in agents.py
_SkillEntry  # used as string type hint in agents.py
_MergedComponents  # used as string type hint in agents.py
_ProvenanceRecord  # used as string type hint in agents.py
_read_conf_version  # re-exported compatibility helper used by tests and callers
assemble_component  # public API for future use
_ = LoadedKit.constraints_paths  # public context field for multi-constraints consumers
_ = Scenario.gold_path  # part of the scenario format; consumed by the advisory judge
_ = ScorerKind.ADVISORY  # public gate-contract value used by the advisory judge
ReferencePresenceScorer  # minimal seam example + gate-contract test fixture (see tests)
run_suite  # public disk-loading convenience wrapper; cmd_eval uses run_suite_over, tests use this
_ = Gold.rules_assessed  # part of the gold format; consumed by per-rule judge scoring (future)
INCLUDE_ERROR = ManifestLayerState.INCLUDE_ERROR  # valid enum value for future use

# doc-index summary annotation and section-level staleness diff: called by
# a future partial-rebuild caller (an LLM re-summarizing only changed
# sections), not yet reached from production paths. Exercised by tests. See
# skills/studio/scripts/studio/utils/doc_index.py.
annotate_section_summary  # noqa: B018
diff_stale_sections  # noqa: B018

# OKF concept-file writer: called by a future external LLM caller after it
# has actually produced a summary, not yet reached from production paths.
# Exercised by tests. See skills/studio/scripts/studio/utils/okf.py.
write_concept_file  # noqa: B018

# cfs map module — symbols retained for layout/configuration completeness.
from studio.commands.map.layout import MAX_ROW_W  # noqa: E402
from studio.commands.map.categorize import OverrideCategory  # noqa: E402

MAX_ROW_W  # documented packing cap, retained for future tuning
_oc = OverrideCategory(name="", paths=[], color=None, background=None)
_oc.background  # set by md-map.toml [categories.<name>.style] entries

# decision_log public API — the recorder entrypoints, correlation id, and read view.
# Wired by the forthcoming command instrumentation (dispatch wrapper) and called by
# log consumers; not yet reached from production paths. Exercised by tests.
# See skills/studio/scripts/studio/utils/decision_log.py.
from studio.utils.decision_log import (  # noqa: E402
    EVENTS,
    new_decision_id,
    record_routing,
    record_dispatch,
    record_validation,
    record_review,
    record_escalation,
    record_invocation,
    record_read,
    summarize,
)

EVENTS  # noqa: B018
new_decision_id  # noqa: B018
record_routing  # noqa: B018
record_dispatch  # noqa: B018
record_validation  # noqa: B018
record_review  # noqa: B018
record_escalation  # noqa: B018
record_invocation  # noqa: B018
summarize  # noqa: B018

# record_read: called by a future external caller once a read-and-answer step
# actually fires (an agent doing the real read), not yet reached from
# production paths. Exercised by tests. See
# skills/studio/scripts/studio/utils/decision_log.py.
record_read  # noqa: B018

# eval_semantic public API — the semantic-coverage engine. Library + tests only for now;
# the `cfs` surface and coverage-report integration are the follow-up, so these are not yet
# reached from a production path. Exercised by tests.
# See skills/studio/scripts/studio/utils/eval_semantic.py.
from studio.utils.eval_semantic import (  # noqa: E402
    reference_stub_judge,
    assess,
    resolve_requirement,
    load_gold,
    calibrate,
    SemanticFinding,
    SemanticGap,
    SemanticReport,
    SemanticCalibration,
)

reference_stub_judge  # noqa: B018
assess  # noqa: B018
resolve_requirement  # noqa: B018
load_gold  # noqa: B018
calibrate  # noqa: B018
SemanticFinding.evidence_ok  # noqa: B018
SemanticFinding.forced  # noqa: B018
SemanticGap.block_id  # noqa: B018
SemanticGap.path  # noqa: B018
SemanticGap.start_line  # noqa: B018
SemanticGap.reason  # noqa: B018
SemanticReport.presumed_covered  # noqa: B018
SemanticReport.skipped_excluded  # noqa: B018
SemanticReport.schema_version  # noqa: B018
SemanticCalibration.accuracy  # noqa: B018
SemanticCalibration.consistency  # noqa: B018
SemanticCalibration.runs_per_scenario  # noqa: B018
SemanticCalibration.per_case  # noqa: B018
SemanticCalibration.excluded  # noqa: B018
SemanticCalibration.judge  # noqa: B018
SemanticCalibration.schema_version  # noqa: B018

# Change-summary core: the window, event-selection and linkage API the
# change-summary command will consume. Landed ahead of its CLI wrapper so the
# pure logic is reviewable on its own, so nothing in production calls it yet.
#
# Listed here are the module's entry points plus the result fields that only an
# external consumer reads. Fields the module reads itself are deliberately absent:
# an entry for one of those is a false positive that suppresses a real dead-code
# signal, so if vulture stops flagging a name here it should be removed rather
# than kept "just in case".
resolve_window  # noqa: B018
select_events  # noqa: B018
group_by_run  # noqa: B018
ChangeWindow.base_ref  # noqa: B018
ChangeWindow.base_sha  # noqa: B018
EventSelection.scanned  # noqa: B018
EventSelection.undated  # noqa: B018
EventSelection.skipped_lines  # noqa: B018
link_changed_files  # noqa: B018
LinkReport.linked  # noqa: B018
LinkReport.declaring  # noqa: B018
LinkReport.deleted  # noqa: B018
LinkReport.unreadable  # noqa: B018
LinkReport.not_a_file  # noqa: B018
LinkReport.examined  # noqa: B018
LinkReport.truncated  # noqa: B018
EventSelection.runless  # noqa: B018
EventSelection.log_overridden  # noqa: B018
RUN_UNATTRIBUTED  # noqa: B018

# Artifact-quality finding model — public API consumed by detectors + the presentation layer,
# which land in later tasks (feature `cpt-studio-feature-artifact-quality`; the scanning flow
# `cpt-studio-flow-artifact-quality-assess` in architecture/features/artifact-quality.md), so these
# are unreferenced within the scanned scope until then. REMOVAL TRIGGER — delete each entry once a
# real consumer imports it: ArtifactFinding / finding_json_schema when the first detector or the
# `cfs artifact-quality` command lands (i.e. once `cpt-studio-flow-artifact-quality-assess` is
# implemented — grep that id here and check its `[ ]`→`[x]` in the feature doc). (VERDICT_UNJUDGEABLE
# is now referenced in-module by the unjudgeable-metadata check, so it no longer needs an entry here.)
# If a later refactor leaves one genuinely unused, delete its line rather than keep suppressing it.
ArtifactFinding  # noqa: B018
finding_json_schema  # noqa: B018

# cpt_reference_scan.graph_for — the def↔ref graph view for the artifact-quality
# gap / traceability / contradiction detectors (later tasks). The four query commands
# consume references / definitions / scan_records now; graph_for is unreferenced until
# the first detector imports it. REMOVAL TRIGGER — delete this entry once a detector
# imports graph_for (grep `graph_for` per the header above, discounting this file; i.e.
# once `cpt-studio-flow-artifact-quality-assess` is implemented — grep that id in
# architecture/features/artifact-quality.md and check its `[ ]`→`[x]`).
# The algo itself is declared in architecture/features/traceability-validation.md (### CPT Reference Scan).
from studio.utils.cpt_reference_scan import graph_for  # noqa: E402
graph_for  # noqa: B018

# plan_decisions.PhaseOutlook.will_run — the forecast a caller reads, with no caller yet.
# `preflight` returns `blocked_on` and uses `PlanLookup.resolved` itself; `will_run` is the
# shape the consumer wants and the consumer is the enforcement increment, which does not
# import this module yet. REMOVAL TRIGGER — delete this entry once a dispatch module's
# Python reads it (grep `will_run` per the header above, discounting this file). Deleting the
# property instead would have the first consumer reinvent `not blocked_on` under a name
# that reads as permission, which this one deliberately is not.
from studio.utils.plan_decisions import PhaseOutlook  # noqa: E402
PhaseOutlook.will_run  # noqa: B018

# gate_surface — the static walk that counts how many gates a workflow can reach, and the
# fields of its result that **nothing reads**. The walk records a baseline before the
# autonomy default is flipped, and the comparison that will read these is a later task.
# Each is a separate number that comparison needs, which is why they are kept rather than
# collapsed into the one total the walk could return today.
#
# The list was three entries longer and said the same thing about all of them. Review
# pointed out that `_warn_about_gaps` reads `tree`, `missing_loads` and
# `duplicate_menu_definitions` to build its warning text — a production read, so the stated
# reason was false for them and the entries were suppressing nothing. They are gone. Each
# remaining entry was checked the only way that settles it: removed, with `make vulture-ci`
# re-run, and kept only where the scan then failed.
#
# An earlier version of this comment argued instead that the numbers were already in use
# because a person had read them and sized a decision on them. Review's first pass called
# that a contradiction with "nothing consumes them yet" in the same block; its second pass
# made the sharper point, which is that the decision it cited appears nowhere in this
# repository — so to anyone reading here, a load-bearing justification rested on something
# they cannot check. The claim is gone rather than restated: what the repository can show
# is that these fields are computed, tested, and unread, and that is enough to justify the
# entry on its own.
#
# REMOVAL TRIGGER — delete these once a command or report reads the fields (grep
# `WorkflowSurface` or `GateSurface` per the header above, discounting this file). The
# algorithm is declared in architecture/features/developer-experience.md (### Count the
# Reachable Gate Surface).
from studio.utils.gate_surface import GateSurface, WorkflowSurface  # noqa: E402
# `WorkflowSurface`'s fields carry no default, so they are instance attributes only --
# `WorkflowSurface.files_reached` is not a class attribute and raises `AttributeError`, unlike
# every other bare `Class.field` entry here (those fields have defaults, so the class attribute
# exists). Marked used on a dummy instance instead: vulture matches the attribute name either
# way, and this stays evaluable, which the header's "dummy usage" convention relies on.
_wf_surface = WorkflowSurface(workflow="", files_reached=0, halt_sites=0, stop_sites=0,
                              non_stop_sites=0, distinct_menus=0)
_wf_surface.files_reached  # noqa: B018
_wf_surface.stop_sites  # noqa: B018
_wf_surface.halt_sites  # noqa: B018
_wf_surface.non_stop_sites  # noqa: B018
_wf_surface.distinct_menus  # noqa: B018
GateSurface.distinct_menu_definitions  # noqa: B018
GateSurface.concentration  # noqa: B018

# gate_chain — the autonomy filter chain skeleton (increment 1). It orders the two filter
# classes and enforces that a safety-added stop is final and the declared type is a ceiling,
# but no filter and no runtime seam imports it yet: the real filters (scope, reversibility,
# blocker; already-answered, plan-and-ledger) and the CLI/runtime wiring are later increments.
# Built before the consumers deliberately, so the ordering invariant exists before the first
# filter can lean on it. REMOVAL TRIGGER — delete each line once a filter increment or the
# runtime seam references it (grep `gate_chain` / `resolve_gate` outside gate_chain.py and its
# tests). The algorithm is declared in architecture/features/core-infra.md (### The Gate Chain).
from studio.utils.gate_chain import SafetyVerdict, EconomyVerdict, resolve_gate  # noqa: E402
_ = resolve_gate
_ = SafetyVerdict.ADD_STOP
_ = EconomyVerdict.no_opinion
_ = EconomyVerdict.indeterminate

# gate_filters -- the three safety filters (reversibility, scope, blocker), and `BLOCKING` (the
# token the ceiling excludes, now referenced only by its binding test since the ceiling checks
# the eligible set instead). Not wired to a runtime yet: the seam that builds a Gate and runs the
# chain is a later increment. REMOVAL TRIGGER -- delete each once the runtime seam constructs and
# runs a filter (grep `ReversibilityFilter`/`ScopeFilter`/`BlockerFilter` outside gate_filters.py
# and its tests). The algorithm is declared in architecture/features/core-infra.md (### The Gate Chain).
from studio.utils.gate_chain import BLOCKING  # noqa: E402
from studio.utils.gate_filters import BlockerFilter, PlanEconomyFilter, ReversibilityFilter, ScopeFilter  # noqa: E402
_ = BLOCKING
_ = ReversibilityFilter
_ = ScopeFilter
_ = BlockerFilter

# extract_declared_gate_keys -- surfaces a source's declared gate keys so a corpus-level check can
# enforce cross-file KEY uniqueness. Its only caller today is the uniqueness guard in
# tests/test_pdsl_keywords.py (a corpus test, since `cfs validate` never parses PDSL and the menu
# files are read there); a CLI/runtime consumer is a later increment. REMOVAL TRIGGER -- delete once
# a non-test caller references it (grep `extract_declared_gate_keys` outside pdsl.py and its tests).
from studio.utils.pdsl import extract_declared_gate_keys  # noqa: E402
_ = extract_declared_gate_keys

# PlanEconomyFilter -- the one economy filter (resolves a gate from the plan). Same status as the
# safety filters above: built before the runtime seam that constructs a Gate and runs the chain
# (a later increment). REMOVAL TRIGGER -- delete once that seam references it (grep
# `PlanEconomyFilter` outside gate_filters.py and its tests).
_ = PlanEconomyFilter

# plan_items -- the deliverable-item reader is now consumed by commands/verify_completion.py. Two
# item fields are not read in production yet: `authored_done` (the summary increment will compare the
# author's claim against the verified verdict) and `verify_kind` (the deterministic-check increment
# will set it to a value other than `explicit`). REMOVAL TRIGGER -- delete each once a non-test caller
# reads it (grep `authored_done` / `verify_kind` outside plan_items.py and its tests).
from studio.utils.plan_items import PlanItem  # noqa: E402
_plan_item = PlanItem(phase=0, ordinal=0, text="", authored_done=False)
_ = _plan_item.authored_done
_ = _plan_item.verify_kind

# artifact-quality structural detectors (HYP-2720 T2): the public detector entry point is
# consumed by the `cfs artifact-quality` command, which lands in a later task. Until then it
# has no production caller. REMOVAL TRIGGER -- delete once the command imports it (grep
# `detect_exact_duplication` outside artifact_quality_detectors.py and its tests).
from studio.utils.artifact_quality_detectors import detect_exact_duplication  # noqa: E402
_ = detect_exact_duplication
