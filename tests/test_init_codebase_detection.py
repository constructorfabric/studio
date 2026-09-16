"""`init` registers the source roots it finds, or says it found none.

A registry with `codebase = []` scans nothing, so every traceability gate
downstream has an empty population to measure and reports success without having
assessed anything. Detection is what stops that state being created; saying so
plainly is what stops it being created silently.

The tests exercise the detector directly and the registry write through
`_finalize_init_files` in dry-run mode. A full `init` run downloads the default
kit from GitHub, so driving it here would make these tests network-dependent --
the existing init e2e tests already fail as a group whenever that download times
out, and correctness of detection has nothing to do with it.
"""

from __future__ import annotations

import errno
import io
import logging
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.init import (
    _CODEBASE_MAX_DEPTH,
    _CODEBASE_REGISTERED_SENTINELS,
    _CodebaseScanFailed,
    _detect_codebase_roots,
    _finalize_init_files,
    _human_init_ok,
)
from studio.utils import toml_utils
from studio.utils._tomllib_compat import tomllib
from studio.utils.artifacts_meta import generate_default_registry


def _tree(root: Path, files: list[str]) -> None:
    """Create every path in *files* relative to *root*, with source-ish content."""
    for rel in files:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")


def _paths(roots: list[dict]) -> list[str]:
    return [str(entry["path"]) for entry in roots]


# ---------------------------------------------------------------------------
# What gets detected
# ---------------------------------------------------------------------------

class TestEveryRootIsRegisteredNotJustTheFirst:
    def test_two_roots_are_both_found(self):
        """The case a single-root rule gets wrong.

        This repository's own layout: a package under `src/` and a CLI nested
        several levels down. A rule that stopped at the first hit would leave
        one of them unscanned while the registry looked populated.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/pkg/__init__.py", "web/app/main.ts"])

            assert _paths(_detect_codebase_roots(root)) == ["src/pkg", "web/app"]

    def test_only_the_extensions_present_are_recorded(self):
        """An entry should state what it covers, not a generic guess."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["api/svc.py", "ui/a.ts", "ui/b.tsx", "ui/c.py"])

            by_path = {str(e["path"]): e["extensions"] for e in _detect_codebase_roots(root)}

        assert by_path["api"] == [".py"]
        assert by_path["ui"] == [".py", ".ts", ".tsx"]

    def test_a_sql_only_project_is_registered(self):
        """`validate` globs a codebase entry's own extensions, so an omission here is silence.

        A registered entry decides what gets scanned. SQL carries markers like
        any other source of record, so leaving `.sql` out would hand a SQL-only
        project the empty registry this whole change exists to prevent.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["db/schema.sql", "db/migrate.sql"])

            roots = _detect_codebase_roots(root)

        assert _paths(roots) == ["db"]
        assert roots[0]["extensions"] == [".sql"]

    def test_the_shallowest_directory_wins(self):
        """One entry per tree: nested subpackages are covered by their parent."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/a.py", "src/deep/b.py", "src/deep/deeper/c.py"])

            assert _paths(_detect_codebase_roots(root)) == ["src"]

    def test_the_project_root_is_never_a_root(self):
        """One stray script must not claim the whole repository.

        A `setup.py` or lint-config file beside the tree would otherwise register
        `.`, pulling every excluded directory back into scope.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["setup.py", "src/pkg/mod.py"])

            assert _paths(_detect_codebase_roots(root)) == ["src/pkg"]


class TestWhatIsDeliberatelySkipped:
    def test_top_level_non_product_directories_are_skipped(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, [
                "tests/test_a.py", "docs/conf.py", "examples/demo.py",
                "scripts/build.py", "src/pkg/mod.py",
            ])

            assert _paths(_detect_codebase_roots(root)) == ["src/pkg"]

    def test_the_same_names_nested_inside_a_package_are_kept(self):
        """`skills/studio/scripts` is product code; a top-level `scripts/` is not.

        The skip list is applied at the top level only, which is what lets this
        repository's own CLI root be found.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["skills/studio/scripts/cli.py"])

            assert _paths(_detect_codebase_roots(root)) == ["skills/studio/scripts"]

    def test_build_output_and_dependencies_are_skipped_at_any_depth(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, [
                "node_modules/dep/index.js", "src/dist/bundle.js",
                "src/vendor/lib.py", "src/__pycache__/mod.py", "src/pkg/mod.py",
            ])

            assert _paths(_detect_codebase_roots(root)) == ["src/pkg"]

    def test_hidden_directories_are_skipped(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, [".venv/lib/mod.py", ".github/scripts/ci.py", "src/mod.py"])

            assert _paths(_detect_codebase_roots(root)) == ["src"]

    def test_non_source_files_do_not_make_a_root(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["assets/logo.svg", "notes/todo.md", "conf/app.yaml"])

            assert _detect_codebase_roots(root) == []


