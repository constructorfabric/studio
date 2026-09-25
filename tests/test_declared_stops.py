"""Tests for the declared-stop non-regression gate.

The story this belongs to reduces how often Studio interrupts a user. A number that is only
reported drifts back up one pull request at a time, each rise too small to argue with, so
this is a gate rather than a report — and these tests are mostly about the ways a gate can
look like it is working while letting a rise through.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio.commands import declared_stops as ds  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
STUDIO = REPO_ROOT / "skills/studio/scripts/studio.py"


def _tree(root: Path, files: dict) -> Path:
    """A miniature kit, with its PDSL fenced the way a real kit file writes it."""
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"```pdsl\n{text}```\n", encoding="utf-8")
    return root


def _in_human_mode(fn, *args):
    """Call ``fn`` with the suite's JSON mode off, so human text is produced."""
    from studio.utils import ui  # noqa: PLC0415

    ui.set_json_mode(False)
    try:
        return fn(*args)
    finally:
        ui.set_json_mode(True)


def _baseline(path: Path, counts: dict) -> Path:
    path.write_text(json.dumps({ds.DECLARED_STOPS: counts}, indent=2), encoding="utf-8")
    return path


ONE_STOP = "UNIT W\nDO:\n  EMIT_MENU Ask\n  WAIT user.reply\n  STOP_TURN\n"
TWO_STOPS = ONE_STOP + "  EMIT_MENU Again\n  WAIT user.reply\n  STOP_TURN\n"


class TestItFailsOnlyOnARise:
    """The one thing the gate exists to do, and the three things it must not do instead."""

    def test_a_workflow_that_gained_a_stop_fails(self, tmp_path: Path, capsys) -> None:
        """The whole point. Named with both numbers, so a reader goes to the file."""
        root = _tree(tmp_path / "kit", {"workflows/w.md": TWO_STOPS})
        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 1})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 2
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "FAIL", said
        assert said["risen"] == [{"workflow": "workflows/w.md", "before": 1, "now": 2}], said

    def test_a_workflow_that_lost_a_stop_passes(self, tmp_path: Path, capsys) -> None:
        """A fall is the goal, so it cannot fail — but it does need re-recording."""
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 4})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 0
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "PASS", said
        assert said["needs_recording"], said
        assert said["fallen"] == [{"workflow": "workflows/w.md", "before": 4, "now": 1}], said

    def test_an_unchanged_tree_passes_silently(self, tmp_path: Path, capsys) -> None:
        """No nudge when there is nothing to re-record, or the nudge stops being read."""
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 1})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 0
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "PASS", said
        assert not said["needs_recording"], said

    def test_one_workflow_rising_is_not_hidden_by_another_falling(
            self, tmp_path: Path, capsys) -> None:
        """Why the baseline is per workflow rather than a total.

        Totals net out: +1 here and -3 there is an improvement of two, and the workflow
        someone has just made worse never appears. This is the case that decided the
        shape of the file.
        """
        root = _tree(tmp_path / "kit", {
            "workflows/worse.md": TWO_STOPS,
            "workflows/better.md": ONE_STOP,
        })
        base = _baseline(tmp_path / "b.json",
                         {"workflows/worse.md": 1, "workflows/better.md": 4})
        # Net across the tree is -2, and it still fails.
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 2
        said = json.loads(capsys.readouterr().out)
        assert [r["workflow"] for r in said["risen"]] == ["workflows/worse.md"], said
        assert [r["workflow"] for r in said["fallen"]] == ["workflows/better.md"], said


