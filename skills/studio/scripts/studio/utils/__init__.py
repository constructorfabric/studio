"""
Studio Validator - Utility Functions

Utility modules for file operations and markdown parsing.

@cpt-algo:cpt-studio-algo-core-infra-config-management:p1
"""

from .files import (
    cfg_get_str,
    find_project_root,
    load_project_config,
    studio_root_from_project_config,
    find_studio_directory,
    load_studio_config,
    load_artifacts_registry,
    iter_registry_entries,
    studio_root_from_this_file,
    load_text,
)

from .parsing import (
    parse_required_sections,
    find_present_section_ids,
    split_by_section_letter,
    split_by_section_letter_with_offsets,
    field_block,
    has_list_item,
    extract_backticked_ids,
)

from .language_config import (
    LanguageConfig,
    load_language_config,
    build_studio_begin_regex,
    build_studio_end_regex,
    build_no_studio_begin_regex,
    build_no_studio_end_regex,
    DEFAULT_FILE_EXTENSIONS,
    EXTENSION_COMMENT_DEFAULTS,
    comment_defaults_for_extensions,
)

from .artifacts_meta import (
    ArtifactsMeta,
    SystemNode,
    Artifact,
    CodebaseEntry,
    Kit,
    load_artifacts_meta,
)

from .codebase import (
    CodeFile,
    ScopeMarker,
    BlockMarker,
    CodeReference,
    load_code_file,
    validate_code_file,
    cross_validate_code,
)

from .context import (
    StudioContext,
    LoadedKit,
    SourceContext,
    WorkspaceContext,
    collect_artifacts_to_scan,
    determine_target_source,
    get_context,
    get_expanded_meta,
    get_primary_context,
    resolve_adapter_context,
    resolve_artifacts_for_command,
    resolve_target_and_artifacts,
    set_context,
    ensure_context,
    is_workspace,
)

from .workspace import (
    VALID_ROLES,
    SourceEntry,
    TraceabilityConfig,
    NamespaceRule,
    ResolveConfig,
    WorkspaceConfig,
    find_workspace_config,
    require_project_root,
    load_inline_config,
)

from .layer_discovery import (
    discover_layers,
)
from .codebase import __all__ as _codebase_all
from .context import __all__ as _context_all
from .language_config import __all__ as _language_config_all
from .workspace import __all__ as _workspace_all

_PUBLIC_LANGUAGE_EXPORTS = [
    name for name in _language_config_all
    if name != "DEFAULT_SINGLE_LINE_COMMENTS"
]
_PUBLIC_CONTEXT_EXPORTS = [
    name for name in _context_all
    if name != "get_workspace_upgrade_error"
]
_PUBLIC_WORKSPACE_EXPORTS = [
    name for name in _workspace_all
    if name != "validate_source_name"
]

__all__ = [
    # File operations
    "cfg_get_str",
    "find_project_root",
    "load_project_config",
    "studio_root_from_project_config",
    "find_studio_directory",
    "load_studio_config",
    "load_artifacts_registry",
    "iter_registry_entries",
    "studio_root_from_this_file",
    "load_text",
    # Parsing utilities
    "parse_required_sections",
    "find_present_section_ids",
    "split_by_section_letter",
    "split_by_section_letter_with_offsets",
    "field_block",
    "has_list_item",
    "extract_backticked_ids",
    # Artifacts metadata
    "ArtifactsMeta",
    "SystemNode",
    "Artifact",
    "CodebaseEntry",
    "Kit",
    "load_artifacts_meta",
    # Layer discovery
    "discover_layers",
    *_PUBLIC_LANGUAGE_EXPORTS,
    *_codebase_all,
    *_PUBLIC_CONTEXT_EXPORTS,
    *_PUBLIC_WORKSPACE_EXPORTS,
]
