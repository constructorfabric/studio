"""Tests for WP6: Validator Resource Path Resolution.

Covers:
- context.py: constraints loading via resource bindings
- validate_kits.py: resource path verification for manifest-driven kits
- validate_kits.py: standalone kit manifest validation
"""
from __future__ import annotations

import sys
import io
import json
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from _test_helpers import bootstrap_test_project, write_registered_sdlc_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bootstrap_project(root: Path, adapter_rel: str = "cypilot") -> Path:
    return bootstrap_test_project(
        root,
        adapter_rel,
        systems=[{"name": "TestProject", "slug": "test"}],
    )


def _write_core_toml(config_dir: Path, data: dict) -> Path:
    """Write core.toml into *config_dir* and return the path."""
    from studio.utils import toml_utils
    config_dir.mkdir(parents=True, exist_ok=True)
    core_path = config_dir / "core.toml"
    toml_utils.dump(data, core_path)
    return core_path


def _write_minimal_constraints(target_dir: Path) -> None:
    """Write a minimal valid constraints.toml into *target_dir*."""
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "constraints.toml").write_text("[artifacts]\n", encoding="utf-8")


def _write_manifest_toml(kit_dir: Path, resources: list[dict]) -> None:
    """Write a valid manifest.toml into *kit_dir*."""
    from studio.utils.toml_utils import dumps
    data = {
        "manifest": {
            "version": "1.0",
            "root": "{cf-studio-path}/config/kits/{slug}",
            "user_modifiable": False,
        },
        "resources": resources,
    }
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "manifest.toml").write_text(dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Context: constraints loading via resource bindings
# ---------------------------------------------------------------------------

class TestContextConstraintsResourceBinding(unittest.TestCase):
    """Test that StudioContext.load() uses resource binding for constraints path."""

    def test_constraints_loaded_from_binding_path(self):
        """When a 'constraints' resource binding exists and the file is present,
        context loads constraints from the binding path (not default kit root)."""
        from studio.utils.context import StudioContext

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            # Create a custom constraints location (outside kit dir but
            # reachable from adapter_dir via '../')
            custom_dir = root / "custom" / "constraints"
            custom_dir.mkdir(parents=True)
            (custom_dir / "constraints.toml").write_text(
                '[artifacts]\n[artifacts.PRD]\nname = "PRD"\n[artifacts.PRD.identifiers]\n',
                encoding="utf-8",
            )

            # Kit dir with NO constraints.toml
            kit_dir = config / "kits" / "sdlc"
            kit_dir.mkdir(parents=True)

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "2.0",
                        "resources": {
                            "constraints": {"path": "../custom/constraints/constraints.toml"},
                        },
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            self.assertIn("sdlc", ctx.kits)
            # Constraints should be loaded (from custom path), not None
            self.assertIsNotNone(ctx.kits["sdlc"].constraints)

    def test_constraints_fallback_to_kit_root(self):
        """When no 'constraints' resource binding exists, constraints loaded from kit root."""
        from studio.utils.context import StudioContext

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            kit_dir = config / "kits" / "sdlc"
            kit_dir.mkdir(parents=True)
            (kit_dir / "constraints.toml").write_text(
                '[artifacts]\n[artifacts.ADR]\nname = "ADR"\n[artifacts.ADR.identifiers]\n',
                encoding="utf-8",
            )

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "1.0",
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            self.assertIn("sdlc", ctx.kits)
            self.assertIsNotNone(ctx.kits["sdlc"].constraints)

    def test_binding_path_missing_file_surfaces_error(self):
        """When constraints binding path does not exist on disk, surface an error."""
        from studio.utils.context import StudioContext

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            kit_dir = config / "kits" / "sdlc"
            kit_dir.mkdir(parents=True)
            # Kit root has constraints
            (kit_dir / "constraints.toml").write_text("[artifacts]\n", encoding="utf-8")

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "2.0",
                        "resources": {
                            "constraints": {"path": "nonexistent/constraints.toml"},
                        },
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            self.assertIn("sdlc", ctx.kits)
            self.assertIsNone(ctx.kits["sdlc"].constraints)
            msgs = [str(e.get("message", "")) for e in (ctx._errors or [])]
            self.assertTrue(any("Invalid constraints" in msg for msg in msgs))
            self.assertTrue(any("Bound constraints resource" in str(e.get("errors", [])) for e in (ctx._errors or [])))


# ---------------------------------------------------------------------------
# validate-kits: resource path verification for registered kits
# ---------------------------------------------------------------------------

class TestValidateKitsResourcePaths(unittest.TestCase):
    """Test that run_validate_kits verifies resource paths for manifest-driven kits."""

    _BOUND_TEMPLATE_KINDS = {
        "prd": "PRD",
        "adr": "ADR",
        "design": "DESIGN",
        "decomposition": "DECOMPOSITION",
        "feature": "FEATURE",
        "upstream_reqs": "UPSTREAM_REQS",
        "pr_code_review": "PR-CODE-REVIEW-TEMPLATE",
        "pr_status_report": "PR-STATUS-REPORT-TEMPLATE",
    }

    def _write_register_mode_bound_template_project(
        self,
        root: Path,
        *,
        include_artifact_bindings: bool = True,
    ) -> tuple[object, Path]:
        from studio.utils.context import StudioContext
        from studio.utils import toml_utils

        adapter = _bootstrap_project(root, ".cf-studio")
        config = adapter / "config"
        kit_root = root / "studio-kit-gears"
        kit_root.mkdir(parents=True)

        template_root = root / "docs" / "spec-templates" / "gears-sdlc"
        artifact_bindings = {}
        constraints_resource = {
            "path": "../studio-kit-gears/constraints.toml",
            "kind": "constraints",
        }
        if include_artifact_bindings:
            constraints_resource["artifacts"] = artifact_bindings
        resources = {
            "constraints": {
                **constraints_resource,
            },
        }
        for prefix, kind in self._BOUND_TEMPLATE_KINDS.items():
            kind_dir = template_root / kind
            kind_dir.mkdir(parents=True, exist_ok=True)
            template = kind_dir / "template.md"
            if kind == "FEATURE":
                template.write_text(
                    "# Feature\n\nThis template intentionally omits the required flow placeholder.\n",
                    encoding="utf-8",
                )
            else:
                template.write_text(f"# {kind}\n", encoding="utf-8")
            resources[f"{prefix}_template"] = {
                "path": f"../docs/spec-templates/gears-sdlc/{kind}/template.md",
            }
            artifact_bindings[kind] = {"template": f"{prefix}_template"}

        feature_examples = template_root / "FEATURE" / "examples"
        feature_examples.mkdir(parents=True)
        (feature_examples / "valid.md").write_text(
            "# Feature\n\n- **ID**: `cpt-test-flow-valid`\n",
            encoding="utf-8",
        )
        resources["feature_example"] = {
            "path": "../docs/spec-templates/gears-sdlc/FEATURE/examples",
        }
        artifact_bindings["FEATURE"]["examples"] = "feature_example"
        prd_example = template_root / "PRD" / "example.md"
        prd_example.write_text("# PRD\n", encoding="utf-8")
        resources["prd_example"] = {
            "path": "../docs/spec-templates/gears-sdlc/PRD/example.md",
        }
        artifact_bindings["PRD"]["examples"] = "prd_example"

        (kit_root / "constraints.toml").write_text(
            "\n".join([
                "[FEATURE.identifiers.flow]",
                "required = true",
                'template = "cpt-{system}-flow-{slug}"',
                "",
            ]),
            encoding="utf-8",
        )

        toml_utils.dump({
            "version": "1.0",
            "project_root": "..",
            "kits": {
                "gears": {
                    "format": "CFS",
                    "path": "../studio-kit-gears",
                    "version": "1.0",
                    "resources": resources,
                },
            },
        }, config / "core.toml")
        toml_utils.dump({
            "version": "1.0",
            "project_root": "..",
            "kits": {
                "gears": {"format": "CFS", "path": "../studio-kit-gears"},
            },
            "systems": [{"name": "Test", "slug": "test", "kit": "gears"}],
        }, config / "artifacts.toml")

        ctx = StudioContext.load(root)
        self.assertIsNotNone(ctx)
        return ctx, adapter

    def test_register_mode_resource_bindings_self_check_all_templates(self):
        """Local/register manifest kits self-check bound resources outside kit root."""
        from studio.utils.context import set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            ctx, _adapter = self._write_register_mode_bound_template_project(root)
            set_context(ctx)
            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                    verbose=True,
                )
            finally:
                set_context(None)

        self.assertEqual(rc, 2)
        self.assertEqual(result.get("templates_checked"), 8)
        self.assertEqual(len(result.get("self_check_results", [])), 8)

    def test_register_mode_resource_bindings_surface_feature_template_mismatch(self):
        """Bound FEATURE template mismatch is reported like copy-mode package layout."""
        from studio.utils.context import set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            ctx, _adapter = self._write_register_mode_bound_template_project(root)
            set_context(ctx)
            try:
                _rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                    verbose=True,
                )
            finally:
                set_context(None)

        feature = next(
            (item for item in result.get("self_check_results", []) if item.get("kind") == "FEATURE"),
            None,
        )
        self.assertIsNotNone(feature)
        assert feature is not None
        self.assertEqual(feature.get("status"), "FAIL")
        messages = [err.get("message", "") for err in feature.get("errors", [])]
        self.assertTrue(any("Template missing ID placeholder" in msg for msg in messages), messages)

    def test_register_mode_without_artifact_bindings_warns_and_skips_templates(self):
        """Manifest resources are not matched to artifact kinds by naming convention."""
        from studio.utils.context import set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            ctx, _adapter = self._write_register_mode_bound_template_project(
                root,
                include_artifact_bindings=False,
            )
            set_context(ctx)
            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                    verbose=True,
                )
            finally:
                set_context(None)

        self.assertEqual(rc, 0)
        self.assertEqual(result.get("templates_checked"), 1)
        feature = next(
            (item for item in result.get("self_check_results", []) if item.get("kind") == "FEATURE"),
            None,
        )
        self.assertIsNotNone(feature)
        assert feature is not None
        self.assertEqual(feature.get("status"), "PASS")
        warnings = [warn.get("message", "") for warn in feature.get("warnings", [])]
        self.assertTrue(any("no manifest resource binding" in msg for msg in warnings), warnings)

    def test_validate_kits_register_mode_uses_manifest_resource_entries(self):
        """Register-mode kits self-check against manifest artifact bindings without persisted resources."""
        from studio.utils.context import StudioContext, set_context
        from studio.utils import toml_utils
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root, ".cf-studio")
            config = adapter / "config"
            kit_root = root / "studio-kit-gears"
            kit_root.mkdir(parents=True)

            (kit_root / "feature-template.md").write_text(
                "# Feature\n\nThis template intentionally omits the required flow placeholder.\n",
                encoding="utf-8",
            )
            examples_dir = kit_root / "feature-examples"
            examples_dir.mkdir()
            (examples_dir / "valid.md").write_text(
                "# Feature\n\n- **ID**: `cpt-test-flow-valid`\n",
                encoding="utf-8",
            )
            (kit_root / "constraints.toml").write_text(
                "[FEATURE.identifiers.flow]\nrequired = true\n"
                'template = "cpt-{system}-flow-{slug}"\n',
                encoding="utf-8",
            )
            (kit_root / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "gears"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "constraints"',
                    'kind = "constraints"',
                    'source = "constraints.toml"',
                    'type = "file"',
                    "",
                    '[kits.resources.artifacts.FEATURE]',
                    'template = "feature_template"',
                    'examples = "feature_examples"',
                    "",
                    "[[kits.resources]]",
                    'id = "feature_template"',
                    'kind = "template"',
                    'source = "feature-template.md"',
                    'type = "file"',
                    "",
                    "[[kits.resources]]",
                    'id = "feature_examples"',
                    'kind = "directory"',
                    'source = "feature-examples"',
                    'type = "directory"',
                ]) + "\n",
                encoding="utf-8",
            )

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "gears": {
                        "format": "CFS",
                        "install_mode": "register",
                        "path": "../studio-kit-gears",
                        "version": "1.0",
                    },
                },
            }, config / "core.toml")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "gears": {"format": "CFS", "path": "../studio-kit-gears"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "gears"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            assert ctx is not None
            set_context(ctx)
            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                    verbose=True,
                )
            finally:
                set_context(None)

        self.assertEqual(rc, 2)
        self.assertEqual(result.get("templates_checked"), 1)
        feature = next(
            (item for item in result.get("self_check_results", []) if item.get("kind") == "FEATURE"),
            None,
        )
        self.assertIsNotNone(feature)
        assert feature is not None
        warnings = [warn.get("message", "") for warn in feature.get("warnings", [])]
        self.assertFalse(any("no manifest resource binding" in msg for msg in warnings), warnings)

    def test_register_mode_self_check_uses_all_constraints_resources(self):
        """Bound templates are checked against every constraints resource, not just one."""
        from studio.utils import toml_utils
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            root = Path(td) / "proj"
            adapter = _bootstrap_project(root, ".cf-studio")
            config = adapter / "config"
            kit_root = root / "studio-kit"
            kit_root.mkdir(parents=True)
            (kit_root / "base.toml").write_text(
                "[PRD.identifiers.fr]\nrequired = true\n",
                encoding="utf-8",
            )
            (kit_root / "feature.toml").write_text(
                "[FEATURE.identifiers.flow]\nrequired = true\n"
                'template = "cpt-{system}-flow-{slug}"\n',
                encoding="utf-8",
            )
            (kit_root / "feature-template.md").write_text(
                "# Feature\n\nThis template intentionally omits the required flow placeholder.\n",
                encoding="utf-8",
            )
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "multi": {
                        "format": "CFS",
                        "path": "../studio-kit",
                        "resources": {
                            "policy-a": {
                                "path": "../studio-kit/base.toml",
                                "kind": "constraints",
                            },
                            "policy-b": {
                                "path": "../studio-kit/feature.toml",
                                "kind": "constraints",
                                "artifacts": {
                                    "FEATURE": {"template": "feature-template"},
                                },
                            },
                            "feature-template": {
                                "path": "../studio-kit/feature-template.md",
                                "kind": "template",
                            },
                        },
                    },
                },
            }, config / "core.toml")
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {"multi": {"format": "CFS", "path": "../studio-kit"}},
                "systems": [{"name": "Test", "slug": "test", "kit": "multi"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            set_context(ctx)
            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                    verbose=True,
                )
            finally:
                set_context(None)

        self.assertEqual(rc, 2)
        self.assertEqual(result.get("templates_checked"), 2)
        feature = next(
            (item for item in result.get("self_check_results", []) if item.get("kind") == "FEATURE"),
            None,
        )
        self.assertIsNotNone(feature)
        assert feature is not None
        messages = [err.get("message", "") for err in feature.get("errors", [])]
        self.assertTrue(any("Template missing ID placeholder" in msg for msg in messages), messages)

    def test_missing_resource_path_produces_error(self):
        """Registered kit with resource binding pointing to missing path → FAIL."""
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            kit_dir = config / "kits" / "sdlc"
            _write_minimal_constraints(kit_dir)

            write_registered_sdlc_config(
                config,
                resources={
                    "adr_artifacts": {"path": "config/kits/sdlc/artifacts/ADR"},
                    "constraints": {"path": "config/kits/sdlc/constraints.toml"},
                },
            )

            # constraints.toml exists but ADR dir does NOT
            # (constraints path exists because _write_minimal_constraints created it)

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            set_context(ctx)

            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                )
                # adr_artifacts path should be missing → error
                self.assertEqual(rc, 2)
                self.assertEqual(result["status"], "FAIL")
                self.assertGreater(result["error_count"], 0)
                # Check that the error mentions the missing resource
                errors = result.get("errors", [])
                resource_errors = [e for e in errors if e.get("type") == "resources"]
                self.assertGreater(len(resource_errors), 0)
                self.assertIn("adr_artifacts", resource_errors[0]["message"])
            finally:
                set_context(None)

    def test_missing_resource_path_marks_failed_kit_in_report(self):
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            kit_dir = config / "kits" / "sdlc"
            _write_minimal_constraints(kit_dir)

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "2.0",
                        "resources": {
                            "adr_artifacts": {"path": "config/kits/sdlc/artifacts/ADR"},
                            "constraints": {"path": "config/kits/sdlc/constraints.toml"},
                        },
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            set_context(ctx)

            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                )
                self.assertEqual(rc, 2)
                self.assertEqual(result["status"], "FAIL")
                self.assertTrue(any(
                    fk.get("kit") == "sdlc" and int(fk.get("error_count", 0)) >= 1
                    for fk in result.get("failed_kits", [])
                ))
            finally:
                set_context(None)

    def test_invalid_binding_resolution_produces_resource_error(self):
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            kit_dir = config / "kits" / "sdlc"
            _write_minimal_constraints(kit_dir)

            invalid_binding = "/opt/cypilot/constraints.toml" if sys.platform.startswith("win") else "C:/external-kits/sdlc/constraints.toml"

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "2.0",
                        "resources": {
                            "constraints": {"path": invalid_binding},
                        },
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            self.assertIn("sdlc", ctx.kits)
            self.assertIsNone(ctx.kits["sdlc"].resource_bindings)
            self.assertTrue(any(err.get("type") == "resources" for err in getattr(ctx, "_errors", [])))
            set_context(ctx)

            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                )
                self.assertEqual(rc, 2)
                self.assertEqual(result["status"], "FAIL")
                self.assertGreater(result["error_count"], 0)
                resource_errors = [
                    e for e in result.get("errors", [])
                    if e.get("type") == "resources"
                ]
                self.assertGreater(len(resource_errors), 0)
                self.assertIn("not accessible on this OS", resource_errors[0]["message"])
            finally:
                set_context(None)

    def test_inaccessible_absolute_kit_path_fails_and_reports_configured_path(self):
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            inaccessible_kit_path = "C:/external-kits/sdlc" if not sys.platform.startswith("win") else "/external-kits/sdlc"

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": inaccessible_kit_path,
                        "version": "2.0",
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            self.assertIn("sdlc", ctx.kits)
            self.assertIsNone(ctx.kits["sdlc"].kit_root)
            self.assertTrue(any(err.get("type") == "resources" for err in getattr(ctx, "_errors", [])))
            set_context(ctx)

            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                    verbose=True,
                )
                self.assertEqual(rc, 2)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["kits"][0]["path"], inaccessible_kit_path)
                self.assertNotEqual(result["kits"][0]["path"], str(ctx.adapter_dir.resolve()))
                self.assertTrue(any(
                    fk.get("kit") == "sdlc" and int(fk.get("error_count", 0)) >= 1
                    for fk in result.get("failed_kits", [])
                ) or result["kits"][0]["error_count"] >= 1)
                resource_errors = [
                    e for e in result.get("errors", [])
                    if e.get("type") == "resources"
                ]
                self.assertGreater(len(resource_errors), 0)
                self.assertIn("not accessible on this OS", resource_errors[0]["message"])
                self.assertEqual(resource_errors[0]["path"], str((config / "core.toml").resolve()))
            finally:
                set_context(None)

    def test_all_resource_paths_exist_passes(self):
        """Registered kit with all resource bindings pointing to existing paths → PASS."""
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            kit_dir = config / "kits" / "sdlc"
            _write_minimal_constraints(kit_dir)

            # Create the ADR artifacts directory so the path exists
            adr_dir = kit_dir / "artifacts" / "ADR"
            adr_dir.mkdir(parents=True)

            write_registered_sdlc_config(
                config,
                resources={
                    "adr_artifacts": {"path": "config/kits/sdlc/artifacts/ADR"},
                    "constraints": {"path": "config/kits/sdlc/constraints.toml"},
                },
            )

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            set_context(ctx)

            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                )
                self.assertEqual(rc, 0)
                self.assertEqual(result["status"], "PASS")
            finally:
                set_context(None)

    def test_legacy_kit_no_resource_check(self):
        """Legacy kit without resource bindings skips resource path verification."""
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            kit_dir = config / "kits" / "sdlc"
            _write_minimal_constraints(kit_dir)

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "1.0",
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            set_context(ctx)

            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                )
                self.assertEqual(rc, 0)
                self.assertEqual(result["status"], "PASS")
            finally:
                set_context(None)

    def test_verbose_report_uses_authoritative_adapter_relative_custom_root(self):
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            custom_kit_dir = adapter / "custom-kits" / "sdlc"
            custom_kit_dir.mkdir(parents=True)
            (custom_kit_dir / "constraints.toml").write_text("[broken\ninvalid", encoding="utf-8")

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "custom-kits/sdlc",
                        "version": "2.0",
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            set_context(ctx)

            try:
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                    verbose=True,
                )
                self.assertEqual(rc, 2)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["kits"][0]["path"], str(custom_kit_dir.resolve()))
                self.assertEqual(
                    result["kits"][0]["errors"][0]["path"],
                    str((custom_kit_dir / "constraints.toml").resolve()),
                )
            finally:
                set_context(None)