class TestWhatTheBaselineCannotQuietlyMiss:
    """A workflow appearing or vanishing changes the total, and the two are not symmetric.

    Appearing **fails** until it is recorded -- an unrecorded workflow is the gap a
    renamed-and-inflated file slips through. Vanishing is only reported: a deletion can
    lower the count but never raise it, so there is no rise to hide behind it.
    """

    def test_an_unrecorded_workflow_fails_until_it_is_recorded(
            self, tmp_path: Path, capsys) -> None:
        """No baseline entry is not a free pass: a rename lands a workflow here inflated."""
        root = _tree(tmp_path / "kit", {"workflows/new.md": TWO_STOPS})
        base = _baseline(tmp_path / "b.json", {})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 2
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "FAIL", said
        assert said["added"] == [{"workflow": "workflows/new.md", "before": 0, "now": 2}], said

    def test_a_rename_cannot_launder_an_inflation(self, tmp_path: Path, capsys) -> None:
        """The hole this closes. Renaming a file resets its history to none.

        Inflate a workflow and rename it in the same commit and a per-key compare sees the
        old name gone and a brand-new one -- no rise anywhere, because nothing lines up. It
        fails because the new name is unrecorded, not because a comparison caught it.
        """
        root = _tree(tmp_path / "kit", {"workflows/plan-v2.md": TWO_STOPS})
        base = _baseline(tmp_path / "b.json", {"workflows/plan.md": 1})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 2
        said = json.loads(capsys.readouterr().out)
        assert said["risen"] == [], said
        assert said["added"] == [{"workflow": "workflows/plan-v2.md", "before": 0, "now": 2}]
        assert said["gone"] == [{"workflow": "workflows/plan.md", "before": 1, "now": 0}], said

    def test_an_empty_baseline_does_not_disable_the_gate(
            self, tmp_path: Path, capsys) -> None:
        """An emptied `{}` baseline turns every workflow into an unrecorded one -- and fails.

        The pre-hardening gate read `{}` as "nothing to compare" and passed the whole tree.
        That is the loudest possible way to switch the gate off, so it must be the loudest
        failure, not the quietest pass.
        """
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        base = _baseline(tmp_path / "b.json", {})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 2
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "FAIL", said

    def test_a_workflow_that_disappeared_is_reported_not_failed(
            self, tmp_path: Path, capsys) -> None:
        """A workflow deleted by accident removes its stops and looks like progress.

        Reported so the baseline is re-recorded, but not failed: a deletion can only lower
        the count, so unlike an addition it cannot carry a hidden rise.
        """
        root = _tree(tmp_path / "kit", {"workflows/kept.md": ONE_STOP})
        base = _baseline(tmp_path / "b.json",
                         {"workflows/kept.md": 1, "workflows/lost.md": 9})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 0
        said = json.loads(capsys.readouterr().out)
        assert said["gone"] == [{"workflow": "workflows/lost.md", "before": 9, "now": 0}], said


class TestAFaultIsNotARegression:
    """A gate that cannot run must not look like one that ran and passed — or failed.

    Per the project's CLI exit-code contract a fault (a runtime/filesystem problem) exits **1**
    (ERROR); a check that failed exits **2** (FAIL). These tests pin the fault half: exit 1, a
    named sentence, and — under `--json` — a JSON object on stdout rather than empty output.
    """

    @pytest.mark.parametrize("broken,why", [
        ("", "not valid JSON"),
        ('{"other": {}}', "declared_stops"),
        ('{"declared_stops": {"workflows/w.md": "nine"}}', "not a whole number"),
        ('{"declared_stops": {"workflows/w.md": true}}', "not a whole number"),
        ('{"declared_stops": {"workflows/w.md": -1}}', "not a whole number"),
    ])
    def test_an_unusable_baseline_exits_one_and_says_which(
            self, tmp_path: Path, capsys, broken: str, why: str) -> None:
        """Different faults, different sentences.

        A missing file is a setup problem, a malformed one is a corrupted commit, and a
        count that is not a whole number is a hand edit that went wrong — fixed different
        ways. `true` is in the list because JSON has no separate boolean in Python's eyes:
        `isinstance(True, int)` is true, so it would have passed as 1.
        """
        base = tmp_path / "b.json"
        base.write_text(broken, encoding="utf-8")
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 1
        assert why in _in_human_mode(ds._read_baseline, base)[1]

    def test_a_non_utf8_baseline_is_a_named_fault(self, tmp_path: Path) -> None:
        """`read_text(utf-8)` raises `UnicodeDecodeError` — a `ValueError`, not an `OSError`.

        Left uncaught it crashed the process instead of producing one of the fault sentences
        the docstring promises.
        """
        base = tmp_path / "b.json"
        base.write_bytes(b"\xff\xfe not utf-8 at all")
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 1
        assert "not valid UTF-8" in ds._read_baseline(base)[1]

    def test_a_duplicate_key_baseline_is_a_named_fault(self, tmp_path: Path) -> None:
        """A workflow recorded twice would otherwise be last-key-wins, silently dropping one."""
        base = tmp_path / "b.json"
        base.write_text('{"declared_stops": {"workflows/w.md": 1, "workflows/w.md": 2}}',
                        encoding="utf-8")
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 1
        assert "more than once" in ds._read_baseline(base)[1]

    def test_a_missing_baseline_exits_one(self, tmp_path: Path, capsys) -> None:
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        missing = tmp_path / "absent.json"
        assert ds.cmd_declared_stops(
            ["--root", str(root), "--baseline", str(missing)]) == 1
        assert "nothing to compare against" in ds._read_baseline(missing)[1]

    def test_a_fault_emits_a_json_error_object_on_stdout(
            self, tmp_path: Path, capsys) -> None:
        """The `--json` contract: every path prints a JSON object, faults included.

        `ui.error` is a no-op in JSON mode, so a fault that only called it left stdout empty.
        The suite runs in JSON mode, so a fault here must leave a parseable ERROR object.
        """
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        assert ds.cmd_declared_stops(
            ["--root", str(root), "--baseline", str(tmp_path / "absent.json")]) == 1
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "ERROR", said
        assert "nothing to compare against" in said["message"], said

    def test_a_bad_argument_is_a_json_error_not_a_plain_crash(self, capsys) -> None:
        """A malformed argument goes through the JSON-safe parser, not argparse's exit."""
        assert ds.cmd_declared_stops(["--this-flag-does-not-exist"]) == 2
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "ERROR", said

    def test_an_unwalkable_tree_exits_one(self, tmp_path: Path, capsys) -> None:
        """A root with no workflows/ is a misconfiguration, not a tree with no stops."""
        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 1})
        assert ds.cmd_declared_stops(
            ["--root", str(tmp_path), "--baseline", str(base)]) == 1


