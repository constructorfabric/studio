"""
Cyber Constructor Validator - Python Package

Entry point for the Cyber Constructor validation CLI tool.

@cpt-flow:cpt-cypilot-flow-core-infra-cli-invocation:p1
"""

from typing import List, Optional

# Import from modular components
from .constants import *
from .utils import *

# Import CLI entry point
def main(argv: Optional[List[str]] = None) -> int:
    from .cli import main as _main
    return _main(argv)

__version__ = "v4.0.0"

__all__ = [
    # Main entry point
    "main",
]