# ---------------------------------------------------------------------------
# validate-kits by path: manifest validation for standalone kits
# ---------------------------------------------------------------------------

class TestValidateKitByPathManifest(unittest.TestCase):
    """Test _validate_kit_by_path with manifest.toml validation."""

    def test_valid_manifest_passes(self):
        """Standalone kit with valid manifest.toml → no resource errors."""
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_dir = td_path / "mykit"
            kit_dir.mkdir()

            # Create constraints
            _write_minimal_constraints(kit_dir)

            # Create manifest with valid source paths
            (kit_dir / "artifacts").mkdir()
            (kit_dir / "artifacts" / "ADR").mkdir()
            _write_manifest_toml(kit_dir, [
                {
                    "id": "adr_artifacts",
                    "source": "artifacts/ADR",
                    "default_path": "artifacts/ADR",
                    "type": "directory",
                    "description": "ADR artifacts",
                },
            ])

            rc, result = _validate_kit_by_path(kit_dir, verbose=True)
            self.assertEqual(rc, 0)
            self.assertEqual(result["kits"][0]["manifest_source"], "legacy_manifest")
            self.assertEqual(result["kits"][0]["resource_count"], 1)
            resource_errors = [
                e for e in result.get("errors", [])
                if e.get("type") == "resources"
            ]
            self.assertEqual(len(resource_errors), 0)

    def test_invalid_manifest_source_produces_error(self):
        """Standalone kit with manifest referencing missing source → error."""
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_dir = td_path / "mykit"
            kit_dir.mkdir()

            _write_minimal_constraints(kit_dir)

            # Manifest references source that does not exist
            _write_manifest_toml(kit_dir, [
                {
                    "id": "missing_resource",
                    "source": "nonexistent/dir",
                    "default_path": "some/path",
                    "type": "directory",
                    "description": "Missing resource",
                },
            ])

            rc, result = _validate_kit_by_path(kit_dir, verbose=True)
            resource_errors = [
                e for e in result.get("errors", [])
                if e.get("type") == "resources"
            ]
            kit_report = result["kits"][0]
            self.assertEqual(rc, 2)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(kit_report["status"], "FAIL")
            self.assertGreater(kit_report["error_count"], 0)
            self.assertTrue(any(
                e.get("type") == "resources"
                for e in kit_report.get("errors", [])
            ))
            self.assertGreater(len(resource_errors), 0)

    def test_no_manifest_no_resource_check(self):
        """Standalone kit without manifest.toml → no resource errors."""
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_dir = td_path / "mykit"
            kit_dir.mkdir()

            _write_minimal_constraints(kit_dir)

            rc, result = _validate_kit_by_path(kit_dir)
            resource_errors = [
                e for e in result.get("errors", [])
                if e.get("type") == "resources"
            ]
            self.assertEqual(len(resource_errors), 0)

    def test_canonical_manifest_ignores_malformed_legacy_manifest(self):
        """Standalone validation ignores manifest.toml when canonical manifest exists."""
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_dir = td_path / "mykit"
            kit_dir.mkdir()
            (kit_dir / "constraints.toml").write_text(
                "[FEATURE.identifiers.flow]\nrequired = true\n",
                encoding="utf-8",
            )
            (kit_dir / "feature-template.md").write_text("# Feature\n", encoding="utf-8")
            (kit_dir / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "mykit"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "ruleset"',
                    'kind = "constraints"',
                    'source = "constraints.toml"',
                    'type = "file"',
                    "",
                    "[[kits.resources]]",
                    'id = "feature-template"',
                    'kind = "template"',
                    'source = "feature-template.md"',
                    'type = "file"',
                ]) + "\n",
                encoding="utf-8",
            )
            (kit_dir / "manifest.toml").write_text("[broken\ninvalid", encoding="utf-8")

            rc, result = _validate_kit_by_path(kit_dir, verbose=True)

            self.assertEqual(rc, 0)
            self.assertEqual(result["kits"][0]["manifest_source"], "canonical")
            resource_errors = [
                e for e in result.get("errors", [])
                if e.get("type") == "resources"
            ]
            self.assertEqual(resource_errors, [])

    def test_canonical_constraints_kind_resources_with_arbitrary_names(self):
        """Standalone canonical kit loads constraints by kind, not filename or id."""
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_dir = td_path / "mykit"
            kit_dir.mkdir()
            (kit_dir / "base-rules.toml").write_text(
                "[PRD.identifiers.fr]\nrequired = true\n",
                encoding="utf-8",
            )
            (kit_dir / "extra-rules.toml").write_text(
                "[DESIGN.identifiers.component]\nrequired = true\n",
                encoding="utf-8",
            )
            (kit_dir / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "mykit"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "policy-a"',
                    'kind = "constraints"',
                    'source = "base-rules.toml"',
                    'type = "file"',
                    "",
                    "[[kits.resources]]",
                    'id = "policy-b"',
                    'kind = "constraints"',
                    'source = "extra-rules.toml"',
                    'type = "file"',
                ]) + "\n",
                encoding="utf-8",
            )

            rc, result = _validate_kit_by_path(kit_dir, verbose=True)

            self.assertEqual(rc, 0)
            self.assertEqual(result["kits"][0]["manifest_source"], "canonical")
            self.assertEqual(result["kits"][0]["kinds"], ["DESIGN", "PRD"])

    def test_canonical_constraints_artifact_bindings_survive_model_load(self):
        """Canonical constraints resources carry explicit artifact-kind bindings."""
        from studio.utils.kit_model import kit_models_to_toml_data, load_kit_model

        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "mykit"
            kit_dir.mkdir()
            (kit_dir / "constraints.toml").write_text(
                "[FEATURE.identifiers.flow]\nrequired = true\n",
                encoding="utf-8",
            )
            (kit_dir / "feature-template.md").write_text("# Feature\n", encoding="utf-8")
            (kit_dir / "feature-examples").mkdir()
            (kit_dir / "feature-examples" / "valid.md").write_text("# Feature\n", encoding="utf-8")
            (kit_dir / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "mykit"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "ruleset"',
                    'kind = "constraints"',
                    'source = "constraints.toml"',
                    'type = "file"',
                    "",
                    "[kits.resources.artifacts.FEATURE]",
                    'template = "feature-template"',
                    'examples = "feature-examples"',
                    "",
                    "[[kits.resources]]",
                    'id = "feature-template"',
                    'kind = "template"',
                    'source = "feature-template.md"',
                    'type = "file"',
                    "",
                    "[[kits.resources]]",
                    'id = "feature-examples"',
                    'kind = "directory"',
                    'source = "feature-examples"',
                    'type = "directory"',
                ]) + "\n",
                encoding="utf-8",
            )

            model = load_kit_model(kit_dir)

        constraints_resource = [res for res in model.resources if res.id == "ruleset"][0]
        self.assertEqual(
            constraints_resource.artifact_bindings,
            {"FEATURE": {"template": "feature-template", "examples": "feature-examples"}},
        )
        rendered = kit_models_to_toml_data([model])
        rendered_constraints = [
            res for res in rendered["kits"][0]["resources"]
            if res["id"] == "ruleset"
        ][0]
        self.assertEqual(
            rendered_constraints["artifacts"],
            {"FEATURE": {"template": "feature-template", "examples": "feature-examples"}},
        )

    def test_validate_kit_by_path_uses_canonical_artifact_bindings_outside_layout(self):
        """Standalone canonical validation uses explicit bound resources outside artifacts/."""
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "mykit"
            kit_dir.mkdir()
            (kit_dir / "constraints.toml").write_text(
                "[FEATURE.identifiers.flow]\nrequired = true\n"
                'template = "cpt-{system}-flow-{slug}"\n',
                encoding="utf-8",
            )
            (kit_dir / "feature-template.md").write_text(
                "# Feature\n\nThis template intentionally omits the required flow placeholder.\n",
                encoding="utf-8",
            )
            (kit_dir / "feature-examples").mkdir()
            (kit_dir / "feature-examples" / "valid.md").write_text(
                "# Feature\n\n- **ID**: `cpt-test-flow-valid`\n",
                encoding="utf-8",
            )
            (kit_dir / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "mykit"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "ruleset"',
                    'kind = "constraints"',
                    'source = "constraints.toml"',
                    'type = "file"',
                    "",
                    "[kits.resources.artifacts.FEATURE]",
                    'template = "feature-template"',
                    'examples = "feature-examples"',
                    "",
                    "[[kits.resources]]",
                    'id = "feature-template"',
                    'kind = "template"',
                    'source = "feature-template.md"',
                    'type = "file"',
                    "",
                    "[[kits.resources]]",
                    'id = "feature-examples"',
                    'kind = "directory"',
                    'source = "feature-examples"',
                    'type = "directory"',
                ]) + "\n",
                encoding="utf-8",
            )

            rc, result = _validate_kit_by_path(kit_dir, verbose=True)

        self.assertEqual(rc, 2)
        self.assertEqual(result.get("templates_checked"), 1)
        feature = next(
            (item for item in result.get("self_check_results", []) if item.get("kind") == "FEATURE"),
            None,
        )
        self.assertIsNotNone(feature)
        assert feature is not None
        messages = [err.get("message", "") for err in feature.get("errors", [])]
        self.assertTrue(any("Template missing ID placeholder" in msg for msg in messages), messages)

    def test_validate_kit_by_path_canonical_without_bindings_warns_and_skips_layout(self):
        """Canonical path validation does not infer template bindings from artifacts/ layout."""
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "mykit"
            kit_dir.mkdir()
            (kit_dir / "constraints.toml").write_text(
                "[FEATURE.identifiers.flow]\nrequired = true\n"
                'template = "cpt-{system}-flow-{slug}"\n',
                encoding="utf-8",
            )
            artifacts_feature = kit_dir / "artifacts" / "FEATURE"
            artifacts_feature.mkdir(parents=True)
            (artifacts_feature / "template.md").write_text("# Feature\n", encoding="utf-8")
            (kit_dir / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "mykit"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "ruleset"',
                    'kind = "constraints"',
                    'source = "constraints.toml"',
                    'type = "file"',
                ]) + "\n",
                encoding="utf-8",
            )

            rc, result = _validate_kit_by_path(kit_dir, verbose=True)

        self.assertEqual(rc, 0)
        self.assertEqual(result.get("templates_checked"), 1)
        feature = next(
            (item for item in result.get("self_check_results", []) if item.get("kind") == "FEATURE"),
            None,
        )
        self.assertIsNotNone(feature)
        assert feature is not None
        warnings = [warn.get("message", "") for warn in feature.get("warnings", [])]
        self.assertTrue(any("no manifest resource binding" in msg for msg in warnings), warnings)

    def test_canonical_constraints_artifact_bindings_reject_invalid_shapes(self):
        """Canonical artifact bindings fail closed on malformed explicit maps."""
        from studio.utils.kit_model import load_kit_model

        cases = [
            ("artifacts = []", "must be a table"),
            ('[kits.resources.artifacts.""]\ntemplate = "feature-template"', "empty artifact kind"),
            ('[kits.resources.artifacts]\nFEATURE = "feature-template"', "FEATURE' must be a table"),
            ('[kits.resources.artifacts.FEATURE]\nunknown = "feature-template"', "unsupported"),
            ('[kits.resources.artifacts.FEATURE]\ntemplate = ""', "non-empty string"),
        ]
        with TemporaryDirectory() as td:
            base = Path(td)
            for idx, (artifacts_toml, message) in enumerate(cases):
                with self.subTest(message=message):
                    kit_dir = base / f"case-{idx}"
                    kit_dir.mkdir()
                    (kit_dir / "constraints.toml").write_text("[artifacts]\n", encoding="utf-8")
                    (kit_dir / "feature-template.md").write_text("# Feature\n", encoding="utf-8")
                    (kit_dir / ".cf-studio-kit.toml").write_text(
                        "\n".join([
                            'manifest_version = "1.0"',
                            "",
                            "[[kits]]",
                            'slug = "mykit"',
                            'version = "1.0"',
                            "",
                            "[[kits.resources]]",
                            'id = "ruleset"',
                            'kind = "constraints"',
                            'source = "constraints.toml"',
                            'type = "file"',
                            artifacts_toml,
                        ]) + "\n",
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(ValueError, message):
                        load_kit_model(kit_dir)

    def test_canonical_artifact_bindings_only_allowed_on_constraints(self):
        """Template resources cannot declare artifact-kind self-check bindings."""
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            kit_dir = Path(td) / "mykit"
            kit_dir.mkdir()
            (kit_dir / "feature-template.md").write_text("# Feature\n", encoding="utf-8")
            (kit_dir / ".cf-studio-kit.toml").write_text(
                "\n".join([
                    'manifest_version = "1.0"',
                    "",
                    "[[kits]]",
                    'slug = "mykit"',
                    'version = "1.0"',
                    "",
                    "[[kits.resources]]",
                    'id = "feature-template"',
                    'kind = "template"',
                    'source = "feature-template.md"',
                    'type = "file"',
                    "",
                    "[kits.resources.artifacts.FEATURE]",
                    'template = "feature-template"',
                ]) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "only allowed for constraints"):
                load_kit_model(kit_dir)

    def test_core_resource_artifact_bindings_survive_model_load(self):
        """Installed core.toml resource bindings carry artifact-kind maps too."""
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            studio_root = Path(td) / "adapter"
            kit_dir = studio_root / "config" / "kits" / "mykit"
            kit_dir.mkdir(parents=True)
            (kit_dir / "constraints.toml").write_text("[artifacts]\n", encoding="utf-8")
            (kit_dir / "feature-template.md").write_text("# Feature\n", encoding="utf-8")
            _write_core_toml(studio_root / "config", {
                "kits": {
                    "mykit": {
                        "path": "config/kits/mykit",
                        "resources": {
                            "ruleset": {
                                "path": "config/kits/mykit/constraints.toml",
                                "kind": "constraints",
                                "artifacts": {
                                    "FEATURE": {"template": "feature-template"},
                                },
                            },
                            "feature-template": {
                                "path": "config/kits/mykit/feature-template.md",
                                "kind": "template",
                            },
                        },
                    },
                },
            })

            model = load_kit_model(kit_dir, source_hint="core")

        constraints_resource = [res for res in model.resources if res.id == "ruleset"][0]
        self.assertEqual(
            constraints_resource.artifact_bindings,
            {"FEATURE": {"template": "feature-template"}},
        )

    def test_core_resource_artifact_bindings_reject_non_constraints(self):
        """Installed core.toml cannot attach artifact-kind maps to template resources."""
        from studio.utils.kit_model import load_kit_model

        with TemporaryDirectory() as td:
            studio_root = Path(td) / "adapter"
            kit_dir = studio_root / "config" / "kits" / "mykit"
            kit_dir.mkdir(parents=True)
            (kit_dir / "feature-template.md").write_text("# Feature\n", encoding="utf-8")
            _write_core_toml(studio_root / "config", {
                "kits": {
                    "mykit": {
                        "path": "config/kits/mykit",
                        "resources": {
                            "feature-template": {
                                "path": "config/kits/mykit/feature-template.md",
                                "kind": "template",
                                "artifacts": {
                                    "FEATURE": {"template": "feature-template"},
                                },
                            },
                        },
                    },
                },
            })

            with self.assertRaisesRegex(ValueError, "only allowed for constraints"):
                load_kit_model(kit_dir, source_hint="core")

    def test_malformed_manifest_produces_error(self):
        """Standalone kit with malformed manifest.toml → resource error reported."""
        from studio.commands.validate_kits import _validate_kit_by_path

        with TemporaryDirectory() as td:
            td_path = Path(td)
            kit_dir = td_path / "mykit"
            kit_dir.mkdir()

            _write_minimal_constraints(kit_dir)

            # Write malformed TOML
            (kit_dir / "manifest.toml").write_text("[broken\ninvalid", encoding="utf-8")

            rc, result = _validate_kit_by_path(kit_dir)
            resource_errors = [
                e for e in result.get("errors", [])
                if e.get("type") == "resources"
            ]
            self.assertGreater(len(resource_errors), 0)


# ---------------------------------------------------------------------------
# Kit filter respects resource checks
# ---------------------------------------------------------------------------

class TestValidateKitsFilterWithResources(unittest.TestCase):
    """Test that kit_filter applies to resource path verification."""

    def test_filter_skips_other_kit_resources(self):
        """With kit_filter, only the filtered kit's resources are verified."""
        from studio.utils.context import StudioContext, set_context
        from studio.commands.validate_kits import run_validate_kits

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"

            # Kit "sdlc" with all paths present
            kit_dir = config / "kits" / "sdlc"
            _write_minimal_constraints(kit_dir)
            (kit_dir / "artifacts" / "ADR").mkdir(parents=True)

            # Kit "other" with missing resource path
            other_kit_dir = config / "kits" / "other"
            _write_minimal_constraints(other_kit_dir)

            from studio.utils import toml_utils
            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "config/kits/sdlc",
                        "version": "2.0",
                        "resources": {
                            "adr_artifacts": {"path": "config/kits/sdlc/artifacts/ADR"},
                        },
                    },
                    "other": {
                        "format": "CFS",
                        "path": "config/kits/other",
                        "version": "1.0",
                        "resources": {
                            "missing_thing": {"path": "nonexistent/path"},
                        },
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                    "other": {"format": "CFS", "path": "config/kits/other"},
                },
                "systems": [{"name": "Test", "slug": "test", "kit": "sdlc"}],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            set_context(ctx)

            try:
                # Filter to "sdlc" only — should PASS because sdlc paths exist
                rc, result = run_validate_kits(
                    project_root=ctx.project_root,
                    adapter_dir=ctx.adapter_dir,
                    kit_filter="sdlc",
                )
                self.assertEqual(rc, 0)
                self.assertEqual(result["status"], "PASS")
            finally:
                set_context(None)