class TestAFloorIsAFault:
    """A walk that skipped something is a lower bound, so it cannot certify "no rise".

    The danger is precise: a file the walk could not read drops that workflow's stops from
    the count, and a rise elsewhere the same size reads as no change. So an under-read tree
    is a fault (exit 1, ERROR), not a pass -- on the comparing path and, harder, on `--update`,
    where a floor would otherwise be written in as the new baseline every later run measures on.
    """

    def _surface_with(self, **floor):
        from studio.utils import gate_surface  # noqa: PLC0415

        return gate_surface.GateSurface(tree="kit", **floor)

    def test_floor_names_unreadable_files(self) -> None:
        assert ds._floor(self._surface_with(unreadable=["workflows/w.md: OSError"]))
        assert "could not be read" in ds._floor(
            self._surface_with(unreadable=["workflows/w.md: OSError"]))

    def test_floor_names_missing_loads(self) -> None:
        assert "missing" in ds._floor(self._surface_with(missing_loads=["skills/gone.md"]))

    def test_a_clean_surface_is_not_a_floor(self) -> None:
        assert ds._floor(self._surface_with()) == ""

    def test_a_duplicate_menu_name_is_not_a_floor(self) -> None:
        """A name defined twice does not lower any count, so it must not fail the build."""
        assert ds._floor(self._surface_with(
            duplicate_menu_definitions=["TerminalStates"])) == ""

    def test_an_unreadable_tree_exits_one_before_comparing(
            self, tmp_path: Path, monkeypatch, capsys) -> None:
        """The whole point: a hidden rise must not read as no change."""
        from studio.utils import gate_surface  # noqa: PLC0415

        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 1})
        monkeypatch.setattr(gate_surface, "walk",
                            lambda _root: self._surface_with(unreadable=["x.md: OSError"]))
        assert ds.cmd_declared_stops(
            ["--root", str(tmp_path), "--baseline", str(base)]) == 1

    def test_update_refuses_to_record_a_floor(
            self, tmp_path: Path, monkeypatch) -> None:
        """`--update` writes the baseline. Writing a floor poisons every run after it."""
        from studio.utils import gate_surface  # noqa: PLC0415

        base = tmp_path / "b.json"
        base.write_text('{"declared_stops": {"workflows/w.md": 1}}', encoding="utf-8")
        monkeypatch.setattr(gate_surface, "walk",
                            lambda _root: self._surface_with(missing_loads=["skills/gone.md"]))
        assert ds.cmd_declared_stops(
            ["--root", str(tmp_path), "--baseline", str(base), "--update"]) == 1
        # And the baseline it refused to overwrite is untouched.
        assert json.loads(base.read_text())[ds.DECLARED_STOPS]["workflows/w.md"] == 1


