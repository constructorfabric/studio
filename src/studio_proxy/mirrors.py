"""
Mirror Override Configuration

Persists user-defined URL overrides applied to every git/HTTP URL the proxy and
skill engine resolve (default install repo, kit sources, GitHub API bases).

Match semantics
---------------
**Substring replacement**. Each override is a pair ``(from, to)``: when ``from``
appears anywhere inside a URL, it is replaced with ``to``. All registered
overrides are applied in load order (XDG first, then brand-home); later
overrides may further transform a URL that an earlier override already
matched. This lets users replace either a full URL prefix
(``github.com/constructorfabric/studio`` → ``github.com/ainetx/studio``) or a
bare token that recurs across many URLs (``constructorfabric`` → ``ainetx``
remaps both ``studio`` and ``studio-kit-sdlc`` and any other repo in the same
org with a single override).

Two-location read-merge / write-primary scheme:

    1. ${XDG_CONFIG_HOME:-~/.config}/constructor-studio/mirrors.toml  (primary)
    2. ~/.constructor-studio/mirrors.toml                              (brand fallback)

On read, both files are loaded and merged with brand-home entries overriding
XDG entries on duplicate ``from``. On write the target is brand-home if it
exists, else XDG (creating XDG for new installs).

File format::

    [[mirror]]
    from = "github.com/constructorfabric/studio"
    to   = "github.com/ainetx/studio"

    [[mirror]]
    from = "constructorfabric"
    to   = "ainetx"

Public API
----------
- :func:`xdg_path` — XDG-style config path
- :func:`brand_home_path` — brand-home config path
- :func:`load_overrides` — load and merge overrides from both locations
- :func:`list_overrides` — alias for ``load_overrides`` (ADR-0020)
- :func:`apply_override` — apply every registered override to a URL
- :func:`set_override` — write or update a single override entry
- :func:`remove_override` — remove an override from the write-target file
- :func:`clear_overrides` — remove all overrides from the write-target file
- :func:`mirror_sources` — enumerate the proxy's default URLs that can be mirrored

@cpt-algo:cpt-studio-algo-core-infra-mirror-override:p1
@cpt-dod:cpt-studio-dod-core-infra-mirror-override:p1
"""

import os
import tomllib
from pathlib import Path
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Config file locations
# ---------------------------------------------------------------------------

