"""Tests for the usage-report command (usage_report.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
from pathlib import Path

from studio.commands.usage_report import cmd_usage_report
from studio.utils import decision_log as dl


class TestCmdUsageReport:
    def test_unknown_argument_emits_json_error_not_a_plain_text_banner(self, capsys):
        """CodeRabbit PR #111: cmd_usage_report now uses
        JsonSafeArgumentParser, so an unrecognized argument must still
        emit the project's own --json ERROR contract, not argparse's
        default usage banner + SystemExit."""
        rc = cmd_usage_report(["--bogus"])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_no_project_reports_no_log_found(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        rc = cmd_usage_report([])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["summary"]["exists"] is False
        assert out["reads"] == {"methods": {}, "total_tokens": 0}

    def test_json_output_reflects_logged_reads(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        dl.record_read("tfidf", "doc.md", 8925, 49676)
        dl.record_read("baseline", "doc.md", 8925, 333573)

        rc = cmd_usage_report([])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["reads"]["methods"]["tfidf"]["total_tokens"] == 49676
        assert out["reads"]["total_tokens"] == 49676 + 333573
        assert out["summary"]["exists"] is True

    def test_human_output_no_log(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_usage_report([])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "no decision log found" in capsys.readouterr().out

    def test_human_output_no_reads_yet(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        dl.record("routing", {"a": 1})  # something logged, but no read events

        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_usage_report([])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "no read events logged yet" in capsys.readouterr().out

    def test_human_output_with_reads(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        dl.record_read("tfidf", "doc.md", 8925, 49676)

        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_usage_report([])
        finally:
            set_json_mode(orig)
        assert rc == 0
        out = capsys.readouterr().out
        assert "tfidf" in out
        assert "49676" in out

    def test_human_output_surfaces_event_counts_and_time_range(self, tmp_path: Path, capsys, monkeypatch):
        """CodeRabbit PR #111: the JSON summary includes event_counts/
        first_ts/last_ts, but the human renderer used to print neither --
        an interactive user saw strictly less than a --json caller."""
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        dl.record_read("tfidf", "doc.md", 8925, 49676)

        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_usage_report([])
        finally:
            set_json_mode(orig)
        assert rc == 0
        out = capsys.readouterr().out
        assert "read" in out  # event type name from event_counts
        assert "time range" in out
