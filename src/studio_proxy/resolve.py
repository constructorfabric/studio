"""
Skill Target Resolution

Walks directory tree to find project-installed skill, falls back to cache.

@cpt-algo:cpt-studio-algo-core-infra-resolve-skill:p1
"""

# @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-resolve-helpers
import os
import re
import tomllib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

MARKER_START = "<!-- @cf:root-agents -->"

_TOML_FENCE_RE = re.compile(r"```toml\s*\n(.*?)```", re.DOTALL)

def find_project_root(start_dir: Optional[Path] = None) -> Optional[Path]:
    """Find the project root by walking up looking for AGENTS.md with @cf:root-agents marker."""
    current = (start_dir or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        agents_file = parent / "AGENTS.md"
        if agents_file.is_file():
            try:
                head = agents_file.read_text(encoding="utf-8")[:512]
            except OSError:
                continue
            if MARKER_START in head:
                return parent
    return None

def _parse_toml_from_markdown(text: str) -> Dict[str, Any]:
    """Extract and merge all ``toml`` fenced code blocks from markdown."""
    merged: Dict[str, Any] = {}
    for m in _TOML_FENCE_RE.finditer(text):
        try:
            data = tomllib.loads(m.group(1))
            merged.update(data)
        except (tomllib.TOMLDecodeError, ValueError):
            continue
    return merged

def read_cf_studio_path(project_root: Path) -> Optional[str]:
    """
    Read the ``cf-studio-path`` variable from root AGENTS.md.

    Returns the install directory path (relative to project root) or None.
    """
    agents_file = project_root / "AGENTS.md"
    if not agents_file.is_file():
        return None
    try:
        content = agents_file.read_text(encoding="utf-8")
    except OSError:
        return None
    if MARKER_START not in content:
        return None

    toml_data = _parse_toml_from_markdown(content)
    value = toml_data.get("cf-studio-path")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None

def find_install_dir(project_root: Path) -> Optional[str]:
    """
    Determine the Constructor Studio install directory relative to project root.

    Resolution order:
    1. Read ``cf-studio-path`` variable from AGENTS.md managed block
    2. Scan for the default install directory name
    """
    from_var = read_cf_studio_path(project_root)
    if from_var is not None:
        return from_var

    for candidate in (".cf-studio", ".cf", ".cf-constructor"):
        if (project_root / candidate / "skills").is_dir():
            return candidate

    return None
# @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-resolve-helpers

# @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-resolve-helpers
def get_cache_dir() -> Path:
    """Return the global Constructor Studio cache directory.

    Honors the ``CFS_CACHE_DIR`` environment variable when set; otherwise
    defaults to ``~/.cf-studio/cache/``.
    """
    override = os.environ.get("CFS_CACHE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cf-studio" / "cache"

def get_version_file() -> Path:
    """Return the version marker file path."""
    return get_cache_dir() / ".version"
# @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-resolve-helpers

def find_project_skill(start_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Find project-installed skill by reading ``cf-studio-path`` variable from root AGENTS.md.

    Walks up from start_dir to find AGENTS.md with @cf:root-agents marker,
    reads the ``cf-studio-path`` variable to get the install directory, then looks
    for the skill entry point there.

    Returns path to the skill entry point (studio.py) or None.
    """
    # @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-walk-parents
    project_root = find_project_root(start_dir)
    if project_root is None:
        return None

    install_dir = read_cf_studio_path(project_root)
    if install_dir is None:
        return None
    # @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-walk-parents

    # @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-if-marker
    # Check .core/ layout first, then flat layout (new: studio; legacy: cypilot)
    for skill_name in ("studio", "cypilot"):
        core_skill_dir = project_root / install_dir / ".core" / "skills" / skill_name / "scripts"
        skill_dir = core_skill_dir if core_skill_dir.is_dir() else project_root / install_dir / "skills" / skill_name / "scripts"
        entry_point = skill_dir / f"{skill_name}.py"
        if entry_point.is_file():
            # @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-return-project-path
            return entry_point
            # @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-return-project-path

        # Also check for the package directly
        package_dir = skill_dir / skill_name
        if package_dir.is_dir() and (package_dir / "__init__.py").is_file():
            return skill_dir / f"{skill_name}.py"
    # @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-if-marker

    return None

def find_cached_skill() -> Optional[Path]:
    """
    Check for cached skill at ~/.cf-studio/cache/.

    Returns path to the skill entry point or None.
    """
    # @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-check-global-cache
    cache_dir = get_cache_dir()
    # Check new layout first (studio), then legacy layout (cypilot)
    for skill_name in ("studio", "cypilot"):
        entry_point = cache_dir / "skills" / skill_name / "scripts" / f"{skill_name}.py"
        if entry_point.is_file():
            # @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-return-cache-path
            return entry_point
            # @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-return-cache-path
    # @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-check-global-cache
    return None

def resolve_skill(start_dir: Optional[Path] = None) -> Tuple[Optional[Path], str]:
    """
    Resolve skill target: project-installed first, then cache.

    Returns (path_to_skill_entry, source) where source is "project" or "cache".
    Returns (None, "none") if no skill found.
    """
    # @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-if-marker
    project_skill = find_project_skill(start_dir)
    if project_skill is not None:
        return project_skill, "project"
    # @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-if-marker

    # @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-if-cache-exists
    cached_skill = find_cached_skill()
    if cached_skill is not None:
        return cached_skill, "cache"
    # @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-if-cache-exists

    # @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-return-not-found
    return None, "none"
    # @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-return-not-found

# @cpt-begin:cpt-studio-algo-core-infra-resolve-skill:p1:inst-resolve-helpers
def get_cached_version() -> Optional[str]:
    """Read the cached skill version from .version marker file."""
    version_file = get_version_file()
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return None

def get_project_version(skill_path: Path) -> Optional[str]:
    """Read version from project-installed skill's __init__.py."""
    # Try studio package name first, then legacy cypilot
    for pkg_name in ("studio", "cypilot"):
        init_file = skill_path.parent / pkg_name / "__init__.py"
        if init_file.is_file():
            try:
                content = init_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if line.startswith("__version__"):
                        # Extract version string
                        return line.split("=", 1)[1].strip().strip("\"'")
            except (OSError, ValueError):
                pass
    return None
# @cpt-end:cpt-studio-algo-core-infra-resolve-skill:p1:inst-resolve-helpers
