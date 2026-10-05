"""Tests for the static walk of the declared gate surface.

The walk exists because the obvious alternative was refuted: a transcript cannot tell a
gate the workflow declared from one the model invented, and the same request varied by
1-8 stops between runs. So determinism is not a nicety here — it is the property that made
this approach worth having, and it is asserted directly.
"""
from __future__ import annotations

import logging
import os
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

    @pytest.mark.parametrize("token", [
        "PlainMenu", "Plan-Approval-Gate", "Name:", "Name.", "M", "Menu_1",
        "Caf\u00e9Menu",      # precomposed: the validator rejects it outright
        "Cafe\u0301Menu",     # decomposed: the validator truncates it to `Cafe`
        "9Menu", "-Menu", "",
    ])
    def test_a_name_is_read_exactly_as_the_validator_reads_it(self, token: str) -> None:
        """Agreement with the validator asserted directly, not case by case.

        This walk exists to count menus the product can actually emit, so a name it reads
        differently from the validator is a number about nothing. It did disagree: Python's
        `isalpha`/`isalnum` are Unicode-aware, so `Caf\u00e9Menu` came back whole while the
        validator — whose grammar is ASCII and whose name ends at a word boundary — rejects
        that declaration entirely. Raised in review.

        The comparison is against the validator's own regex rather than a copy of its
        rules, so if that grammar changes this fails rather than drifting.
        """
        from studio.utils.pdsl import UNIT_OR_MENU_RE  # noqa: PLC0415

        matched = UNIT_OR_MENU_RE.match(f"MENU {token}")
        expected = matched.group("name") if matched else None
        assert gs._menu_name(token) == expected, token

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

    def test_one_name_emitted_both_ways_counts_only_its_unconditional_sites(
            self, tmp_path: Path) -> None:
        """`WHEN` is decided per emit site, not per name — the case every fixture avoided.

        Elsewhere a menu is either always conditional or always not, and its name settles
        the question. So a walk that keyed `unconditional` off the *name* — present as soon
        as one site lacks `WHEN`, or copied wholesale from `menu_reachability` — passed every
        one of them. Here `Ask` is emitted three times in one workflow, twice bare and once
        behind a `WHEN`, and the three published numbers are deliberately different: one
        workflow reaches it (reachability **1**), two of its sites are unconditional
        (**2**), and it has three sites in all (**3**). Only counting each site on its own
        `WHEN` gives 2, so a per-name shortcut lands on 3 and fails here.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": ("UNIT W\nDO:\n"
                               "  EMIT_MENU Ask\n"
                               "  EMIT_MENU Ask WHEN the caller left it open\n"
                               "  EMIT_MENU Ask\n"),
        })
        surface = gs.walk(root)

        assert surface.menu_reachability == {"Ask": 1}, surface.menu_reachability
        assert surface.unconditional == {"Ask": 2}, surface.unconditional
        # And all three sites were seen, so `unconditional == 2` is the `WHEN` filter doing
        # its job, not a walk that quietly dropped the conditional site down to two sites.
        [w] = surface.workflows
        assert w.stop_sites + w.non_stop_sites == 3, surface.workflows

    def test_when_is_a_whole_word_not_a_substring(self, tmp_path: Path) -> None:
        """`WHENEVER` in trailing prose is not a `WHEN` clause; a standalone `WHEN` is.

        The validator leaves the text after `EMIT_MENU <name>` free-form, so a bare
        `"WHEN" in tail` read a longer word like `WHENEVER` as a condition and flipped the
        emit to conditional -- misreporting `unconditional`. Matched at a word boundary now.
        Raised in review; no such line is in the corpus, so the fixture is synthetic.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": ("UNIT W\nDO:\n"
                               "  EMIT_MENU Always fires WHENEVER ready\n"
                               "  EMIT_MENU Maybe WHEN the caller asked\n"),
        })
        surface = gs.walk(root)
        # `Always` carries only `WHENEVER` in its trailing prose -- not a WHEN clause.
        assert surface.unconditional.get("Always") == 1, surface.unconditional
        # `Maybe` carries a real standalone `WHEN` -- conditional, so absent from unconditional.
        assert "Maybe" not in surface.unconditional, surface.unconditional
        assert set(surface.menu_reachability) == {"Always", "Maybe"}, surface.menu_reachability


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

    def test_every_property_together_on_one_tree(self, tmp_path: Path) -> None:
        """One tree exercising every property at once, with each number derived by hand.

        Asked for in review three times, and I declined twice on the grounds that a fixture
        this size fails for many reasons and localises none. That objection was to it
        *replacing* the narrow fixtures — which nobody proposed. As an addition it buys
        something they cannot: that the properties still hold **while interacting**, which
        is the only place a composition bug can show.

        The tree, and the derivation:

        * `w01`..`w12`, each loading one shared skill. `w{i}` emits `M1`..`M{i}`, so `Mk` is
          reached by workflows `k`..`12` — `13 - k` of them.
        * the shared skill emits `Shared` behind a `WHEN`, reached by all 12.
        * each workflow carries prose *outside* its fence naming a `MENU` and an
          `EMIT_MENU` that must be counted as nothing.
        * `Dup` is declared in two skill files that nothing loads.

        So: **12 workflows**; stops are `i + 1` per workflow — its own emits plus the shared
        one — totalling **90**; reachability is `12, 12, 11 … 1` across **13 menus**, summing
        to **90**, of which the ten largest are **84**; definitions are `Shared` and `Dup`,
        with `Dup` the duplicate; `Shared` is conditional so it is absent from
        `unconditional` while every `Mk` is present.
        """
        tree = {
            "skills/shared.md": ("UNIT Shared\nDO:\n"
                                 "  EMIT_MENU Shared WHEN the caller asked for it\n"
                                 "  WAIT user.reply\n  STOP_TURN\n"
                                 "MENU Shared\n  OPTIONS:\n    1 go -> CONTINUE Next\n"),
            "skills/dup-a.md": "MENU Dup\n  OPTIONS:\n    1 go -> CONTINUE Next\n",
            "skills/dup-b.md": "MENU Dup\n  OPTIONS:\n    1 go -> CONTINUE Next\n",
        }
        for i in range(1, 13):
            emits = "".join(f"  EMIT_MENU M{k}\n  WAIT user.reply\n  STOP_TURN\n"
                            for k in range(1, i + 1))
            tree[f"workflows/w{i:02d}.md"] = (
                f"UNIT W{i}\nDO:\n"
                "  LOAD {cf-studio-path}/.core/skills/shared.md\n" + emits)
        root = _tree(tmp_path, tree)
        # Prose outside the fences, which must count as nothing at all.
        for i in range(1, 13):
            path = root / f"workflows/w{i:02d}.md"
            path.write_text(
                "MENU NotReal is described in this sentence.\n"
                "EMIT_MENU NotReal is how the runtime would show it.\n\n"
                + path.read_text(encoding="utf-8"), encoding="utf-8")

        surface = gs.walk(root)

        assert len(surface.workflows) == 12, surface.workflows
        assert sum(w.stop_sites for w in surface.workflows) == 90, surface.workflows
        assert sum(w.non_stop_sites for w in surface.workflows) == 0, surface.workflows
        assert sum(w.halt_sites for w in surface.workflows) == 0, surface.workflows

        assert surface.distinct_menu_definitions == 2, surface.distinct_menu_definitions
        assert surface.duplicate_menu_definitions == ["Dup"], \
            surface.duplicate_menu_definitions
        assert surface.missing_loads == [], surface.missing_loads
        assert surface.unreadable == [], surface.unreadable


        expected = {"Shared": 12, **{f"M{k}": 13 - k for k in range(1, 13)}}
        assert surface.menu_reachability == expected, surface.menu_reachability
        assert surface.concentration == (84, 90), surface.concentration

        # `Shared` carries a `WHEN`, so it is reachable but never unconditional.
        assert "Shared" not in surface.unconditional, surface.unconditional
        assert surface.unconditional["M1"] == 12, surface.unconditional

    def test_one_file_defining_a_name_twice_is_not_called_a_collision_between_files(
            self, tmp_path: Path, caplog) -> None:
        """It was reported as two files disagreeing, which sends the reader to find a
        second file that does not exist.

        `_definitions` appends the path once per `MENU` block, so a file defining the same
        name twice produces `[rel, rel]` -- length two, and therefore flagged by the same
        `len(where) > 1` test as a genuine cross-file collision. The name belongs in the
        list either way; the warning's wording was what was wrong. Raised in review.

        The corpus has no instance of this today, which is why the fixture is synthetic:
        measuring the real tree cannot tell a fix from its absence when the count is zero.
        """
        import logging  # noqa: PLC0415

        root = _tree(tmp_path, {
            "workflows/w.md": ("UNIT W\nDO:\n"
                               "  LOAD {cf-studio-path}/.core/skills/twice.md\n"
                               "  EMIT_MENU Twice\n  WAIT user.reply\n  STOP_TURN\n"),
            "skills/twice.md": ("MENU Twice\n  OPTIONS:\n    1 go -> CONTINUE Next\n"
                                "MENU Twice\n  OPTIONS:\n    1 go -> CONTINUE Next\n"),
        })

        with caplog.at_level(logging.WARNING, logger=gs.logger.name):
            surface = gs.walk(root)

        assert surface.duplicate_menu_definitions == ["Twice"], \
            surface.duplicate_menu_definitions
        said = " ".join(r.getMessage() for r in caplog.records)
        assert "more than one definition" in said, said
        assert "more than one file" not in said, said

    def test_concentration_reports_the_top_ten_and_not_the_whole_tail(
            self, tmp_path: Path) -> None:
        """Twelve reachable menus, so `counts[:10]` actually cuts something.

        The tree above reaches four menus, so the slice was a no-op under it: summing all
        twelve values and summing the top ten gave the same answer, and deleting the
        truncation failed nothing. The only fixture with more than ten menus is the pinned
        kit, which skips wherever `.bootstrap/.core` is absent — so on CI, where that is
        every run, the figure the whole sizing argument rests on was unchecked. Raised in
        review.

        Workflow `w{i}` emits `M1`..`M{i}`, so `Mk` is reachable from the workflows `k`
        through `12` — that is `13 - k` of them. The counts are therefore `12, 11, ... 1`:
        **78** in total, and **75** in the ten largest. Derived here, not read off a run.
        """
        files = {
            f"workflows/w{i:02d}.md": "UNIT W%d\nDO:\n%s" % (
                i, "".join(f"  EMIT_MENU M{k}\n  WAIT user.reply\n  STOP_TURN\n"
                           for k in range(1, i + 1)))
            for i in range(1, 13)
        }
        surface = gs.walk(_tree(tmp_path, files))

        assert len(surface.menu_reachability) == 12, surface.menu_reachability
        assert sorted(surface.menu_reachability.values(), reverse=True) == \
            [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1], surface.menu_reachability

        top, total = surface.concentration
        assert (top, total) == (75, 78), (top, total)
        # Stated rather than implied: the pair must differ, or a later edit to the fixture
        # could quietly return this test to the no-op it replaces.
        assert top < total, "the fixture has no tail, so the truncation is untested again"

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

    def test_a_menu_emitted_twice_in_one_workflow_is_reachable_once(
            self, tmp_path: Path) -> None:
        """The units above are stated; this is the fixture that can tell them apart.

        `menu_reachability` counts **workflows** and `unconditional` counts **emit sites**,
        and in every other fixture here no workflow emits the same menu twice — so counting
        per workflow and counting per site give the same answer and the distinction is
        untested. Swapping the per-workflow dedup for `menus.elements()` passed the whole
        file, kit included. Raised in review.

        Hand-derived: `w1` emits `Twice` at two sites, `w2` at one. Two workflows reach it,
        so reachability is **2**; there are three sites, so `unconditional` is **3**. The
        numbers differ, and neither is the number of workflows times anything.
        """
        root = _tree(tmp_path, {
            "workflows/w1.md": ("UNIT One\nDO:\n"
                                "  EMIT_MENU Twice\n  WAIT user.reply\n  STOP_TURN\n"
                                "  EMIT_MENU Twice\n  WAIT user.reply\n  STOP_TURN\n"),
            "workflows/w2.md": ("UNIT Two\nDO:\n"
                                "  EMIT_MENU Twice\n  WAIT user.reply\n  STOP_TURN\n"),
        })
        surface = gs.walk(root)

        assert surface.menu_reachability == {"Twice": 2}, surface.menu_reachability
        assert surface.unconditional == {"Twice": 3}, surface.unconditional
        # And the per-workflow stop counts, so the fixture cannot be satisfied by a walk
        # that lost one of the two sites in `w1` rather than by one that deduped correctly.
        assert [w.stop_sites for w in surface.workflows] == [2, 1], surface.workflows



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

    def test_a_root_whose_workflows_directory_is_empty_is_refused(self, tmp_path: Path) -> None:
        """The sneakier half of the same misconfiguration: the directory exists but is empty.

        `walk()` guarded a *missing* `workflows/` but not an existing empty one — a root
        pointed one level too deep, or a tree emptied by accident, walked to a clean zero
        with no warning, indistinguishable from a tree that genuinely declares no gates. That
        silent zero is the exact failure this feature exists to prevent. Raised in review as a
        blocking change; guarded now the same way the missing directory is. The `skills/` file
        with no workflow file is the shape that slipped through: `workflows/` is a real
        directory, just empty of `.md`, so the missing-directory guard did not fire.
        """
        (tmp_path / "workflows").mkdir()
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "a.md").write_text("MENU M\n  OPTIONS:\n", encoding="utf-8")
        with pytest.raises(FileNotFoundError, match="no workflow files"):
            gs.walk(tmp_path)

    def test_a_workflows_directory_with_only_unreadable_files_is_not_called_empty(
            self, tmp_path: Path) -> None:
        """An unreadable workflow file is a reported gap, not a silent zero, so it is walked.

        The empty guard must fire only when there is *nothing* workflow-shaped. A `workflows/`
        holding a file that exists but cannot be read is not the silent-zero failure — that
        path lands in `unreadable` and the warning — so raising "empty" there would be false
        *and* would swallow the report the module exists to surface. A directory named like a
        workflow file reproduces an unreadable `.md` without a permission dance: `rglob` matches
        it and reading it raises. Found by adversarial review of the empty-directory guard.
        """
        (tmp_path / "workflows" / "w.md").mkdir(parents=True)   # a dir where a file is expected
        surface = gs.walk(tmp_path)                              # does not raise "empty"
        assert surface.workflows == [], surface.workflows        # nothing readable to walk
        assert any("workflows/w.md" in u for u in surface.unreadable), surface.unreadable

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
                # `LOAD` named separately because it is read by different code — the
                # closure and the missing-target check, not the menu walk — and a prose
                # dependency line creates a phantom reachability edge rather than a
                # phantom gate. Named in review as the case no fixture covered.
                "LOAD {cf-studio-path}/.core/not-a-real-target.md shows the syntax.\n"
                "\n"
                "```pdsl\nUNIT W\nDO:\n  EMIT_MENU Real\n  WAIT user.reply\n```\n"
                "\n"
                "A closing paragraph that mentions EMIT_MENU Afterwards.\n"),
        }, fenced=False)
        surface = gs.walk(root)
        assert list(surface.menu_reachability) == ["Real"], surface.menu_reachability
        assert surface.distinct_menu_definitions == 0, surface.distinct_menu_definitions
        assert surface.missing_loads == [], surface.missing_loads

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

    @pytest.mark.parametrize("renamed", ["LOAD", "EMIT_MENU", "STOP_TURN", "WAIT"])
    def test_the_keyword_guard_fires_if_pdsl_renames_an_action(
            self, monkeypatch: pytest.MonkeyPatch, renamed: str) -> None:
        """A rename would otherwise leave this counting zero and calling it clean.

        The silent-zero failure is the one that matters: nobody questions a number that
        went down in a project whose goal is to make it go down. Parametrised over **every**
        keyword the module depends on -- including WAIT, which `_ends_the_turn` reads and which
        the guard's checked set previously omitted -- so a keyword dropped from the guard while
        still consumed by the code fails here. The cases are literal strings, not drawn from the
        guard's own set (A5a).
        """
        from studio.utils import pdsl  # noqa: PLC0415

        monkeypatch.setattr(pdsl, "DO_KEYWORDS",
                            {"LOAD", "EMIT_MENU", "STOP_TURN", "WAIT"} - {renamed})
        with pytest.raises(RuntimeError, match=renamed):
            gs._check_keywords_still_exist()

    def test_the_keyword_guard_fires_as_a_consequence_of_import(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The guarantee is "this module fails loudly at import", so import is what is run.

        The test above calls the function directly, which checks its logic and not the
        promise: deleting the module-level `_check_keywords_still_exist()` call left the
        whole file green — 81 tests, no failure. A guard whose placement nothing checks is
        a guard that can be moved into a function nobody calls. Raised in review.

        The module is reloaded rather than imported fresh, because it is already in
        `sys.modules` by the time any test runs, and restored in `finally` so a failure here
        cannot leave a half-initialised module behind for every test after it.
        """
        import importlib  # noqa: PLC0415

        from studio.utils import pdsl  # noqa: PLC0415

        monkeypatch.setattr(pdsl, "DO_KEYWORDS", {"LOAD", "EMIT_MENU"})
        try:
            with pytest.raises(RuntimeError, match="no longer PDSL actions"):
                importlib.reload(gs)
        finally:
            monkeypatch.undo()
            importlib.reload(gs)


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

    def test_any_wait_ends_the_turn_not_only_the_common_one(
            self, tmp_path: Path) -> None:
        """The corpus writes `WAIT user.advance` as well as `WAIT user.reply`.

        Matching the full phrase `WAIT user.reply` read the other form as *not* waiting, so
        the emit before it counted as non-stopping — an undercount, which this module calls
        its worst failure because it is indistinguishable from progress.

        Neither published figure moves: the one `user.advance` line lives in
        `requirements/`, outside the scanned roots. That is why this is pinned on a fixture
        rather than measured — swapping the constant for a bare `WAIT` changed nothing any
        test or corpus number could see, which is how it survived until mutation.

        `WAITING` is not a wait: the match is on the first token, not a prefix.
        """
        # No `STOP_TURN` after the wait, deliberately: `STOP_TURN` ends the turn on its own,
        # so a fixture carrying one cannot tell a wait from a non-wait. My first version had
        # one and the "not a wait" case passed for the wrong reason.
        for wait in ("WAIT user.reply", "WAIT user.advance", "WAIT"):
            root = _tree(tmp_path / wait.replace(" ", "_").replace(".", "_"), {
                "workflows/w.md": f"UNIT W\nDO:\n  EMIT_MENU M\n  {wait}\n",
            })
            counted = gs.walk(root).workflows[0]
            assert (counted.stop_sites, counted.non_stop_sites) == (1, 0), (wait, counted)

        # `WAITING` shares the prefix and is not a wait, so this emit never stops.
        root = _tree(tmp_path / "waiting", {
            "workflows/w.md": "UNIT W\nDO:\n  EMIT_MENU M\n  WAITING for something\n",
        })
        counted = gs.walk(root).workflows[0]
        assert (counted.stop_sites, counted.non_stop_sites) == (0, 1), counted

    def test_a_malformed_emit_does_not_swallow_the_halt_after_it(
            self, tmp_path: Path) -> None:
        """A prefix test accepted tokens the validator rejects, and that *hid* a halt.

        `_halts_outside_menus` marked a sequence "already emitted" on any line starting
        with the eight characters of `EMIT_MENU`, so `EMIT_MENUX` — a different token —
        and `EMIT_MENU 9Invalid` — not a legal name — each suppressed the `STOP_TURN`
        after them. The count moved in the direction that flatters the measurement: fewer
        halts, from a line that is not an emit at all.

        Zero instances in the tree today. Fixed anyway, because the defect is that two
        scans in one module disagreed about what an emit is, and `_emit_on` is the one
        that already matches the validator. Raised in review.
        """
        cases = {
            "EMIT_MENUX": 1,            # a longer token, not `EMIT_MENU` with an argument
            "EMIT_MENU 9Invalid": 1,    # a name the validator will not accept
            "EMIT_MENU Real": 0,        # the control: a real emit does suppress it
        }
        for line, expected in cases.items():
            root = _tree(tmp_path / line.replace(" ", "_"), {
                "workflows/w.md": f"UNIT W\nDO:\n  {line}\n  STOP_TURN\n",
            })
            assert gs.walk(root).workflows[0].halt_sites == expected, (line, expected)

    def test_a_bare_colon_line_that_is_not_a_section_does_not_swallow_a_halt(
            self, tmp_path: Path) -> None:
        """A `Word:` line that is not a real section header must not drop the halt after it.

        `_halts_outside_menus` reset the counted section on *any* bare `token:` line, not only
        a real PDSL header — while the sibling `_ends_the_sequence` checks membership in the
        authoritative `_SECTIONS`. A mixed-case `Important:` is legal inside a validator-passing
        `DO` block (the validator only rejects ALL-CAPS dashless tokens it does not know), so it
        silently reset the section and the following `STOP_TURN` was skipped — an under-count,
        the one direction this walk must never take. The boundary is `_SECTIONS` now too. Zero
        instances in the corpus; the fixture is synthetic. Raised in review.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "UNIT W\nDO:\n  Important:\n  STOP_TURN\n",
        })
        # `DO` stays the section across the non-header `Important:` line, so the halt counts;
        # the old bare-colon heuristic reset it to `Important` and dropped the STOP_TURN to 0.
        assert gs.walk(root).workflows[0].halt_sites == 1, gs.walk(root).workflows[0]

    def test_a_stop_turn_that_is_not_the_first_token_still_ends_the_turn(
            self, tmp_path: Path) -> None:
        """`EMIT "..." and STOP_TURN` after an emit is a stop; a prefix test missed it.

        `_ends_the_turn` matched `STOP_TURN` only at the *start* of the action, while the
        sibling `_halts_outside_menus` matched it as a substring — so the emit before the
        corpus's `EMIT "..." and STOP_TURN` line was settled as non-stopping, an under-count,
        and the two scans disagreed about the same token. Both use one whole-token recogniser
        now. Raised in review.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": 'UNIT W\nDO:\n  EMIT_MENU Ask\n  EMIT "refused" and STOP_TURN\n',
        })
        w = gs.walk(root).workflows[0]
        assert w.stop_sites == 1, w        # the emit's sequence ends in a STOP_TURN
        assert w.non_stop_sites == 0, w

    def test_a_longer_token_beginning_with_stop_turn_is_not_a_stop_or_halt(
            self, tmp_path: Path) -> None:
        """`STOP_TURNX` is a different token — not the halt keyword — in both scans.

        `_ends_the_turn` matched by prefix and `_halts_outside_menus` by substring, so
        `STOP_TURNX` (and, for the halt scan, prose like `... STOP_TURNs when ...`) counted
        as a real stop/halt. Whole-token `\\bSTOP_TURN\\b` now, shared by both. Raised in
        review.

        Two fixtures, so each scan's token-safety binds on its own: `STOP_TURNX` **without** a
        preceding emit binds the halt scan (a preceding emit sets `emitted`, which would zero
        the halt either way), and `STOP_TURNX` **after** an emit binds the turn scan (the old
        prefix test read it as a stop).
        """
        # Halt scan: no emit before it, so the old substring test would have counted a halt.
        halt_root = _tree(tmp_path / "halt", {
            "workflows/w.md": "UNIT W\nDO:\n  STOP_TURNX\n",
        })
        assert gs.walk(halt_root).workflows[0].halt_sites == 0, gs.walk(halt_root).workflows[0]

        # Turn scan: after an emit, so the old prefix test read `STOP_TURNX` as ending the turn.
        turn_root = _tree(tmp_path / "turn", {
            "workflows/w.md": "UNIT W\nDO:\n  EMIT_MENU Ask\n  STOP_TURNX\n",
        })
        w = gs.walk(turn_root).workflows[0]
        assert w.stop_sites == 0, w        # STOP_TURNX does not end the emit's turn
        assert w.non_stop_sites == 1, w    # the emit ran on with no real stop

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
        Raised in review. It now reports no component at all -- an opaque placeholder -- and
        says so, because the final component is itself the username when the path reported is
        the home directory, and with `$HOME` unreadable that case cannot be told apart.
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
        # Was `.../kit`. The component is gone: for a path that is itself the home
        # directory, the final component is the username, and with `$HOME` unreadable that
        # case cannot be distinguished from this one. Raised in review.
        assert rendered == "...", rendered
        assert any("could not be read" in r.getMessage()
                   for r in caplog.records), [r.getMessage() for r in caplog.records]

    def test_a_newline_in_the_tree_path_cannot_forge_a_line_in_a_warning(self) -> None:
        """`tree` was the one reported value that skipped the strip every other one passes.

        It is interpolated into all three gap warnings and into the `FileNotFoundError`, so
        a directory named with a newline rendered as two lines there — the second a
        fabricated sentence in output whose whole job is to say the count is incomplete.
        This module's own `_reported` docstring calls that forgery "the third appearance in
        three modules" and says to fix the class; `_said` was a fourth instance of it, in
        the same file. Raised in review.
        """
        forged = gs._said("/tmp/a\nWARNING gate surface: 0 gates found")
        assert "\n" not in forged, forged
        assert "WARNING" in forged, forged  # kept, just no longer on a line of its own

    def test_an_emit_does_not_borrow_a_wait_from_a_later_fence(self, tmp_path: Path) -> None:
        """Blanking the fence marker made the guard against this unreachable from `walk()`.

        `_ends_the_sequence` tests for a ``` line, but `_declared` replaced marker lines
        with blanks before it ever saw them, so an emit at the end of one fenced block
        scanned straight on into the next one and adopted its `WAIT`. The emit counted as a
        declared stop it never makes, and the standalone halt disappeared — an under-count,
        which is the direction this walk must never fail in.

        No instance in the corpus (the published counts are identical either way), so the
        fixture is synthetic: measuring the real tree cannot tell a fix from its absence at
        zero instances. Raised in review.
        """
        root = tmp_path
        (root / "workflows").mkdir(parents=True)
        (root / "skills").mkdir(parents=True)
        # The second block carries **no header**, deliberately. The first version of this
        # test opened it with `UNIT Later`, and `UNIT` is itself a section header that ends
        # the sequence — so the scan stopped for a reason that had nothing to do with the
        # fence, and the test passed identically with the fix reverted. It proved nothing.
        # Caught by mutating; the fence has to be the only thing that can stop the scan.
        (root / "workflows" / "w.md").write_text(
            "```pdsl\nUNIT W\nDO:\n  EMIT_MENU Alpha\n```\n\n"
            "Prose between the two blocks.\n\n"
            "```pdsl\n  WAIT user.reply\n  STOP_TURN\n```\n",
            encoding="utf-8")

        surface = gs.walk(root)

        w = surface.workflows[0]
        assert w.stop_sites == 0, f"the emit borrowed a WAIT across the fence: {w}"
        assert w.non_stop_sites == 1, w

    def test_a_malformed_fence_shape_in_a_block_body_does_not_clip_a_stop(self) -> None:
        """The two fence detectors agree, so neither clips a stop the other keeps.

        `_declared` was pinned to the validator's `FENCE_RE`; its sibling `_ends_the_sequence`
        used a bare `startswith("```")`. They diverge on a fence-shaped line the validator
        rejects — a tag with trailing text, `` ```pdsl garbage `` — sitting inside a pdsl
        block: `_declared` keeps it as ordinary body (as `scan_blocks` does), but the bare
        `startswith` read it as a fence and ended the emit's sequence there, settling the
        emit as a non-stop before its `WAIT`. That under-counts the stop, the one direction
        this walk must never fail in. Pinning `_ends_the_sequence` to `FENCE_RE` too closes
        the asymmetry. No such line is in the corpus (an A6 sibling case, found in review),
        so this is asserted on a synthetic body run through the real pipeline: revert the
        `startswith` and `waits` flips to False.
        """
        raw = ("```pdsl\nUNIT W\nDO:\n"
               "  EMIT_MENU Ask\n"
               "```pdsl garbage\n"          # fence-shaped, but the validator rejects it
               "  WAIT user.reply\n  STOP_TURN\n```\n")
        declared = gs._declared(raw)
        # `_declared` keeps the malformed line verbatim -- it is body, not a fence marker.
        assert "```pdsl garbage" in declared, declared
        [site] = gs.emit_sites(declared)
        assert site.menu == "Ask", site
        assert site.waits is True, site      # the WAIT is reached, not clipped by the ``` shape

    def test_a_redactor_that_silently_did_nothing_is_not_trusted(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`capped_text` returning cleanly is not proof that it redacted anything.

        `decision_log._redact` catches its *own* `Path.home()` failure and returns the
        value unchanged without raising, so the success branch handed back a raw absolute
        path — the username in the one field this function exists to keep it out of.

        Worth naming why this took three rounds: the two earlier fixes both guarded the
        branch where `capped_text` throws, and read the finding as being about the
        fallback. The leak is on the branch where `capped_text` succeeds, which no test
        touched. So the guard now checks the value that came back rather than inferring
        redaction from a clean return. Raised in review three times.
        """
        from studio.utils import decision_log  # noqa: PLC0415

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/someone")))
        # Precisely what `_redact` does when `Path.home()` raises inside it: hand the
        # input straight back. No exception, so the except branch never runs.
        monkeypatch.setattr(decision_log, "capped_text", lambda value: value)

        rendered = gs._said("/home/someone/projects/kit")
        assert "someone" not in rendered, rendered
        assert rendered == "~/projects/kit", rendered

    def test_no_emit_site_field_is_whitelisted_while_this_module_reads_it(self) -> None:
        """A whitelist entry for a field this module reads suppresses a real finding.

        `conditional` had one while `menu` and `waits` — read in the same loop, over the
        same objects, by the same attribute access — did not. An entry kept past its reason
        hides the next genuine dead-code finding, which is what this whitelist's own removal
        triggers exist to prevent. Raised in review, and confirmed by deleting it: the scan
        still passes.

        The rule is **measured, not declared**. The first version simply banned any
        `EmitSite.*` entry, which happens to be right today and would be wrong the moment a
        field is genuinely unused — and its failure message named a reader function it had
        not checked. This reads the module and pairs the two facts, so a field that really
        does go unread may still be whitelisted, and one that is read may not.

        Asserted over the dataclass's fields rather than the one name, so a field added
        later is covered without anyone remembering.
        """
        import ast  # noqa: PLC0415
        import dataclasses  # noqa: PLC0415

        root = Path(__file__).resolve().parents[1]
        whitelist = (root / "vulture_whitelist.py").read_text(encoding="utf-8")
        module = ast.parse(
            (root / "skills/studio/scripts/studio/utils/gate_surface.py").read_text(
                encoding="utf-8"))
        read_here = {n.attr for n in ast.walk(module)
                     if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load)}

        contradictory = [f.name for f in dataclasses.fields(gs.EmitSite)
                         if f"EmitSite.{f.name}" in whitelist and f.name in read_here]
        assert not contradictory, (
            f"these EmitSite fields are whitelisted as dead while this module reads them: "
            f"{contradictory}. The entry suppresses the next real finding on the same field."
        )

    def test_unreadable_files_are_reported_in_a_stable_order(self, tmp_path: Path) -> None:
        """Two machines must report the same list, and it lands in a saved baseline.

        The order came out sorted already — but only because the walk happened to be
        sorted, which made the guarantee incidental rather than owned. Dropping that
        `sorted` reordered the report to filesystem order (`alpha, zeta, mid` for files
        created `zeta, alpha, mid`) and no test noticed. Found by mutation.

        Created deliberately out of order, because a fixture whose creation order is already
        alphabetical cannot tell a sorted report from an unsorted one.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "UNIT W\nDO:\n  EMIT_MENU M\n  WAIT user.reply\n  STOP_TURN\n",
        })
        skills = root / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        for name in ("zeta.md", "alpha.md", "mid.md"):
            (skills / name).write_bytes(b"\xff\xfe")

        reported = gs.walk(root).unreadable
        assert reported == sorted(reported), reported
        assert [entry.split(":")[0] for entry in reported] == [
            "skills/alpha.md", "skills/mid.md", "skills/zeta.md"], reported

    def test_a_windows_path_still_keys_the_tree_in_forward_slashes(self) -> None:
        """The claim in the comment, finally exercised.

        `str()` on a relative path yields `workflows\\w.md` on Windows, and everything
        downstream speaks forward slashes — the workflow set is selected by a `workflows/`
        prefix and `LOAD` targets are written with `/`. The consequence is not a wrong
        number but **zero** workflows walked and every in-tree load reported missing: a
        silent empty surface on one platform.

        That was asserted in a comment and by nothing else. On POSIX the two calls are
        identical, so only handing the helper a `PureWindowsPath` can tell them apart —
        which is why the key is a function rather than an inline expression. Found by
        mutation: swapping `as_posix()` for `str()` changed nothing any test could see.
        """
        from pathlib import PurePosixPath, PureWindowsPath  # noqa: PLC0415

        windows = gs._tree_key(PureWindowsPath(r"C:\repo\workflows\w.md"),
                               PureWindowsPath(r"C:\repo"))
        assert windows == "workflows/w.md", windows
        assert "\\" not in windows, windows
        # And the prefix the walk selects on actually matches, which is the thing that broke.
        assert windows.startswith("workflows/"), windows

        posix = gs._tree_key(PurePosixPath("/repo/skills/deep/s.md"), PurePosixPath("/repo"))
        assert posix == "skills/deep/s.md", posix

    def test_the_read_works_where_the_nonblocking_flag_does_not_exist(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`O_NONBLOCK` is POSIX-only, and naming it directly broke Windows entirely.

        `os.O_RDONLY | os.O_NONBLOCK` raises `AttributeError` while *evaluating the
        expression*, so the walk failed on the first ordinary file it touched — not only
        when the hazard the flag guards was present. Every workflow, every run, on that
        platform. Raised in review as a Major, against a module that already carries a
        Windows fix for path separators.

        Simulated by deleting the attribute, which is what that platform looks like from
        here. The flag is taken with `getattr(..., 0)` now; losing it on Windows loses
        nothing, because the `S_ISREG` check is what carries the guarantee and named pipes
        there are not in the filesystem namespace this walk globs.
        """
        monkeypatch.delattr(os, "O_NONBLOCK", raising=False)
        monkeypatch.delattr(os, "O_BINARY", raising=False)
        import importlib  # noqa: PLC0415

        reloaded = importlib.reload(gs)
        try:
            root = _tree(tmp_path, {
                "workflows/w.md": "UNIT W\nDO:\n  EMIT_MENU M\n  WAIT user.reply\n  STOP_TURN\n",
            })
            surface = reloaded.walk(root)
            assert [w.workflow for w in surface.workflows] == ["workflows/w.md"], surface
        finally:
            # Restore the module for every later test, whatever happened above.
            monkeypatch.undo()
            importlib.reload(gs)

    def test_a_named_pipe_in_the_tree_does_not_hang_the_walk(
            self, tmp_path: Path, caplog) -> None:
        """`read_text` on a path this walk did not create is a blocking acquisition.

        A FIFO named `*.md` is matched by the glob, reports `st_size == 0` so any size
        guard passes it, and opening it for reading waits for a writer that never comes —
        no exception and no timeout. Reproduced before fixing: `walk()` over a tree
        containing one never returned. This module is about to run as a gate on every pull
        request, where that is a stalled build rather than a slow one. Found by the pre-PR
        pattern walk, which carries this rule after the same defect in another module.

        The file is still **reported**, not quietly skipped: a file dropped in silence
        lowers every count after it, and a lower count is indistinguishable from progress.
        """
        root = _tree(tmp_path, {
            "workflows/real.md": "UNIT W\nDO:\n  EMIT_MENU M\n  WAIT user.reply\n  STOP_TURN\n",
        })
        if not hasattr(os, "mkfifo"):
            # No FIFOs on this platform. Skipping is honest; the hang this guards is
            # reachable wherever they exist.
            pytest.skip("this platform does not support named pipes")
        skills = root / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        # Not wrapped in try/except. A first version caught `OSError` around `mkfifo` and
        # skipped on it -- and `skills/` did not exist, so the call failed on a missing
        # parent and the whole test reported as "platform does not support named pipes".
        # A skip that fires for the wrong reason is worse than a failure: it is green.
        os.mkfifo(skills / "trap.md")

        # Run on a thread with a bounded join. Without the guard this call does not fail,
        # it *blocks forever* -- and a test that hangs stops the suite, which reads as CI
        # being broken rather than as this check failing. Verified: with the guard removed
        # the direct call had to be killed at 90s, and this reports in ten.
        #
        # The runaway thread is left blocked in `open` on the FIFO, holding one descriptor
        # and allocating nothing, so bounding the wait is enough here; where the runaway
        # would keep working, the work needs its own ceiling too.
        import threading  # noqa: PLC0415

        outcome: dict = {}

        def _walk() -> None:
            outcome["surface"] = gs.walk(root)

        worker = threading.Thread(target=_walk, daemon=True)
        with caplog.at_level(logging.WARNING, logger=gs.logger.name):
            worker.start()
            worker.join(timeout=10)

        assert not worker.is_alive(), (
            "walk() did not return within 10s on a tree containing a named pipe -- the "
            "read is blocking again"
        )
        surface = outcome["surface"]

        assert [w.workflow for w in surface.workflows] == ["workflows/real.md"], surface.workflows
        assert any("trap.md" in entry for entry in surface.unreadable), surface.unreadable
        assert any("floor rather than a total" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

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

        **This replaced a wall-clock test of the same regression.** Both caught it; this
        one in 1.6 seconds against 49, without depending on the scheduler. The case a call
        count cannot see -- a regex backtracking inside `re`, where the work happens without
        touching this function at all -- is pinned by the test below, by what each pattern
        is given rather than by how long it takes.
        """
        calls = []
        real = gs._action
        monkeypatch.setattr(gs, "_action", lambda line: calls.append(1) or real(line))
        text = "UNIT U\nDO:\n" + ("  EMIT_MENU M\n" * 500) + "RULES:\n  ALWAYS x\n"
        sites = gs.emit_sites(text)
        assert len(sites) == 500, len(sites)
        assert len(calls) == len(text.splitlines()), (len(calls), len(text.splitlines()))

    def test_no_pattern_in_the_emit_scan_is_given_more_than_one_line(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The cross-line backtracking this class is named for, made impossible rather than timed.

        The regression measured 0.8 / 3.2 / 12.5 / 52.4 ms for 500 / 1000 / 2000 / 4000 lines:
        `^\\s*` under `re.M`, where `\\s` matches a newline, so a run of blank lines followed
        by a near-miss backtracked across lines. That cost needs a pattern that is *given*
        more than one line. A pattern applied to one line at a time cannot backtrack across
        lines, whatever its shape, so the property is asserted on the input each pattern
        receives.

        This replaced a wall-clock ratio (`elapsed(64000) < elapsed(16000) * 8`), which went
        red on loaded runners with no defect behind it -- 8.05x under coverage on CI, 10x and
        14.5x under `pytest -n 8` locally, each passing alone (#418). A red run that may be the
        scheduler makes every red run ambiguous.

        Every compiled pattern in the module's namespace (its own and the `FENCE_RE` it
        imports) is wrapped, and so is the `re` module it calls, so a pattern compiled inside
        a function is seen too. The input is the old hostile shape plus real emits, waits and
        a fence, so every pattern the scan uses runs and the spy cannot pass by being skipped.
        """
        import re  # noqa: PLC0415

        given: list = []

        class _PatternSpy:
            def __init__(self, real: "re.Pattern[str]") -> None:
                self._real = real

            def __getattr__(self, name: str):
                attr = getattr(self._real, name)
                if not callable(attr) or name not in {
                        "search", "match", "fullmatch", "finditer", "findall",
                        "sub", "subn", "split"}:
                    return attr

                def call(*args, **kwargs):
                    # `sub`/`subn` take the replacement first; the text is the last string.
                    text = [a for a in args if isinstance(a, str)][-1]
                    given.append(text)
                    return attr(*args, **kwargs)
                return call

        class _ReSpy:
            def __getattr__(self, name: str):
                attr = getattr(re, name)
                if name == "compile":
                    return lambda *a, **k: _PatternSpy(re.compile(*a, **k))
                if name not in {"search", "match", "fullmatch", "finditer", "findall",
                                "sub", "subn", "split"}:
                    return attr

                def call(*args, **kwargs):
                    # The text is `string`: third for `sub`/`subn` (pattern, repl, string),
                    # second for the rest -- positional, or by keyword.
                    at = 2 if name in {"sub", "subn"} else 1
                    given.append(kwargs["string"] if len(args) <= at else args[at])
                    return attr(*args, **kwargs)
                return call

        for name, value in list(vars(gs).items()):
            if isinstance(value, re.Pattern):
                monkeypatch.setattr(gs, name, _PatternSpy(value))
        monkeypatch.setattr(gs, "re", _ReSpy())

        text = (("   \n" * 200) + "EMIT_MENUX\n"
                + "UNIT U\nDO:\n  - EMIT_MENU Asks WHEN x\n  WAIT user.reply\n"
                + "  EMIT_MENU Proceeds\n  CONTINUE Next\n```pdsl\n```\n"
                + "  EMIT_MENU Halts\n  STOP_TURN\n")
        sites = gs.emit_sites(text)

        # A stop that is conditional, a non-stop, and a stop: the scan's three outcomes.
        assert [(s.menu, s.waits, s.conditional) for s in sites] == [
            ("Asks", True, True), ("Proceeds", False, False), ("Halts", True, False)], sites
        assert given, "no pattern ran: the spy saw nothing, so this asserted nothing"
        multi = [t for t in given if "\n" in t]
        assert multi == [], f"{len(multi)} pattern call(s) were given more than one line"

    @staticmethod
    def _findall_spy(monkeypatch: pytest.MonkeyPatch) -> list:
        """Count `LOAD_TARGET.findall` calls, delegating to the real compiled pattern."""
        calls: list = []
        real = gs.LOAD_TARGET

        class _Spy:
            def findall(self, text: str) -> list:
                calls.append(1)
                return real.findall(text)

        monkeypatch.setattr(gs, "LOAD_TARGET", _Spy())
        return calls

    def test_missing_loads_runs_findall_once_per_file(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Linear in the corpus: one `LOAD_TARGET.findall` per file, not per file per workflow.
        Counted, not timed -- the sibling `emit_sites` linearity is pinned this way and the
        timing tests above went red on CI without a defect. (A6: the siblings now match.)
        """
        calls = self._findall_spy(monkeypatch)
        files = {f"f{i}.md": "LOAD {cf-studio-path}/.core/a.md\n" for i in range(50)}
        gs._missing_loads(files)
        assert len(calls) == len(files), (len(calls), len(files))

    def test_closure_runs_findall_once_per_distinct_reachable_file(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The `seen` set makes closure scan each reachable file once, not once per path to
        it -- the memoisation the walk depends on. A diamond reaches `c` by two paths; findall
        must still touch it once (4 files -> 4 calls). Counted, not timed.
        """
        calls = self._findall_spy(monkeypatch)
        load = "LOAD {cf-studio-path}/.core/"
        files = {"start.md": f"{load}a.md\n{load}b.md\n", "a.md": f"{load}c.md\n",
                 "b.md": f"{load}c.md\n", "c.md": ""}
        reached = gs._closure("start.md", files)
        assert reached == {"start.md", "a.md", "b.md", "c.md"}, reached
        assert len(calls) == 4, len(calls)   # start, a, b, c -- c once despite two paths

    def test_halts_outside_menus_reads_each_line_once(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """One `_action` call per line is what one pass means -- the same property `emit_sites`
        pins above, its uncovered sibling now pinned too. Counted, not timed.
        """
        calls: list = []
        real = gs._action
        monkeypatch.setattr(gs, "_action", lambda line: calls.append(1) or real(line))
        text = "UNIT U\nDO:\n" + ("  STOP_TURN\n" * 500) + "RULES:\n  ALWAYS x\n"
        gs._halts_outside_menus(text)
        assert len(calls) == len(text.splitlines()), (len(calls), len(text.splitlines()))

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

    def test_a_block_header_is_recognised_the_way_the_validator_recognises_it(self) -> None:
        """Indentation does not decide whether a line opens a block; the first token does.

        This asserted the opposite until review: a header had to sit at the left margin.
        The validator has no such rule — `_handle_unit_or_menu_line` matches
        `UNIT_OR_MENU_RE` against the *stripped* line — so an indented `MENU Name` opened a
        block there and was body text here, folding one block's body into the one before it
        and putting its `WAIT` in the wrong menu.

        Zero lines in the tree or the pinned kit are indented headers, and every published
        figure is unchanged, so this closes a divergence rather than moving a number. It is
        closed toward the validator because agreeing with it is what this module says it
        does, and because the error ran in the under-counting direction.
        """
        blocks = dict(gs.menu_blocks(
            "MENU Outer\n  OPTIONS:\n  MENU Inner\n  WAIT user.reply\n"))
        assert set(blocks) == {"Outer", "Inner"}, sorted(blocks)
        # The `WAIT` belongs to the block that was open when it appeared.
        assert "WAIT user.reply" in blocks["Inner"], blocks
        assert "WAIT user.reply" not in blocks["Outer"], blocks

    def test_block_header_recognition_agrees_with_the_validator_programmatically(self) -> None:
        """The header-recognition rule pinned to the validator's own regex, not fixed pairs.

        The sibling menu-name grammar (test_a_name_is_read_exactly_...) asserts against
        `UNIT_OR_MENU_RE` directly, so a validator change fails rather than drifts. This rule
        had only hand-picked pairs plus a docstring mention of the validator, never importing
        it. This closes that asymmetry: for each candidate line, `_block_header` opens a block
        (returns non-``None``) iff the validator matches the *stripped* line, so a change to
        `UNIT_OR_MENU_RE`'s block recognition fails here. Cases are literal strings, not drawn
        from the pattern (A5a).
        """
        from studio.utils.pdsl import UNIT_OR_MENU_RE  # noqa: PLC0415

        # Both bare keywords (no name) are included: the validator requires a name for each,
        # and `_block_header`'s UNIT branch used to open on a bare `UNIT` while MENU did not —
        # the sibling asymmetry this biconditional exists to catch (found by an A6 review pass).
        for line in ("MENU Outer", "  MENU Inner", "\tUNIT One", "UNIT One",
                     "1 go -> see MENU X", "  OPTIONS:", "not a header",
                     "  WAIT user.reply", "MENU", "UNIT", "  UNIT", ""):
            validator_opens = UNIT_OR_MENU_RE.match(line.strip()) is not None
            assert (gs._block_header(line) is not None) == validator_opens, line

    def test_fence_language_recognition_agrees_with_the_validator_programmatically(self) -> None:
        """Which fence declares PDSL pinned to the validator's own scan, not a private regex.

        `_declared` used a home-grown `^```(\\w*)` compared case-sensitively to ``"pdsl"``,
        which diverged from `scan_blocks` in three ways review named: ```PDSL was declared
        there and not here (case), ```pdsl-x was pdsl here and not there (`\\w` stops at the
        hyphen, the validator does not), and ```pdsl trailing was pdsl here and not there
        (un-anchored here, `\\s*$` there). A fence the walk reads as PDSL but the validator
        rejects — or the reverse — is a gate counted against a block that will never run, or
        a real block dropped. This closes the asymmetry the way the block-header sibling
        above does: for each candidate opener, `_declared` keeps a fenced line iff the
        validator captures it in a PDSL block. Cases are literal strings, not drawn from the
        pattern (A5a), and include all three divergences.
        """
        from studio.utils import pdsl  # noqa: PLC0415

        sentinel = "EMIT_MENU Sentinel"
        for opener in ("```pdsl", "```PDSL", "```Pdsl", "```pdsl ", "```",
                       "```bash", "```json", "```pdsl-x", "```pdsl garbage",
                       "```pdslx", "```  ", "~~~pdsl"):
            doc = f"{opener}\n{sentinel}\n```\n"
            blocks, _ = pdsl.scan_blocks("t", doc)
            # A block opened *at a fence* starts on the line after it, so `line > 1`. The one
            # block that can start at line 1 is `scan_blocks`'s delimiter-free fallback (no
            # fences and no findings anywhere -> treat the whole file as pure PDSL), which is
            # a different mechanism from fence-language recognition and one `_declared` does
            # not model. Excluding it keeps this biconditional about which *fence* declares.
            validator_declares = any(sentinel in b.text and b.line > 1 for b in blocks)
            walk_declares = sentinel in gs._declared(doc)
            assert walk_declares == validator_declares, opener

    def test_a_line_whose_first_token_is_not_the_keyword_opens_nothing(self) -> None:
        """What the left-margin rule was really protecting, kept without it.

        `MENU` appearing *inside* an option must still not end the definition it sits in.
        The distinction is the first token, not the indentation — and it has to be written
        as its own case, because the previous test's own comment records that a first
        version used `1 go -> see MENU Inner`, whose first token is `1`, so it passed with
        the rule removed and proved nothing.
        """
        blocks = dict(gs.menu_blocks(
            "MENU Outer\n  OPTIONS:\n    1 go -> see MENU Inner\n  WAIT user.reply\n"))
        assert set(blocks) == {"Outer"}, sorted(blocks)
        assert "WAIT user.reply" in blocks["Outer"], blocks["Outer"]

    def test_a_shared_file_is_parsed_once_not_once_per_workflow(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Skill files are shared, and every reaching workflow re-parsed them.

        The kit's most-reached menu sits in a file 46 of 47 workflows can get to, so its
        text was scanned 46 times. Measured on the real tree: 2122 scans before, 205 after,
        and the walk went from ~170ms to ~40ms with every published figure unchanged.
        Raised in review.

        Counted rather than timed. A timing assertion on a 40ms walk is a flake generator,
        and the claim here is about *how many times a file is parsed*, which is exactly what
        a call count says and a stopwatch only implies.
        """
        shared = "UNIT Shared\nDO:\n  EMIT_MENU Common\n  WAIT user.reply\n  STOP_TURN\n"
        tree = {"skills/shared.md": shared}
        for i in range(6):
            tree[f"workflows/w{i}.md"] = (
                f"UNIT W{i}\nDO:\n"
                "  LOAD {cf-studio-path}/.core/skills/shared.md\n"
                "  STOP_TURN\n")
        root = _tree(tmp_path, tree)

        scans: list = []
        real = gs.emit_sites
        monkeypatch.setattr(gs, "emit_sites", lambda text: (scans.append(text), real(text))[1])
        surface = gs.walk(root)

        assert len(surface.workflows) == 6, surface.workflows
        # Six workflows reach it; it is parsed once. Matched on content rather than on the
        # fixture string, because the scan receives the fence-filtered text, not the raw.
        parsed = sum("EMIT_MENU Common" in text for text in scans)
        assert parsed == 1, f"the shared file was parsed {parsed} times, not once"
        # And the general property, not only this file: nothing is parsed twice.
        assert len(scans) == len(set(scans)), "some file was parsed more than once"
        # And the counting is unaffected: every workflow still sees the menu it reaches.
        assert surface.menu_reachability == {"Common": 6}, surface.menu_reachability

    def test_two_walks_sharing_a_relative_path_do_not_leak_across_trees(
            self, tmp_path: Path) -> None:
        """The scan cache is per `walk()`, so a shared relative path in a second tree gets the
        second tree's content — the non-staleness the cache docstring claims.

        `_scanned`/`_count_reached` are private and reached only through `walk`, which builds a
        fresh `scan_cache` each call, so the one-cache-per-`files`-mapping contract is enforced
        by structure rather than convention. This pins it: two trees each declaring
        `workflows/w.md` with *different* menus, walked in sequence, and the second walk must
        report its own menu, not the first's. Raised in review.
        """
        a = _tree(tmp_path / "a", {"workflows/w.md": "UNIT A\nDO:\n  EMIT_MENU Alpha\n  WAIT user.reply\n"})
        b = _tree(tmp_path / "b", {"workflows/w.md": "UNIT B\nDO:\n  EMIT_MENU Beta\n  WAIT user.reply\n"})
        assert list(gs.walk(a).menu_reachability) == ["Alpha"]      # first tree
        assert list(gs.walk(b).menu_reachability) == ["Beta"]       # second: its own content, not Alpha

    def test_the_cycle_guard_failing_is_a_loud_failure_not_a_spin(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The fail-safe in `_closure`, which nothing reached.

        `seen` makes the budget unreachable by construction, so the `RuntimeError` branch
        was never executed by any test — a guard whose whole purpose is to fire when that
        construction breaks, with no evidence it fires. Raised in review.

        Simulated by making every `LOAD` target distinct and present, which is exactly what
        a broken `seen` would look like from the loop's side. The generator stops after 50
        targets rather than running forever: with the guard removed this must **fail**, not
        hang — a test that hangs reads as CI being broken rather than as this check failing,
        and it keeps allocating on a thread nobody is waiting on.
        """
        import itertools  # noqa: PLC0415

        class _EverythingIsInTheTree(dict):
            """`rel in files` always true, so no target is skipped as missing."""

            def __contains__(self, key: object) -> bool:
                return True

        counter = itertools.count()

        class _AlwaysANewTarget:
            @staticmethod
            def findall(_text: str) -> list:
                nth = next(counter)
                return [f"generated-{nth}.md"] if nth < 50 else []

        monkeypatch.setattr(gs, "LOAD_TARGET", _AlwaysANewTarget)
        # Built outside the block so only the call under test can raise inside it.
        files = _EverythingIsInTheTree({"a.md": ""})
        with pytest.raises(RuntimeError, match="cycle guard is not holding"):
            gs._closure("a.md", files)

    def test_a_sequence_does_not_run_past_its_section_into_the_next(
            self, tmp_path: Path) -> None:
        """`ON_ERROR`'s halt was being read as the preceding emit's wait.

        `_SECTIONS` was hand-written and missing six of the language's section headers, so
        `_ends_the_sequence` did not stop at `ON_ERROR:`. A `DO` block ending in an emit
        that never waits ran on into the recovery section and took *its* `STOP_TURN` as the
        emit's own — recording a stop no user was ever asked, in the direction that inflates
        the baseline this module exists to set. Raised in review as a Major.

        Derived: one emit, nothing after it in `DO`, so one non-stopping site and zero
        stops; `ON_ERROR`'s bare `STOP_TURN` is a halt, which is counted separately.
        """
        root = _tree(tmp_path, {
            "workflows/w.md": "UNIT W\nDO:\n  EMIT_MENU Trailing\nON_ERROR:\n  STOP_TURN\n",
        })
        surface = gs.walk(root)
        counted = surface.workflows[0]
        assert (counted.stop_sites, counted.non_stop_sites) == (0, 1), counted
        assert counted.halt_sites == 1, counted

    def test_the_section_vocabulary_is_the_validators_own(self) -> None:
        """Derived, not re-listed — the drift above is what a second copy produces."""
        from studio.utils.pdsl import SECTION_HEADERS  # noqa: PLC0415

        assert set(SECTION_HEADERS) <= gs._SECTIONS, sorted(set(SECTION_HEADERS) - gs._SECTIONS)
        # The two the validator keeps elsewhere, because they open blocks not sections.
        assert {"UNIT", "MENU"} <= gs._SECTIONS
