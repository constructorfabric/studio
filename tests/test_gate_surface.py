"""Tests for the static walk of the declared gate surface.

The walk exists because the obvious alternative was refuted: a transcript cannot tell a
gate the workflow declared from one the model invented, and the same request varied by
1-8 stops between runs. So determinism is not a nicety here — it is the property that made
this approach worth having, and it is asserted directly.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio.utils import gate_surface as gs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tree(root: Path, files: dict, *, fenced: bool = True) -> Path:
    """Write a miniature kit: ``workflows/`` plus ``skills/``.

    Each file's PDSL goes inside a ```pdsl fence, because that is what a kit file is: the
    walk reads declarations from fenced blocks and treats everything around them as prose.
    Fixtures that wrote bare PDSL were not shaped like the corpus they stand in for.

    ``fenced=False`` writes the text raw, for the tests that check what happens to
    declarations written outside a fence.
    """
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"```pdsl\n{text}```\n" if fenced else text, encoding="utf-8")
    return root


class TestWhatTheWalkCounts:
    """Reachability through LOAD, and the two numbers kept apart."""

    def test_a_menu_two_load_hops_away_is_reached(self, tmp_path: Path) -> None:
        """The whole point of a closure rather than a per-file count."""
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": "LOAD {cf-studio-path}/.core/skills/b.md\n",
            "skills/b.md": "MENU Deep\n  EMIT_MENU Deep\n",
        })
        surface = gs.walk(root)
        assert surface.menu_reachability == {"Deep": 1}, surface.menu_reachability
        assert surface.workflows[0].files_reached == 3, surface.workflows[0]

    def test_a_menu_no_workflow_can_reach_is_not_counted(self, tmp_path: Path) -> None:
        """Declared surface and reachable surface are different questions.

        A menu nothing loads cannot interrupt anyone, and counting it would inflate the
        number the autonomy work is judged against.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": "EMIT_MENU Reached\n",
            "skills/orphan.md": "MENU Unreached\n  EMIT_MENU Unreached\n",
        })
        surface = gs.walk(root)
        assert "Unreached" not in surface.menu_reachability, surface.menu_reachability
        assert surface.distinct_menu_definitions == 1, "the definition count still sees it"

    def test_the_wait_is_read_at_the_emit_site_not_in_the_menu(self, tmp_path: Path) -> None:
        """The declared stop is the emit *whose sequence* ends the turn.

        This is where the first version looked on the wrong side of the join. The corpus
        writes the wait at the emit site — `EMIT_MENU PlanGateMenu` / `WAIT user.reply` /
        `STOP_TURN` — and reading the menu definition instead scored the plan approval
        gate, the git-commit-mode gate and the simple-mode gate as menus that interrupt
        nobody.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": (
                "EMIT_MENU Waits\n  WAIT user.reply\n  STOP_TURN\n"
                "MENU Waits\n  OPTIONS:\n  1 go -> CONTINUE Next\n"),
        })
        surface = gs.walk(root)
        assert surface.workflows[0].stop_sites == 1, surface.workflows[0]
        assert surface.workflows[0].non_stop_sites == 0, surface.workflows[0]

    def test_an_option_the_user_might_pick_is_not_the_menu_waiting(
            self, tmp_path: Path) -> None:
        """The false positive the old join produced, pinned so it cannot come back.

        `3 stop -> STOP_TURN` is what happens *after* the user replies, and an
        `INVALID ->` branch is the re-prompt for a bad one. Neither is a declaration that
        this emit stops the turn. Reading the body for a wait token counted both, which
        is how a menu that runs straight on was reported as an interruption.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": (
                "EMIT_MENU Proceeds\n  CONTINUE Next\n"
                "MENU Proceeds\n  OPTIONS:\n  1 go -> CONTINUE Next\n"
                "  3 stop -> STOP_TURN\n"
                "  INVALID -> EMIT_MENU Proceeds\n  WAIT user.reply\n"),
        })
        surface = gs.walk(root)
        assert surface.workflows[0].stop_sites == 0, surface.workflows[0]
        assert surface.workflows[0].non_stop_sites == 1, surface.workflows[0]

    def test_a_stop_is_counted_once_per_emit_site(self, tmp_path: Path) -> None:
        """"Counted once per emit site" — two emits that each wait are two stops.

        The user meets the interruption twice; counting the menu once would say the
        workflow stops them half as often as it does.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": (
                "EMIT_MENU Ask\n  WAIT user.reply\n  STOP_TURN\n"
                "  EMIT_MENU Ask WHEN again\n  WAIT user.reply\n  STOP_TURN\n"),
        })
        assert gs.walk(root).workflows[0].stop_sites == 2

    def test_one_wait_covers_the_emits_before_it_in_its_sequence(
            self, tmp_path: Path) -> None:
        """The corpus puts other actions between the emit and the wait.

        `SET` lines in `kit-edit-render.md`, and in `root-intent-routing.md` two guarded
        emits that one `WAIT user.reply` serves. A fixed lookahead of one line scores 374
        on the pinned kit where scanning to the end of the block scores 377 — so the rule
        is the block, not a window, and both emits here are stops.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": (
                "EMIT_MENU First WHEN no intent\n  EMIT_MENU Second WHEN intent\n"
                "  SET PENDING = unset\n  WAIT user.reply\n  STOP_TURN\n"),
        })
        assert gs.walk(root).workflows[0].stop_sites == 2

    def test_a_wait_in_the_next_block_does_not_reach_back(self, tmp_path: Path) -> None:
        """The other half of that rule, or the scan would call every emit a stop.

        Without a boundary, an emit at the end of one unit would borrow the wait of the
        next one down the file.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": (
                "UNIT One\nDO:\n  EMIT_MENU Runs on\n"
                "RULES:\n  ALWAYS something\n"
                "UNIT Two\nDO:\n  WAIT user.reply\n"),
        })
        w = gs.walk(root).workflows[0]
        assert (w.stop_sites, w.non_stop_sites) == (0, 1), w

    def test_an_emit_written_as_a_list_item_is_still_an_emit(self, tmp_path: Path) -> None:
        """The corpus writes actions bare and as markdown bullets, and both are actions.

        Reading only the bare form found 80 of the pinned kit's 88 emit sites. Seven of
        the eight it dropped sit in files no workflow reaches, so the headline never
        moved — the eighth is reachable from 39 workflows, and a miss that only shows up
        in one of eight places is the kind that survives a review.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": "- EMIT_MENU Bulleted\n- WAIT user.reply\n- STOP_TURN\n",
        })
        w = gs.walk(root).workflows[0]
        assert (w.stop_sites, w.distinct_menus) == (1, 1), w

    def test_a_keyword_quoted_in_prose_is_not_a_halt(self, tmp_path: Path) -> None:
        """The PDSL reference lists the keywords in a sentence; that halts nothing.

        166 such sentences in the pinned kit, against 1332 real halts. The first version
        of this test asserted on `menu_reachability` instead and could not fail: a line
        that quotes the keyword starts with a backtick, so it never reads as an emit
        whether the guard is there or not. The halt count is the one number it moves, so
        the halt count is what this asserts.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": (
                "UNIT Doc\nDO:\n  RUN something\n"
                "NOTES:\n  `STOP_TURN` ends the turn without asking\n"),
        })
        assert gs.walk(root).workflows[0].halt_sites == 0, gs.walk(root).workflows[0]

    def test_a_hyphenated_menu_name_is_read_whole(self) -> None:
        """The validator permits `[A-Za-z][A-Za-z0-9_-]*`, and this stopped at the hyphen.

        `Plan-Approval-Gate` was read as `Plan` — a name that merges with any real menu
        called `Plan` and takes its reachability with it. The pinned kit has no hyphenated
        names today, so nothing in the corpus would have caught this: a scanner that
        mis-reads a legal name is a wrong number waiting for the first author to write one.
        """
        sites = gs.emit_sites("EMIT_MENU Plan-Approval-Gate\n  WAIT user.reply\n")
        assert [s.menu for s in sites] == ["Plan-Approval-Gate"], sites
        blocks = dict(gs.menu_blocks("MENU Plan-Approval-Gate\n  OPTIONS:\n"))
        assert set(blocks) == {"Plan-Approval-Gate"}, sorted(blocks)

    def test_a_conditional_emit_is_marked_and_an_unconditional_one_is_not(
            self, tmp_path: Path) -> None:
        """`WHEN` on the emit line is the difference between "may ask" and "asks"."""
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": "EMIT_MENU Always\n  EMIT_MENU Sometimes WHEN x\n",
        })
        surface = gs.walk(root)
        assert surface.unconditional.get("Always") == 1, surface.unconditional
        assert "Sometimes" not in surface.unconditional, surface.unconditional


class TestItTerminatesAndRepeats:
    """The two properties that made this approach worth choosing."""

    def test_a_load_cycle_terminates(self, tmp_path: Path) -> None:
        """Two modules loading each other must not recurse forever.

        Run on a thread with a bounded join. The first version of this called the walk
        directly, and removing the cycle guard made it **loop instead of fail** — it stalled
        the whole suite, which reads as CI being broken rather than as a defect. A test for
        "this terminates" that does not terminate is worse than no test.
        """
        import threading  # noqa: PLC0415

        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": "LOAD {cf-studio-path}/.core/skills/b.md\n  EMIT_MENU A\n",
            "skills/b.md": "LOAD {cf-studio-path}/.core/skills/a.md\n  EMIT_MENU B\n",
        })
        out: list = []

        def _run() -> None:
            # Captured rather than left to die on the thread: a daemon swallows whatever
            # the walk raised, so `out` stayed empty and the assertion below reported an
            # `IndexError` for a `RuntimeError`. Raised in review, and the same shape the
            # reversal check's hang test needed.
            try:
                out.append(gs.walk(root))
            except BaseException as exc:  # noqa: BLE001  # pylint: disable=broad-except
                out.append(exc)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=20)
        # A thread still alive here means the *work* bound regressed, not just the cycle
        # guard: `_closure` raises once it has visited more files than exist, so nothing
        # that terminates can reach this. Said explicitly because a daemon thread outliving
        # its test keeps allocating and drags the rest of the suite down with it.
        assert not worker.is_alive(), (
            "the walk did not terminate on a LOAD cycle, so a runaway thread is still "
            "running: the work bound in _closure is what should have stopped it"
        )
        assert out, "the walk neither returned nor raised"
        assert not isinstance(out[0], BaseException), f"it raised: {out[0]!r}"
        assert out[0].workflows[0].distinct_menus == 2, out[0].workflows[0]

    def test_the_same_tree_walked_twice_gives_the_same_numbers(self, tmp_path: Path) -> None:
        """Determinism is the property the transcript approach could not offer.

        The spike measured a 1-8 stop spread on an identical request; this must not vary
        at all, or it cannot serve as a baseline.
        """
        root = _tree(tmp_path, {
            "workflows/one.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "workflows/two.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": "EMIT_MENU M\n  EMIT_MENU N WHEN y\n",
        })
        first, second = gs.walk(root), gs.walk(root)
        assert first.menu_reachability == second.menu_reachability
        assert [w.stop_sites for w in first.workflows] == [w.stop_sites for w in second.workflows]

    def test_a_workflow_that_loads_nothing_reports_zero(self, tmp_path: Path) -> None:
        """Zero is an answer; failing on it would make an empty workflow unmeasurable."""
        root = _tree(tmp_path, {"workflows/w.md": "PURPOSE: does nothing\n"})
        surface = gs.walk(root)
        assert surface.workflows[0].stop_sites == 0, surface.workflows[0]
        assert surface.concentration == (0, 0), surface.concentration


class TestAnUnreadableFileIsNeverSilent:
    """Under-counting is indistinguishable from progress."""

    def test_an_unreadable_file_is_reported_not_skipped(
            self, tmp_path: Path, caplog) -> None:
        """A file dropped in silence lowers every count made afterwards.

        That matters more here than almost anywhere: the number exists to be compared, and
        a floor presented as a total makes the next comparison look like an improvement.
        """
        root = _tree(tmp_path, {"workflows/w.md": "EMIT_MENU M\n"})
        (root / "skills").mkdir(exist_ok=True)
        (root / "skills" / "bad.md").write_bytes(b"\xff\xfe not utf-8 \xff")
        with caplog.at_level(logging.WARNING, logger=gs.logger.name):
            surface = gs.walk(root)
        assert surface.unreadable, "an undecodable file was skipped without a trace"
        assert any("floor rather than a total" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]


_ALGORITHM_TREE = {
    # Nested on purpose: `workflows/` is walked to any depth, and it used to be flat.
    "workflows/alpha.md": (
        "UNIT Alpha\nDO:\n"
        "  LOAD {cf-studio-path}/.core/skills/gates.md\n"
        "  EMIT_MENU Alpha-Gate\n  WAIT user.reply\n  STOP_TURN\n"),
    "workflows/nested/beta.md": (
        "UNIT Beta\nDO:\n"
        "  LOAD {cf-studio-path}/.core/skills/gates.md\n"
        '  EMIT "refused" and STOP_TURN WHEN unapproved\n'),
    "skills/gates.md": (
        "UNIT Gates\nDO:\n"
        "  EMIT_MENU Waiting\n  WAIT user.reply\n  STOP_TURN\n"
        "  - EMIT_MENU Bulleted WHEN asked\n  - WAIT user.reply\n"
        "  EMIT_MENU Running-On\n  CONTINUE Next\n"
        "MENU Waiting\n  OPTIONS:\n    1 go -> CONTINUE Next\n"
        "MENU Running-On\n  OPTIONS:\n    3 stop -> STOP_TURN\n"
        "    INVALID -> EMIT_MENU Running-On\n"),
    # Loaded by nothing: definitions are counted tree-wide, reachability is not.
    "skills/deep/also.md": "MENU Waiting\n  OPTIONS:\n    1 go -> CONTINUE Next\n",
}


class TestTheAlgorithmIsPinnedWhereCiCanSeeIt:
    """The acceptance fixture that does not need the kit, because CI does not have it.

    `.bootstrap/.core/` is gitignored, so the pinned-kit test below takes its `skip`
    branch on every CI run and the measurement contract went unchecked there — raised in
    review, and correct. That test also could not tell two failures apart: the scanner
    changed, or the corpus grew a 48th workflow.

    This tree is checked in with the test, so it runs everywhere and it moves only when
    someone edits it. Every number below is derived by hand in the docstrings, not copied
    out of a run — a fixture pinned to whatever the code printed asserts nothing.
    """

    TREE = _ALGORITHM_TREE

    def test_the_two_workflows_count_what_they_should(self, tmp_path: Path) -> None:
        """Three stops for alpha, two for beta, and one halt that belongs to neither.

        `alpha.md` emits `Alpha-Gate` and waits (1), and reaches `gates.md`, which waits
        on `Waiting` and on the bulleted `Bulleted` (2) — three. `beta.md` reaches only
        `gates.md`, so two, and its own `EMIT "refused" and STOP_TURN` asks nothing, which
        is the halt. `Running-On` is emitted and the sequence runs into `CONTINUE`, so it
        is the non-stop in both — its body's `3 stop -> STOP_TURN` is an option the user
        may pick and its `INVALID ->` is a re-prompt, and neither makes the emit a stop.
        """
        surface = gs.walk(_tree(tmp_path, self.TREE))
        counted = {w.workflow: (w.stop_sites, w.non_stop_sites, w.halt_sites,
                                w.distinct_menus, w.files_reached)
                   for w in surface.workflows}
        assert counted == {
            "workflows/alpha.md": (3, 1, 0, 4, 2),
            "workflows/nested/beta.md": (2, 1, 1, 3, 2),
        }, counted

    def test_the_tree_wide_numbers_count_what_they_should(self, tmp_path: Path) -> None:
        """Two menu names are defined, one of them twice, and four are reachable.

        `Waiting` and `Running-On` are the definitions; `also.md` defines `Waiting` again
        and is reached by nothing, so it changes the duplicate list and not the
        reachability. `Alpha-Gate` and `Bulleted` are emitted without being defined here,
        which is normal — the kit defines plenty of menus in files this walk does not read.
        """
        surface = gs.walk(_tree(tmp_path, self.TREE))
        assert surface.distinct_menu_definitions == 2, surface.distinct_menu_definitions
        assert surface.duplicate_menu_definitions == ["Waiting"], \
            surface.duplicate_menu_definitions
        assert surface.menu_reachability == {"Waiting": 2, "Bulleted": 2,
                                             "Running-On": 2, "Alpha-Gate": 1}, \
            surface.menu_reachability

    def test_the_two_denominators_are_different_and_stay_different(
            self, tmp_path: Path) -> None:
        """`menu_reachability` counts workflows; `unconditional` counts emit sites.

        Both are `Dict[str, int]` and read alike, which is why review asked for the units
        to be written down. `Bulleted` carries a `WHEN`, so it is absent here while being
        present above — the one case that shows the two dicts are not the same shape of
        answer.
        """
        surface = gs.walk(_tree(tmp_path, self.TREE))
        assert surface.unconditional == {"Waiting": 2, "Running-On": 2, "Alpha-Gate": 1}, \
            surface.unconditional


class TestNothingIsSkippedInSilence:
    """The module's own invariant, applied to the three ways it was being broken."""

    def test_a_root_with_no_workflows_directory_is_refused(self, tmp_path: Path) -> None:
        """A root pointed one level too high returned a clean empty surface.

        No workflows, no unreadable files, no warning — indistinguishable from a tree that
        genuinely declares no gates, and the caller has nothing to tell them apart with.
        That is this module's stated failure mode written into its own entry point.
        """
        (tmp_path / "skills").mkdir()
        with pytest.raises(FileNotFoundError, match="no workflows/ directory"):
            gs.walk(tmp_path)

    def test_a_load_target_that_should_be_in_the_tree_is_reported(
            self, tmp_path: Path, caplog) -> None:
        """A typo and a legitimately out-of-scope reference were the same silent skip.

        Every menu behind the missing module drops out of the count, and an under-count
        reads as progress in a project whose goal is to make the number go down.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": (
                "LOAD {cf-studio-path}/.core/skills/comfirmation.md\n"
                "LOAD {cf-studio-path}/.core/requirements/plan-template.md\n"),
        })
        with caplog.at_level(logging.WARNING, logger=gs.logger.name):
            surface = gs.walk(root)
        # Only the one inside the scanned directories. The kit really does load 17
        # `requirements/` and `architecture/specs/` files this walk has no reason to read,
        # so reporting those would be 17 false alarms on every run.
        assert surface.missing_loads == ["skills/comfirmation.md"], surface.missing_loads
        assert any("not in the tree" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_prose_outside_a_fence_is_not_a_declaration(self, tmp_path: Path) -> None:
        """A sentence beginning with MENU, unindented and unquoted, was read as one.

        Neither the left-margin test nor the backtick test helps here: the line starts at
        the margin and quotes nothing. The fence is the structural answer — PDSL lives
        inside ```pdsl blocks and prose lives around them. Raised in review as a Major.

        Measured before the change: on the pinned kit every declaration is already fenced
        — 88 of 88 emit sites, 107 of 107 menu headers and 526 of 526 LOAD lines — so this
        excludes nothing the walk was counting.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": (
                "MENU Selection is described in the section below, and\n"
                "EMIT_MENU NotReal is what the runtime would call.\n"
                "\n"
                "```pdsl\nUNIT W\nDO:\n  EMIT_MENU Real\n  WAIT user.reply\n```\n"
                "\n"
                "A closing paragraph that mentions EMIT_MENU Afterwards.\n"),
        }, fenced=False)
        surface = gs.walk(root)
        assert list(surface.menu_reachability) == ["Real"], surface.menu_reachability
        assert surface.distinct_menu_definitions == 0, surface.distinct_menu_definitions

    def test_a_fence_in_another_language_is_not_pdsl(self, tmp_path: Path) -> None:
        """A shell or json block can hold anything, including these words."""
        root = _tree(tmp_path, {
            "workflows/w.md": (
                "```bash\nEMIT_MENU NotReal\nWAIT user.reply\n```\n"
                "```pdsl\nUNIT W\nDO:\n  EMIT_MENU Real\n  WAIT user.reply\n```\n"),
        }, fenced=False)
        assert list(gs.walk(root).menu_reachability) == ["Real"], gs.walk(root).menu_reachability

    def test_a_rule_about_halting_is_not_a_halt(self, tmp_path: Path) -> None:
        """`ALWAYS treat WAIT plus STOP_TURN as a boundary` states something; it halts nothing.

        Counted only where actions live — `DO` and `ON_ERROR`. This replaced a backtick
        test that was wrong both ways: it dropped a real halt whose line quotes a command
        name, and kept rule prose that quoted none.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": (
                "UNIT W\n"
                "PURPOSE: mentions STOP_TURN in passing\n"
                "DO:\n"
                "  INVOKE skill `cf-explain` to run the session, then STOP_TURN\n"
                "ON_ERROR:\n"
                "  EMIT \"it failed\" and STOP_TURN\n"
                "RULES:\n"
                "  ALWAYS treat WAIT plus STOP_TURN as a hard boundary\n"
                "INVARIANTS:\n"
                "  NEVER weaken WAIT, STOP_TURN, or REQUIRE\n"),
        })
        # Two: the DO action — whose line quotes a command and was previously dropped —
        # and the ON_ERROR one. The PURPOSE, RULES and INVARIANTS mentions are not halts.
        assert gs.walk(root).workflows[0].halt_sites == 2, gs.walk(root).workflows[0]

    def test_a_workflow_in_a_subdirectory_is_walked(self, tmp_path: Path) -> None:
        """`glob("workflows/*.md")` saw only the top level, and nothing said so.

        No docstring, architecture input description or fixture claimed workflows had to
        be flat — a `workflows/review/plan.md` simply vanished.
        """
        root = _tree(tmp_path, {
            "workflows/review/plan.md": "EMIT_MENU Deep\n  WAIT user.reply\n",
        })
        surface = gs.walk(root)
        assert [w.workflow for w in surface.workflows] == ["workflows/review/plan.md"], \
            surface.workflows

    def test_a_byte_order_mark_does_not_swallow_the_first_declaration(
            self, tmp_path: Path) -> None:
        """An editor's BOM sits before the first character, so the first line matched nothing.

        `EMIT_MENU First` arrived as `\ufeffEMIT_MENU First` and was not an emit; a
        first-line `MENU` header vanished and took its whole body with it. Nothing reports
        it — the file reads cleanly, it simply declares one thing less. Found by walking
        the encoding battery, which is the half of the checklist that was skipped.
        """
        (tmp_path / "workflows").mkdir()
        # The mark sits before the very first character of the file, so it lands on the
        # fence rather than on a declaration — and swallows the fence, which takes the
        # whole block with it.
        (tmp_path / "workflows" / "w.md").write_bytes(
            "\ufeff```pdsl\nEMIT_MENU First\nWAIT user.reply\n"
            "EMIT_MENU Second\nWAIT user.reply\n```\n".encode("utf-8"))
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "d.md").write_bytes(
            "\ufeff```pdsl\nMENU First\n  OPTIONS:\n```\n".encode("utf-8"))
        surface = gs.walk(tmp_path)
        assert sorted(surface.menu_reachability) == ["First", "Second"], \
            surface.menu_reachability
        assert surface.distinct_menu_definitions == 1, surface.distinct_menu_definitions

    def test_tree_keys_are_posix_on_every_platform(self, tmp_path: Path) -> None:
        """Everything downstream speaks forward slashes, so the keys must too.

        `str(path.relative_to(root))` gives `workflows\\w.md` on Windows, where the
        workflow set is selected by a `workflows/` prefix and `LOAD` targets are written
        with `/`. The result is zero workflows walked and every in-tree load reported
        missing — a silent empty surface, on one platform only. Raised in review.

        Asserted on the keys rather than by simulating Windows, which is the part that can
        actually be checked here: a nested path proves the separator is normalised.
        """
        root = _tree(tmp_path, {
            "workflows/review/plan.md": "LOAD {cf-studio-path}/.core/skills/deep/a.md\n",
            "skills/deep/a.md": "EMIT_MENU M\n  WAIT user.reply\n",
        })
        files, _ = gs._read_tree(root)
        assert sorted(files) == ["skills/deep/a.md", "workflows/review/plan.md"], sorted(files)
        assert all("\\" not in key for key in files), sorted(files)
        # and the load resolves through those keys, which is what the separator breaks
        assert gs.walk(root).workflows[0].files_reached == 2

    def test_a_skills_directory_belonging_to_something_else_is_not_swept(
            self, tmp_path: Path) -> None:
        """The mirror image: `rglob("skills/**/*.md")` is `**/skills/**/*.md`.

        pathlib prepends `**/` to an `rglob` pattern, so the scan took in any directory
        named `skills` at any depth — a vendored copy, another kit, a fixture tree — and
        counted its menus as part of this surface.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "EMIT_MENU Mine\n  WAIT user.reply\n",
            "skills/mine.md": "MENU Mine\n  OPTIONS:\n",
            "vendor/skills/theirs.md": "MENU Theirs\n  OPTIONS:\n",
        })
        surface = gs.walk(root)
        assert surface.distinct_menu_definitions == 1, surface.distinct_menu_definitions


class TestItStillMeasuresWhatTheSpikeMeasured:
    """Promoting a script invites rewriting it; these are the published figures."""

    def test_the_pinned_kit_reproduces_the_spikes_numbers(self) -> None:
        """The spike's result is the acceptance fixture, not a memory of it.

        Published: 47 workflows, 106 distinct MENU definitions, and the ten most-reachable
        menus at 71% of the surface, led by `NextActionsMenu` at 46 of 47. If promoting the
        script changed any of those, it is measuring something else.

        **When the corpus legitimately changes, these numbers change with it** — a 48th
        workflow or a renamed menu fails this test without anything being wrong. Tell the
        two apart by running the class above first: it pins the *algorithm* on a checked-in
        tree, so if it still passes, the corpus moved and these four numbers should be
        re-measured and updated in the same commit as the corpus change, here and in the
        task's design note. If it fails too, the scanner changed and the numbers are
        evidence of a defect. That is also why this test cannot be the only one: the kit
        is gitignored, so this skips in CI and the class above is what actually runs there.
        """
        kit = REPO_ROOT / ".bootstrap" / ".core"
        if not kit.is_dir():
            pytest.skip("the pinned kit is not extracted in this checkout")
        surface = gs.walk(kit)
        assert len(surface.workflows) == 47, len(surface.workflows)
        assert surface.distinct_menu_definitions == 106, surface.distinct_menu_definitions
        top, total = surface.concentration
        assert round(100 * top / total) == 71, (top, total)
        assert surface.menu_reachability.get("NextActionsMenu") == 46, \
            surface.menu_reachability.get("NextActionsMenu")

    def test_the_keyword_guard_fires_if_pdsl_renames_an_action(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A rename would otherwise leave this counting zero and calling it clean.

        The silent-zero failure is the one that matters: nobody questions a number that
        went down in a project whose goal is to make it go down.
        """
        from studio.utils import pdsl  # noqa: PLC0415

        monkeypatch.setattr(pdsl, "DO_KEYWORDS", {"LOAD", "EMIT_MENU"})
        with pytest.raises(RuntimeError, match="no longer PDSL actions"):
            gs._check_keywords_still_exist()


