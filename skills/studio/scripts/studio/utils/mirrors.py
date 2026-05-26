"""
Mirror Override — Skill-Engine View

Reads the same `mirrors.toml` config the `cfs` proxy writes and exposes a
single :func:`apply_override` helper for skill-engine commands that perform
network operations (`kit install`, `kit update`, future kit-source resolvers).

The config format and lookup rules are owned by ``src/studio_proxy/mirrors.py``;
this module is a read-only mirror of the same TOML files so the skill engine
can honor user overrides without depending on the proxy package.

Match semantics: substring replacement. Each ``from`` is replaced anywhere it
occurs in a URL. All registered overrides are applied in load order.

Read locations (merged; brand-home wins on duplicate ``from``):
  1. ``${XDG_CONFIG_HOME:-~/.config}/constructor-studio/mirrors.toml``
  2. ``~/.constructor-studio/mirrors.toml``

@cpt-algo:cpt-studio-algo-core-infra-mirror-override:p1
"""

import os
from pathlib import Path
from typing import List, Tuple

from ._tomllib_compat import tomllib

# @cpt-begin:cpt-studio-algo-core-infra-mirror-override:p1:inst-mirror-config-paths
def _xdg_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / "constructor-studio" / "mirrors.toml"


def _brand_home_path() -> Path:
    return Path.home() / ".constructor-studio" / "mirrors.toml"
# @cpt-end:cpt-studio-algo-core-infra-mirror-override:p1:inst-mirror-config-paths

# @cpt-begin:cpt-studio-algo-core-infra-mirror-override:p1:inst-mirror-load-file
def _load_file(path: Path) -> List[Tuple[str, str]]:
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    out: List[Tuple[str, str]] = []
    for item in data.get("mirror", []):
        f = item.get("from", "")
        t = item.get("to", "")
        if f and t:
            out.append((f, t))
    return out
# @cpt-end:cpt-studio-algo-core-infra-mirror-override:p1:inst-mirror-load-file

# @cpt-begin:cpt-studio-algo-core-infra-mirror-override:p1:inst-mirror-merge-overrides
def _load_overrides() -> List[Tuple[str, str]]:
    """Merged overrides in apply order (XDG first, then brand-home).

    On duplicate ``from``, the brand-home entry wins (later in the list).
    """
    xdg = _load_file(_xdg_path())
    brand = _load_file(_brand_home_path())
    merged: dict = {}
    for f, t in xdg + brand:
        merged[f] = (f, t)
    return list(merged.values())
# @cpt-end:cpt-studio-algo-core-infra-mirror-override:p1:inst-mirror-merge-overrides

# @cpt-begin:cpt-studio-algo-core-infra-mirror-override:p1:inst-mirror-apply-override
def apply_override(url: str) -> str:
    """Apply every registered mirror override to ``url`` as substring replacement.

    Returns the substituted URL or the original if no override matches. All
    matching overrides are applied in load order.
    """
    if not url:
        return url
    result = url
    for from_, to_ in _load_overrides():
        if from_ in result:
            result = result.replace(from_, to_)
    return result
# @cpt-end:cpt-studio-algo-core-infra-mirror-override:p1:inst-mirror-apply-override
