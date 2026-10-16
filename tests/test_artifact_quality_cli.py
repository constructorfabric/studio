"""#118 — `cfs artifact-quality` command.

End-to-end through the command entry: the parser, the real duplication detector over real temp
Markdown, the output-bound cap, the JSON shape, and the advisory never-gates invariant (exit 0).
JSON mode is autouse in conftest, so `ui.result` prints JSON we parse back.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.artifact_quality import (  # noqa: E402
    _human_artifact_quality,
    _resolve_detectors,
    cmd_artifact_quality,
)
from studio.cli import _ALL_COMMANDS, _COMMAND_HANDLERS  # noqa: E402

# A section well above the detector's domain-token floor, so two copies are a real duplicate pair.
_PARA = (
    "The plugin resolver selects an instance by priority and caches the chosen client for reuse "
    "across concurrent callers without duplicating the single-flight protection the toolkit already "
    "provides for every registered gear in the workspace."
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _arts(*paths: Path) -> List[Tuple[Path, str]]:
    return [(p, "feature") for p in paths]


def _run(tmp_path: Path, artifacts: List[Tuple[Path, str]], args: List[str]) -> Tuple[int, dict]:
    """Run the command with a stub context over *artifacts*, returning (exit_code, parsed_json)."""
    ctx = MagicMock()
    ctx.project_root = tmp_path
    with patch("studio.commands.artifact_quality.get_context", return_value=ctx), patch(
        "studio.commands.artifact_quality.collect_artifacts_to_scan", return_value=(artifacts, {})
    ), patch("sys.stdout", new_callable=StringIO) as out:
        rc = cmd_artifact_quality(args)
    raw = out.getvalue()
    # --output writes to a file and prints nothing; callers that use it read the file instead.
    return rc, (json.loads(raw) if raw.strip() else {})


def test_duplicated_sections_are_reported(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# Beta\n\n{_PARA}\n")
    rc, data = _run(tmp_path, _arts(a, b), [])
    assert rc == 0
    assert data["status"] == "OK"
    assert data["total_findings"] >= 1
    assert data["findings"][0]["detector"] == "duplication"


def test_findings_never_gate_the_exit_code(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# Beta\n\n{_PARA}\n")
    rc, data = _run(tmp_path, _arts(a, b), [])
    # The whole contract: a finding is advisory — the command still exits 0.
    assert rc == 0
    assert data["total_findings"] >= 1


def test_a_clean_corpus_is_empty_and_exits_zero(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", "# Beta\n\nAn entirely different paragraph about shipping cadence, "
              "release trains, calendar windows, and the approval queue that precedes a cut.\n")
    rc, data = _run(tmp_path, _arts(a, b), [])
    assert rc == 0
    assert data["total_findings"] == 0
    assert data["findings"] == []


def test_max_findings_caps_output_and_flags_truncation(tmp_path: Path) -> None:
    # Three identical sections → three distinct pairs → three findings.
    arts = _arts(
        _write(tmp_path, "a.md", f"# A\n\n{_PARA}\n"),
        _write(tmp_path, "b.md", f"# B\n\n{_PARA}\n"),
        _write(tmp_path, "c.md", f"# C\n\n{_PARA}\n"),
    )
    rc, data = _run(tmp_path, arts, ["--max-findings", "1"])
    assert rc == 0
    assert data["total_findings"] == 3
    assert data["truncated"] is True
    assert len(data["findings"]) == 1


def test_max_findings_zero_disables_the_cap(tmp_path: Path) -> None:
    arts = _arts(
        _write(tmp_path, "a.md", f"# A\n\n{_PARA}\n"),
        _write(tmp_path, "b.md", f"# B\n\n{_PARA}\n"),
        _write(tmp_path, "c.md", f"# C\n\n{_PARA}\n"),
    )
    rc, data = _run(tmp_path, arts, ["--max-findings", "0"])
    assert rc == 0
    assert data["truncated"] is False
    assert len(data["findings"]) == data["total_findings"] == 3


def test_json_shape_has_the_bound_fields(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# Beta\n\n{_PARA}\n")
    _rc, data = _run(tmp_path, _arts(a, b), [])
    for key in ("status", "schema_version", "detectors", "artifacts_scanned", "total_findings",
                "truncated", "findings"):
        assert key in data
    assert data["detectors"] == ["duplication"]
    assert data["artifacts_scanned"] == 2


def test_output_writes_json_to_a_file(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# Beta\n\n{_PARA}\n")
    out_file = tmp_path / "report.json"
    rc, _stdout = _run(tmp_path, _arts(a, b), ["--output", str(out_file)])
    assert rc == 0
    written = json.loads(out_file.read_text(encoding="utf-8"))
    assert written["status"] == "OK"
    assert written["total_findings"] >= 1


def test_unknown_detector_is_reported_not_silently_skipped(tmp_path: Path) -> None:
    rc, data = _run(tmp_path, [], ["--detectors", "bogus"])
    assert rc == 1
    assert data["status"] == "ERROR"
    assert "bogus" in data["message"]


def test_negative_max_findings_is_rejected(tmp_path: Path) -> None:
    rc, data = _run(tmp_path, [], ["--max-findings", "-1"])
    assert rc == 1
    assert data["status"] == "ERROR"


def test_no_context_reports_not_initialized() -> None:
    with patch("studio.commands.artifact_quality.get_context", return_value=None), patch(
        "sys.stdout", new_callable=StringIO
    ) as out:
        rc = cmd_artifact_quality([])
    data = json.loads(out.getvalue())
    assert rc == 1
    assert data["status"] == "ERROR"


def test_command_is_registered_in_the_cli() -> None:
    # B7: wiring asserted, not assumed — a handler that dispatches nowhere looks identical otherwise.
    assert "artifact-quality" in _ALL_COMMANDS
    assert _COMMAND_HANDLERS["artifact-quality"] == "_cmd_artifact_quality"


def test_main_dispatches_to_the_command() -> None:
    # Drives the real cli.py thunk end-to-end (unknown-detector path needs no project context).
    from studio.cli import main

    with patch("sys.stdout", new_callable=StringIO):
        rc = main(["artifact-quality", "--detectors", "bogus"])
    assert rc == 1


def test_resolve_detectors_defaults_and_dedups() -> None:
    assert _resolve_detectors(None) == (["duplication"], [])
    # A repeated known name collapses; a repeated unknown is reported once, not per repeat.
    assert _resolve_detectors(["duplication", "duplication"]) == (["duplication"], [])
    assert _resolve_detectors(["bogus", "bogus"]) == ([], ["bogus"])


def test_human_summary_renders_findings_and_errors(capsys) -> None:
    # The human path never runs under autouse JSON mode (the ui helpers suppress there), and
    # ui.result only calls it in human mode — so drop to human mode to exercise the renderer.
    from studio.utils.ui import is_json_mode, set_json_mode

    was_json = is_json_mode()
    set_json_mode(False)
    ok = {
        "status": "OK",
        "detectors": ["duplication"],
        "artifacts_scanned": 2,
        "total_findings": 2,
        "truncated": True,
        "findings": [
            "not-a-dict-defensive-skip",  # the renderer skips a malformed entry, never crashes
            {"detector": "duplication", "severity": "warn",
             "primary": {"artifact_path": "a.md", "anchor": "alpha"}, "message": "duplicated section"},
        ],
    }
    _human_artifact_quality(ok)
    out = capsys.readouterr().out
    assert "a.md#alpha" in out
    assert "duplicated section" in out
    assert "max-findings" in out  # the truncation note

    _human_artifact_quality({"status": "ERROR", "message": "boom"})
    assert "boom" in capsys.readouterr().out
    set_json_mode(was_json)