class TestTheResultIsSafeToKeep:
    """The baseline artifact is made to be shared, so what lands in it matters."""

    def test_the_tree_path_does_not_carry_the_username(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An absolute path under `$HOME` puts a username into a file made to be compared.

        Found by walking the checklist, and it is the second appearance of this leak in a
        day — the reversal check had it too. Fixing the class rather than the instance is
        exactly what did not happen the first time.
        """
        home = tmp_path / "home" / "someone"
        tree = home / "kit"
        (tree / "workflows").mkdir(parents=True)
        (tree / "workflows" / "w.md").write_text("EMIT_MENU M\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(home))
        surface = gs.walk(tree)
        assert "someone" not in surface.tree, surface.tree
        assert surface.tree.startswith("~"), surface.tree

    def test_every_reported_entry_is_bounded(self, tmp_path: Path) -> None:
        """A tree can hold a 200,000-character name as easily as a short one.

        All three lists the result carries are built from text the tree controls, and the
        correction review has already made twice is to bound the *class* of value rather
        than the one field somebody noticed. So this exercises the two newest fields and
        the oldest one together.
        """
        long_name = "M" + "e" * 400
        root = _tree(tmp_path, {
            "workflows/w.md": f"LOAD {{cf-studio-path}}/.core/skills/{'x' * 400}.md\n",
            "skills/one.md": f"MENU {long_name}\n  OPTIONS:\n",
            "skills/two.md": f"MENU {long_name}\n  OPTIONS:\n",
        })
        (root / "skills" / ("b" * 200 + ".md")).write_bytes(b"\xff\xfe")
        surface = gs.walk(root)
        reported = (surface.missing_loads + surface.duplicate_menu_definitions
                    + surface.unreadable)
        assert reported, "the fixture produced nothing to bound"
        assert all(len(entry) <= gs._MAX_REPORTED + 3 for entry in reported), \
            [len(entry) for entry in reported]

    def test_the_cap_fires_at_the_length_it_says(self) -> None:
        """Where the cap fires, not merely that one exists.

        The test above uses 400-character inputs and asserts a ceiling, which passes for
        any cap at or below the real one — changing `<=` to `<`, or the constant from 200
        to 199, left it green. Raised in review, and both mutations confirmed before this
        was written. So the three lengths that matter are named here against literals.
        """
        assert gs._MAX_REPORTED == 200, gs._MAX_REPORTED
        assert gs._reported("a" * 199) == "a" * 199
        # The last length that survives whole, and the first that does not.
        assert gs._reported("a" * 200) == "a" * 200
        assert gs._reported("a" * 201) == "a" * 200 + "...", gs._reported("a" * 201)

    def test_a_halt_is_excluded_by_where_it_is_not_by_what_it_says(
            self, tmp_path: Path) -> None:
        """Menu bodies were skipped by line *text*, so a real halt elsewhere vanished.

        `STOP_TURN` is a whole line in both places, so any file with a menu containing one
        silently dropped every identical halt in its units — the exact case reproduced
        here returned zero. Raised in review.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": ("UNIT W\nDO:\n  STOP_TURN\n"
                               "MENU M\n  OPTIONS:\n  STOP_TURN\n"),
        })
        assert gs.walk(root).workflows[0].halt_sites == 1, gs.walk(root).workflows[0]

    def test_the_last_fallback_still_does_not_report_an_absolute_path(
            self, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """The fallback's own fallback was the one that leaked.

        With the shared redactor gone this collapses `$HOME` itself — so `Path.home()`
        failing left it with no prefix to remove, and it returned the raw absolute path
        truncated: a username in the one field this function exists to keep it out of.
        Raised in review. It now reports the final component only, and says that it did.
        """
        import builtins  # noqa: PLC0415

        real_import = builtins.__import__

        def _no_redactor(name, *args, **kwargs):
            if name.endswith("decision_log") or name == "decision_log":
                raise ImportError("gone")
            return real_import(name, *args, **kwargs)

        def _no_home(cls):
            raise RuntimeError("no home directory")

        monkeypatch.setattr(builtins, "__import__", _no_redactor)
        monkeypatch.setattr(Path, "home", classmethod(_no_home))
        with caplog.at_level(logging.WARNING, logger=gs.logger.name):
            rendered = gs._said("/home/someone/projects/kit")
        assert "someone" not in rendered, rendered
        assert rendered == ".../kit", rendered
        assert any("only the final path component" in r.getMessage()
                   for r in caplog.records), [r.getMessage() for r in caplog.records]

    def test_a_filename_cannot_forge_a_line_in_the_result(
            self, tmp_path: Path, caplog) -> None:
        """A newline in a filename wrote its own verdict into `unreadable`.

        The entry rendered as two lines, the second reading `STOPS: 0 — no gates found`:
        a fabricated outcome inside the one field whose whole job is to say the count is
        incomplete. Third appearance of this forgery in three modules — a directory name
        forged a refusal, a quote closed a hand-rolled delimiter early — which is why the
        strip and the delimiter sit at the one point every reported entry passes through
        rather than on the field that happened to be noticed.
        """
        (tmp_path / "workflows").mkdir()
        (tmp_path / "workflows" / "w.md").write_text("EMIT_MENU M\n", encoding="utf-8")
        (tmp_path / "skills").mkdir()
        hostile = tmp_path / "skills" / "bad\nSTOPS: 0 — no gates found.md"
        try:
            hostile.write_bytes(b"\xff\xfe")
        except OSError:
            # A newline is a legal path character on POSIX and not on Windows. Skipping is
            # honest; the forgery this guards is reachable wherever the name is legal.
            pytest.skip("this filesystem does not allow a newline in a name")
        with caplog.at_level(logging.WARNING, logger=gs.logger.name):
            surface = gs.walk(tmp_path)
        assert surface.unreadable, "the undecodable file was not reported at all"
        entry = surface.unreadable[0]
        assert len(entry.splitlines()) == 1, entry
        assert "\n" not in entry, entry
        # And the warning that names entries delimits them, so a name carrying `, ` does
        # not read as two. The list field needs no quotes — a list already ends its own
        # entries — which is why the strip and the delimiter live in different places.
        assert all(len(record.getMessage().splitlines()) == 1 for record in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_an_entry_naming_two_files_is_not_read_as_two(self, tmp_path: Path,
                                                          caplog) -> None:
        """A filename may contain `, `, and the warning joins entries with `, `.

        So one unreadable file called `a, b.md` reads as two in a line meant to tell a
        reader exactly how much of the tree went uncounted. `unreadable` is the only one of
        the three lists whose entries can contain a comma at all — a LOAD target matches a
        pattern without one and a menu name is a single token — which is why this is the
        list the warning names, rather than a delimiter defending a case that cannot occur.
        """
        (tmp_path / "workflows").mkdir()
        (tmp_path / "workflows" / "w.md").write_text("EMIT_MENU M\n", encoding="utf-8")
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "a, b.md").write_bytes(b"\xff\xfe")
        with caplog.at_level(logging.WARNING, logger=gs.logger.name):
            gs.walk(tmp_path)
        said = [r.getMessage() for r in caplog.records if "could not be read" in r.getMessage()]
        assert said, [r.getMessage() for r in caplog.records]
        assert '"skills/a, b.md: UnicodeDecodeError"' in said[0], said[0]

    def test_unreadable_entries_are_relative_to_the_tree(self, tmp_path: Path) -> None:
        """The other path the result carries, checked rather than assumed safe."""
        (tmp_path / "workflows").mkdir()
        (tmp_path / "workflows" / "w.md").write_text("EMIT_MENU M\n", encoding="utf-8")
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "bad.md").write_bytes(b"\xff\xfe")
        surface = gs.walk(tmp_path)
        assert surface.unreadable == ["skills/bad.md: UnicodeDecodeError"], surface.unreadable
        assert str(tmp_path) not in surface.unreadable[0], surface.unreadable


