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
from studio.commands.resolve_vars import assemble_component
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
assemble_component  # public API for future use
INCLUDE_ERROR = ManifestLayerState.INCLUDE_ERROR  # valid enum value for future use

# cfs map module — symbols retained for layout/configuration completeness.
from studio.commands.map.layout import MAX_ROW_W  # noqa: E402
from studio.commands.map.categorize import OverrideCategory  # noqa: E402

MAX_ROW_W  # documented packing cap, retained for future tuning
_oc = OverrideCategory(name="", paths=[], color=None, background=None)
_oc.background  # set by md-map.toml [categories.<name>.style] entries
