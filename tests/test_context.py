"""
Tests for StudioContext and related functions.

Tests cover:
- StudioContext methods: get_template, get_template_for_kind, get_known_id_kinds
- Global context functions: get_context, set_context, ensure_context
"""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils.context import (
    StudioContext,
    LoadedKit,
    get_context,
    set_context,
    ensure_context,
    _global_context,
)
from studio.utils.artifacts_meta import ArtifactsMeta, Kit
from studio.utils.constraints import ArtifactKindConstraints, IdConstraint, KitConstraints


def _make_mock_template(kind: str, blocks: list = None) -> MagicMock:
    """Create a mock Template with kind and blocks."""
    tmpl = MagicMock()
    tmpl.kind = kind
    tmpl.blocks = blocks or []
    return tmpl


def _make_mock_block(block_type: str, name: str) -> MagicMock:
    """Create a mock TemplateBlock."""
    block = MagicMock()
    block.type = block_type
    block.name = name
    return block


class TestStudioContextMethods:
    """Tests for StudioContext instance methods."""

    def _make_context(self) -> StudioContext:
        """Create a mock StudioContext with templates."""
        # Create mock templates
        prd_tmpl = _make_mock_template("PRD", [
            _make_mock_block("id", "fr"),
            _make_mock_block("id", "actor"),
        ])
        design_tmpl = _make_mock_template("DESIGN", [
            _make_mock_block("id", "component"),
            _make_mock_block("id", "seq"),
        ])
        spec_tmpl = _make_mock_template("SPEC", [
            _make_mock_block("id", "flow"),
            _make_mock_block("id", "algo"),
        ])

        # Create kits
        kit1 = Kit(kit_id="cypilot-sdlc", format="CFS", path="kits/sdlc")
        kit2 = Kit(kit_id="custom", format="CFS", path="kits/custom")

        loaded_kit1 = LoadedKit(
            kit=kit1,
            templates={"PRD": prd_tmpl, "DESIGN": design_tmpl},
            constraints=KitConstraints(by_kind={
                "PRD": ArtifactKindConstraints(name=None, description=None, defined_id=[
                    IdConstraint(kind="fr"),
                    IdConstraint(kind="actor"),
                ]),
                "DESIGN": ArtifactKindConstraints(name=None, description=None, defined_id=[
                    IdConstraint(kind="component"),
                    IdConstraint(kind="seq"),
                ]),
            }),
        )
        loaded_kit2 = LoadedKit(
            kit=kit2,
            templates={"SPEC": spec_tmpl},
            constraints=KitConstraints(by_kind={
                "SPEC": ArtifactKindConstraints(name=None, description=None, defined_id=[
                    IdConstraint(kind="flow"),
                    IdConstraint(kind="algo"),
                ]),
            }),
        )

        # Create mock meta
        meta = MagicMock(spec=ArtifactsMeta)
        meta.project_root = ".."

        return StudioContext(
            adapter_dir=Path("/fake/adapter"),
            project_root=Path("/fake/project"),
            meta=meta,
            kits={"cypilot-sdlc": loaded_kit1, "custom": loaded_kit2},
            registered_systems={"myapp", "test-system"},
            _errors=[{"type": "context", "message": "error1"}, {"type": "context", "message": "error2"}],
        )

    def test_get_known_id_kinds(self):
        """get_known_id_kinds extracts id kinds from template markers."""
        ctx = self._make_context()
        id_kinds = ctx.get_known_id_kinds()
        # PRD has fr, actor; DESIGN has component, seq; SPEC has flow, algo
        assert id_kinds == {"fr", "actor", "component", "seq", "flow", "algo"}