class TestTheThirdNumberAndItsBoundaries:
    """Raised in review: a halt that asks nothing was counted in neither column."""

    def test_a_halt_outside_a_menu_is_counted(self, tmp_path: Path) -> None:
        """Refusing to dispatch an unapproved plan ends the turn and asks nothing.

        It is not an emit site, so it appeared in neither `stop_sites` nor
        `non_stop_sites` — the very case that motivated keeping the numbers apart went
        uncounted when the measure was corrected to the declared stop.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": ("UNIT Refuse\nDO:\n"
                            '  EMIT "not approved" and STOP_TURN WHEN unapproved\n'),
        })
        surface = gs.walk(root)
        assert surface.workflows[0].halt_sites == 1, surface.workflows[0]
        assert surface.workflows[0].stop_sites == 0, surface.workflows[0]

    def test_the_stop_turn_that_ends_an_emit_is_not_also_a_halt(
            self, tmp_path: Path) -> None:
        """The `STOP_TURN` after an `EMIT_MENU` is what makes that emit a stop.

        Counting it again as a halt takes one declaration and adds it to both numbers, and
        a change touching menus then moves a column that is supposed to be independent.
        On the pinned kit that double count was 543 of 1875 halts.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": "EMIT_MENU Ask\n  WAIT user.reply\n  STOP_TURN\n",
        })
        surface = gs.walk(root)
        assert surface.workflows[0].stop_sites == 1, surface.workflows[0]
        assert surface.workflows[0].halt_sites == 0, "a menu's own halt was counted twice"

    def test_the_three_numbers_move_independently(self, tmp_path: Path) -> None:
        """The property the separation exists for, asserted rather than described."""
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": (
                "UNIT Three\nDO:\n"
                '  EMIT "no" and STOP_TURN WHEN x\n'
                "  EMIT_MENU Waits\n  WAIT user.reply\n  STOP_TURN\n"
                "  EMIT_MENU Proceeds\n  CONTINUE Next\n"),
        })
        w = gs.walk(root).workflows[0]
        assert (w.stop_sites, w.non_stop_sites, w.halt_sites) == (1, 1, 1), w


