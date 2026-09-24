"""Tests for asserting a reversal mechanism is armed before an autonomous edit.

The rule these pin is one sentence: assert that a mechanism is armed, never judge whether
an action looks undoable. Most of what follows is about the second half.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio.utils import armed_reversal as ar  # noqa: E402
from studio.utils import change_summary  # noqa: E402


def _git(cwd: Path, *args: str) -> None:
    """Run git for a fixture, in the environment the production module already defines.

    `_git_env` rather than a list written here. The first version of this hardcoded eight
    redirect variables, which covered the ones I thought of and omitted every
    *configuration* channel the shipped helper carries — `GIT_CONFIG_PARAMETERS`,
    `GIT_CONFIG_COUNT` and the indexed `KEY_n`/`VALUE_n` pairs it gates,
    `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_CONFIG_NOSYSTEM` and
    `GIT_DISCOVERY_ACROSS_FILESYSTEM`. Those were added to the production list by
    measurement, in response to real failures, and a second copy is exactly how that work
    gets lost: the copy is the one that stops being updated. Raised in review, twice —
    the first fix wrote the duplicate, the second removed it.
    """
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True, env=change_summary._git_env())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with one commit, on a named branch."""
    root = tmp_path / "project"
    root.mkdir()
    # `--initial-branch` arrived in git 2.28 (2020). Set the name after `init` instead, so
    # the fixture does not fail on an older git with an error about a flag rather than
    # about the thing under test.
    _git(root, "init", "--quiet")
    _git(root, "checkout", "--quiet", "-B", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    (root / "file.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "file.txt")
    _git(root, "commit", "--quiet", "-m", "first")
    return root


class TestWhichMechanismAnswers:
    """Three mechanisms, weakest last, first answer wins."""

    def test_a_linked_worktree_arms_the_check(self, repo: Path, tmp_path: Path) -> None:
        """The strongest: the edit happens in a checkout that can simply be thrown away."""
        linked = tmp_path / "linked"
        _git(repo, "worktree", "add", "--quiet", str(linked), "-b", "side")
        found = ar.armed_reversal(linked)
        assert found.armed is True, found
        assert found.mechanism == ar.WORKTREE, found

    def test_a_named_branch_arms_the_check(self, repo: Path) -> None:
        found = ar.armed_reversal(repo)
        assert found.armed is True, found
        assert found.mechanism == ar.BRANCH, found

    def test_worktree_wins_when_both_are_available(self, repo: Path, tmp_path: Path) -> None:
        """The order is fixed, not a preference.

        A linked worktree on a named branch satisfies both. Each mechanism is strictly
        weaker than the one before, so the first that answers must be the strongest
        available — "try them in any order" is how the weakest becomes the default.
        """
        linked = tmp_path / "both"
        _git(repo, "worktree", "add", "--quiet", str(linked), "-b", "named")
        branched, failed = ar._on_named_branch(linked)
        assert not failed, "the branch probe failed rather than answering"
        assert branched, "the fixture no longer satisfies both mechanisms"
        assert ar.armed_reversal(linked).mechanism == ar.WORKTREE

    def test_the_main_checkout_is_not_reported_as_a_linked_worktree(self, repo: Path) -> None:
        """A main checkout must not satisfy the strongest mechanism it does not have.

        This does **not** guard the `resolve()` in that comparison — an earlier version of
        this docstring said it did, and removing the `resolve()` leaves the test green. It
        guards the verdict, which is what matters; the flags are what make the comparison
        safe, and those are asserted below.
        """
        linked, failed = ar._in_linked_worktree(repo)
        assert not failed, "the probe failed rather than answering"
        assert linked is False, "the main checkout was reported as a linked worktree"


    def test_both_git_dir_probes_ask_for_an_absolute_answer(self) -> None:
        """What actually makes the comparison safe.

        The bare `--git-dir` answers relative in the main checkout and absolute in a
        linked one, so comparing those reports a main checkout as linked from some
        directories and not others. Both probes ask absolutely; that is the guard.
        """
        source = inspect.getsource(ar._in_linked_worktree)
        assert "--absolute-git-dir" in source, source
        assert "--path-format=absolute" in source, source


class TestWhenNothingIsArmedItRefuses:
    """The acceptance criterion: refused with a distinct reason, not attempted."""

    def test_a_project_that_is_not_a_git_repository_is_refused(self, tmp_path: Path) -> None:
        """The case that prompted this row — the audit session was not a git repo at all."""
        found = ar.armed_reversal(tmp_path)
        assert found.armed is False, found
        assert found.mechanism is None, found
        assert "not inside a git work tree" in found.why, found.why

    def test_that_refusal_says_the_snapshot_mechanism_is_missing(self, tmp_path: Path) -> None:
        """Otherwise it reads as "arm something" when nothing can be armed there today.

        The mechanism that would cover a non-git project is not built, and saying so is the
        difference between a reader trying things and a reader knowing the gap is ours.
        """
        assert "not built" in ar.armed_reversal(tmp_path).why

    def test_a_detached_head_with_no_worktree_is_refused(self, repo: Path) -> None:
        """A git directory is present and still nothing puts a file back by itself."""
        _git(repo, "checkout", "--quiet", "--detach", "HEAD")
        found = ar.armed_reversal(repo)
        assert found.armed is False, found
        assert "no named branch" in found.why, found.why

    def test_every_refusal_names_all_three_mechanisms(self, tmp_path: Path, repo: Path) -> None:
        """"No reversal is armed" tells an operator nothing they can act on.

        Asserted across every refusing path rather than one, since a new refusal is where
        the next bare message appears.
        """
        _git(repo, "checkout", "--quiet", "--detach", "HEAD")
        for found in (ar.armed_reversal(tmp_path), ar.armed_reversal(repo)):
            assert found.armed is False, found
            for mechanism in ar.MECHANISMS:
                assert mechanism in found.why, (mechanism, found.why)


class TestUnknownIsRefusalNeverPermission:
    """The one direction this must never fail is open."""

    def test_a_failing_git_refuses_rather_than_proceeding(
            self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A failed probe fires exactly when the environment is unusual.

        Reading it as "git is not saying no, carry on" would arm nothing and allow
        everything, in the circumstances least likely to be recoverable.
        """
        monkeypatch.setattr(ar, "_git", lambda root, args: (None, True))
        found = ar.armed_reversal(repo)
        assert found.armed is False, found
        assert "could not be consulted" in found.why, found.why

    def test_a_probe_that_answers_nothing_refuses(
            self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No answer and no failure is still no evidence a mechanism is armed."""
        monkeypatch.setattr(ar, "_git", lambda root, args: (None, False))
        assert ar.armed_reversal(repo).armed is False

    def test_the_shared_git_helper_going_missing_refuses_and_warns(
            self, repo: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """A missing helper is not evidence that a reversal is armed."""
        import builtins  # noqa: PLC0415

        real_import = builtins.__import__

        def _no_change_summary(name, *args, **kwargs):
            if name.endswith("change_summary") or name == "change_summary":
                raise ImportError("gone")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_change_summary)
        import logging  # noqa: PLC0415

        with caplog.at_level(logging.WARNING, logger=ar.logger.name):
            found = ar.armed_reversal(repo)
        assert found.armed is False, found
        assert any("unavailable" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]


class TestItCannotDriftBackIntoJudging:
    """The behaviour this replaces, guarded structurally rather than by intent."""

    def test_the_check_is_told_nothing_about_the_action(self) -> None:
        """A parameter describing the action is all it would take.

        The shipped eligibility modules classify an action's "visible action path" and
        decide whether it looks reversible. This answers a question about the environment,
        and it can only keep doing that while the action is not in scope.
        """
        params = list(inspect.signature(ar.armed_reversal).parameters)
        assert params == ["project_root"], (
            f"the check now takes {params} — anything describing the action lets it judge "
            "whether the action looks undoable, which is what it replaces"
        )

    def test_nothing_in_the_module_inspects_an_action(self) -> None:
        """Swept, because the next parameter is not the only way it could creep back."""
        source = Path(ar.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)}
        forbidden = {"action", "option", "choice", "command", "operation", "menu"}
        assert not (names & forbidden), (
            f"a parameter naming the action appeared: {sorted(names & forbidden)}"
        )

    def test_it_reports_rather_than_gating(self) -> None:
        """Same shape as the plan lookup: it answers, the caller decides.

        Nothing here runs, blocks or permits an edit — it has no side effect beyond
        reading git, so a caller cannot mistake calling it for enforcing it.
        """
        source = Path(ar.__file__).read_text(encoding="utf-8")
        for forbidden in ("os.remove", "shutil.", "open(", ".write(", "subprocess.run"):
            assert forbidden not in source, (
                f"{forbidden!r} appears — this module reports and must not act"
            )


class TestARefusalDoesNotCarryTheUsername:
    """CWE-532: a project root is very often under `$HOME`."""

    def test_the_project_path_is_redacted_in_the_refusal(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """It read `/home/<username>/project is not inside a git work tree`.

        Found by walking the checklist over this module, not by review — the same leak
        class the ledger's redactor exists for, in a message written the day after fixing
        four of them there.
        """
        home = tmp_path / "home" / "someone"
        project = home / "work" / "thing"
        project.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        found = ar.armed_reversal(project)
        assert found.armed is False, found
        assert "someone" not in found.why, found.why
        assert "~" in found.why, found.why

    def test_a_long_path_is_bounded_on_its_way_into_a_reason(self) -> None:
        """The other half of the same helper: bounded as well as redacted.

        Asserted on the helper, because a path long enough to matter is long enough that
        git fails first — the refusal is then "git could not be consulted" and the path
        never reaches the message at all. Testing through `armed_reversal` would pass
        without the bound doing anything.
        """
        assert len(ar._said("x" * 100_000)) < 2_000

    def test_every_reason_stays_bounded_whatever_the_path(self, tmp_path: Path) -> None:
        """And the property that matters to a reader, across the refusing paths."""
        for candidate in (tmp_path, Path(str(tmp_path / ("x" * 100_000)))):
            assert len(ar.armed_reversal(candidate).why) < 2_000


class TestTheChecksThatGuardTheseTests:
    """Each of these exists because the checklist found the test above could not see it."""

    def test_the_mechanisms_are_the_three_this_is_built_around(self) -> None:
        """Pinned to literals, because the refusal tests iterate this tuple.

        Shrinking it to one entry left all eighteen green while checking one mechanism —
        a constant a test draws its cases from has to be pinned somewhere, or it is
        testing itself.
        """
        assert ar.MECHANISMS == ("worktree", "branch", "snapshot"), ar.MECHANISMS
        assert ar.WORKTREE == "worktree", ar.WORKTREE
        assert ar.BRANCH == "branch", ar.BRANCH
        assert ar.SNAPSHOT == "snapshot", ar.SNAPSHOT

    def test_a_path_cannot_forge_a_second_line_in_the_refusal(self, tmp_path: Path) -> None:
        """A directory named with a newline wrote its own verdict into the refusal.

        It rendered as a second line reading `ARMED: yes — reversal confirmed`: a
        fabricated outcome, saying the opposite of the real one, inside the check whose
        whole job is to refuse. Whitespace is collapsed and the value delimited now.
        """
        hostile = tmp_path / "proj\nARMED: yes — reversal confirmed"
        try:
            hostile.mkdir()
        except OSError:
            # A newline is a legal path character on POSIX and not on Windows. Skipping is
            # honest; the forgery this guards is reachable wherever the name is legal.
            pytest.skip("this filesystem does not allow a newline in a name")
        found = ar.armed_reversal(hostile)
        assert found.armed is False, found
        assert len(found.why.splitlines()) == 1, found.why
        assert "\n" not in found.why, found.why

    @pytest.mark.parametrize("hostile", [
        "a\rb",            # carriage return — overwrites the line on a terminal
        "a\tb",            # tab
        "a\x1b[31mb",      # an escape sequence — recolours the rest of the output
        "a\vb",            # vertical tab
    ])
    def test_no_control_character_survives_into_a_reason(self, hostile: str) -> None:
        """Swept beyond the newline that was found, since it is a class not an instance.

        A carriage return overwrites the line on a terminal and an escape sequence
        recolours it — both forge as effectively as the newline did.
        """
        rendered = ar._said(hostile)
        offenders = [ch for ch in rendered if not ch.isprintable()]
        assert not offenders, (repr(rendered), [hex(ord(c)) for c in offenders])

    def test_the_value_is_delimited_so_a_reader_sees_where_it_ends(self) -> None:
        """Bounding and stripping still leave a path running into the sentence after it."""
        assert ar._said("some/path").startswith('"'), ar._said("some/path")
        assert ar._said("some/path").endswith('"'), ar._said("some/path")

    def test_the_check_returns_rather_than_hanging(self, tmp_path: Path) -> None:
        """It shells out, so "cannot hang" is a claim that needs a bounded test.

        Run on a thread with a bounded join: a test for "this does not hang" that hangs
        stops the suite instead of failing it, which reads as CI being broken.
        """
        import threading  # noqa: PLC0415

        out: list = []

        def _run() -> None:
            # The exception is captured rather than allowed to die on the thread. Appending
            # only on success left `out` empty when the call raised, so the assertion below
            # failed with an `IndexError` and hid what actually went wrong.
            try:
                out.append(ar.armed_reversal(tmp_path))
            except BaseException as exc:  # noqa: BLE001  # pylint: disable=broad-except
                out.append(exc)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=30)
        assert not worker.is_alive(), "the reversal check did not return"
        assert not isinstance(out[0], BaseException), f"it raised: {out[0]!r}"
        assert out[0].armed is False, out[0]


class TestWhatReviewFoundOnTheFirstPush:
    """Four findings, each a way this reported a way back that was not there."""

    def test_a_repository_with_no_commits_does_not_arm(self, tmp_path: Path) -> None:
        """`git init` reports a named branch with nothing behind it.

        `symbolic-ref` succeeds on an unborn branch, so the check said `branch` — while the
        repository held zero commits and there was nothing to reset to. Reporting a way
        back that does not exist is the worst thing this module can do; every other failure
        mode refuses something that would have been fine.
        """
        root = tmp_path / "fresh"
        root.mkdir()
        _git(root, "init", "--quiet")
        found = ar.armed_reversal(root)
        assert found.armed is False, found
        assert found.mechanism is None, found

    def test_a_path_containing_a_quote_cannot_escape_the_delimiter(self) -> None:
        """The forgery fix, defeated by the fix's own delimiter.

        A `"` is printable, survives the whitespace strip, and closes a hand-rolled pair of
        quotes early — so the text after it lands outside the delimiter and reads as part
        of the sentence, which is exactly what delimiting was added to prevent.
        """
        rendered = ar._said('proj" ARMED: yes')
        # Asserted by round-trip rather than by counting quotes — an earlier version of
        # this counted them and got the number wrong, which would have passed for the
        # wrong reason had the escaping been broken in a different way.
        assert json.loads(rendered) == 'proj" ARMED: yes', rendered
        assert rendered.startswith('"'), rendered
        assert rendered.endswith('"'), rendered

    def test_a_refusal_does_not_offer_a_mechanism_that_is_not_built(
            self, tmp_path: Path, repo: Path) -> None:
        """Listing `snapshot` beside two armable things reads as three options.

        Only the non-git refusal said it was unbuilt; the detached-HEAD and tool-failure
        refusals sent a reader looking for a switch that does not exist.
        """
        _git(repo, "checkout", "--quiet", "--detach", "HEAD")
        for found in (ar.armed_reversal(tmp_path), ar.armed_reversal(repo)):
            assert "snapshot (not built)" in found.why, found.why

    def test_the_redactor_fallback_still_collapses_home(
            self, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """The one failure path of a username guard was the one that leaked the username.

        With the shared redactor unavailable the fallback returned the raw path truncated.
        It collapses `$HOME` itself now, and says out loud that it is running.
        """
        import builtins  # noqa: PLC0415
        import logging  # noqa: PLC0415

        real_import = builtins.__import__

        def _no_decision_log(name, *args, **kwargs):
            if name.endswith("decision_log") or name == "decision_log":
                raise ImportError("gone")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_decision_log)
        monkeypatch.setenv("HOME", "/home/someone")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/someone")))
        with caplog.at_level(logging.WARNING, logger=ar.logger.name):
            rendered = ar._said("/home/someone/project")
        assert "someone" not in rendered, rendered
        assert any("shared redactor is unavailable" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_the_borrowed_private_helper_is_asserted_to_exist(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A rename there would refuse every edit here, silently and forever.

        `_git_query` is private to its module and promises nothing. Without this, a rename
        leaves every probe reporting "the tool failed", which this turns into a refusal —
        a permanent behaviour change with no error anywhere. The same guard the gate-surface
        walk uses against a renamed keyword; it was applied there and not here.
        """
        from studio.utils import change_summary  # noqa: PLC0415

        monkeypatch.delattr(change_summary, "_git_query")
        with pytest.raises(RuntimeError, match="_git_query is gone"):
            ar._check_borrowed_helper_exists()

    def test_the_home_directory_failing_is_said_not_swallowed(
            self, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """The last line of the guard, and it used to give up without a word.

        The fallback collapses `$HOME` itself, so `Path.home()` failing is the one path
        where the username guard stops guarding. It set `home = ""` and carried on. Every
        other `except` in this module either refuses or warns; this one did neither, which
        is precisely the shape the project's own silent-exception rule exists to catch.
        """
        import builtins  # noqa: PLC0415
        import logging  # noqa: PLC0415

        real_import = builtins.__import__

        def _no_decision_log(name, *args, **kwargs):
            if name.endswith("decision_log") or name == "decision_log":
                raise ImportError("gone")
            return real_import(name, *args, **kwargs)

        def _no_home(cls):
            raise RuntimeError("no home directory")

        monkeypatch.setattr(builtins, "__import__", _no_decision_log)
        monkeypatch.setattr(Path, "home", classmethod(_no_home))
        with caplog.at_level(logging.WARNING, logger=ar.logger.name):
            rendered = ar._said("/somewhere/project")
        assert "project" in rendered, rendered
        assert any("home directory could not be read" in r.getMessage()
                   for r in caplog.records), [r.getMessage() for r in caplog.records]

    def test_the_probe_refuses_when_the_import_fails_any_way_at_all(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Importing a module runs it, so the failures are not only `ImportError`.

        Naming `ImportError` and `AttributeError` covered the ones imagined. A module that
        does not parse after an edit raises `SyntaxError`, and that went straight through
        a probe whose stated contract is that unknown is refusal — the one direction this
        must never fail is open.
        """
        import builtins  # noqa: PLC0415

        real_import = builtins.__import__

        def _broken(name, *args, **kwargs):
            if name.endswith("change_summary") or name == "change_summary":
                raise SyntaxError("invalid syntax")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _broken)
        answer, failed = ar._git(Path("."), ["rev-parse", "--is-inside-work-tree"])
        assert (answer, failed) == (None, True), (answer, failed)


class TestTheFixtureGitCannotBeRedirected:
    """The fixtures run real git, so an exported redirect variable is a real hazard.

    Moved out of the removal-trigger class, whose subject is the dead-code whitelist:
    someone looking for environment sanitisation would not have found it there. Raised in
    review.
    """

    def test_the_fixture_git_uses_the_shared_sanitised_environment(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """One list, not two. A second copy is the one that stops being updated.

        The first fix for this wrote its own eight-variable list, which covered the
        redirect channels and omitted every *configuration* one the shipped helper
        carries — the `GIT_CONFIG_*` family and `GIT_DISCOVERY_ACROSS_FILESYSTEM`, each
        added to the production list by measurement after a real failure. Raised in
        review twice: once for inheriting the ambient environment, and again for
        duplicating an incomplete list instead of reusing what exists.
        """
        source = inspect.getsource(_git)
        assert "change_summary._git_env()" in source, source
        # And the helper still removes the config channels a local list forgot.
        for channel in ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_CONFIG_GLOBAL",
                        "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
                        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
                        # Named because adopting the shared tuple dropped it: the local
                        # list had it and the shared one did not. It is in the shared tuple
                        # now so one list holds the union -- though measurement says it
                        # changes none of the local queries here, and the claim that it did
                        # was mine and wrong. Raised in review.
                        "GIT_NAMESPACE"):
            assert channel in change_summary._GIT_REDIRECT_VARS, channel
        # Seeded first. Without this the behavioural half was vacuous: no redirect
        # variable is set in a normal shell or under pytest, so the intersection was
        # empty whether or not `_git_env` removed anything — removing the sanitisation
        # entirely left this green. Raised in review, and confirmed by mutation before
        # the fix. Every name is set, so a helper that drops some and keeps others fails
        # here rather than passing on the subset that happened to be tried.
        for name in change_summary._GIT_REDIRECT_VARS:
            monkeypatch.setenv(name, "/somewhere/else")
        sanitised = change_summary._git_env()
        left = sorted(set(sanitised) & set(change_summary._GIT_REDIRECT_VARS))
        assert not left, f"the shared helper let these through: {left}"
        # And it is a sanitised copy rather than an empty one: the rest of the
        # environment still reaches git, or the fixtures would run without a PATH.
        assert "PATH" in sanitised or not os.environ.get("PATH"), sorted(sanitised)[:5]

    def test_an_exported_git_dir_does_not_move_the_fixture_repository(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Behaviour, not list membership — which is what the list comparison missed.

        Everything else here asserts that the helper's tuple contains certain names and
        that its output does not. None of that proves the fixture's **real** git actually
        stays in `tmp_path`. `GIT_DIR` is the bluntest of the redirects: exported, it makes
        every command operate on the repository it names, wherever `cwd` points.
        """
        decoy = tmp_path / "decoy.git"
        decoy.mkdir()
        monkeypatch.setenv("GIT_DIR", str(decoy))

        root = tmp_path / "project"
        root.mkdir()
        _git(root, "init", "--quiet")
        _git(root, "checkout", "--quiet", "-B", "main")

        assert (root / ".git").is_dir(), "the fixture repository did not land in tmp_path"
        assert not (decoy / "refs").exists(), (
            f"git wrote into the exported GIT_DIR: {sorted(p.name for p in decoy.iterdir())}"
        )


class TestTheRemovalTriggerIsCheckedRatherThanWritten:
    """A comment saying "delete these when a consumer appears" is not a constraint."""

    def test_the_whitelist_entries_go_when_a_consumer_arrives(self) -> None:
        """The correlation the whitelist comment asserts, asserted by something that runs.

        Nothing imports `armed_reversal` yet, so the dead-code whitelist correctly
        suppresses its fields today and the note telling a future author to delete them is
        operator intent with no mechanism behind it. Raised in review. This is the
        mechanism: when the first consumer appears, the entries must go with it, and until
        then they must stay — a whitelist kept past its reason hides the next real finding.
        """
        root = Path(__file__).resolve().parents[1]
        module = root / "skills/studio/scripts/studio/utils/armed_reversal.py"
        consumers = sorted(
            path.relative_to(root)
            for path in root.rglob("*.py")
            if path != module
            and path.name not in {"vulture_whitelist.py", Path(__file__).name}
            and ".bootstrap" not in path.parts and "build" not in path.parts
            and "armed_reversal" in path.read_text(encoding="utf-8", errors="replace"))
        whitelisted = "armed_reversal" in (root / "vulture_whitelist.py").read_text(
            encoding="utf-8")
        assert whitelisted is not bool(consumers), (
            f"consumers={consumers}, whitelisted={whitelisted}: the whitelist entries and "
            "the first consumer of armed_reversal must never exist at the same time")