class TestValidateCustomKitRootMetadata(unittest.TestCase):
    def setUp(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)

    def tearDown(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(False)

    def test_cmd_validate_uses_authoritative_constraints_path_for_custom_root(self):
        from _test_helpers import write_constraints_toml
        from studio.commands.validate import cmd_validate
        from studio.utils.context import StudioContext, set_context
        from studio.utils import toml_utils

        with TemporaryDirectory() as td:
            td_path = Path(td)
            root = td_path / "proj"
            adapter = _bootstrap_project(root)
            config = adapter / "config"
            custom_kit_dir = adapter / "custom-kits" / "sdlc"
            (custom_kit_dir / "artifacts" / "PRD").mkdir(parents=True, exist_ok=True)
            (custom_kit_dir / "artifacts" / "PRD" / "template.md").write_text("# PRD\n\n## Required Section\n", encoding="utf-8")
            write_constraints_toml(custom_kit_dir, {
                "PRD": {
                    "identifiers": {"fr": {"required": False}},
                    "headings": [
                        {"level": 1, "pattern": "PRD", "id": "prd-title"},
                        {"level": 2, "pattern": "Required Section", "id": "required-section"},
                    ],
                },
            })

            artifacts_dir = root / "architecture"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = artifacts_dir / "PRD.md"
            artifact_path.write_text("# PRD\n", encoding="utf-8")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {
                        "format": "CFS",
                        "path": "custom-kits/sdlc",
                        "version": "2.0",
                    },
                },
            }, config / "core.toml")

            toml_utils.dump({
                "version": "1.0",
                "project_root": "..",
                "kits": {
                    "sdlc": {"format": "CFS", "path": "config/kits/sdlc"},
                },
                "systems": [{
                    "name": "Test",
                    "slug": "test",
                    "kit": "sdlc",
                    "artifacts": [{
                        "path": "architecture/PRD.md",
                        "kind": "PRD",
                        "traceability": "FULL",
                    }],
                }],
            }, config / "artifacts.toml")

            ctx = StudioContext.load(root)
            self.assertIsNotNone(ctx)
            set_context(ctx)

            try:
                buf = io.StringIO()
                with patch("studio.commands.validate_kits.run_validate_kits", return_value=(0, {"status": "PASS"})):
                    with redirect_stdout(buf):
                        rc = cmd_validate(["--skip-code"])
                self.assertEqual(rc, 2)
                out = json.loads(buf.getvalue())
                self.assertEqual(out["status"], "FAIL")
                self.assertTrue(any(
                    err.get("constraints_path") == str((custom_kit_dir / "constraints.toml").resolve())
                    for err in out.get("errors", [])
                ))
            finally:
                set_context(None)


if __name__ == "__main__":
    unittest.main()
