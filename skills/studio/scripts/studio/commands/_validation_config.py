"""Shared validation-config helpers for CLI commands.

@cpt-flow:cpt-studio-flow-traceability-validation-check-language:p1
"""

# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-support
from __future__ import annotations

import argparse
from typing import Optional


def add_ignore_argument(parser: argparse.ArgumentParser, help_text: str) -> None:
    """Register the shared repeatable ignore glob flag."""
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="PATTERN",
        help=help_text,
    )


def load_current_validation_config() -> Optional[object]:
    """Load validation config for the current project with user-facing errors."""
    from ..utils.context import get_context
    from ..utils.files import load_validation_config

    ctx = get_context()
    if ctx is None:
        return None
    validation, validation_err = load_validation_config(ctx.project_root)
    if validation_err:
        raise ValueError(f"Validation config error: {validation_err}")
    return validation
# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-support