# ---------------------------------------------------------------------------
# Fail-safe, privacy, determinism, bounds
# ---------------------------------------------------------------------------

def _raise_on(attr: str, target_name: str, err: int):
    """Patch `Path.<attr>` so it raises OSError(err) for one path name."""
    original = getattr(Path, attr)

    def fake(self, *args, **kwargs):
        if self.name == target_name:
            raise OSError(err, os.strerror(err))
        return original(self, *args, **kwargs)

    return patch.object(Path, attr, fake)


class TestFilesystemErrorsAreClassified:
    """Only expected access failures may register less; the rest must not pass.

    These use mocks rather than `chmod`, so they run as root, in containers and
    on Windows -- where the permission-based tests cannot.
    """

    def test_permission_denied_registers_less_and_says_so(self, caplog):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["locked/secret.py", "src/mod.py"])
            with _raise_on("iterdir", "locked", errno.EACCES):
                with caplog.at_level(logging.DEBUG, logger="studio.commands.init"):
                    roots = _detect_codebase_roots(root)

        assert _paths(roots) == ["src"]
        skips = [r for r in caplog.records if "unreadable directory" in r.getMessage()]
        assert skips, "the omitted subtree must be reported"
        for record in skips:
            assert record.levelno >= logging.WARNING, "below the CLI's own threshold"
            assert tmpdir not in record.getMessage()
            assert str(Path.home()) not in record.getMessage()

    @pytest.mark.parametrize("err", [errno.EIO, errno.EMFILE, errno.ESTALE])
    def test_a_systemic_error_is_not_reported_as_an_absent_source_tree(self, err):
        """Registering less because of an I/O failure is a false success."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/mod.py"])
            with _raise_on("iterdir", "src", err):
                with pytest.raises(_CodebaseScanFailed) as caught:
                    _detect_codebase_roots(root)

        assert caught.value.errno_name == errno.errorcode[err]
        assert tmpdir not in str(caught.value), "the label must stay project-relative"

    @pytest.mark.parametrize("err", [errno.EIO, errno.ESTALE])
    def test_a_file_metadata_failure_is_not_silently_a_non_source_file(self, err):
        """`is_file()` turns a metadata error into False; that hides source."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/mod.py"])
            with _raise_on("lstat", "mod.py", err):
                with pytest.raises(_CodebaseScanFailed):
                    _detect_codebase_roots(root)

    def test_a_denied_file_probe_is_skipped_not_escalated(self, caplog):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/mod.py", "src/other.py"])
            with _raise_on("lstat", "mod.py", errno.EACCES):
                with caplog.at_level(logging.DEBUG, logger="studio.commands.init"):
                    roots = _detect_codebase_roots(root)

        assert _paths(roots) == ["src"]
        assert any("unreadable file" in r.getMessage() for r in caplog.records)

    def test_a_directory_replaced_by_a_symlink_is_refused(self, caplog):
        """The queue-time check cannot bind a mutable path; re-check before listing."""
        with TemporaryDirectory() as outside_dir, TemporaryDirectory() as tmpdir:
            outside = Path(outside_dir)
            _tree(outside, ["secret.py"])
            root = Path(tmpdir)
            _tree(root, ["src/mod.py", "swapped/placeholder.py"])
            # Stand in for the race: the path is a directory when queued and a
            # symlink by the time it is listed.
            swapped = root / "swapped"
            for child in swapped.iterdir():
                child.unlink()
            swapped.rmdir()
            swapped.symlink_to(outside, target_is_directory=True)

            with caplog.at_level(logging.DEBUG, logger="studio.commands.init"):
                roots = _detect_codebase_roots(root)

        assert _paths(roots) == ["src"], "an external tree must not be registered"


