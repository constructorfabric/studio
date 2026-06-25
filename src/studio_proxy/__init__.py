"""
Constructor Studio Global CLI Proxy

Thin proxy package that resolves skill targets (project-installed or cached)
and forwards commands. Installable via pipx.

@cpt-dod:cpt-studio-dod-core-infra-global-package:p1
"""

import logging
from importlib.metadata import PackageNotFoundError, version


LOGGER = logging.getLogger(__name__)

try:
    __version__ = version("constructor-studio")
except PackageNotFoundError as exc:
    __version__ = "0.0.0-dev"
    LOGGER.warning(
        "Warning: package metadata for constructor-studio is unavailable; "
        "using fallback version %s (%s).",
        __version__,
        exc,
    )
