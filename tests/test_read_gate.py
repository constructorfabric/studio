"""Tests for the large-read confirmation gate (read_gate.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
from pathlib import Path

from studio.commands.read_gate import cmd_read_gate
from studio.utils.read_gate import DEFAULT_GATE_THRESHOLD_LINES, check_gate


class TestCheckGate:
    def test_below_threshold_needs_no_confirmation(self):
        result = check_gate(100, threshold=5000)
        assert result == {"needs_confirmation": False, "total_lines": 100, "threshold": 5000}

    def test_above_threshold_needs_confirmation(self):
        result = check_gate(8925, threshold=5000)
        assert result == {"needs_confirmation": True, "total_lines": 8925, "threshold": 5000}

    def test_exactly_at_threshold_needs_no_confirmation(self):
        """Real, tested boundary: this is a "crosses" threshold, not "reaches" -- a
        document exactly at the threshold hasn't gone over it yet."""
        result = check_gate(5000, threshold=5000)
        assert result["needs_confirmation"] is False

    def test_uses_the_documented_default_threshold(self):
        result = check_gate(8925)
        assert result["threshold"] == DEFAULT_GATE_THRESHOLD_LINES == 5000

    def test_negative_total_lines_is_clamped_to_zero(self):
        result = check_gate(-5)
        assert result == {"needs_confirmation": False, "total_lines": 0, "threshold": DEFAULT_GATE_THRESHOLD_LINES}


class TestCmdReadGate:
    def test_missing_file(self, tmp_path: Path, capsys):
        rc = cmd_read_gate([str(tmp_path / "nope.md")])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_missing_required_argument_emits_json_error_not_a_plain_text_banner(self, capsys):
        """CodeRabbit PR #111: cmd_read_gate now uses JsonSafeArgumentParser
        (like every other single-file command), so omitting a required
        positional must still emit the project's own --json ERROR contract,
        not argparse's default usage banner + SystemExit."""
        rc = cmd_read_gate([])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_non_utf8_file_reports_a_clean_error_not_a_raw_traceback(self, tmp_path: Path, capsys):
        f = tmp_path / "bad.md"
        f.write_bytes(b"# Title\n\xff\xfe not valid utf-8\n")
        rc = cmd_read_gate([str(f)])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_basic_json_output(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = tmp_path / "doc.md"
        f.write_text("## A\n\nshort content\n", encoding="utf-8")
        rc = cmd_read_gate([str(f)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["needs_confirmation"] is False
        assert out["threshold"] == DEFAULT_GATE_THRESHOLD_LINES

    def test_custom_threshold_flag(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = tmp_path / "doc.md"
        f.write_text("## A\n\n" + "\n".join(f"line {i}" for i in range(20)) + "\n", encoding="utf-8")
        rc = cmd_read_gate([str(f), "--threshold", "10"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["needs_confirmation"] is True
        assert out["threshold"] == 10

    def test_human_output_needs_confirmation(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = tmp_path / "doc.md"
        f.write_text("## A\n\n" + "\n".join(f"line {i}" for i in range(20)) + "\n", encoding="utf-8")
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_read_gate([str(f), "--threshold", "10"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "needs confirmation" in capsys.readouterr().out

    def test_human_output_no_confirmation_needed(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = tmp_path / "doc.md"
        f.write_text("## A\n\nshort content\n", encoding="utf-8")
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_read_gate([str(f)])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "no confirmation needed" in capsys.readouterr().out
