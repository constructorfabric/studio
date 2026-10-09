"""One run's answer must never complete a different run — GH #434.

`record()` stamps every event with the run id read from the **shared, project-wide** run-id file at
write time, and `start_run()` overwrites that file. So a gate that waits on a human, while a second
run starts in the same checkout, has its answer written after the file changed and attributed to
the wrong run. That run's close then reads a `(needs: …)` item as answered and reports COMPLETE on
an answer nobody gave it.

The acceptance bar is a **matrix, not a pair**: both overlap shapes against every answering kind.
The failure is caused by the run id reaching the close at all, not by any one kind, so a regression
written against only the newest kind would pass while the older ones stayed broken.

Every test here must fail against the code as it was before the fix. One that passes unfixed is
evidence of nothing.

**One honest limit, stated rather than hidden.** `exception-asked` closes a question only once the
conditional rule from the completion-check work exists. On this branch it never answers, so the
*close* half of its three matrix cells passes whatever the run id says — fail-safe, but not
load-bearing here. The *attribution* half (the event carries the asking run's id) is meaningful for
all three kinds on any branch, and it is the half this change is actually about. The close half
becomes load-bearing for `exception-asked` when the two branches meet, which is the point of
covering it now rather than later.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio.commands import verify_completion as vc  # noqa: E402
from studio.utils import decision_log as dl  # noqa: E402

#: The item under test declares the key it waits on, so the close must hold it until that key is
#: answered *within the run being closed*.
_KEY = "pricing_model"
_ITEM = f"PRD approved (needs: {_KEY})"
_PHASE = f"## Acceptance Criteria\n- [ ] {_ITEM}\n"
_MANIFEST = '[plan]\ntask = "t"\napproval_status = "approved"\n[[phases]]\nnumber = 1\nfile = "p.md"\n'

#: Every kind that closes a question, with the status that makes it one. `plan-resolved` and
#: `blocking-confirmed` predate the completion check; `exception-asked` is newer. All three must
#: be covered -- see the module docstring.
_ANSWERING_KINDS = [
    pytest.param("plan-resolved", "plan", id="plan-resolved"),
    pytest.param("blocking-confirmed", dl.UNSPECIFIED, id="blocking-confirmed"),
    pytest.param("exception-asked", dl.UNSPECIFIED, id="exception-asked"),
]


@pytest.fixture(autouse=True)
def _no_ambient_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from a known session environment, whatever the developer's shell holds.

    Review finding, reproduced: `_session` set the vendor variable but never cleared
    `CFS_RUN_SESSION`, which is checked **first** — so under a driver that exports it, both
    "sessions" resolved to one key and seven tests failed. Clearing in one autouse place rather
    than in the helper fixes the class: a test added later cannot inherit a session it did not
    ask for, whichever of the two names is set.
    """
    for name in dl._SESSION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(name="log")
def _log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated decision log for each test.

    `conftest` points `CFS_DECISION_LOG` at one session-scoped telemetry directory and says
    telemetry tests must override it themselves. Without this they did: `run_id_path()` resolved
    to that shared directory rather than the test's own, so every test here wrote its run-id file
    to the same place and the isolation each one claims to prove was never isolated.
    """
    log = tmp_path / ".cache" / "decisions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    return log


def _plan_at(root: Path) -> tuple[Path, Path]:
    """A plan whose single criterion waits on `_KEY`, with that criterion already satisfied.

    Satisfied on purpose: the only thing that may hold this run is the unanswered question, so a
    run that still reports INCOMPLETE is being held for the right reason.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "plan.toml").write_text(_MANIFEST, encoding="utf-8")
    (root / "p.md").write_text(_PHASE, encoding="utf-8")
    verdicts = root / "verdicts.toml"
    verdicts.write_text(
        f'[[verdicts]]\nitem = "{_ITEM}"\nverdict = "satisfied"\nevidence = "signed off"\n',
        encoding="utf-8")
    return root, verdicts