class TestGlobalContextFunctions:
    """Tests for global context getter/setter functions."""

    def teardown_method(self, method):
        """Reset global context after each test."""
        set_context(None)

    def test_get_context_initially_none(self):
        """get_context returns None when not set."""
        set_context(None)
        assert get_context() is None

    @patch("studio.utils.context.WorkspaceContext.load", return_value=None)
    def test_set_and_get_context(self, _mock_ws_load):
        """set_context stores context retrievable by get_context."""
        mock_ctx = MagicMock(spec=StudioContext)
        set_context(mock_ctx)
        # get_context() lazily attempts workspace upgrade on first call
        assert get_context() is mock_ctx

    def test_set_context_to_none(self):
        """set_context(None) clears the context."""
        mock_ctx = MagicMock(spec=StudioContext)
        set_context(mock_ctx)
        set_context(None)
        assert get_context() is None

    @patch("studio.utils.context.WorkspaceContext.load", return_value=None)
    @patch("studio.utils.context.StudioContext.load")
    def test_ensure_context_loads_when_none(self, mock_load, _mock_ws_load):
        """ensure_context loads context when global is None."""
        set_context(None)
        mock_ctx = MagicMock(spec=StudioContext)
        mock_load.return_value = mock_ctx

        result = ensure_context()

        mock_load.assert_called_once_with(None)
        assert result is mock_ctx
        assert get_context() is mock_ctx

    @patch("studio.utils.context.WorkspaceContext.load", return_value=None)
    @patch("studio.utils.context.StudioContext.load")
    def test_ensure_context_passes_start_path(self, mock_load, _mock_ws_load):
        """ensure_context passes start_path to StudioContext.load."""
        set_context(None)
        mock_ctx = MagicMock(spec=StudioContext)
        mock_load.return_value = mock_ctx
        start = Path("/some/path")

        result = ensure_context(start)

        mock_load.assert_called_once_with(start)

    def test_ensure_context_returns_existing(self):
        """ensure_context returns existing context without reloading."""
        existing_ctx = MagicMock(spec=StudioContext)
        set_context(existing_ctx)

        with patch("studio.utils.context.StudioContext.load") as mock_load:
            result = ensure_context()
            mock_load.assert_not_called()
            assert result is existing_ctx


