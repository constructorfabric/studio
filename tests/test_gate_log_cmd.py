"""`cfs gate-log` — the write path a chat gate uses to record how it resolved.

Driven through the command entry point rather than the writer, because that is
what a PDSL gate invokes: `RUN `{cfs_cmd} gate-log ...``. A test that only
exercised `record_gate` would prove the library and not the path.

Covers the invariant the rest of the task rests on: a resolution's authority comes
from its declared type, so the command must succeed even when nothing is
recorded. If it failed instead, a user who turned logging off -- or a full disk --
would silently stop Studio deciding anything for itself.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.commands import gate_log
from studio.commands.gate_log import cmd_gate_log
from studio.utils import decision_log as dl
from studio.utils.decision_log import UNSPECIFIED


def _args(**over) -> list[str]:
    """A complete, valid argv, with named overrides.

    Took an unused `log` argument at every call site; the log location comes from
    `$CFS_DECISION_LOG`, which each test sets.
    """
    base = {"--kind": "auto-proceeded", "--gate": "PlanProduceChoice",
            "--declared-type": "decision", "--cost-if-wrong": "a rebuild",
            "--decision-key": "plan.produce-mode", "--value": "inline",
            "--provenance": "plan", "--status": "resolved"}
    base.update(over)
    argv: list[str] = []
    for flag, value in base.items():
        argv += [flag, value]
    return argv


def _events(log: Path) -> list[dict]:
    return list(dl.read_events(path=log)) if log.exists() else []


class TestExitCodes:
    """The truth table a caller can rely on."""

    def test_a_complete_ruling_records_and_exits_zero(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        assert cmd_gate_log(_args()) == 0
        gates = [e for e in _events(log) if e["event"] == "gate"]
        assert len(gates) == 1
        # every flag's value, not just one: dropping `declared_type` and the whole
        # ruling in the call left the previous assertions passing.
        payload = gates[0]["payload"]
        assert payload["gate"] == "PlanProduceChoice"
        assert payload["declared_type"] == "decision"
        assert payload["decision_key"] == "plan.produce-mode"
        assert payload["value"] == "inline"
        assert payload["provenance"] == "plan"
        assert payload["status"] == "resolved"
        assert payload["cost_if_wrong"] == "a rebuild"

    def test_an_autonomous_ruling_without_a_cost_is_refused_and_says_so(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """The three-part ruling is what makes it auditable rather than merely recorded.

        Refusing silently would be worse than accepting: the caller is a workflow
        that cannot see an exit code without being told what to fix.
        """
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        rc = cmd_gate_log(_args(**{"--cost-if-wrong": "   "}))
        assert rc == 2
        assert not [e for e in _events(log) if e["event"] == "gate"]
        # `tests/conftest.py` forces JSON mode, so the machine contract is what
        # reaches stdout; the prose is asserted on the formatter directly below.
        payload = json.loads(capsys.readouterr().out)
        assert payload["recorded"] is False
        assert payload["reason"] == "missing-cost-if-wrong"

    def test_a_missing_required_argument_is_reported_not_crashed(self, capsys) -> None:
        """v3 B3: the argparse-omitted case, which a helper-only test never reaches.

        The exact code, not `!= 0`: 2 is the contract for a refusal and 1 would be
        an error, so a loose assertion passed for either and the sibling test one
        screen down already pinned 2.
        """
        assert cmd_gate_log([]) == 2
        captured = capsys.readouterr()          # read once: a second call returns empty
        assert captured.out or captured.err, "exited non-zero without saying why"

    def test_an_unknown_kind_is_rejected_at_the_boundary(self, capsys) -> None:
        """The five subtypes are a closed set at the CLI, whatever the writer tolerates."""
        assert cmd_gate_log(["--kind", "invented", "--gate", "G",
                             "--declared-type", "decision"]) == 2
        captured = capsys.readouterr()
        assert "invalid choice" in (captured.out + captured.err), \
            "a bad --kind must be reported, not raised as a traceback"


class TestTheLedgerIsNeverAuthority:
    """D-e: a resolution proceeds whether or not the ledger accepted it."""

    def test_logging_off_still_exits_zero_and_names_the_reason(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        monkeypatch.setenv("CFS_DECISION_LOG", "off")
        assert cmd_gate_log(_args()) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["recorded"] is False
        assert payload["logging_enabled"] is False   # the reason, machine-readable

    def test_a_refused_write_still_exits_zero_and_names_a_different_reason(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """"Not recorded" must not collapse into one reason.

        Named for what it does: it stubs the writer's return value rather than
        causing a write to fail, so it pins the *reporting*, not the failure. The
        real unwritable-path behaviour is covered by the never-raises tests in
        `test_decision_log.py`.

        A user who opted out and a user whose disk is full need different
        answers, and one code for two failures is the defect this separates.
        """
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        # Patch the name `gate_log` bound at import, not the one in `decision_log`:
        # `from ... import record_gate` copies the reference, so patching the module
        # it came from leaves this caller pointing at the original.
        monkeypatch.setattr(gate_log, "record_gate", lambda *_a, **_k: False)
        assert cmd_gate_log(_args()) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["recorded"] is False
        assert payload["logging_enabled"] is True    # not the opt-out: a real write failure


class TestPayloadShape:
    def test_json_mode_reports_whether_it_recorded(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """A caller parsing the result must be able to tell, without reading prose."""
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        cmd_gate_log(_args())
        payload = json.loads(capsys.readouterr().out)
        assert payload["recorded"] is True
        assert payload["logging_enabled"] is True
        assert payload["gate"] == "PlanProduceChoice"


class TestTheHumanFormatterNamesTheReason:
    """The prose path, tested directly -- JSON mode hides it from the command tests.

    An earlier draft of this command returned its text instead of printing it, so
    it exited 2 in silence. These pin that the reason is said out loud.
    """

    @pytest.fixture(autouse=True)
    def _human_mode(self):
        """`ui.header`/`substep` return early in JSON mode, which conftest forces on."""
        from studio.utils.ui import set_json_mode
        set_json_mode(False)
        yield
        set_json_mode(True)

    @pytest.mark.parametrize(("reason", "expected"), [
        (None, "recorded plan-resolved"),
        ("logging-off", "logging is off"),
        ("logging-state-unknown", "could not be determined"),
        ("no-log-location", "not a Studio project"),
        ("write-failed", "could not be written"),
        ("missing-cost-if-wrong", "cost-if-wrong"),
        ("empty-gate", "the gate must be named"),
    ])
    def test_every_reason_has_its_own_line(self, reason, expected: str, capsys) -> None:
        """One line per reason, so the prose and the machine-readable code agree."""
        gate_log._human_gate_log({"recorded": reason is None, "logging_enabled": True,
                                  "reason": reason, "kind": "plan-resolved", "gate": "G"})
        assert expected in capsys.readouterr().out

    def test_every_reason_the_command_can_emit_has_a_line(self) -> None:
        """A new reason with no line would raise a KeyError mid-render."""
        assert set(gate_log._REASON_TEXT) >= {
            "logging-off", "logging-state-unknown", "no-log-location", "write-failed",
            "missing-cost-if-wrong", "empty-gate"}


class TestTheCommandIsReachable:
    """Registration, because deleting it broke nothing.

    Removing `gate-log` from the dispatch table left 1108 CLI tests passing while
    the command became undispatchable -- and being dispatchable is its whole
    purpose, since a PDSL gate reaches Python only by running a subcommand.
    """

    def test_it_is_present_in_every_registration_table(self) -> None:
        from studio import cli
        assert "gate-log" in cli._COMMAND_DESCRIPTIONS
        assert "gate-log" in cli._COMMAND_HANDLERS
        assert cli._cmd_gate_log in cli._COMMAND_HANDLER_REFERENCES, \
            "the handler is not in the reference tuple, so the lazy import is unverified"
        assert any("gate-log" in names for _, names in cli._COMMAND_SECTIONS), \
            "absent from every help section, so it is undiscoverable"

    def test_the_dispatcher_actually_routes_to_it(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """Through `cli.main`, not the helper -- the truth table above is helper-level."""
        from studio import cli
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        rc = cli.main(["gate-log", "--kind", "plan-resolved", "--gate", "G",
                       "--declared-type", "decision", "--cost-if-wrong", "x",
                       "--decision-key", "plan.produce-mode"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["recorded"] is True


class TestOneShapeOnEveryPath:
    """A caller must never branch on key presence."""

    # A frozen set for a class-level constant, which is what the module's own
    # `frozenset` constants already do. `set(payload) == KEYS` compares equal either
    # way, so nothing about the assertion changes.
    KEYS = frozenset({"recorded", "logging_enabled", "reason", "gate", "kind"})

    @pytest.mark.parametrize(("argv_over", "expected_reason"), [
        ({}, None),
        ({"--cost-if-wrong": UNSPECIFIED}, "missing-cost-if-wrong"),
        ({"--gate": "  "}, "empty-gate"),
    ])
    def test_success_and_both_refusals_carry_the_same_keys(
            self, argv_over: dict, expected_reason, tmp_path: Path,
            monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        cmd_gate_log(_args(**argv_over))
        payload = json.loads(capsys.readouterr().out)
        assert set(payload) == self.KEYS, f"key set differs: {sorted(payload)}"
        assert payload["reason"] == expected_reason


class TestTheCostGuardCoversEveryAutonomousKind:
    """`plan-resolved` proceeds without a human too, so it is held to the same rule."""

    @pytest.mark.parametrize("kind", ["auto-proceeded", "plan-resolved"])
    def test_a_kind_that_proceeds_alone_is_refused_without_a_cost(
            self, kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        rc = cmd_gate_log(_args(**{"--kind": kind, "--cost-if-wrong": UNSPECIFIED}))
        capsys.readouterr()
        assert rc == 2, f"{kind} recorded an autonomous ruling with no stated cost"

    @pytest.mark.parametrize("kind", ["exception-asked", "blocking-confirmed", "open-question"])
    def test_a_kind_involving_a_person_needs_no_cost(
            self, kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """Requiring one here would be wrong: nothing was decided without asking."""
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        rc = cmd_gate_log(_args(**{"--kind": kind, "--cost-if-wrong": UNSPECIFIED}))
        capsys.readouterr()
        assert rc == 0


class TestHumanModeGoesThroughTheCommand:
    """The formatter must be *wired*, not merely correct.

    Nulling both `human_fn=` arguments left every test passing while the command
    printed a bare `Status:` and exited 2 in silence -- the regression the format
    step exists to prevent.
    """

    @pytest.fixture(autouse=True)
    def _human_mode(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)
        yield
        set_json_mode(True)

    def test_a_refusal_names_its_reason_through_the_command(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        rc = cmd_gate_log(_args(**{"--cost-if-wrong": UNSPECIFIED}))
        out = capsys.readouterr().out
        assert rc == 2
        assert "cost-if-wrong" in out, f"exited 2 in silence; stdout was {out!r}"

    def test_a_crafted_gate_name_cannot_forge_an_outcome_line(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """`--gate` is author-controlled text from a MENU block."""
        monkeypatch.setenv("CFS_DECISION_LOG", "off")
        forged = "RealGate\n  \x1b[32m*\x1b[0m recorded blocking-confirmed for RealGate"
        cmd_gate_log(_args(**{"--gate": forged}))
        out = capsys.readouterr().out
        # The UI colourises its own header, so the output legitimately contains
        # escapes; what must not survive is an escape or a line break *from the
        # gate value*. Both show up structurally: the forged text would otherwise
        # open its own line.
        assert not any(line.strip().startswith("recorded blocking-confirmed")
                       for line in out.splitlines()), "a forged outcome line was rendered"
        assert "\x1b[32m" not in out, "a colour code from the gate value survived"
        assert '"' in out, "the author-controlled value is not delimited"
        assert "not recorded" in out, "the real outcome is no longer stated"


class TestValidationPrecedence:
    """Which guard wins when two are violated at once.

    Staged checks with no asserted order are how a caller learns the wrong thing
    first: a workflow told "state a cost" would add one and still be refused, for
    the gate name it never heard about.
    """

    def test_an_unnamed_gate_is_reported_before_a_missing_cost(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        rc = cmd_gate_log(_args(**{"--gate": "  ", "--cost-if-wrong": UNSPECIFIED}))
        payload = json.loads(capsys.readouterr().out)
        assert rc == 2
        assert payload["reason"] == "empty-gate", \
            "identity is reported before the ruling, so a caller fixes the right thing first"

    def test_an_invisible_cost_is_refused_like_an_absent_one(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """A BOM plus a zero-width space is not a stated cost."""
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        rc = cmd_gate_log(_args(**{"--cost-if-wrong": chr(0xFEFF) + chr(0x200B)}))
        payload = json.loads(capsys.readouterr().out)
        assert rc == 2
        assert payload["reason"] == "missing-cost-if-wrong"


class TestTheCommandSurvivesAnUndeterminableHome:
    """A1a: the never-raise promise has to hold in the command, not only the writer.

    `is_enabled()` reaches `Path.home()`, which raises `RuntimeError` -- not
    `OSError`, so its own guard misses it -- when `$HOME` is unset and the uid has
    no passwd entry, as under `docker run --user 1234`. The writer degraded to
    `False`; the command then died *reporting* that, by traceback, having printed
    nothing. Nothing pinned it until this test.
    """

    def test_it_reports_rather_than_raising(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        def _boom():
            raise RuntimeError("Could not determine home directory.")

        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        monkeypatch.setattr(Path, "home", _boom)

        rc = cmd_gate_log(_args())          # must not raise
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0, "a logging problem must never fail the caller"
        assert payload["logging_enabled"] is None, "an unknown state is not False"
        assert payload["reason"] == "logging-state-unknown"


class TestTheVocabulariesAreCheckedTogether:
    """Each closed set validating alone accepted a contradictory record.

    The frozen contract is that `absent` and `ambiguous` both *ask*, and the ask is
    logged as an exception -- so neither can sit on a kind claiming the gate
    resolved. `--kind auto-proceeded --status absent` passed both vocabularies and
    recorded a resolution that had not happened.
    """

    @pytest.mark.parametrize("kind", ["auto-proceeded", "plan-resolved"])
    @pytest.mark.parametrize("status", ["absent", "ambiguous"])
    def test_a_resolving_kind_cannot_carry_a_non_resolving_status(
            self, kind: str, status: str, tmp_path: Path,
            monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        rc = cmd_gate_log(_args(**{"--kind": kind, "--status": status}))
        payload = json.loads(capsys.readouterr().out)
        assert rc == 2, f"{kind} + {status} recorded a resolution that did not happen"
        assert payload["reason"] == "status-contradicts-kind"

    @pytest.mark.parametrize("status", ["absent", "ambiguous"])
    def test_the_asking_kind_may_carry_them(
            self, status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        """`exception-asked` is what the contract says these become."""
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        rc = cmd_gate_log(_args(**{"--kind": "exception-asked", "--status": status,
                                   "--cost-if-wrong": UNSPECIFIED}))
        capsys.readouterr()
        assert rc == 0

    def test_a_resolving_kind_may_still_carry_resolved_or_unspecified(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        for status in ("resolved", UNSPECIFIED):
            assert cmd_gate_log(_args(**{"--status": status})) == 0
            capsys.readouterr()



class TestTheJsonReasonNamesTheRealCause:
    """The reason in the JSON, driven from the condition rather than handed in.

    The reason lines were pinned by calling the formatter with a dict built in the
    test, and the vocabulary was pinned by set membership. Neither exercised the
    mapping from a real condition to a real reason -- so `logging-off` could have
    been produced for an unwritable log, or `write-failed` for a missing project,
    and every assertion would still have passed. These start from the condition.
    """

    def _reason(self, argv: list[str], capsys, *, logging_enabled=...) -> dict:
        """Return the payload, having asserted the whole triple rather than one key.

        Three of the four causes asserted only `reason`, so a cause reporting the
        wrong `recorded` or `logging_enabled` alongside the right reason would have
        passed. The triple is the contract a caller reads.
        """
        assert cmd_gate_log(argv) == 0, "a logging failure must never fail the command"
        payload = json.loads(capsys.readouterr().out)
        assert payload["recorded"] is False
        if logging_enabled is not ...:
            assert payload["logging_enabled"] is logging_enabled, payload
        assert set(payload) == {"recorded", "logging_enabled", "reason", "gate", "kind"}
        return payload

    def test_an_off_value_in_the_env_is_reported_as_logging_off(
            self, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CFS_DECISION_LOG", "off")
        payload = self._reason(_args(), capsys, logging_enabled=False)
        assert payload["reason"] == "logging-off"

    def test_no_project_and_no_override_is_reported_as_no_log_location(
            self, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CFS_DECISION_LOG", raising=False)
        # Both names: the command resolved `None` while the writer resolved the
        # real project log from its own module and recorded the event anyway, so
        # patching only the command's copy tested nothing it claimed to.
        monkeypatch.setattr(gate_log, "default_log_path", lambda: None)
        monkeypatch.setattr(dl, "default_log_path", lambda: None)
        payload = self._reason(_args(), capsys, logging_enabled=True)
        assert payload["reason"] == "no-log-location"

    def test_a_failed_write_with_a_location_is_reported_as_write_failed(
            self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        """The residual cause: logging on, a location known, the write still failed."""
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / ".cache" / "decisions.jsonl"))
        monkeypatch.setattr(gate_log, "record_gate", lambda *a, **k: False)
        payload = self._reason(_args(), capsys, logging_enabled=True)
        assert payload["reason"] == "write-failed"

    def test_an_undeterminable_opt_out_state_is_not_reported_as_off(
            self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        """The distinction the tri-state was introduced for, at the JSON boundary."""
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / ".cache" / "decisions.jsonl"))
        monkeypatch.setattr(dl, "opt_out_sentinel_path",
                            lambda: (_ for _ in ()).throw(OSError("no home")))
        payload = self._reason(_args(), capsys, logging_enabled=None)
        assert payload["reason"] == "logging-state-unknown"

    def test_the_echoed_gate_is_redacted_and_capped_like_the_record(
            self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        """The echo is a third sink for author-controlled text, not a copy of argv.

        A gate name carrying an absolute home path kept the username on the way
        out while losing it on the way in.
        """
        log = tmp_path / ".cache" / "decisions.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        monkeypatch.setenv("HOME", "/home/someone")
        payload = json.loads(
            (cmd_gate_log(_args(**{"--gate": "Gate at /home/someone/work"})),
             capsys.readouterr().out)[1])
        assert "/home/someone" not in payload["gate"]
        assert payload["gate"] == "Gate at ~/work"

    def test_a_gate_name_longer_than_the_cap_is_cut_in_the_echo_too(
            self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / ".cache" / "decisions.jsonl"))
        cmd_gate_log(_args(**{"--gate": "G" * 5000}))
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["gate"]) <= dl._GATE_TEXT_CAP
        assert payload["gate"].endswith(dl._TRUNCATION_MARKER)


class TestTheLoggingStateIsSaidOutLoudWhenItIsNotTheCause:
    """A validation refusal happens before the writer, so its reason cannot carry it.

    `empty-gate` rendered one identical line whether logging was on, off or
    undeterminable -- a state the JSON carried and the human read dropped.
    """

    @pytest.fixture(autouse=True)
    def _human_mode(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)
        yield
        set_json_mode(True)

    @pytest.mark.parametrize(("state", "expected"), [
        (True, "logging: on"), (False, "logging: off by choice"),
        (None, "logging: unknown"),
    ])
    def test_each_state_is_rendered_on_a_validation_refusal(
            self, state, expected: str, capsys) -> None:
        gate_log._human_gate_log({"recorded": False, "logging_enabled": state,
                                  "reason": "empty-gate", "kind": "auto-proceeded",
                                  "gate": ""})
        assert expected in capsys.readouterr().out

    def test_a_logging_state_reason_does_not_repeat_itself(self, capsys) -> None:
        """`logging-off` already says it; a second line would be noise."""
        gate_log._human_gate_log({"recorded": False, "logging_enabled": False,
                                  "reason": "logging-off", "kind": "auto-proceeded",
                                  "gate": "G"})
        out = capsys.readouterr().out
        assert "logging is off" in out
        assert "logging: off by choice" not in out

    def test_every_validation_refusal_is_a_reason_the_command_can_emit(self) -> None:
        """A typo here would silently stop the state ever being rendered."""
        assert set(gate_log._VALIDATION_REFUSALS) <= set(gate_log._REASON_TEXT)


class TestAnAutonomousRulingMustSayWhatAndWhatItCosts:
    """Both anchors, and neither defeatable by how the sentinel is spelled."""

    @pytest.mark.parametrize("spelling", [
        "unspecified", "Unspecified", "UNSPECIFIED", "  UnSpEcIfIeD  ", "",
    ])
    @pytest.mark.parametrize("kind", ["auto-proceeded", "plan-resolved"])
    def test_a_sentinel_cost_is_refused_however_it_is_cased(
            self, spelling: str, kind: str, tmp_path: Path, capsys,
            monkeypatch: pytest.MonkeyPatch) -> None:
        """`Unspecified` is visible text that means nothing, so `is_blank` passed it."""
        log = tmp_path / "d.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        assert cmd_gate_log(_args(**{"--kind": kind,
                                     "--cost-if-wrong": spelling})) == 2
        assert json.loads(capsys.readouterr().out)["reason"] == "missing-cost-if-wrong"
        assert not [e for e in _events(log) if e["event"] == "gate"]

    @pytest.mark.parametrize("spelling", ["unspecified", "UNSPECIFIED", " Unspecified ", ""])
    def test_a_sentinel_decision_key_is_refused_the_same_way(
            self, spelling: str, tmp_path: Path, capsys,
            monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        assert cmd_gate_log(_args(**{"--decision-key": spelling})) == 2
        assert json.loads(capsys.readouterr().out)["reason"] == "missing-decision-key"

    def test_a_kind_that_involved_a_human_needs_neither(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The requirement is about proceeding *without* being asked."""
        log = tmp_path / "d.jsonl"
        monkeypatch.setenv("CFS_DECISION_LOG", str(log))
        assert cmd_gate_log(_args(**{"--kind": "exception-asked",
                                     "--status": "absent",
                                     "--cost-if-wrong": UNSPECIFIED,
                                     "--decision-key": UNSPECIFIED})) == 0
        assert len([e for e in _events(log) if e["event"] == "gate"]) == 1

    def test_the_cost_refusal_still_takes_precedence_over_the_key(
            self, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
        """Order is fixed so one call reports one reason, not whichever it noticed."""
        monkeypatch.setenv("CFS_DECISION_LOG", str(tmp_path / "d.jsonl"))
        assert cmd_gate_log(_args(**{"--cost-if-wrong": "", "--decision-key": ""})) == 2
        assert json.loads(capsys.readouterr().out)["reason"] == "missing-cost-if-wrong"