def _timed(call) -> float:
    """Seconds one call took. Wall clock, so callers take the minimum of several."""
    import time  # noqa: PLC0415

    start = time.perf_counter()
    call()
    return time.perf_counter() - start


class TestThePatternsStayLinear:
    """Raised by the analyser: `\\s` matches a newline, and `re.M` then spans lines."""

    def test_the_scan_looks_at_each_line_exactly_once(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The linearity property, counted rather than timed.

        The timing tests below went red three times on CI without a defect behind any of
        them — a ratio of wall-clock times on a runner with six parallel workers, where
        the smaller sample sits near the noise floor. A test that is red for reasons other
        than the thing it describes makes every red run ambiguous, so the property is
        asserted here where it can be counted exactly.

        One `_action` call per line is what "one pass" means. The regression review found —
        asking each emit separately how its sequence ended, each answer scanning forward —
        shows up as many times that, deterministically and on any machine.
        """
        calls = []
        real = gs._action
        monkeypatch.setattr(gs, "_action", lambda line: calls.append(1) or real(line))
        text = "UNIT U\nDO:\n" + ("  EMIT_MENU M\n" * 500) + "RULES:\n  ALWAYS x\n"
        sites = gs.emit_sites(text)
        assert len(sites) == 500, len(sites)
        assert len(calls) == len(text.splitlines()), (len(calls), len(text.splitlines()))

    def test_finding_emit_sites_stays_linear(self) -> None:
        """Measured 0.8 / 3.2 / 12.5 / 52.4 ms for 500 / 1000 / 2000 / 4000 lines.

        A clean doubling into quadrupling — textbook super-linear backtracking, from `\\s*`
        crossing newlines under `re.M` on whitespace followed by a near-miss. An indent is
        horizontal whitespace, so `[ \\t]*` is both faster and the more accurate statement.

        Asserted as a ratio rather than an absolute time, since a wall-clock threshold is a
        flake on a loaded machine. A first attempt to reproduce this used the wrong hostile
        input and found nothing, which is why the shape of the input is spelled out here.
        """
        def elapsed(n: int) -> float:
            """The *fastest* of several runs, not the median.

            A contended runner only ever adds time, so the minimum is the sample closest
            to the real cost and the one a parallel CI job cannot inflate. The median
            still moved: CI's Python 3.14 reported 11x with a single sample and 9.5x with
            a median of five, on an input measured linear at 2.0x per doubling across a
            32x range locally.
            """
            hostile = ("   \n" * n) + "EMIT_MENUX"
            gs.emit_sites(hostile)                      # warm up, then measure
            return min(_timed(lambda: gs.emit_sites(hostile)) for _ in range(7))

        # Sizes large enough that the work dominates the noise, and a median rather than a
        # single sample. The first version timed one run at n=1000 — 0.13ms locally — and
        # failed on CI's Python 3.14 at a ratio of 11x on an input this is provably linear
        # in: measured 2.04, 2.05, 2.01, 1.93, 2.14 for each doubling from 1k to 32k. A
        # test whose failures are GC pauses reports the runner, not the code.
        small, large = elapsed(16000), elapsed(64000)
        # Four times the input; quadratic would be ~16x. Generous headroom, and still fails
        # the behaviour that was there.
        assert large < small * 8, (small, large)

    def test_classifying_many_emits_stays_linear(self) -> None:
        """The test above measures the one path this cost nothing on.

        Its hostile input is `EMIT_MENUX`, rejected before an emit is ever classified — so
        a block of *n* valid emits, each separately scanning forward to the next boundary,
        was O(n squared) and invisible here: 57ms, 236ms, 946ms, 3597ms for 500 to 4000
        emits. Raised in review. One pass settles them together, and the same shape now
        measures 0.44ms, 0.91ms, 1.9ms, 4.0ms.
        """

        def elapsed(n: int) -> float:
            # Many valid emits, no wait and no boundary until the very end, so every one
            # of them is still open when the scan reaches the thing that decides it.
            text = "UNIT U\nDO:\n" + ("  EMIT_MENU M\n" * n) + "RULES:\n  ALWAYS x\n"
            assert len(gs.emit_sites(text)) == n, "the fixture stopped exercising the path"
            return min(_timed(lambda: gs.emit_sites(text)) for _ in range(7))

        small, large = elapsed(1000), elapsed(4000)
        # Four times the input; quadratic would be ~16x, and was measured at 15.2x.
        assert large < small * 8, (small, large)

    def test_the_headline_on_the_pinned_kit_is_the_declared_stop(self) -> None:
        """377 of 478 emit-site visits, and the 62 that moved are the correction.

        This read 315 while the wait was looked up in the menu definition. Reading it at
        the emit site — where the corpus writes it — is what moved the number, and the
        difference is not noise: it is the plan approval gate, the git-commit-mode gate
        and the simple-mode gate rejoining the count they had been excluded from.
        """
        root = REPO_ROOT / ".bootstrap" / ".core"
        if not root.is_dir():
            pytest.skip("the pinned kit is not extracted in this checkout")
        surface = gs.walk(root)
        stops = sum(w.stop_sites for w in surface.workflows)
        non_stops = sum(w.non_stop_sites for w in surface.workflows)
        assert (stops, non_stops) == (377, 101), (stops, non_stops)
        assert surface.distinct_menu_definitions == 106, surface.distinct_menu_definitions
        assert surface.menu_reachability.get("NextActionsMenu") == 46


    def test_a_menu_name_ending_in_a_colon_is_still_that_menu(self) -> None:
        """The corpus writes both `MENU Name` and `MENU Name:`.

        Keeping the colon files the block under a name no `EMIT_MENU` will ever reference.
        Four menus went missing that way when the pattern became a line scan, and nothing
        but the published-figures fixture noticed — the count of *waiting* menus stayed at
        60, because four others silently took their place.
        """
        blocks = dict(gs.menu_blocks("MENU Plain\n  a\nMENU Colon:\n  b\n"))
        assert set(blocks) == {"Plain", "Colon"}, sorted(blocks)

    def test_a_longer_token_starting_with_the_keyword_is_not_an_emit(self) -> None:
        """`EMIT_MENUX` is a different word, and the scan must not read it as `EMIT_MENU X`.

        The linearity test above uses exactly this string as its near-miss, but it measures
        only time — nothing asserted the result, so dropping the boundary check left a menu
        named `X` counted from text that emits nothing.
        """
        assert gs.emit_sites("EMIT_MENUX\n") == [], gs.emit_sites("EMIT_MENUX\n")
        assert [s.menu for s in gs.emit_sites("EMIT_MENU Real\n")] == ["Real"]

    @pytest.mark.parametrize("header", ["PURPOSE", "DO", "RULES", "WHEN", "STATE",
                                       "INVARIANTS", "OPTIONS", "INVALID", "NOTES",
                                       "TITLE", "UNIT", "MENU"])
    def test_every_block_header_ends_the_sequence_before_it(self, header: str) -> None:
        """Each name pinned by a literal, because the corpus pins almost none of them.

        Only `RULES`, `INVARIANTS` and `MENU` are ever reached as a boundary on the pinned
        kit — the other 81 emit sites reach a wait first — so dropping any single entry
        changed neither a test nor a number, another entry always catching the same case.
        That is the shape where a shrunk constant looks like coverage and is not, so the
        cases are written out here rather than read from the set under test.

        `UNIT` is the one that matters most and fires zero times on this corpus: every unit
        in this kit ends with `RULES` before the next `UNIT` begins. A kit that did not
        would have each emit borrowing the following unit's wait.
        """
        assert header in gs._SECTIONS, sorted(gs._SECTIONS)
        assert gs._ends_the_sequence(f"{header}:"), header
        assert gs._ends_the_sequence(f"{header} Something"), header

    def test_an_emit_does_not_borrow_the_next_units_wait(self, tmp_path: Path) -> None:
        """The boundary stated as behaviour, not as membership of a set.

        Written with `UNIT` directly after the emit, so no other entry in the set can
        stand in for it — which is how the previous version of this passed with `UNIT`
        removed.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "LOAD {cf-studio-path}/.core/skills/a.md\n",
            "skills/a.md": ("UNIT One\nDO:\n  EMIT_MENU RunsOn\n"
                            "UNIT Two\nDO:\n  WAIT user.reply\n  STOP_TURN\n"),
        })
        w = gs.walk(root).workflows[0]
        assert (w.stop_sites, w.non_stop_sites) == (0, 1), w

    def test_an_indented_menu_line_does_not_close_a_block(self) -> None:
        """A block header is a block header only at the left margin.

        `MENU` written inside a body — quoted in prose, or as part of an option — must not
        end the definition it appears in, or every menu after it in the file is attributed
        to the wrong block. The pattern this replaced anchored with `^`; the scan has to say
        the same thing explicitly.
        """
        # The indented line's *first token* must be `MENU`, or the branch under test is
        # never reached — a first version wrote `1 go -> see MENU Inner`, whose first token
        # is `1`, so removing the left-margin check changed nothing and the test passed.
        blocks = dict(gs.menu_blocks(
            "MENU Outer\n  OPTIONS:\n  MENU Inner is described here\n  WAIT user.reply\n"))
        assert set(blocks) == {"Outer"}, sorted(blocks)
        assert "WAIT user.reply" in blocks["Outer"], blocks["Outer"]