def _session(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Act as a different driving session, which is what distinguishes one run from another.

    Sets the **vendor** name deliberately: `_cfs` drives the neutral one, so between them both
    entries of `_SESSION_ENV_VARS` are exercised rather than only the convenient one. The autouse
    fixture above guarantees the higher-priority name is not also set.
    """
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", name)


@pytest.mark.parametrize("kind, provenance", _ANSWERING_KINDS)
@pytest.mark.parametrize("same_plan", [True, False], ids=["same-plan", "different-plans"])
def test_an_overlapping_runs_answer_cannot_complete_this_run(
        tmp_path: Path, log: Path, monkeypatch: pytest.MonkeyPatch,
        kind: str, provenance: str, same_plan: bool) -> None:

    # Run A starts, then run B starts while A is still going -- the overlap. Before the fix both
    # wrote the same project-wide file, so B's id replaced A's for every later command.
    _session(monkeypatch, "session-a")
    id_a = dl.start_run(log.parent)
    _session(monkeypatch, "session-b")
    id_b = dl.start_run(log.parent)
    assert id_a, "run A never started, so there is nothing to misattribute"
    assert id_b, "run B never started, so there is no overlap to test"
    assert id_a != id_b, "the two runs share an id, so no test below can tell them apart"

    # A's user answers the gate *after* B started. This is the write that used to be misattributed.
    _session(monkeypatch, "session-a")
    assert dl.record_gate(kind, "PricingGate", "decision",
                          dl.GateRuling(decision_key=_KEY, value="usage-based",
                                        provenance=provenance, status="resolved"),
                          path=log), "the answer was not recorded, so this proves nothing"

    events = [e for e in dl.read_events(path=log) if e.get("event") == "gate"]
    assert events, "no gate event reached the log"
    assert events[-1].get("run_id") == id_a, (
        "run A's answer was stamped with another run's id; B's close will now read it as its own")

    # B closes. Nobody answered this question in B, so B must be held.
    b_root = tmp_path / ("plan-p" if same_plan else "plan-q")
    plan_dir, verdicts = _plan_at(b_root)
    _session(monkeypatch, "session-b")
    result = vc.assess(plan_dir, verdicts, log_path=log, run_id=id_b)

    assert result.exit_code == 2, (
        f"run B reported {result.status} on an answer given in run A ({kind})")
    assert _ITEM in result.blocked_on_question, (
        "B was held, but not because the question is unanswered -- so this test is not watching "
        "the thing it claims to watch")


#: The kinds that close a question **on this branch**. `exception-asked` answers only once the
#: conditional rule from the completion-check work lands; until then a run cannot complete on one,
#: so asserting that it does would be asserting someone else's change. It joins this list in the
#: branch that adds the rule.
_KINDS_THAT_ANSWER_HERE = [p for p in _ANSWERING_KINDS if p.id != "exception-asked"]


@pytest.mark.parametrize("kind, provenance", _KINDS_THAT_ANSWER_HERE)
def test_a_runs_own_answer_still_completes_it(
        tmp_path: Path, log: Path, monkeypatch: pytest.MonkeyPatch,
        kind: str, provenance: str) -> None:
    """The other edge: scoping must not become so strict that a run cannot read its own answer.

    Without this, every test above would pass against a build that simply never matched anything,
    which is the failure mode the open-questions register is most likely to regress into.
    """

    _session(monkeypatch, "session-a")
    id_a = dl.start_run(log.parent)
    assert id_a
    assert dl.record_gate(kind, "PricingGate", "decision",
                          dl.GateRuling(decision_key=_KEY, value="usage-based",
                                        provenance=provenance, status="resolved"),
                          path=log)

    plan_dir, verdicts = _plan_at(tmp_path / "plan-p")
    result = vc.assess(plan_dir, verdicts, log_path=log, run_id=id_a)
    assert result.exit_code == 0, (
        f"a run could not complete on its own answer ({kind}): {result.message}")


def test_two_sessions_do_not_share_a_run_id_file(
        log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The mechanism itself: concurrent sessions must not overwrite each other's run id.

    Asserted separately from the behaviour above so a regression says *which* layer broke.
    """

    _session(monkeypatch, "session-a")
    id_a = dl.start_run(log.parent)
    _session(monkeypatch, "session-b")
    dl.start_run(log.parent)

    _session(monkeypatch, "session-a")
    assert dl.current_run_id(log.parent) == id_a, (
        "a second session's run-start replaced the first session's id")


@pytest.mark.parametrize("value", [
    "sess-\u00e9\u00e8",                     # non-ASCII
    "\U0001f600-session",                     # outside the BMP
    "sess\udcff",                             # a lone surrogate, as an undecodable byte arrives
    " padded ",                                # whitespace, which must not make two sessions one
    "../../escape",                            # path characters, which must not reach the filename
    "x" * 4096,                                # longer than any filesystem name limit
], ids=["non-ascii", "astral", "surrogate", "padded", "path-chars", "very-long"])
def test_any_session_value_yields_a_safe_filename(
        tmp_path: Path, log: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """The session comes from the environment, so it is arbitrary text, not a tidy identifier.

    It is digested rather than used literally: a name built from the raw value could leave the
    directory, collide after case-folding, exceed the OS limit, or raise on an undecodable byte
    while resolving a path -- and this module must never raise, since everything downstream of it
    is instrumentation.
    """
    monkeypatch.setenv("CFS_RUN_SESSION", value)

    path = dl.run_id_path(log.parent)
    assert path is not None
    assert path.parent == log.parent, "the run-id file escaped the directory it belongs in"
    assert len(path.name) < 64, "the filename could exceed a filesystem name limit"
    assert "/" not in path.name, "a path separator reached the filename"
    assert "\\" not in path.name, "a Windows path separator reached the filename"

    run_id = dl.start_run(log.parent)
    assert run_id, "a run could not start under this session value"
    assert dl.current_run_id(log.parent) == run_id


def test_surrounding_whitespace_does_not_split_one_session_in_two(
        log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`" a "` and `"a"` are the same session, so they must key the same run-id file.

    Caught by mutation: removing the `.strip()` from the digest killed nothing, because the
    padded case only checked that the *filename* was safe and never that the identity was the
    same. If a driver reported its session with stray whitespace on one command and without it on
    the next, the run would split in two mid-flight -- quietly, and exactly the class of failure
    this change exists to remove.
    """
    monkeypatch.setenv("CFS_RUN_SESSION", "  a-session  ")
    padded = dl.run_id_path(log.parent)
    monkeypatch.setenv("CFS_RUN_SESSION", "a-session")
    bare = dl.run_id_path(log.parent)
    assert padded == bare, "whitespace around the session value made it a different run"


def test_a_whitespace_only_session_is_no_session(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Otherwise an empty-but-set variable would read as isolation that is not there -- the guard
    # reporting itself present while behaving exactly like the unprotected case.
    monkeypatch.setenv("CFS_RUN_SESSION", "   ")
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    assert dl.session_key() is None


def test_runs_in_one_session_still_replace_each_other(
        log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """...and the opposite must stay true: within one session, runs are sequential, so a new
    run-start replaces the previous id. Keying by session must not turn into keying by nothing."""

    _session(monkeypatch, "session-a")
    first = dl.start_run(log.parent)
    second = dl.start_run(log.parent)
    assert first != second
    assert dl.current_run_id(log.parent) == second, (
        "a later run in the same session did not take over, so one session's runs would pool")


# ---------------------------------------------------------------------------
# across real processes

_CLI = Path(__file__).resolve().parents[1] / "skills/studio/scripts/studio.py"


def _cfs(session: str, log: Path, *args: str) -> subprocess.CompletedProcess:
    """One `cfs` command, as a separate process in a named session.

    The whole mechanism rests on environment **inheritance** across processes, which an
    in-process test cannot exercise: it patches `os.environ` in the one interpreter that also
    holds the module state. Running the real entry point is the only way to show that a run's
    commands agree on their id for the reason claimed, rather than because they share memory.
    """
    env = {**os.environ, "CFS_RUN_SESSION": session, "CFS_DECISION_LOG": str(log)}
    env.pop("CLAUDE_CODE_SESSION_ID", None)   # the neutral name must carry this on its own
    return subprocess.run([sys.executable, str(_CLI), *args],
                          capture_output=True, text=True, env=env, check=False, timeout=60)


def _run_id_of(session: str, log: Path) -> str:
    """Start a run in `session` and return the id that run was given, read from the JSON result."""
    done = _cfs(session, log, "--json", "run-start")
    assert done.returncode == 0, done.stdout + done.stderr
    payload = json.loads(done.stdout[done.stdout.index("{"):])
    assert payload["session_isolated"] is True, (
        "a named session was not reported as isolated, so the id is project-wide after all")
    return payload["run_id"]


def test_across_processes_an_overlapping_run_cannot_steal_the_answer(tmp_path: Path) -> None:
    log = tmp_path / ".cache" / "decisions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)

    alpha = _run_id_of("alpha", log)
    beta = _run_id_of("beta", log)          # the overlap: starts while alpha is still going
    assert alpha != beta

    # `--cost-if-wrong` is required for an autonomous ruling at the CLI layer. The unit tests
    # above call `record_gate` directly and never meet that rule, which is exactly why this
    # end-to-end exists: the first hand-run of it failed here, silently writing nothing.
    answered = _cfs("alpha", log, "gate-log", "--kind", "plan-resolved", "--gate", "PricingGate",
                    "--declared-type", "decision", "--decision-key", _KEY, "--value", "usage-based",
                    "--provenance", "plan", "--status", "resolved", "--why", "the plan says so",
                    "--cost-if-wrong", "low")
    assert answered.returncode == 0, f"the answer was not recorded: {answered.stdout}{answered.stderr}"

    gates = [e for e in dl.read_events(path=log) if e.get("event") == "gate"]
    assert gates, "no gate event reached the log"
    stamped = gates[-1].get("run_id")

    assert stamped == alpha, (
        "the answer was attributed to the overlapping run rather than the one that asked")
    assert stamped != beta
    assert len(list(log.parent.glob("run-id-*"))) == 2, "the two sessions shared one run-id file"
