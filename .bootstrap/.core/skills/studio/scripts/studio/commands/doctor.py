"""
Doctor Command — environment health check for Studio.

Runs diagnostic checks against the local environment and reports
issues as PASS, WARN, or FAIL.

@cpt-algo:cpt-studio-algo-developer-experience-doctor:p2
"""

import argparse
import logging
from pathlib import Path
from typing import List

from ..utils.ui import ui

logger = logging.getLogger(__name__)


# @cpt-begin:cpt-studio-dod-ralphex-delegation-diagnostics:p1:inst-cmd-doctor
def cmd_doctor(argv: List[str]) -> int:
    """Run environment health checks and report results."""
    p = argparse.ArgumentParser(
        prog="doctor",
        description="Run Studio environment health checks",
    )
    p.add_argument(
        "--root",
        default=".",
        help="Project root to check (default: current directory)",
    )
    args = p.parse_args(argv)
    project_root = Path(args.root).resolve()

    ui.header("Studio Doctor")

    has_fail = False
    has_warn = False
    check_fns = [
        ("ralphex", _check_ralphex),
    ]
    checks = []
    for check_name, check_fn in check_fns:
        try:
            checks.append(check_fn(project_root))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            checks.append({
                "level": "FAIL",
                "name": check_name,
                "message": f"Check raised an exception: {exc}",
            })

    for check in checks:
        level = check["level"]
        name = check["name"]
        message = check["message"]

        if level == "PASS":
            ui.step(f"[PASS] {name}: {message}")
        elif level == "WARN":
            ui.step(f"[WARN] {name}: {message}")
            has_warn = True
        elif level == "FAIL":
            ui.error(f"[FAIL] {name}: {message}")
            has_fail = True

    ui.blank()
    if has_fail:
        summary = "Doctor found issues that need attention."
        ui.error(summary)
        exit_code = 2
    elif has_warn:
        summary = "All checks passed with warnings."
        ui.step(summary)
        exit_code = 0
    else:
        summary = "All checks passed."
        ui.step(summary)
        exit_code = 0

    # Map internal check dicts to the documented JSON contract shape
    # (cli.md specifies {"status": "healthy", "checks": [{"status": "pass", ...}]})
    _level_to_status = {"PASS": "pass", "WARN": "warn", "FAIL": "fail"}
    spec_checks = [
        {"name": c["name"], "status": _level_to_status.get(c["level"], c["level"].lower()), "detail": c["message"]}
        for c in checks
    ]
    overall = "unhealthy" if has_fail else "degraded" if has_warn else "healthy"

    ui.result(
        {"status": overall, "checks": spec_checks, "summary": summary},
        human_fn=lambda d: None,  # already printed above
    )

    return exit_code
# @cpt-end:cpt-studio-dod-ralphex-delegation-diagnostics:p1:inst-cmd-doctor


# @cpt-begin:cpt-studio-algo-developer-experience-doctor:p2:inst-check-ralphex
def _check_ralphex(project_root: Path) -> dict:
    """Check ralphex availability — WARN if missing, never FAIL.

    Discovers ralphex on PATH or via persisted core.toml config,
    then validates the version. Missing ralphex is optional, so
    the worst outcome is WARN with installation guidance.
    """
    from ..ralphex_discover import discover, validate

    # Load core.toml config for persisted path lookup
    from ._core_config import load_core_config
    config = load_core_config(project_root)

    path = discover(config)
    if path is None:
        from ..ralphex_discover import INSTALL_GUIDANCE
        logger.info("inst-check-ralphex: ralphex not found")
        return {
            "name": "inst-check-ralphex",
            "level": "WARN",
            "message": f"ralphex not found. {INSTALL_GUIDANCE}",
        }

    result = validate(path)
    if result["status"] == "available":
        logger.info("inst-check-ralphex: ralphex %s at %s", result["version"], path)
        return {
            "name": "inst-check-ralphex",
            "level": "PASS",
            "message": f"ralphex {result['version']} at {path}",
        }

    # incompatible — still WARN, not FAIL (ralphex is optional)
    logger.warning("inst-check-ralphex: %s", result["message"])
    return {
        "name": "inst-check-ralphex",
        "level": "WARN",
        "message": result["message"],
    }
# @cpt-end:cpt-studio-algo-developer-experience-doctor:p2:inst-check-ralphex


