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


def _run_doctor_checks(project_root: Path) -> list[dict]:
    checks = []
    # @cpt-begin:cpt-studio-flow-developer-experience-doctor:p2:inst-run-checks
    for check_name, check_fn in [("ralphex", _check_ralphex)]:
        try:
            checks.append(check_fn(project_root))
        except (OSError, ValueError, KeyError, RuntimeError, TypeError) as exc:
            checks.append({
                "level": "FAIL",
                "name": check_name,
                "message": f"Check raised an exception: {exc}",
            })
    # @cpt-end:cpt-studio-flow-developer-experience-doctor:p2:inst-run-checks
    return checks


def _render_doctor_checks(checks: list[dict]) -> tuple[bool, bool]:
    has_fail = False
    has_warn = False
    # @cpt-begin:cpt-studio-flow-developer-experience-doctor:p2:inst-render-checks
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
    # @cpt-end:cpt-studio-flow-developer-experience-doctor:p2:inst-render-checks
    return has_fail, has_warn


def _doctor_result_payload(checks: list[dict], has_fail: bool, has_warn: bool, summary: str) -> dict:
    # @cpt-begin:cpt-studio-dod-developer-experience-doctor:p2:inst-json-result
    level_to_status = {"PASS": "pass", "WARN": "warn", "FAIL": "fail"}
    spec_checks = [
        {
            "name": check["name"],
            "status": level_to_status.get(check["level"], check["level"].lower()),
            "detail": check["message"],
        }
        for check in checks
    ]
    overall = "unhealthy" if has_fail else "degraded" if has_warn else "healthy"
    payload = {"status": overall, "checks": spec_checks, "summary": summary}
    # @cpt-end:cpt-studio-dod-developer-experience-doctor:p2:inst-json-result
    return payload


def cmd_doctor(argv: List[str]) -> int:
    """Run environment health checks and report results."""
    # @cpt-begin:cpt-studio-flow-developer-experience-doctor:p2:inst-user-doctor
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
    # @cpt-end:cpt-studio-flow-developer-experience-doctor:p2:inst-user-doctor

    checks = _run_doctor_checks(project_root)
    has_fail, has_warn = _render_doctor_checks(checks)

    # @cpt-begin:cpt-studio-flow-developer-experience-doctor:p2:inst-return-health
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
    # @cpt-end:cpt-studio-flow-developer-experience-doctor:p2:inst-return-health

    # Map internal check dicts to the documented JSON contract shape
    # (cli.md specifies {"status": "healthy", "checks": [{"status": "pass", ...}]})
    ui.result(
        _doctor_result_payload(checks, has_fail, has_warn, summary),
        human_fn=lambda d: None,  # already printed above
    )
    return exit_code


def _check_ralphex(project_root: Path) -> dict:
    """Check ralphex availability — WARN if missing, never FAIL.

    Discovers ralphex on PATH or via persisted core.toml config,
    then validates the version. Missing ralphex is optional, so
    the worst outcome is WARN with installation guidance.
    """
    from ..ralphex_discover import discover, validate

    # Load core.toml config for persisted path lookup
    from ._core_config import load_core_config
    # @cpt-begin:cpt-studio-algo-developer-experience-doctor:p2:inst-check-ralphex
    config = load_core_config(project_root)

    path = discover(config)
    if path is None:
        from ..ralphex_discover import INSTALL_GUIDANCE
        logger.info("inst-check-ralphex: ralphex not found")
        check_result = {
            "name": "inst-check-ralphex",
            "level": "WARN",
            "message": f"ralphex not found. {INSTALL_GUIDANCE}",
        }
    else:
        result = validate(path)
        if result["status"] == "available":
            logger.info("inst-check-ralphex: ralphex %s at %s", result["version"], path)
            check_result = {
                "name": "inst-check-ralphex",
                "level": "PASS",
                "message": f"ralphex {result['version']} at {path}",
            }
        else:
            # incompatible — still WARN, not FAIL (ralphex is optional)
            logger.warning("inst-check-ralphex: %s", result["message"])
            check_result = {
                "name": "inst-check-ralphex",
                "level": "WARN",
                "message": result["message"],
            }
    # @cpt-end:cpt-studio-algo-developer-experience-doctor:p2:inst-check-ralphex
    return check_result
