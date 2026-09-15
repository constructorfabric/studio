"""One policy decides which files a codebase entry covers.

`init` writes `codebase` entries and no `ignore` patterns, so in a fresh project
the only thing standing between a registered root and its vendored or generated
subdirectories is the default exclusion policy. That policy lived in
`utils/codebase.py` and was applied by one of the three consumers of a registry
entry: `list-ids`/`where-used` honoured it, while `validate` and `spec-coverage`
globbed the entry directly. The same entry therefore covered different files
depending on which command read it.

These tests pin the shared resolver so the three cannot drift apart again.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils.codebase import resolve_entry_code_files


def _tree(root: Path, files: list[str]) -> None:
    for rel in files:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")


def _names(files: list[Path], root: Path) -> list[str]:
    return sorted(f.relative_to(root).as_posix() for f in files)


class TestExcludedDirectoriesStayExcluded:
    def test_a_registered_parent_does_not_re_admit_vendored_code(self):
        """The case a bare rglob gets wrong.

        Registration refuses `vendor/` and `node_modules/`, but it registers the
        shallowest parent -- so scanning that parent recursively pulled the
        refused trees back in, and traceability then demanded markers in
        third-party code.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, [
                "src/main.py",
                "src/vendor/dependency.py",
                "src/node_modules/pkg/index.py",
                "src/dist/bundle.py",
                "src/__pycache__/main.py",
            ])

            files, excluded = resolve_entry_code_files(
                root / "src", [".py"], project_root=root
            )

        assert _names(files, root) == ["src/main.py"]
        assert excluded == 4, "the count is the denominator; a bare total hides the scope"

    def test_nothing_excluded_is_reported_as_nothing_excluded(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/a.py", "src/pkg/b.py"])

            files, excluded = resolve_entry_code_files(
                root / "src", [".py"], project_root=root
            )

        assert _names(files, root) == ["src/a.py", "src/pkg/b.py"]
        assert excluded == 0


class TestNothingOutsideTheProjectIsScanned:
    def test_a_symlinked_source_file_is_refused(self):
        with TemporaryDirectory() as outside_dir, TemporaryDirectory() as tmpdir:
            outside = Path(outside_dir)
            _tree(outside, ["secret.py"])
            root = Path(tmpdir)
            _tree(root, ["src/main.py"])
            (root / "src" / "linked.py").symlink_to(outside / "secret.py")

            files, excluded = resolve_entry_code_files(
                root / "src", [".py"], project_root=root
            )

        assert _names(files, root) == ["src/main.py"]
        assert excluded == 1

    def test_a_symlinked_directory_does_not_bring_in_an_external_tree(self):
        """Pins the outcome, which is currently guaranteed twice over.

        `rglob`'s `**` does not descend into symlinked directories (verified on
        3.11), so the external file is never yielded and the containment check
        never sees it -- hence `excluded == 0` rather than 1. The check is kept
        as defence in depth: it covers the routes the traversal does yield, and
        it does not depend on that traversal behaviour staying the same across
        the Python versions this project supports.
        """
        with TemporaryDirectory() as outside_dir, TemporaryDirectory() as tmpdir:
            outside = Path(outside_dir)
            _tree(outside, ["secret.py"])
            root = Path(tmpdir)
            _tree(root, ["src/main.py"])
            (root / "src" / "linked").symlink_to(outside, target_is_directory=True)

            files, excluded = resolve_entry_code_files(
                root / "src", [".py"], project_root=root
            )

        assert _names(files, root) == ["src/main.py"]
        assert excluded == 0

    def test_a_symlink_pointing_back_inside_the_project_is_still_refused(self):
        """Containment is necessary but not sufficient: a link is still a duplicate.

        Following it would scan the same file twice under two names and count
        its lines twice in coverage.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/main.py"])
            (root / "src" / "alias.py").symlink_to(root / "src" / "main.py")

            files, excluded = resolve_entry_code_files(
                root / "src", [".py"], project_root=root
            )

        assert _names(files, root) == ["src/main.py"]
        assert excluded == 1


class TestTheResolverIsPredictable:
    def test_an_entry_naming_a_single_file_resolves_to_it(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/main.py"])

            files, excluded = resolve_entry_code_files(
                root / "src" / "main.py", [".py"], project_root=root
            )

        assert _names(files, root) == ["src/main.py"]
        assert excluded == 0

    def test_a_single_file_entry_outside_the_project_is_refused(self):
        """The rules apply to the single-file branch too.

        Returning the path unconditionally left this case enforced only by a
        pre-check on the query path, so an entry resolving outside the project
        was refused by `list-ids` and read by `validate` and `spec-coverage`.
        """
        with TemporaryDirectory() as outside_dir, TemporaryDirectory() as tmpdir:
            outside = Path(outside_dir)
            _tree(outside, ["secret.py"])
            root = Path(tmpdir)
            root.mkdir(exist_ok=True)

            files, excluded = resolve_entry_code_files(
                outside / "secret.py", [".py"], project_root=root
            )

        assert files == []
        assert excluded == 1

    def test_an_escaping_directory_entry_is_refused_without_being_walked(self):
        """The entry is judged before anything is read.

        Checking only the candidates meant an external tree was traversed
        first and every file in it counted separately toward a total that is
        supposed to describe this project. `rglob` is patched to fail so the
        test proves traversal never starts, not merely that the result is empty.
        """
        from unittest.mock import patch

        with TemporaryDirectory() as outside_dir, TemporaryDirectory() as tmpdir:
            outside = Path(outside_dir)
            _tree(outside, ["a.py", "nested/b.py"])
            root = Path(tmpdir)

            def refuse(self, pattern):
                raise AssertionError(f"traversal started on {self}")

            with patch.object(Path, "rglob", refuse):
                files, excluded = resolve_entry_code_files(
                    outside, [".py"], project_root=root
                )

        assert files == []
        assert excluded == 1, "the refused entry counts once, not once per file inside it"

    def test_a_missing_entry_resolves_to_nothing(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            assert resolve_entry_code_files(root / "gone", [".py"], project_root=root) == ([], 0)

    def test_overlapping_extensions_do_not_double_count(self):
        """Two globs matching one file must yield it once, and count it once.

        The file list was deduplicated and the excluded total was not, so the
        denominator disagreed with the list it describes.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/main.py", "src/vendor/dep.py"])

            once = resolve_entry_code_files(root / "src", [".py"], project_root=root)
            twice = resolve_entry_code_files(root / "src", [".py", ".py"], project_root=root)

        assert _names(once[0], root) == ["src/main.py"]
        assert once == twice, "repeating an extension must change neither list nor count"
        assert twice[1] == 1, "one excluded file counted once"

    def test_repeated_runs_agree_exactly(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/a.py", "src/b.py", "src/pkg/c.py", "src/vendor/d.py"])

            results = {
                repr(resolve_entry_code_files(root / "src", [".py"], project_root=root))
                for _ in range(5)
            }

        assert len(results) == 1


class TestTheCommandsAgreeOnOneEntry:
    """The property this convergence exists to guarantee, asserted directly.

    The resolver's own tests pin its behaviour, but they cannot catch the two
    call sites drifting -- one passing different extensions or a different
    project root, or post-processing the result differently. This drives both
    call sites over one fixture and compares the file sets.
    """

    def test_validate_and_spec_coverage_select_the_same_files(self):
        from unittest.mock import MagicMock

        from studio.commands.spec_coverage import _collect_codebase_files
        from studio.commands.validate import _resolve_code_scan_targets

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, [
                "src/main.py",
                "src/pkg/mod.py",
                "src/vendor/dependency.py",
                "src/node_modules/pkg/index.py",
                "src/dist/bundle.py",
            ])
            (root / "src" / "linked.py").symlink_to(root / "src" / "main.py")

            entry = MagicMock()
            entry.path = "src"
            entry.extensions = [".py"]
            entry.source = None

            session = MagicMock()
            session.project_root = root
            session.ws_ctx = None
            session.code_files_excluded = 0
            validate_files = {p.resolve() for p in _resolve_code_scan_targets(session, entry)}

            node = MagicMock()
            node.codebase = [entry]
            node.children = []
            collected: list = []
            _collect_codebase_files(node, root, collected)
            coverage_files = {p.resolve() for p in collected}

        assert validate_files == coverage_files, (
            "the two commands must select the same files for one registry entry"
        )
        assert {p.name for p in validate_files} == {"main.py", "mod.py"}, (
            "and the shared policy must actually be in force in both"
        )

    def test_validate_and_spec_coverage_agree_on_a_single_file_entry(self):
        """A file entry has to go through the resolver in both commands.

        `validate` used to return the path before ever calling the resolver, so
        a file entry was the one shape where the two commands could still
        disagree -- and an external file was read by one and refused by the
        other.
        """
        from unittest.mock import MagicMock

        from studio.commands.spec_coverage import _collect_codebase_files
        from studio.commands.validate import _resolve_code_scan_targets

        with TemporaryDirectory() as outside_dir, TemporaryDirectory() as tmpdir:
            outside = Path(outside_dir)
            _tree(outside, ["secret.py"])
            root = Path(tmpdir)
            _tree(root, ["src/main.py"])

            for label, rel in (("inside", "src/main.py"), ("outside", os.path.relpath(outside / "secret.py", root))):
                entry = MagicMock()
                entry.path = rel
                entry.extensions = [".py"]
                entry.source = None

                session = MagicMock()
                session.project_root = root
                session.ws_ctx = None
                session.code_files_excluded = 0
                validate_files = {p.resolve() for p in _resolve_code_scan_targets(session, entry)}

                node = MagicMock()
                node.codebase = [entry]
                node.children = []
                collected: list = []
                _collect_codebase_files(node, root, collected)
                coverage_files = {p.resolve() for p in collected}

                assert validate_files == coverage_files, f"{label} file entry: commands disagree"
                if label == "outside":
                    assert validate_files == set(), "an external file entry must be refused"
                else:
                    assert {p.name for p in validate_files} == {"main.py"}
