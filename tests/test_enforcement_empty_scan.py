"""Enforcement reachability: an empty scan must not read as compliance.

Each test names the repository state it builds and the verdict that state
produces. The corpus separates two questions that a single ``status`` field
currently conflates:

* **"did anything fail?"** -> ``status``. An empty scope fails nothing: the
  check ran and correctly found nothing to cover, so ``PASS`` is honest.
* **"was there anything to assess?"** -> a separate boolean. This is what the
  report cannot currently express, so a legitimately empty repository and a
  misconfigured one that scans nothing are indistinguishable.

The exit code is a third, independent question: it should turn non-zero only
when the caller demanded a guarantee that cannot be given -- thresholds were
passed, or a checked ``to_code="true"`` ID exists with nothing backing it.

Most tests here pin behaviour that was already correct, so they are ordinary
regression cover against a change to either command being too broad. The last
class covers the three cases this change fixes.
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.spec_coverage import cmd_spec_coverage
from studio.utils.artifacts_meta import ArtifactsMeta, CodebaseEntry, Kit, SystemNode
from studio.utils.codebase import CodeFile, cross_validate_code
from studio.utils.ui import set_json_mode

TO_CODE_IDS = {
    "cpt-flags-flow-evaluate",
    "cpt-flags-algo-core-bucket",
    "cpt-flags-dod-core-verification",
}


def _context(project_root: Path, codebase: list[CodebaseEntry] | None = None) -> MagicMock:
    """Build a context whose single system registers ``codebase``."""
    meta = ArtifactsMeta(
        version=1,
        project_root=".",
        kits={"test": Kit("test", "CFS", "kits/test")},
        systems=[
            SystemNode(
                name="sys1",
                slug="sys1",
                kit="test",
                artifacts=[],
                codebase=codebase or [],
                children=[],
            ),
        ],
    )
    ctx = MagicMock()
    ctx.meta = meta
    ctx.project_root = project_root
    return ctx


def _nested_context(project_root: Path, child_codebase: list[CodebaseEntry]) -> MagicMock:
    """Build a context where a *child* system holds the only codebase entry.

    File collection recurses into children, so a parent match scans its
    descendants' entries too. Anything that reports the registered-entry count
    has to walk the same subtree or it contradicts the scan it describes.
    """
    child = SystemNode(
        name="sub1",
        slug="sub1",
        kit="test",
        artifacts=[],
        codebase=child_codebase,
        children=[],
    )
    meta = ArtifactsMeta(
        version=1,
        project_root=".",
        kits={"test": Kit("test", "CFS", "kits/test")},
        systems=[
            SystemNode(
                name="sys1",
                slug="sys1",
                kit="test",
                artifacts=[],
                codebase=[],
                children=[child],
            ),
        ],
    )
    ctx = MagicMock()
    ctx.meta = meta
    ctx.project_root = project_root
    return ctx


def _run_spec_coverage(ctx: MagicMock, argv: list[str] | None = None) -> tuple[int, dict]:
    """Run spec-coverage against ``ctx`` and return (exit code, parsed report)."""
    with patch("studio.utils.context.get_context", return_value=ctx):
        with patch("sys.stdout", new_callable=StringIO) as out:
            code = cmd_spec_coverage(argv or [])
    return code, json.loads(out.getvalue())


# ---------------------------------------------------------------------------
# The enforcement already exists -- it is only unreachable.
#
# These pass today. They are the evidence that closing the gap is a guard
# change and not new validation logic, so they must keep passing afterwards.
# ---------------------------------------------------------------------------

class TestEnforcementExistsOnEmptyInput:
    def test_every_unmet_to_code_id_is_reported_when_no_code_files_exist(self):
        result = cross_validate_code([], set(TO_CODE_IDS), set(TO_CODE_IDS), traceability="FULL")

        coverage_errors = [e for e in result["errors"] if e["type"] == "coverage"]
        assert len(coverage_errors) == len(TO_CODE_IDS)
        assert {e["id"] for e in coverage_errors} == TO_CODE_IDS

    def test_nothing_claimed_means_nothing_owed(self):
        """No checked to_code IDs and no code is a legitimately clean state.

        This is the leniency the design deliberately keeps: a spec-first
        repository with a PRD and an ADR but no implementation yet must not be
        failed. It is also the assertion most at risk from an over-broad fix.
        """
        result = cross_validate_code([], set(), set(), traceability="FULL")

        assert result["errors"] == []
        assert result["warnings"] == []

    def test_docs_only_traceability_is_unaffected(self, tmp_path: Path):
        result = cross_validate_code([], set(), set(), traceability="DOCS-ONLY")

        assert result["errors"] == []


class TestKnownGoodStaysGreen:
    """Regression pins. A fix that breaks one of these is too broad."""

    def test_a_marked_implementation_reports_no_coverage_error(self, tmp_path: Path):
        source = tmp_path / "evaluator.py"
        source.write_text(
            "# @cpt-algo:cpt-flags-algo-core-bucket:p1\ndef bucket():\n    return 0\n",
            encoding="utf-8",
        )
        code_file, _ = CodeFile.from_path(source)

        result = cross_validate_code(
            [code_file],
            {"cpt-flags-algo-core-bucket"},
            {"cpt-flags-algo-core-bucket"},
            traceability="FULL",
        )

        assert [e for e in result["errors"] if e["type"] == "coverage"] == []

    def test_an_unmarked_file_still_fails(self, tmp_path: Path):
        """Already-correct behaviour: one scanned file makes enforcement fire."""
        source = tmp_path / "store.py"
        source.write_text("def put():\n    return None\n", encoding="utf-8")
        code_file, _ = CodeFile.from_path(source)

        result = cross_validate_code(
            [code_file],
            {"cpt-flags-algo-core-bucket"},
            {"cpt-flags-algo-core-bucket"},
            traceability="FULL",
        )

        coverage_errors = [e for e in result["errors"] if e["type"] == "coverage"]
        assert len(coverage_errors) == 1
        assert coverage_errors[0]["id"] == "cpt-flags-algo-core-bucket"

    def test_populated_codebase_reports_normally(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            src = root / "src"
            src.mkdir()
            (src / "main.py").write_text(
                "# @cpt-algo:cpt-flags-algo-core-bucket:p1\nx = 1\n", encoding="utf-8"
            )
            ctx = _context(root, [CodebaseEntry(path="src", extensions=[".py"])])

            code, report = _run_spec_coverage(ctx)

        assert code == 0
        assert report["summary"]["total_files"] > 0

    def test_an_unassessable_report_without_thresholds_still_exits_zero(self):
        """No guarantee was requested, so the exit code must not move.

        ``status`` stays PASS too -- nothing failed. Only the applicability flag
        below is missing. Keeping this exit code is what lets the change land
        without failing spec-first projects.
        """
        with TemporaryDirectory() as directory:
            ctx = _context(Path(directory), codebase=[])

            code, _ = _run_spec_coverage(ctx)

        assert code == 0


class TestVerdictIsDeterministic:
    def test_repeated_runs_agree(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            src = root / "src"
            src.mkdir()
            (src / "main.py").write_text(
                "# @cpt-algo:cpt-flags-algo-core-bucket:p1\nx = 1\n", encoding="utf-8"
            )
            verdicts = set()
            for _ in range(5):
                ctx = _context(root, [CodebaseEntry(path="src", extensions=[".py"])])
                code, report = _run_spec_coverage(ctx)
                verdicts.add((code, report["status"], report["summary"]["total_files"]))

        assert len(verdicts) == 1


# ---------------------------------------------------------------------------
# Known-bad must go red. These fail today; that is the defect.
# ---------------------------------------------------------------------------

class TestEmptyScopeIsVisibleAndGuaranteesAreHonoured:
    """An empty scope is honest-green -- but it must be *visible*, and a
    demanded guarantee must still be honoured."""

    def test_an_empty_scan_is_flagged_as_not_applicable(self):
        """``status`` stays PASS -- nothing failed -- but that is not the whole answer.

        The check ran and found nothing to cover, so PASS is honest. What the
        report cannot currently say is that there was nothing to assess in the
        first place. Field name is provisional pending discussion.
        """
        with TemporaryDirectory() as directory:
            ctx = _context(Path(directory), codebase=[])

            _, report = _run_spec_coverage(ctx)

        assert report["status"] == "PASS"
        assert report.get("applicable") is False

    def test_requested_thresholds_cannot_be_satisfied_by_an_empty_scan(self):
        """0.0% against a required 90 is the maximum possible miss, not a pass.

        All four flags are exercised, and the failure text is asserted rather
        than just the exit code -- a per-flag regression in the message would
        otherwise pass unnoticed.
        """
        for flag, value in (
            ("--min-coverage", "90"),
            ("--min-file-coverage", "60"),
            ("--min-granularity", "0.46"),
            ("--min-file-granularity", "0.3"),
        ):
            with TemporaryDirectory() as directory:
                ctx = _context(Path(directory), codebase=[])

                code, report = _run_spec_coverage(ctx, [flag, value])

            assert code == 2, flag
            assert report["status"] == "FAIL", flag
            assert report["applicable"] is False, flag
            assert report["threshold_failures"] == [
                f"cannot assess {flag}: 0 files from 0 registered codebase entries"
            ], flag

    def test_every_demanded_threshold_is_reported_not_just_the_first(self):
        """One invocation demanding all four must answer for all four.

        The per-flag cases above would all still pass if the report emitted a
        single entry and dropped the rest, so this pins one failure per
        requested flag against a short-circuit or overwrite.
        """
        flags = [
            "--min-coverage", "90",
            "--min-file-coverage", "60",
            "--min-granularity", "0.46",
            "--min-file-granularity", "0.3",
        ]
        with TemporaryDirectory() as directory:
            ctx = _context(Path(directory), codebase=[])

            code, report = _run_spec_coverage(ctx, flags)

        assert code == 2
        assert report["status"] == "FAIL"
        assert report["applicable"] is False
        assert report["threshold_failures"] == [
            f"cannot assess {flag}: 0 files from 0 registered codebase entries"
            for flag in flags[::2]
        ]

    def test_a_threshold_no_scope_can_miss_is_not_a_demanded_guarantee(self):
        """A non-positive floor is met by any scope, so it must not fail one.

        A populated repository sitting at 0.0% coverage passes
        ``--min-coverage 0``; an empty one has to agree, or the flag means two
        different things depending on what happens to be registered.
        """
        for flag in (
            "--min-coverage",
            "--min-file-coverage",
            "--min-granularity",
            "--min-file-granularity",
        ):
            for value in ("0", "-5"):
                with TemporaryDirectory() as directory:
                    ctx = _context(Path(directory), codebase=[])

                    code, report = _run_spec_coverage(ctx, [flag, value])

                assert code == 0, (flag, value)
                assert report["status"] == "PASS", (flag, value)
                assert "threshold_failures" not in report, (flag, value)

    def test_unregistered_and_resolved_to_nothing_are_distinguishable(self):
        """Two different setup mistakes must not produce the same report.

        No registered entry is a missing-configuration problem; an entry that
        resolves to zero files is a wrong-path problem. A report that cannot
        tell them apart cannot state its own denominator.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, unregistered = _run_spec_coverage(_context(root, codebase=[]))
            _, resolved_to_nothing = _run_spec_coverage(
                _context(root, [CodebaseEntry(path="does/not/exist", extensions=[".py"])])
            )

        assert unregistered != resolved_to_nothing

    def test_a_child_systems_entry_counts_towards_the_denominator(self):
        """The count must cover the subtree the scan itself walks.

        ``_collect_codebase_files`` recurses into a matched node's children, so
        a parent match scans its descendants' entries. A count that stops at
        the matched node calls a repository unregistered when it registered
        something and got zero files back -- reintroducing, one level down, the
        exact confusion this change removes.
        """
        with TemporaryDirectory() as directory:
            ctx = _nested_context(
                Path(directory), [CodebaseEntry(path="does/not/exist", extensions=[".py"])]
            )

            _, report = _run_spec_coverage(ctx)

        assert report["message"] == (
            "No code files found: 1 registered codebase entry resolved to 0 files"
        )

    def test_selecting_the_parent_counts_the_childs_entry(self):
        """Same rule under an explicit ``--system`` selector on the parent."""
        with TemporaryDirectory() as directory:
            ctx = _nested_context(
                Path(directory), [CodebaseEntry(path="does/not/exist", extensions=[".py"])]
            )

            _, report = _run_spec_coverage(ctx, ["--system", "sys1"])

        assert "1 registered codebase entry" in report["message"]


