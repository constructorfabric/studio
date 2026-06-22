"""
Compatibility shim for tomllib (Python 3.11+) / tomli (Python < 3.11).

Import this module instead of importing tomllib directly:

    from studio.utils._tomllib_compat import tomllib

@cpt-algo:cpt-studio-algo-core-infra-config-management:p1
"""

import logging
import sys

from .stderr_logging import emit_stderr_message

logger = logging.getLogger(__name__)


def _emit_error(message: str) -> None:
    """Emit a fatal compatibility error through a handler bound to current stderr."""
    emit_stderr_message(message.rstrip("\n"), level=logging.ERROR, logger_name=f"{__name__}.stderr")

# Python 3.11+ has tomllib in stdlib, earlier versions need tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        _emit_error(
            "ERROR: tomllib/tomli not available.\n"
            "Please either:\n"
            "  1. Use Python 3.11+ (tomllib is included in stdlib), or\n"
            "  2. Install tomli: pip install tomli\n",
        )
        sys.exit(1)

__all__ = ["tomllib"]