class TestWhatAPersonReads:
    """The human rendering, which the suite's JSON mode hides from every other test.

    Worth its own class rather than an afterthought: the machine payload is what CI keys
    on, and this is what the author who broke the build actually sees. It went untested
    until coverage said so.
    """

    def _rendered(self, payload: dict) -> str:
        from studio.utils import ui  # noqa: PLC0415
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415

        buf = io.StringIO()
        ui.set_json_mode(False)
        try:
            with contextlib.redirect_stdout(buf):
                ds._say(payload)
        finally:
            ui.set_json_mode(True)
        return buf.getvalue()

    def test_a_rise_names_the_workflow_and_both_numbers(self) -> None:
        """"declared stops rose" sends a reader to a diff; this sends them to a file."""
        payload = ds._payload(
            {"risen": [("workflows/plan.md", 9, 11)], "fallen": [], "added": [], "gone": []},
            411)
        said = self._rendered(payload)
        assert "ROSE" in said, said
        assert "workflows/plan.md: 9 -> 11 (+2)" in said, said
        assert "re-record with --update" in said, said

    def test_every_kind_of_change_is_rendered(self) -> None:
        """All four lists, since each has its own wording and three take a different shape."""
        payload = ds._payload(
            {"risen": [("a.md", 1, 2)], "fallen": [("b.md", 4, 1)],
             "added": [("c.md", 0, 3)], "gone": [("d.md", 7, 0)]}, 6)
        said = self._rendered(payload)
        assert "ROSE     a.md: 1 -> 2 (+1)" in said, said
        assert "fell     b.md: 4 -> 1 (-3)" in said, said
        assert "new      c.md: 3" in said, said
        assert "gone     d.md: was 7" in said, said
        assert "total declared stops: 6" in said, said

    def test_a_clean_run_says_the_total_and_nothing_else(self) -> None:
        """No nudge when there is nothing to re-record, or the nudge stops being read."""
        payload = ds._payload({"risen": [], "fallen": [], "added": [], "gone": []}, 415)
        said = self._rendered(payload)
        assert said.strip() == "total declared stops: 415", repr(said)


class TestRecordingIsDeliberate:
    """Re-recording on a fall would make an accidental reduction the new normal."""

    def test_update_rewrites_the_baseline_only_when_asked(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 4})
        # A run that finds a fall leaves the file alone...
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 0
        assert json.loads(base.read_text())[ds.DECLARED_STOPS]["workflows/w.md"] == 4
        # ...and only `--update` moves it.
        assert ds.cmd_declared_stops(
            ["--root", str(root), "--baseline", str(base), "--update"]) == 0
        assert json.loads(base.read_text())[ds.DECLARED_STOPS]["workflows/w.md"] == 1

    def test_update_creates_a_missing_baseline(self, tmp_path: Path, capsys) -> None:
        """`--update` records what was measured whether or not a baseline exists yet.

        It never calls `_read_baseline`, so a missing or malformed pre-existing file is not a
        fault on this path — the point of `--update` is to write the current truth.
        """
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        base = tmp_path / "does-not-exist-yet.json"
        assert ds.cmd_declared_stops(
            ["--root", str(root), "--baseline", str(base), "--update"]) == 0
        assert json.loads(base.read_text())[ds.DECLARED_STOPS]["workflows/w.md"] == 1
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "OK", said
        assert said["recorded"] == 1, said

    def test_update_overwrites_a_malformed_baseline(self, tmp_path: Path) -> None:
        """A corrupt pre-existing baseline does not block `--update` — it replaces it."""
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        base = tmp_path / "b.json"
        base.write_text("this is not json", encoding="utf-8")
        assert ds.cmd_declared_stops(
            ["--root", str(root), "--baseline", str(base), "--update"]) == 0
        assert json.loads(base.read_text())[ds.DECLARED_STOPS]["workflows/w.md"] == 1

    def test_update_names_workflows_it_drops(self, tmp_path: Path, capsys) -> None:
        """A workflow in the old baseline but gone from the tree is named, not dropped silently.

        `--update` still records the current truth, but a vanished workflow is the quiet
        under-record the gate exists to surface, so it appears in the result.
        """
        root = _tree(tmp_path / "kit", {"workflows/a.md": ONE_STOP})
        base = _baseline(tmp_path / "b.json",
                         {"workflows/a.md": 1, "workflows/b.md": 3})
        assert ds.cmd_declared_stops(
            ["--root", str(root), "--baseline", str(base), "--update"]) == 0
        said = json.loads(capsys.readouterr().out)
        assert said["dropped"] == ["workflows/b.md"], said
        assert json.loads(base.read_text())[ds.DECLARED_STOPS] == {"workflows/a.md": 1}

    def test_a_baseline_write_failure_is_a_clean_fault(
            self, tmp_path: Path, monkeypatch, capsys) -> None:
        """A read-only mount or full disk during `--update` is a fault (1), not a traceback."""
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 1})

        def _boom(*_a, **_k):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(ds, "atomic_write_text", _boom)
        assert ds.cmd_declared_stops(
            ["--root", str(root), "--baseline", str(base), "--update"]) == 1
        said = json.loads(capsys.readouterr().out)
        assert said["status"] == "ERROR", said
        assert "could not be written" in said["message"], said


