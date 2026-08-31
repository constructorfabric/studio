# Vulture whitelist — false positives that should be ignored.
# Each entry is a dummy usage of the flagged name.

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
from studio.utils.eval_harness import ReferencePresenceScorer, Scenario, ScorerKind, run_suite
from studio.utils.eval_judge import Gold
from studio.utils.manifest import ManifestLayerState

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