def xdg_path() -> Path:
    """Return the XDG-style mirrors config path."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / "constructor-studio" / "mirrors.toml"


def brand_home_path() -> Path:
    """Return the brand-home mirrors config path."""
    return Path.home() / ".constructor-studio" / "mirrors.toml"


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _load_file(path: Path) -> List[Tuple[str, str]]:
    """Load mirrors from a single TOML file. Returns [(from, to)]."""
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    entries: List[Tuple[str, str]] = []
    for item in data.get("mirror", []):
        f = item.get("from", "")
        t = item.get("to", "")
        if f and t:
            entries.append((f, t))
    return entries


def load_overrides() -> List[Tuple[str, str, Path]]:
    """Load and merge mirror overrides from both config locations.

    Returns ``[(from, to, source_path)]`` in apply order: XDG entries first,
    then brand-home entries. On duplicate ``from`` the brand-home entry wins
    (later in the merged list).
    """
    xdg = xdg_path()
    brand = brand_home_path()

    xdg_entries = [(f, t, xdg) for f, t in _load_file(xdg)]
    brand_entries = [(f, t, brand) for f, t in _load_file(brand)]

    # Merge: brand-home overrides XDG on duplicate 'from' (exact-string match)
    merged: Dict[str, Tuple[str, str, Path]] = {}
    for f, t, src in xdg_entries + brand_entries:
        merged[f] = (f, t, src)

    return list(merged.values())


#: Alias for :func:`load_overrides` — required public export per ADR-0020.
list_overrides = load_overrides


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_override(url: str) -> str:
    """Apply every registered mirror override to ``url`` as substring replacement.

    Each override's ``from`` is replaced with its ``to`` anywhere it occurs.
    Overrides are applied in load order so later overrides can further
    transform a URL already touched by an earlier one.
    """
    if not url:
        return url
    result = url
    for from_, to_, _src in load_overrides():
        if from_ and from_ in result:
            result = result.replace(from_, to_)
    return result


# ---------------------------------------------------------------------------
# Default URLs the proxy knows about (for `cfs mirror sources`)
# ---------------------------------------------------------------------------

#: Default URL sources that pass through ``apply_override``. Listed here so
#: ``cfs mirror sources`` can show users what they can mirror.
DEFAULT_URL_SOURCES: List[Tuple[str, str]] = [
    ("proxy.github_api_base", "https://api.github.com/repos/constructorfabric/studio"),
    ("proxy.github_web",      "https://github.com/constructorfabric/studio"),
    ("kit.sdlc.github_web",   "https://github.com/constructorfabric/studio-kit-sdlc"),
    ("kit.sdlc.github_api",   "https://api.github.com/repos/constructorfabric/studio-kit-sdlc"),
    ("kit.shorthand.studio",       "github:constructorfabric/studio"),
    ("kit.shorthand.sdlc",         "github:constructorfabric/studio-kit-sdlc"),
]


def mirror_sources() -> List[Tuple[str, str, str]]:
    """Return ``[(source_name, original_url, effective_url)]`` for every known
    default URL after current overrides are applied.

    Used by ``cfs mirror sources`` to show users what URLs they can mirror and
    where each currently resolves to.
    """
    out: List[Tuple[str, str, str]] = []
    for name, url in DEFAULT_URL_SOURCES:
        out.append((name, url, apply_override(url)))
    return out


# ---------------------------------------------------------------------------
# Write target resolution
# ---------------------------------------------------------------------------

def _resolve_write_target() -> Path:
    """Determine which file to write overrides to (brand-home preferred when
    it already exists; otherwise XDG path for new installs).
    """
    brand = brand_home_path()
    xdg = xdg_path()
    if brand.is_file():
        return brand
    if xdg.is_file():
        return xdg
    return xdg  # new-install default


# ---------------------------------------------------------------------------
# TOML serialization
# ---------------------------------------------------------------------------

def _validate_value(value: str, field: str) -> None:
    """Reject values containing newlines or control characters."""
    for ch in value:
        code = ord(ch)
        if ch in ("\n", "\r") or (code < 32 and ch not in ("\t",)):
            raise ValueError(f"Invalid character in mirror {field}: {repr(ch)}")


def _escape_toml_string(value: str) -> str:
    """Escape backslashes and double-quotes for TOML basic strings."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _serialize_mirrors(entries: List[Tuple[str, str]]) -> str:
    """Serialize a list of ``(from, to)`` pairs to TOML text."""
    lines: List[str] = []
    for f, t in entries:
        lines.append("[[mirror]]")
        lines.append(f'from = "{_escape_toml_string(f)}"')
        lines.append(f'to   = "{_escape_toml_string(t)}"')
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------

def set_override(from_url: str, to_url: str) -> Path:
    """Write or update a mirror override. Returns the path written to."""
    _validate_value(from_url, "from")
    _validate_value(to_url, "to")

    target = _resolve_write_target()
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_file(target)
    # Replace if exact-string match exists, otherwise append
    new_entries = [(f, t) for f, t in existing if f != from_url]
    new_entries.append((from_url, to_url))

    target.write_text(_serialize_mirrors(new_entries), encoding="utf-8")
    return target


def remove_override(from_url: str) -> bool:
    """Remove an override from the write-target config file."""
    target = _resolve_write_target()
    existing = _load_file(target)
    filtered = [(f, t) for f, t in existing if f != from_url]
    if len(filtered) == len(existing):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_serialize_mirrors(filtered), encoding="utf-8")
    return True


def clear_overrides() -> int:
    """Clear every override in the write-target config file. Returns count removed."""
    target = _resolve_write_target()
    existing = _load_file(target)
    if not existing:
        return 0
    count = len(existing)
    target.write_text("", encoding="utf-8")
    return count