class TestStudioContextLoad:
    """Tests for StudioContext.load() method."""

    def teardown_method(self, method):
        """Reset global context after each test."""
        set_context(None)

    def test_load_from_dir_uses_constraint_resources_by_kind_and_merges(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            adapter_dir = tmp / "adapter"
            config_dir = adapter_dir / "config"
            kit_dir = config_dir / "kits" / "custom"
            kit_dir.mkdir(parents=True)

            (config_dir / "artifacts.toml").write_text(
                'version = "1.1"\nproject_root = ".."\nsystems = []\n',
                encoding="utf-8",
            )
            (config_dir / "core.toml").write_text(
                """
version = "1.0"
project_root = ".."

[kits.custom]
format = "CFS"
path = "config/kits/custom"

[kits.custom.resources.alpha]
path = "config/kits/custom/base-rules.toml"
kind = "constraints"

[kits.custom.resources.beta]
path = "config/kits/custom/extra-rules.toml"
kind = "constraints"
""",
                encoding="utf-8",
            )
            (kit_dir / "base-rules.toml").write_text(
                "[PRD.identifiers.fr]\nrequired = true\n",
                encoding="utf-8",
            )
            (kit_dir / "extra-rules.toml").write_text(
                "[DESIGN.identifiers.component]\nrequired = true\n",
                encoding="utf-8",
            )

            ctx = StudioContext.load_from_dir(adapter_dir)

            assert ctx is not None
            loaded = ctx.kits["custom"]
            assert loaded.constraints is not None
            assert sorted(loaded.constraints.by_kind) == ["DESIGN", "PRD"]
            assert loaded.constraints_paths == [
                (kit_dir / "base-rules.toml").resolve(),
                (kit_dir / "extra-rules.toml").resolve(),
            ]

    @patch("studio.utils.files.find_studio_directory")
    def test_load_returns_none_when_no_adapter(self, mock_find):
        """load returns None when adapter directory not found."""
        mock_find.return_value = None
        result = StudioContext.load()
        assert result is None

    @patch("studio.utils.context.load_constraints_toml")
    @patch("studio.utils.context.load_artifacts_meta")
    @patch("studio.utils.files.find_studio_directory")
    def test_load_success_loads_templates_and_expands_autodetect(
        self,
        mock_find,
        mock_load_meta,
        mock_load_constraints,
    ):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            adapter_dir = tmp / "adapter"
            adapter_dir.mkdir(parents=True)

            # project_root = adapter_dir / '..' => tmp
            # Create kit template structure: <tmp>/kits/sdlc/artifacts/PRD/template.md
            tmpl_dir = tmp / "kits" / "sdlc" / "artifacts" / "PRD"
            tmpl_dir.mkdir(parents=True)
            (tmpl_dir / "template.md").write_text("x", encoding="utf-8")

            # Create autodetect target file: <tmp>/subsystems/docs/PRD.md
            docs_dir = tmp / "subsystems" / "docs"
            docs_dir.mkdir(parents=True)
            (docs_dir / "PRD.md").write_text("x", encoding="utf-8")

            meta = ArtifactsMeta.from_dict({
                "version": "1.1",
                "project_root": "..",
                "kits": {"k": {"format": "CFS", "path": "kits/sdlc"}},
                "systems": [
                    {
                        "name": "App",
                        "slug": "app",
                        "kit": "k",
                        "autodetect": [
                            {
                                "kit": "k",
                                "system_root": "{project_root}/subsystems",
                                "artifacts_root": "{system_root}/docs",
                                "artifacts": {
                                    "PRD": {"pattern": "PRD.md", "traceability": "FULL"},
                                    "UNKNOWN": {"pattern": "missing.md", "traceability": "FULL"},
                                },
                                "validation": {"require_kind_registered_in_kit": True},
                            }
                        ],
                    }
                ],
            })

            # Make constraints error branch execute, but still provide kit_constraints
            kit_constraints = MagicMock()
            kit_constraints.by_kind = {"PRD": MagicMock()}
            mock_load_constraints.return_value = (kit_constraints, ["bad constraints"])

            # Template.from_path returns a template for PRD
            mock_find.return_value = adapter_dir
            mock_load_meta.return_value = (meta, None)

            ctx = StudioContext.load()
            assert ctx is not None

            # We should have:
            # - constraints.toml parse error surfaced
            # - autodetect kind-not-registered error surfaced
            msgs = [str(e.get("message", "")) for e in (ctx._errors or [])]
            assert any("Invalid constraints" in m for m in msgs)
            assert any("Autodetect validation error" in m for m in msgs)

    @patch("studio.utils.context.load_artifacts_meta")
    @patch("studio.utils.files.find_studio_directory")
    def test_load_autodetect_exception_is_captured(self, mock_find, mock_load_meta):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            adapter_dir = tmp / "adapter"
            adapter_dir.mkdir(parents=True)

            meta = ArtifactsMeta.from_dict({
                "version": "1.1",
                "project_root": "..",
                "kits": {},
                "systems": [],
            })

            def boom(*args, **kwargs):
                raise ValueError("boom")

            meta.expand_autodetect = boom  # type: ignore[assignment]

            mock_find.return_value = adapter_dir
            mock_load_meta.return_value = (meta, None)

            ctx = StudioContext.load()
            assert ctx is not None
            msgs = [str(e.get("message", "")) for e in (ctx._errors or [])]
            assert any("Autodetect expansion failed" in m for m in msgs)

    @patch("studio.utils.context.load_artifacts_meta")
    @patch("studio.utils.files.find_studio_directory")
    def test_load_returns_none_on_meta_error(self, mock_find, mock_load_meta):
        """load returns None when artifacts registry fails to load."""
        mock_find.return_value = Path("/fake/adapter")
        mock_load_meta.return_value = (None, "Some error")

        result = StudioContext.load()
        assert result is None