class TestRootAndBoundaryScoping:
    """The default baseline follows `--root`, and the zero-count edges behave as documented."""

    def test_an_unspecified_baseline_resolves_under_root(self, tmp_path: Path) -> None:
        """`--root other/tree` with no `--baseline` compares against that tree's baseline.

        The default used to be a fixed CWD-relative path, so pointing the gate at another tree
        silently compared its counts against the current directory's baseline.
        """
        root = _tree(tmp_path / "kit", {"workflows/w.md": TWO_STOPS})
        (root / ds.BASELINE).parent.mkdir(parents=True, exist_ok=True)
        _baseline(root / ds.BASELINE, {"workflows/w.md": 1})
        # No --baseline: it must find the one under --root and see the rise (exit 2), not
        # fault because a CWD-relative default is missing.
        assert ds.cmd_declared_stops(["--root", str(root)]) == 2

    def test_a_zero_stop_workflow_added_is_recorded_not_ignored(
            self, tmp_path: Path, capsys) -> None:
        """A new workflow with zero stops is still unrecorded, so it still fails."""
        root = _tree(tmp_path / "kit", {"workflows/quiet.md": "UNIT W\nDO:\n  NOTE ok\n"})
        base = _baseline(tmp_path / "b.json", {})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 2
        said = json.loads(capsys.readouterr().out)
        assert said["added"] == [{"workflow": "workflows/quiet.md", "before": 0, "now": 0}], said

    def test_a_workflow_that_dropped_to_zero_is_a_fall_not_a_gone(
            self, tmp_path: Path, capsys) -> None:
        """Still present with zero stops is a fall to 0, distinct from a deleted workflow."""
        root = _tree(tmp_path / "kit", {"workflows/quiet.md": "UNIT W\nDO:\n  NOTE ok\n"})
        base = _baseline(tmp_path / "b.json", {"workflows/quiet.md": 3})
        assert ds.cmd_declared_stops(["--root", str(root), "--baseline", str(base)]) == 0
        said = json.loads(capsys.readouterr().out)
        assert said["fallen"] == [{"workflow": "workflows/quiet.md", "before": 3, "now": 0}], said
        assert said["gone"] == [], said


