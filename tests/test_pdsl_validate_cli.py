from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from studio.cli import main
from studio.utils.pdsl import (
    PdslError,
    PdslFinding,
    PdslSource,
    build_envelope,
    error_result,
    exit_code_for_results,
    read_source_file,
    scan_blocks,
    validate_source,
)
from studio.utils.ui import set_json_mode


VALID_PDSL = """UNIT Demo

PURPOSE:
  Validate a small block.

DO:
  - RUN Do something deterministic

RULES:
  - ALWAYS keep output stable

MENU Pick:
  OPTIONS:
    1 one -> RETURN done
    2 two -> RETURN done
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


def test_pdsl_result_serialization_verbose_and_error_locations() -> None:
    finding = PdslFinding(
        rule_id="PDSL200",
        severity="error",
        message="bad starter",
        source_path="sample.md",
        block_index=0,
        line=2,
        column=3,
        end_line=2,
        end_column=12,
        hint="Use RUN.",
        context="- BAD action",
    )
    error = PdslError("cannot read", "missing.md", line=4, column=5, kind="READ_ERROR")
    result = error_result("missing.md", error)
    envelope = build_envelope([result], command="pdsl validate", verbose=True)

    assert "context" not in finding.to_dict()
    assert finding.to_dict(verbose=True)["context"] == "- BAD action"
    assert error.to_dict()["line"] == 4
    assert error.to_dict()["column"] == 5
    assert result.status == "ERROR"
    assert envelope["ok"] is False
    assert envelope["results"][0]["errors"][0]["kind"] == "READ_ERROR"
    assert exit_code_for_results([result]) == 1


def test_pdsl_read_source_file_reports_utf8_decode_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe")

    text, error = read_source_file(bad)

    assert text is None
    assert error is not None
    assert error.kind == "DECODE_ERROR"


def test_pdsl_scan_flags_wrong_and_unclosed_fences() -> None:
    text = """```text
UNIT WrongFence
```
```pdsl
UNIT OpenFence
"""

    blocks, findings = scan_blocks("sample.md", text)

    assert blocks == []
    assert [finding.rule_id for finding in findings] == ["PDSL100", "PDSL100"]
    assert findings[0].message == "PDSL-shaped instruction block must use a ```pdsl fence"
    assert findings[1].message == "Unclosed ```pdsl fence"


def test_pdsl_validate_source_covers_structural_edge_cases() -> None:
    text = """MENU Pick
TITLE:
  Pick one.
OPTIONS:
  1 one -> RETURN ok
  - two -> RETURN bad
  - 3 three -> RETURN bad
UNIT Dup
UNIT Dup
IGNORED_LABEL:
  - This is prompt-adjacent metadata
PATTERNS:
  known: /ok/
  known: /again/
DO:
      - RUN deeply indented ignored
  - RUN matches(reply, missing)
STATE:
  - LOAD invalid state starter
WHEN:
  - SET invalid when starter
RULES:
  - RUN invalid rule starter
"""

    result = validate_source(PdslSource("edge.md", text))

    assert result.status == "FAIL"
    messages = [finding.message for finding in result.findings]
    assert "MENU OPTIONS item must start with a decimal number and contain ->" in messages
    assert "MENU option number must be 2, got 3" in messages
    assert "Duplicate UNIT name `Dup` in source" in messages
    assert "Duplicate PATTERNS name `known`" in messages
    assert "Undefined local matches() pattern `missing`" in messages
    assert any("STATE item must start with one of: SET; got LOAD" in msg for msg in messages)
    assert any("WHEN item must start with one of:" in msg and "got SET" in msg for msg in messages)
    assert any("RULES item must start with one of:" in msg and "got RUN" in msg for msg in messages)