class TestTheEntryStatesWhatItCovers:
    def test_extensions_nested_under_a_root_are_recorded(self):
        """The entry names a directory and validation walks it recursively.

        Recording only the top level under-claims: `src` would register `.py`
        alone and leave `src/web/app.ts` unscanned while the registry looked
        complete.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/main.py", "src/web/app.ts"])

            roots = _detect_codebase_roots(root)

        assert _paths(roots) == ["src"]
        assert roots[0]["extensions"] == [".py", ".ts"]

    def test_nested_extensions_still_honour_the_skip_policy(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/main.py", "src/node_modules/dep.ts"])

            roots = _detect_codebase_roots(root)

        assert roots[0]["extensions"] == [".py"], "a skipped directory must not add extensions"

    def test_the_suffix_is_recorded_in_the_case_it_has_on_disk(self):
        """Downstream globbing is case-sensitive where the filesystem is.

        Normalising `main.PY` to `.py` registered an entry that resolves to no
        file at all on a case-sensitive filesystem.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/main.PY"])

            roots = _detect_codebase_roots(root)

        assert roots[0]["extensions"] == [".PY"]


class TestDetectionIsSafeToRun:
    def test_an_unreadable_directory_is_skipped_not_raised(self):
        """Registering less is the right answer; failing init is not."""
        if os.name == "nt" or os.geteuid() == 0:
            # A silent `return` here reports as a pass, so the assertions below
            # would be quietly absent from root/container CI and from Windows.
            # The mocked cases in TestFilesystemErrorsAreClassified cover the
            # same behaviour independently of effective user identity.
            pytest.skip("chmod does not restrict listing for root or on Windows")
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["locked/secret.py", "src/mod.py"])
            (root / "locked").chmod(0o000)
            try:
                roots = _detect_codebase_roots(root)
            finally:
                (root / "locked").chmod(0o755)

        assert _paths(roots) == ["src"]

    def test_the_skip_reaches_normal_cli_output_without_the_absolute_path(self, caplog):
        """Visible at the CLI's own threshold, and carrying no machine.

        `cli.py` configures the `studio` logger at WARNING, so an INFO record
        would report the omitted subtree to nobody -- silent under-registration
        is the failure detection exists to prevent. The record must therefore
        clear that threshold while still naming a relative path only.
        """
        if os.name == "nt" or os.geteuid() == 0:
            # A silent `return` here reports as a pass, so the assertions below
            # would be quietly absent from root/container CI and from Windows.
            # The mocked cases in TestFilesystemErrorsAreClassified cover the
            # same behaviour independently of effective user identity.
            pytest.skip("chmod does not restrict listing for root or on Windows")
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["locked/secret.py", "src/mod.py"])
            (root / "locked").chmod(0o000)
            try:
                with caplog.at_level(logging.DEBUG, logger="studio.commands.init"):
                    _detect_codebase_roots(root)
            finally:
                (root / "locked").chmod(0o755)

        skips = [r for r in caplog.records if "unreadable directory" in r.getMessage()]
        assert skips, "an unreadable directory must be reported, not passed over"
        for record in skips:
            assert record.levelno >= logging.WARNING, (
                "below the CLI's configured level, so no user would see it"
            )
            text = record.getMessage() + (record.exc_text or "")
            assert tmpdir not in text
            assert str(Path.home()) not in text
            assert record.exc_info is None, "a traceback repeats the absolute path"

    def test_the_studio_install_tree_is_never_a_source_root(self):
        """Studio's own files are not the project's product code.

        The default install dir is hidden, so the hidden-directory rule covers
        it, but `--install-dir` accepts a visible name. The shipped SDLC kit
        carries `config/kits/sdlc/scripts/pr.py`, and `scripts` is only refused
        at the top level -- nested five deep it is not, so the installation
        would register itself and later gates would demand markers in files
        Studio manages.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["adapter/config/kits/sdlc/scripts/run.py", "src/mod.py"])

            roots = _detect_codebase_roots(root, studio_dir=root / "adapter")

        assert _paths(roots) == ["src"]

    def test_symlinks_are_not_followed(self):
        """A self-referential link must not turn the walk into a loop."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/mod.py"])
            (root / "loop").symlink_to(root, target_is_directory=True)

            assert _paths(_detect_codebase_roots(root)) == ["src"]

    def test_a_symlinked_source_file_does_not_make_a_root(self):
        """`is_file()` follows links, so a link would register a directory that owns no code.

        The directory policy already refuses symlinked directories; the file
        filter has to agree, or a single link re-opens the tree it excludes.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/mod.py"])
            (root / "linked").mkdir()
            (root / "linked" / "mod.py").symlink_to(root / "src" / "mod.py")

            assert _paths(_detect_codebase_roots(root)) == ["src"]

    def test_the_walk_is_depth_bounded(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            deep = "/".join(f"d{i}" for i in range(_CODEBASE_MAX_DEPTH + 3))
            _tree(root, [f"{deep}/mod.py"])

            assert _detect_codebase_roots(root) == []

    def test_no_absolute_path_reaches_the_result(self):
        """Registry contents get committed, so they must not carry the machine."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/pkg/mod.py"])

            roots = _detect_codebase_roots(root)

        for entry in roots:
            path = str(entry["path"])
            assert not Path(path).is_absolute()
            assert tmpdir not in path
            assert str(Path.home()) not in path

    def test_repeated_runs_agree_exactly(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/a.py", "web/b.ts", "svc/c.go", "lib/d.rs"])

            results = {repr(_detect_codebase_roots(root)) for _ in range(5)}

        assert len(results) == 1


# ---------------------------------------------------------------------------
# What lands in the registry
# ---------------------------------------------------------------------------

class TestTheRegistryIsWellFormed:
    def test_detected_roots_round_trip_through_toml(self):
        registry = generate_default_registry(
            "Demo", kit_slug="sdlc",
            codebase=[{"path": "src/pkg", "extensions": [".py"]}],
        )
        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "artifacts.toml"
            toml_utils.dump(registry, target, header_comment="test")
            text = target.read_text(encoding="utf-8")
            parsed = tomllib.loads(text)

        assert parsed["systems"][0]["codebase"] == [
            {"path": "src/pkg", "extensions": [".py"]}
        ]
        # The two spellings must never appear together: a `codebase = []` key
        # beside [[systems.codebase]] blocks makes the file unparseable.
        assert "[[systems.codebase]]" in text
        assert "codebase = []" not in text

    def test_no_detected_roots_leaves_the_empty_list_form(self):
        registry = generate_default_registry("Demo", kit_slug="sdlc", codebase=[])
        with TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "artifacts.toml"
            toml_utils.dump(registry, target, header_comment="test")
            text = target.read_text(encoding="utf-8")
            tomllib.loads(text)

        assert "codebase = []" in text
        assert "[[systems.codebase]]" not in text

    def test_the_default_stays_empty_when_no_roots_are_passed(self):
        """Callers that cannot detect keep the previous behaviour."""
        registry = generate_default_registry("Demo")

        assert registry["systems"][0]["codebase"] == []


# ---------------------------------------------------------------------------
# The write itself: idempotence and the warning
# ---------------------------------------------------------------------------

def _finalize(root: Path, *, force: bool = False) -> tuple[dict, str]:
    """Run the registry-writing step in dry-run mode, returning (actions, stdout)."""
    from studio.utils.ui import is_json_mode, set_json_mode

    config_dir = root / "adapter" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    args = MagicMock()
    args.dry_run = True
    args.force = force
    layout = MagicMock()
    layout.config_dir = config_dir
    layout.studio_dir = root / "adapter"
    state = MagicMock()
    state.project_root = root
    state.project_name = "Demo"
    actions: dict = {}

    saved = is_json_mode()
    out = io.StringIO()
    try:
        set_json_mode(False)
        with redirect_stdout(out):
            _finalize_init_files(
                args=args, layout=layout, state=state,
                kit_results={"sdlc": {}}, actions=actions,
            )
    finally:
        set_json_mode(saved)
    return actions, out.getvalue()


def _render_human(actions: dict, *, dry_run: bool = False) -> str:
    """Render the human success output for *actions*, returning stdout."""
    from studio.utils.ui import is_json_mode, set_json_mode

    saved = is_json_mode()
    out = io.StringIO()
    try:
        set_json_mode(False)
        with redirect_stdout(out):
            _human_init_ok(
                {"dry_run": dry_run, "actions": actions},
                Path("/does/not/matter"),
                Path("/does/not/matter/adapter"),
                "adapter",
                "Demo",
                {},
            )
    finally:
        set_json_mode(saved)
    return out.getvalue()


class TestTheWriteSaysWhatItDid:
    def test_detected_roots_are_named_in_the_actions(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/pkg/mod.py", "web/app/main.ts"])

            actions, out = _finalize(root)

        assert actions["artifacts_registry"] == "created"
        assert actions["codebase_registered"] == "src/pkg, web/app"
        assert "No source directories were detected" not in out

    def test_finding_nothing_warns_explicitly_rather_than_passing_quietly(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["README.md"])

            actions, out = _finalize(root)

        assert actions["codebase_registered"] == "none"
        assert "No source directories were detected" in out
        assert "[[systems.codebase]]" in out

    def test_the_warning_leaks_no_absolute_path(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["README.md"])

            _, out = _finalize(root)

        assert tmpdir not in out
        assert str(Path.home()) not in out
        assert "adapter/config/artifacts.toml" in out

    def test_human_output_names_every_registered_root(self):
        """A root reported only in the payload is a root the user cannot check.

        Covers the dry-run path too: a dry run is exactly when someone wants to
        see what detection *would* register before it writes anything.
        """
        registered = {"codebase_registered": "skills/studio/scripts, src/studio_proxy"}
        for dry_run in (False, True):
            output = _render_human(registered, dry_run=dry_run)
            assert "skills/studio/scripts" in output, f"dry_run={dry_run}"
            assert "src/studio_proxy" in output, f"dry_run={dry_run}"

    @pytest.mark.parametrize("outcome", sorted(_CODEBASE_REGISTERED_SENTINELS))
    def test_human_output_names_no_root_when_none_was_registered(self, outcome):
        """These outcomes already warn; naming one as a root contradicts the warning.

        Parametrised over the sentinel set rather than spelled out, so a new
        outcome that registers nothing is covered the moment it is added.
        """
        assert "Codebase roots registered" not in _render_human({"codebase_registered": outcome})

    def test_an_existing_registry_is_never_rewritten(self):
        """Idempotence: a second run must not touch the user's registration.

        This is also the known-good case -- an already-correct project produces
        no detection work and no new output at all.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/pkg/mod.py"])
            config = root / "adapter" / "config"
            config.mkdir(parents=True)
            original = '[[systems]]\nname = "Mine"\nslug = "mine"\nkit = "sdlc"\n'
            (config / "artifacts.toml").write_text(original, encoding="utf-8")

            actions, out = _finalize(root)

            assert (config / "artifacts.toml").read_text(encoding="utf-8") == original

        assert actions["artifacts_registry"] == "unchanged"
        assert "codebase_registered" not in actions
        assert out == ""

    def test_force_re_detects_over_an_existing_registry(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _tree(root, ["src/pkg/mod.py"])
            config = root / "adapter" / "config"
            config.mkdir(parents=True)
            (config / "artifacts.toml").write_text("[[systems]]\n", encoding="utf-8")

            actions, _ = _finalize(root, force=True)

        assert actions["artifacts_registry"] == "updated"
        assert actions["codebase_registered"] == "src/pkg"