class TestTheCommandIsReachable:
    """A gate nothing can invoke is not a gate."""

    def test_it_is_registered_in_the_dispatch_table(self) -> None:
        """Asserted rather than assumed: a command can be written and undispatchable.

        The repo has had exactly that — a registration deletable with the whole CLI suite
        still green, leaving the command unreachable, which was its entire purpose.
        """
        from studio import cli  # noqa: PLC0415

        assert "declared-stops" in cli._COMMAND_HANDLERS, sorted(cli._COMMAND_HANDLERS)
        assert hasattr(cli, cli._COMMAND_HANDLERS["declared-stops"])

    def test_it_runs_through_the_real_entry_point(self) -> None:
        """End to end, through `studio.py`, on the repository's own tree."""
        done = subprocess.run(
            [sys.executable, str(STUDIO), "declared-stops", "--root", str(REPO_ROOT)],
            capture_output=True, text=True, check=False, cwd=str(REPO_ROOT))
        assert done.returncode == 0, done.stdout + done.stderr
        assert "total declared stops:" in done.stdout, done.stdout

    def test_the_committed_baseline_matches_the_tree(self) -> None:
        """The gate is only meaningful while its own baseline is current.

        This fails the moment someone changes a workflow's stops without re-recording,
        which is the same signal CI gives — asserted here too so it shows up in a local
        run rather than only after a push.
        """
        recorded, why = ds._read_baseline(REPO_ROOT / ds.BASELINE)
        assert recorded is not None, why
        from studio.utils import gate_surface  # noqa: PLC0415

        surface = gate_surface.walk(REPO_ROOT)
        measured = {w.workflow: w.stop_sites for w in surface.workflows}
        changes = ds._compare(measured, recorded)
        assert not changes["risen"], changes["risen"]
        assert not changes["fallen"], changes["fallen"]
        assert not changes["added"], changes["added"]
        assert not changes["gone"], changes["gone"]


class TestTheExitCodeSurvivesTheRealProcess:
    """The exit code is the gate. A function returning 1 that the process reports as 0 fails
    open, so the number CI keys on is driven through `studio.py` here, not asserted on the
    return value of a call the entry point might not propagate.
    """

    def _run(self, root: Path, base: Path):
        return subprocess.run(
            [sys.executable, str(STUDIO), "declared-stops",
             "--root", str(root), "--baseline", str(base)],
            capture_output=True, text=True, check=False, cwd=str(REPO_ROOT))

    def test_a_rise_exits_two_through_the_process(self, tmp_path: Path) -> None:
        """A check that failed exits 2 (FAIL) per the contract, and the process must report it."""
        root = _tree(tmp_path / "kit", {"workflows/w.md": TWO_STOPS})
        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 1})
        done = self._run(root, base)
        assert done.returncode == 2, done.stdout + done.stderr

    def test_a_fault_exits_one_through_the_process(self, tmp_path: Path) -> None:
        """A missing baseline is a fault (ERROR), and the process must report it as 1, not as a
        check failure (2) and not as a pass (0)."""
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        done = self._run(root, tmp_path / "absent.json")
        assert done.returncode == 1, done.stdout + done.stderr

    def test_a_clean_tree_exits_zero_through_the_process(self, tmp_path: Path) -> None:
        root = _tree(tmp_path / "kit", {"workflows/w.md": ONE_STOP})
        base = _baseline(tmp_path / "b.json", {"workflows/w.md": 1})
        done = self._run(root, base)
        assert done.returncode == 0, done.stdout + done.stderr


class TestCICannotRewriteItsOwnBaseline:
    """`--update` is the escape hatch: it rewrites the baseline from whatever is measured, so
    a rise clears itself. It must never be what CI runs, or the gate re-records the regression
    it is meant to catch and always passes. Asserted against the real Makefile and CI job.
    """

    def test_the_make_target_never_passes_update(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        target = makefile.split("\ndeclared-stops:", 1)[1].split("\n\n", 1)[0]
        assert "declared-stops" in target
        assert "--update" not in target, target

    def _job_block(self, yaml_text: str, name: str) -> str:
        """The lines of one top-level CI job: from its two-space key to the next one.

        A line scan rather than a regex: a job body is indented four spaces or more (or
        blank), so the next line indented two spaces or less is the following job.
        """
        lines = yaml_text.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln == f"  {name}:")
        body = []
        for ln in lines[start + 1:]:
            if ln and not ln.startswith("   "):
                break
            body.append(ln)
        return "\n".join(body)

    def test_the_ci_job_runs_the_make_target_not_a_raw_update(self) -> None:
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = self._job_block(ci, "declared-stops")
        assert "make declared-stops" in job, job
        assert "--update" not in job, job
