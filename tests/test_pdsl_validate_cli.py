from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from studio.cli import main
from studio.utils.ui import set_json_mode


VALID_PDSL = """UNIT Demo

PURPOSE:
  Validate a small block.

DO:
  - RUN Do something deterministic

RULES:
  - ALWAYS keep output stable
"""


INVALID_PDSL = """UNIT Demo
UNIT Demo

DO:
  - EXECUTE unsupported action

MENU Pick:
  OPTIONS:
    - 1 one -> RETURN done
    - 3 three -> RETURN done

WHEN:
  - REQUIRE matches(reply, missing-pattern)
"""


def _run(argv: list[str], *, stdin: str = "") -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.object(sys, "stdin", io.StringIO(stdin)):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = main(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


def test_pdsl_validate_text_json_pass() -> None:
    set_json_mode(False)
    rc, stdout, stderr = _run(["pdsl", "validate", "--text", VALID_PDSL, "--json"])

    assert rc == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["command"] == "pdsl validate"
    assert payload["ok"] is True
    assert payload["summary"] == {
        "pass_count": 1,
        "fail_count": 0,
        "error_count": 0,
        "finding_count": 0,
    }
    assert payload["results"][0]["source"] == "<text>"
    assert payload["results"][0]["status"] == "PASS"


def test_pdsl_validate_text_human_fail_without_json() -> None:
    set_json_mode(False)
    rc, stdout, stderr = _run(["pdsl", "validate", "--text", INVALID_PDSL])

    assert rc == 2
    assert stdout == ""
    assert "PDSL validation did not pass" in stderr
    assert "PDSL200" in stderr
    assert "PDSL300" in stderr
    assert "PDSL400" in stderr
    assert "PDSL500" in stderr


def test_pdsl_validate_stdin_json() -> None:
    set_json_mode(False)
    rc, stdout, _stderr = _run(["pdsl", "validate", "-", "--json"], stdin=VALID_PDSL)

    assert rc == 0
    payload = json.loads(stdout)
    assert payload["results"][0]["source"] == "<stdin>"


def test_pdsl_validate_multi_file_preserves_order_and_read_error() -> None:
    set_json_mode(False)
    with TemporaryDirectory() as td:
        root = Path(td)
        first = root / "first.md"
        second = root / "second.md"
        missing = root / "missing.md"
        first.write_text("```pdsl\n" + VALID_PDSL + "\n```\n", encoding="utf-8")
        second.write_text(INVALID_PDSL, encoding="utf-8")

        rc, stdout, _stderr = _run(["pdsl", "validate", str(first), str(second), str(missing), "--json"])

    assert rc == 1
    payload = json.loads(stdout)
    assert [result["source"] for result in payload["results"]] == [str(first), str(second), str(missing)]
    assert [result["status"] for result in payload["results"]] == ["PASS", "FAIL", "ERROR"]
    assert payload["summary"]["pass_count"] == 1
    assert payload["summary"]["fail_count"] == 1
    assert payload["summary"]["error_count"] == 1


def test_pdsl_validate_rejects_mixed_selectors() -> None:
    set_json_mode(False)
    rc, stdout, _stderr = _run(["pdsl", "validate", "--text", VALID_PDSL, "-", "--json"], stdin=VALID_PDSL)

    assert rc == 1
    payload = json.loads(stdout)
    assert payload["results"][0]["status"] == "ERROR"
    assert payload["results"][0]["errors"][0]["kind"] == "INVOCATION_ERROR"


def test_pdsl_help_is_validate_only_and_no_scaffold_output() -> None:
    set_json_mode(False)
    rc, stdout, stderr = _run(["pdsl", "--help"])

    assert rc == 0
    assert stdout == ""
    assert "validate" in stderr
    assert "Scaffold generation" in stderr
    assert "scaffold text" not in stderr


def test_pdsl_unsupported_scaffold_is_error() -> None:
    set_json_mode(False)
    rc, stdout, _stderr = _run(["pdsl", "scaffold", "--json"])

    assert rc == 1
    payload = json.loads(stdout)
    assert payload["status"] == "ERROR"
    assert payload["supported"] == ["validate"]


def test_cf_pdsl_workflow_reuses_pdsl_validate_command() -> None:
    workflow = Path(__file__).resolve().parents[1] / "workflows" / "pdsl.md"
    text = workflow.read_text(encoding="utf-8")

    assert "UNIT PdslCommandValidationReuse" in text
    assert "cfs pdsl validate" in text
    assert "NEVER cf-pdsl modes define separate PDSL parser rules" in text
