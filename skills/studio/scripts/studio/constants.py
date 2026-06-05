"""
Constructor Studio Validator - Constants and Regex Patterns

All regular expressions and global constants used throughout the Constructor Studio validation system.
Extracted for easier maintenance and modification by both humans and AI agents.

@cpt-algo:cpt-studio-algo-core-infra-config-management:p1
@cpt-algo:cpt-studio-algo-traceability-validation-validate-structure:p1
"""
# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-headings

import re

# === PROJECT CONFIGURATION ===

ARTIFACTS_REGISTRY_FILENAME = "artifacts.toml"
WORKSPACE_CONFIG_FILENAME = ".cf-workspace.toml"

# Pipeline directive emitted into generated entrypoints (root @cf:root-agents
# managed block and per-skill/workflow follow-protocol preamble) so every agent
# resolves and enforces instruction prerequisites before applying user intent.
ROOT_AGENTS_PIPELINE_INSTRUCTION = (
    "ALWAYS resolve and enforce prerequisites of skills/workflows/commands "
    "BEFORE applying user intent."
)

# === ARTIFACT STRUCTURE PATTERNS ===

SECTION_RE = re.compile(r"^###\s+Section\s+([A-Z0-9]+):\s+(.+?)\s*$")
HEADING_ID_RE = re.compile(r"^#{1,6}\s+([A-Z])\.\s+.*$")

# Field header pattern
FIELD_HEADER_RE = re.compile(r"^\s*[-*]?\s*\*\*([^*]+)\*\*:\s*(.*)$")
# instead of hardcoded field names. Templates are the source of truth.
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-headings