class TestTheHumanSurfaceSaysTheSameThing:
    """The report is only honest if the default output surface says so too.

    The suite runs in JSON mode by default (``conftest.py``), so without an
    explicit opt-out every assertion above could hold while a developer running
    ``cfs spec-coverage`` still read ``All thresholds met`` off an empty scope.
    """

    @staticmethod
    def _run_human(ctx, argv=None) -> tuple[int, str]:
        set_json_mode(False)
        try:
            with patch("studio.utils.context.get_context", return_value=ctx):
                with patch("sys.stdout", new_callable=StringIO) as out:
                    code = cmd_spec_coverage(argv or [])
            return code, out.getvalue()
        finally:
            set_json_mode(True)

    def test_an_empty_scope_is_not_reported_as_all_thresholds_met(self):
        with TemporaryDirectory() as directory:
            code, out = self._run_human(_context(Path(directory), codebase=[]))

        assert code == 0
        assert "thresholds met" not in out
        assert "No codebase entries are registered" in out

    def test_the_two_empty_states_differ_on_the_human_surface_too(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, unregistered = self._run_human(_context(root, codebase=[]))
            _, resolved_to_nothing = self._run_human(
                _context(root, [CodebaseEntry(path="does/not/exist", extensions=[".py"])])
            )

        assert unregistered != resolved_to_nothing
        assert "resolved to 0 files" in resolved_to_nothing

    def test_a_populated_scope_still_reports_its_verdict(self):
        """Regression pin: the ordinary run must be untouched by all of this."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            src = root / "src"
            src.mkdir()
            (src / "main.py").write_text(
                "# @cpt-algo:cpt-flags-algo-core-bucket:p1\nx = 1\n", encoding="utf-8"
            )

            code, out = self._run_human(
                _context(root, [CodebaseEntry(path="src", extensions=[".py"])])
            )

        assert code == 0
        assert "All thresholds met." in out
