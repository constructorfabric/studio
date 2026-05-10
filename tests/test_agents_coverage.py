"""
Targeted tests to increase coverage for agents.py to 90%+.

Covers:
- _ensure_frontmatter_description_quoted edge cases
- _resolve_gen_kits adapter fallback
- _registered_kit_dirs edge cases
- _ensure_cypilot_local copy path
- _list_workflow_files gen kit scanning
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))


class TestEnsureFrontmatterDescriptionQuoted(unittest.TestCase):
    """Cover lines 440, 455-457 in agents.py."""

    def test_no_closing_frontmatter_returns_unchanged(self):
        from cypilot.commands.agents import _ensure_frontmatter_description_quoted

        content = "---\ndescription: hello\nno closing fence\n"
        self.assertEqual(_ensure_frontmatter_description_quoted(content), content)

    def test_description_with_inline_comment(self):
        from cypilot.commands.agents import _ensure_frontmatter_description_quoted

        content = '---\ndescription: some value # a comment\n---\nbody\n'
        result = _ensure_frontmatter_description_quoted(content)
        self.assertIn('"some value"', result)
        self.assertIn("# a comment", result)


class TestResolveConfigKits(unittest.TestCase):
    """Cover _resolve_config_kits in agents.py."""

    def test_fallback_to_adapter_config_kits(self):
        from cypilot.commands.agents import _resolve_config_kits

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cypilot_root = project_root / "somedir"
            cypilot_root.mkdir()
            # No config/kits at cypilot_root level
            # Create adapter config kits
            (project_root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = "myadapter"\n```\n',
                encoding="utf-8",
            )
            adapter_config_kits = project_root / "myadapter" / "config" / "kits"
            adapter_config_kits.mkdir(parents=True)

            result = _resolve_config_kits(cypilot_root, project_root)
            self.assertEqual(result.resolve(), adapter_config_kits.resolve())

    def test_no_adapter_returns_default(self):
        from cypilot.commands.agents import _resolve_config_kits

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = _resolve_config_kits(root, root)
            # Returns the default config/kits path even if it doesn't exist
            self.assertTrue(str(result).endswith("kits"))


class TestRegisteredKitDirs(unittest.TestCase):
    """Cover line 503 in agents.py."""

    def test_kits_not_dict_returns_none(self):
        from cypilot.commands.agents import _registered_kit_dirs

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text(
                '<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = "cypilot"\n```\n',
                encoding="utf-8",
            )
            cfg_dir = root / "cypilot" / "config"
            cfg_dir.mkdir(parents=True)
            # core.toml with kits as a string instead of dict
            (cfg_dir / "core.toml").write_text(
                'schema_version = "1.0"\nproject_root = ".."\nkits = "not_a_dict"\n',
                encoding="utf-8",
            )
            result = _registered_kit_dirs(root)
            self.assertIsNone(result)


class TestEnsureCypilotLocal(unittest.TestCase):
    """Cover lines 117-132 in agents.py."""

    def test_copy_when_external(self):
        from cypilot.commands.agents import _ensure_cypilot_local

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            # No AGENTS.md → will use default "cypilot" name
            cypilot_root = Path(tmpdir) / "external_cypilot"
            cypilot_root.mkdir()

            # Create a minimal cypilot structure at external root
            (cypilot_root / "skills").mkdir()
            (cypilot_root / "skills" / "test.py").write_text("# test", encoding="utf-8")
            (cypilot_root / "workflows").mkdir()
            (cypilot_root / "workflows" / "wf.md").write_text("# wf", encoding="utf-8")

            result_path, report = _ensure_cypilot_local(cypilot_root, project_root, dry_run=False)
            self.assertEqual(report["action"], "copied")
            self.assertGreater(report["file_count"], 0)
            self.assertTrue((result_path / ".core").is_dir())

    def test_copy_error_returns_error_report(self):
        from cypilot.commands.agents import _ensure_cypilot_local
        from unittest.mock import patch

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            cypilot_root = Path(tmpdir) / "external"
            cypilot_root.mkdir()

            with patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
                result_path, report = _ensure_cypilot_local(cypilot_root, project_root, dry_run=False)
            self.assertEqual(report["action"], "error")
            self.assertIn("denied", report["message"])


class TestListWorkflowFilesConfigKits(unittest.TestCase):
    """Cover kit workflow scanning in agents.py."""

    def test_scans_config_kit_workflows(self):
        from cypilot.commands.agents import _list_workflow_files

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # Create core workflows dir (need .core/ so core_subpath routes there)
            core_wf = root / ".core" / "workflows"
            core_wf.mkdir(parents=True)
            (core_wf / "analyze.md").write_text(
                "---\ntype: workflow\ndescription: analyze\n---\nContent\n",
                encoding="utf-8",
            )

            # Create config kit workflows (new layout)
            config_kit_wf = root / "config" / "kits" / "sdlc" / "workflows"
            config_kit_wf.mkdir(parents=True)
            (config_kit_wf / "pr-review.md").write_text(
                "---\ntype: workflow\ndescription: pr review\n---\nContent\n",
                encoding="utf-8",
            )

            results = _list_workflow_files(root, project_root=None)
            names = [r[0] for r in results]
            self.assertIn("analyze.md", names)
            self.assertIn("pr-review.md", names)

    def test_config_kit_iterdir_exception_is_handled(self):
        from cypilot.commands.agents import _list_workflow_files
        from unittest.mock import patch

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            core_wf = root / ".core" / "workflows"
            core_wf.mkdir(parents=True)

            config_kits = root / "config" / "kits"
            config_kits.mkdir(parents=True)

            original_iterdir = Path.iterdir

            def _boom(self):
                if "kits" in str(self) and "config" in str(self):
                    raise OSError("boom")
                return original_iterdir(self)

            with patch.object(Path, "iterdir", _boom):
                results = _list_workflow_files(root)
            # Should not crash, just return core workflows (empty since no files)
            self.assertIsInstance(results, list)


class TestTargetPathFromRoot(unittest.TestCase):
    """Cover line 52 in agents.py (_target_path_from_root with cypilot_root=None)."""

    def test_cypilot_root_none_returns_cypilot_path_prefix(self):
        from cypilot.commands.agents import _target_path_from_root

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            target = project_root / "some" / "file.md"
            result = _target_path_from_root(target, project_root, cypilot_root=None)
            self.assertEqual(result, "{cf-constructor-path}/some/file.md")


class TestHasNonOpenAIInstallSignal(unittest.TestCase):
    """Cover legacy non-OpenAI install detection branches in agents.py."""

    def test_detects_windsurf_follow_link(self):
        from cypilot.commands.agents import _has_non_openai_install_signal

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_path = root / ".windsurf" / "skills" / "cypilot" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text(
                "ALWAYS open and follow `{cf-constructor-path}/.core/skills/cypilot/SKILL.md`\n",
                encoding="utf-8",
            )

            self.assertTrue(_has_non_openai_install_signal(root))

    def test_detects_cursor_follow_link(self):
        from cypilot.commands.agents import _has_non_openai_install_signal

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rule_path = root / ".cursor" / "rules" / "cypilot.mdc"
            rule_path.parent.mkdir(parents=True)
            rule_path.write_text(
                "ALWAYS open and follow `{cf-constructor-path}/.core/skills/cypilot/SKILL.md`\n",
                encoding="utf-8",
            )

            self.assertTrue(_has_non_openai_install_signal(root))

    def test_detects_legacy_copilot_instructions(self):
        from cypilot.commands.agents import _has_non_openai_install_signal

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            legacy_ci = root / ".github" / "copilot-instructions.md"
            legacy_ci.parent.mkdir(parents=True)
            legacy_ci.write_text("# Cypilot\nLegacy instructions\n", encoding="utf-8")

            self.assertTrue(_has_non_openai_install_signal(root))

    def test_ignores_legacy_copilot_read_errors(self):
        from cypilot.commands.agents import _has_non_openai_install_signal
        from unittest.mock import patch

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            legacy_ci = root / ".github" / "copilot-instructions.md"
            legacy_ci.parent.mkdir(parents=True)
            legacy_ci.write_text("# not cypilot\n", encoding="utf-8")

            original_read_text = Path.read_text

            def _boom(self, *args, **kwargs):
                if self == legacy_ci:
                    raise OSError("denied")
                return original_read_text(self, *args, **kwargs)

            with patch.object(Path, "read_text", _boom):
                self.assertFalse(_has_non_openai_install_signal(root))


class TestLoadJsonFileNonDict(unittest.TestCase):
    """Cover lines 137, 141 in agents.py (_load_json_file edge cases)."""

    def test_json_array_returns_none(self):
        from cypilot.commands.agents import _load_json_file

        with TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.json"
            p.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertIsNone(_load_json_file(p))

    def test_nonexistent_file_returns_none(self):
        from cypilot.commands.agents import _load_json_file

        self.assertIsNone(_load_json_file(Path("/nonexistent/file.json")))


def _with_human_mode(fn):
    """Decorator: temporarily disable JSON mode so ui.* writes to stderr."""
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **kw):
        from cypilot.utils.ui import set_json_mode
        set_json_mode(False)
        try:
            return fn(*a, **kw)
        finally:
            set_json_mode(True)
    return wrapper


class TestHumanAgentsList(unittest.TestCase):
    """Cover lines 1128-1158 (_human_agents_list formatter)."""

    @_with_human_mode
    def test_agents_with_existing_files(self):
        from cypilot.commands.agents import _human_agents_list
        import io
        from contextlib import redirect_stderr

        results = {
            "windsurf": {
                "workflows": {"updated": ["/p/.windsurf/workflows/cypilot-generate.md"], "created": []},
                "skills": {"updated": ["/p/.windsurf/skills/cypilot/SKILL.md"], "created": []},
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_agents_list({}, ["windsurf"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("windsurf", output)
        self.assertIn("2 file(s) installed", output)

    @_with_human_mode
    def test_agents_with_no_files(self):
        from cypilot.commands.agents import _human_agents_list
        import io
        from contextlib import redirect_stderr

        results = {
            "cursor": {
                "workflows": {"updated": [], "created": []},
                "skills": {"updated": [], "created": []},
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_agents_list({}, ["cursor"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("no files", output)

    @_with_human_mode
    def test_agents_not_configured(self):
        from cypilot.commands.agents import _human_agents_list
        import io
        from contextlib import redirect_stderr

        results = {
            "copilot": {
                "workflows": {"updated": [], "created": ["/p/.github/prompts/cypilot-generate.prompt.md"]},
                "skills": {"updated": [], "created": ["/p/.github/copilot-instructions.md"]},
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_agents_list({}, ["copilot"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("not configured", output)

    @_with_human_mode
    def test_no_agents_installed_hint(self):
        from cypilot.commands.agents import _human_agents_list
        import io
        from contextlib import redirect_stderr

        results = {
            "windsurf": {
                "workflows": {"updated": [], "created": []},
                "skills": {"updated": [], "created": []},
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_agents_list({}, ["windsurf"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("cfc generate-agents", output)


class TestHumanGenerateAgentsPreview(unittest.TestCase):
    """Cover lines 1166-1191 (_human_generate_agents_preview formatter)."""

    @_with_human_mode
    def test_preview_with_changes(self):
        from cypilot.commands.agents import _human_generate_agents_preview
        import io
        from contextlib import redirect_stderr

        results = {
            "windsurf": {
                "workflows": {
                    "created": ["/p/.windsurf/workflows/cypilot-generate.md"],
                    "updated": ["/p/.windsurf/workflows/cypilot-analyze.md"],
                },
                "skills": {
                    "created": ["/p/.windsurf/skills/cypilot/SKILL.md"],
                    "updated": [],
                },
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_preview(["windsurf"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("windsurf", output)

    @_with_human_mode
    def test_preview_up_to_date(self):
        from cypilot.commands.agents import _human_generate_agents_preview
        import io
        from contextlib import redirect_stderr

        results = {
            "cursor": {
                "workflows": {"created": [], "updated": []},
                "skills": {"created": [], "updated": []},
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_preview(["cursor"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("up to date", output)

    @_with_human_mode
    def test_preview_up_to_date_reports_skipped_subagents(self):
        from cypilot.commands.agents import _human_generate_agents_preview
        import io
        from contextlib import redirect_stderr

        results = {
            "openai": {
                "workflows": {"created": [], "updated": [], "renamed": [], "deleted": []},
                "skills": {"created": [], "updated": [], "deleted": []},
                "subagents": {
                    "created": [],
                    "updated": [],
                    "skipped": True,
                    "skip_reason": "tool does not support subagents",
                },
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_preview(["openai"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("up to date", output)
        self.assertIn("subagents skipped: tool does not support subagents", output)

    @_with_human_mode
    def test_preview_includes_deletion_only_changes(self):
        from cypilot.commands.agents import _human_generate_agents_preview
        import io
        from contextlib import redirect_stderr

        results = {
            "claude": {
                "workflows": {"created": [], "updated": [], "deleted": []},
                "skills": {
                    "created": [],
                    "updated": [],
                    "deleted": ["/p/.claude/commands/cypilot-plan.md", "/p/.claude/commands/cypilot-generate.md"],
                },
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_preview(["claude"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("claude", output)
        self.assertIn("deleted", output.lower())

    @_with_human_mode
    def test_preview_includes_workflow_renames_and_subagents(self):
        from cypilot.commands.agents import _human_generate_agents_preview
        import io
        from contextlib import redirect_stderr

        results = {
            "claude": {
                "workflows": {
                    "created": [],
                    "updated": [],
                    "renamed": [("/p/.claude/commands/cypilot-old.md", "/p/.claude/commands/cypilot-new.md")],
                    "deleted": [],
                },
                "skills": {"created": [], "updated": [], "deleted": []},
                "subagents": {
                    "created": ["/p/.claude/agents/cypilot-codegen.md"],
                    "updated": [],
                    "skipped": False,
                    "skip_reason": "",
                },
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_preview(["claude"], results, Path("/p"))
        output = err.getvalue()
        self.assertIn("workflow renamed", output)
        self.assertIn("cypilot-codegen.md", output)


class TestHumanGenerateAgentsOk(unittest.TestCase):
    """Cover lines 1194-1252 (_human_generate_agents_ok formatter)."""

    @_with_human_mode
    def test_ok_pass_with_files(self):
        from cypilot.commands.agents import _human_generate_agents_ok
        import io
        from contextlib import redirect_stderr

        results = {
            "windsurf": {
                "status": "PASS",
                "workflows": {
                    "created": ["/p/.windsurf/workflows/cypilot-generate.md"],
                    "updated": ["/p/.windsurf/workflows/cypilot-analyze.md"],
                    "counts": {"created": 1, "updated": 1},
                },
                "skills": {
                    "created": ["/p/.windsurf/skills/cypilot/SKILL.md"],
                    "updated": ["/p/.windsurf/workflows/cypilot.md"],
                    "counts": {"created": 1, "updated": 1},
                },
                "errors": [],
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_ok({"status": "PASS"}, ["windsurf"], results, dry_run=False)
        output = err.getvalue()
        self.assertIn("Agent integration complete", output)

    @_with_human_mode
    def test_ok_dry_run(self):
        from cypilot.commands.agents import _human_generate_agents_ok
        import io
        from contextlib import redirect_stderr

        results = {
            "cursor": {
                "status": "PASS",
                "workflows": {"created": [], "updated": [], "counts": {}},
                "skills": {"created": [], "updated": [], "counts": {}},
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_ok({"status": "PASS"}, ["cursor"], results, dry_run=True)
        output = err.getvalue()
        self.assertIn("Dry run", output)

    @_with_human_mode
    def test_ok_dry_run_uses_future_tense_and_reports_subagents(self):
        from cypilot.commands.agents import _human_generate_agents_ok
        import io
        from contextlib import redirect_stderr

        results = {
            "claude": {
                "status": "PASS",
                "workflows": {
                    "created": [],
                    "updated": [],
                    "renamed": [("/p/.claude/commands/cypilot-old.md", "/p/.claude/commands/cypilot-new.md")],
                    "deleted": ["/p/.claude/commands/cypilot-analyze.md"],
                    "counts": {"created": 0, "updated": 0, "renamed": 1, "deleted": 1},
                },
                "skills": {
                    "created": [],
                    "updated": [],
                    "deleted": ["/p/.claude/commands/cypilot-plan.md", "/p/.claude/commands/cypilot-generate.md"],
                    "skipped": [".claude/commands/cypilot-workspace.md (missing generated marker)", ".claude/commands/cypilot-analyze.md (missing generated marker)"],
                    "counts": {"created": 0, "updated": 0, "deleted": 1, "skipped": 1},
                },
                "subagents": {
                    "created": ["/p/.claude/agents/cypilot-codegen.md"],
                    "updated": [],
                    "skipped": False,
                    "skip_reason": "",
                    "counts": {"created": 1, "updated": 0},
                },
                "errors": [],
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_ok({"status": "PASS"}, ["claude"], results, dry_run=True)
        output = err.getvalue()
        self.assertIn("workflow renamed", output)
        self.assertIn("would be removed", output)
        self.assertIn("would be preserved", output)
        self.assertIn("subagent file(s)", output)

    @_with_human_mode
    def test_ok_with_errors(self):
        from cypilot.commands.agents import _human_generate_agents_ok
        import io
        from contextlib import redirect_stderr

        results = {
            "custom": {
                "status": "ERROR",
                "workflows": {"created": [], "updated": [], "counts": {}},
                "skills": {"created": [], "updated": [], "counts": {}},
                "errors": ["something went wrong"],
            },
        }
        err = io.StringIO()
        with redirect_stderr(err):
            _human_generate_agents_ok({"status": "ERROR"}, ["custom"], results, dry_run=False)
        output = err.getvalue()
        self.assertIn("something went wrong", output)
        self.assertIn("errors", output.lower())


class TestProcessSingleAgentEdgeCases(unittest.TestCase):
    """Cover edge cases in _process_single_agent: non-dict output, kit desc enrichment, workflow deletion."""

    def _make_project(self, tmpdir):
        root = (Path(tmpdir) / "proj").resolve()
        root.mkdir()
        (root / ".git").mkdir()
        cpt = root / "cypilot"
        cpt.mkdir()
        core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
        core_skill.parent.mkdir(parents=True)
        core_skill.write_text(
            "---\nname: cypilot\ndescription: Test skill\n---\nContent\n",
            encoding="utf-8",
        )
        # Create config/kits/sdlc/SKILL.md — the path _process_single_agent reads for enrichment
        kit_skill = cpt / "config" / "kits" / "sdlc" / "SKILL.md"
        kit_skill.parent.mkdir(parents=True)
        kit_skill.write_text(
            "---\nname: sdlc-skill\ndescription: SDLC-ENRICHMENT-SENTINEL\n---\nKit content\n",
            encoding="utf-8",
        )
        return root, cpt

    def test_kit_description_enrichment(self):
        """Skill description is enriched with kit descriptions from config/kits/*/SKILL.md."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)

            cfg = _default_agents_config()
            result = _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=False)
            # Skill file should be generated in .agents/skills/ (shared path)
            agents_skill = root / ".agents" / "skills" / "cf-constructor" / "SKILL.md"
            self.assertTrue(agents_skill.exists(), f"Expected {agents_skill} to exist")
            content = agents_skill.read_text(encoding="utf-8")
            # The kit description from config/kits/sdlc/SKILL.md must appear in the output,
            # proving the enrichment branch in _process_single_agent() ran.
            self.assertIn("SDLC-ENRICHMENT-SENTINEL", content, "Kit description enrichment must be present")

    def test_non_dict_output_cfg_skipped(self):
        """Non-dict entries in outputs list are skipped (line 614)."""
        from cypilot.commands.agents import _process_single_agent

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = {
                "version": 1,
                "agents": {
                    "windsurf": {
                        "workflows": {},
                        "skills": {
                            "outputs": [
                                "not_a_dict",  # should be skipped
                                {
                                    "path": ".windsurf/skills/cypilot/SKILL.md",
                                    "template": ["ALWAYS open and follow `{target_skill_path}`"],
                                },
                            ],
                        },
                    },
                },
            }
            result = _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=True)
            self.assertIn("skills", result)

    def test_stale_workflow_deleted(self):
        """Workflow proxy pointing to non-existent target is deleted (lines 767-774)."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            # Ensure .core/workflows/ exists so core_subpath resolves there
            core_wf = cpt / ".core" / "workflows"
            core_wf.mkdir(parents=True, exist_ok=True)
            # Put a real workflow so the agent generates a valid proxy
            (core_wf / "analyze.md").write_text(
                "---\nname: analyze\ndescription: Analyze artifacts\n---\nContent\n",
                encoding="utf-8",
            )

            wf_dir = root / ".windsurf" / "workflows"
            wf_dir.mkdir(parents=True)
            # Create a stale workflow proxy pointing to a removed workflow
            (wf_dir / "cypilot-old.md").write_text(
                "# /cypilot-old\n\nALWAYS open and follow `{cf-constructor-path}/.core/workflows/old-removed.md`\n",
                encoding="utf-8",
            )
            cfg = _default_agents_config()
            result = _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=False)
            wf = result.get("workflows", {})
            self.assertIn(
                (wf_dir / "cypilot-old.md").as_posix(),
                wf.get("deleted", []),
            )
            # File should be removed
            self.assertFalse((wf_dir / "cypilot-old.md").exists())

    def test_claude_generated_legacy_command_deleted(self):
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)
            (cpt / ".core" / "workflows" / "generate.md").write_text(
                "---\nname: cf-constructor-generate\ndescription: Generate\ntype: workflow\n---\n# Generate\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "analyze.md").write_text(
                "---\nname: cf-constructor-analyze\ndescription: Analyze\ntype: workflow\n---\n# Analyze\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "plan.md").write_text(
                "---\nname: cf-constructor-plan\ndescription: Plan\ntype: workflow\n---\n# Plan\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "workspace.md").write_text(
                "---\nname: cf-constructor-workspace\ndescription: Workspace\ntype: workflow\n---\n# Workspace\n",
                encoding="utf-8",
            )

            legacy_dir = root / ".claude" / "commands"
            legacy_dir.mkdir(parents=True)
            legacy_file = legacy_dir / "cf-constructor-generate.md"
            legacy_file.write_text(
                "# /cf-constructor-generate\n\nALWAYS open and follow `{cf-constructor-path}/.core/workflows/generate.md`\n",
                encoding="utf-8",
            )

            result = _process_single_agent("claude", root, cpt, _default_agents_config(), None, dry_run=False)
            self.assertIn(
                legacy_file.relative_to(root).as_posix(),
                result.get("skills", {}).get("deleted", []),
            )
            self.assertFalse(legacy_file.exists())

    def test_claude_generated_legacy_command_wrong_target_is_preserved(self):
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)
            (cpt / ".core" / "workflows" / "plan.md").write_text(
                "---\nname: cf-constructor-plan\ndescription: Plan\ntype: workflow\n---\n# Plan\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "workspace.md").write_text(
                "---\nname: cf-constructor-workspace\ndescription: Workspace\ntype: workflow\n---\n# Workspace\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "generate.md").write_text(
                "---\nname: cf-constructor-generate\ndescription: Generate\ntype: workflow\n---\n# Generate\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "analyze.md").write_text(
                "---\nname: cf-constructor-analyze\ndescription: Analyze\ntype: workflow\n---\n# Analyze\n",
                encoding="utf-8",
            )

            legacy_dir = root / ".claude" / "commands"
            legacy_dir.mkdir(parents=True)
            legacy_file = legacy_dir / "cf-constructor-generate.md"
            legacy_file.write_text(
                "# /cf-constructor-generate\n\nALWAYS open and follow `{cf-constructor-path}/.core/workflows/analyze.md`\n",
                encoding="utf-8",
            )

            result = _process_single_agent("claude", root, cpt, _default_agents_config(), None, dry_run=False)
            self.assertNotIn(
                legacy_file.relative_to(root).as_posix(),
                result.get("skills", {}).get("deleted", []),
            )
            skipped = result.get("skills", {}).get("skipped", [])
            self.assertTrue(any("missing generated marker" in item for item in skipped))
            self.assertTrue(legacy_file.exists())

    def test_claude_hand_authored_legacy_command_preserved(self):
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)
            (cpt / ".core" / "workflows" / "plan.md").write_text(
                "---\nname: cf-constructor-plan\ndescription: Plan\ntype: workflow\n---\n# Plan\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "generate.md").write_text(
                "---\nname: cf-constructor-generate\ndescription: Generate\ntype: workflow\n---\n# Generate\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "analyze.md").write_text(
                "---\nname: cf-constructor-analyze\ndescription: Analyze\ntype: workflow\n---\n# Analyze\n",
                encoding="utf-8",
            )
            (cpt / ".core" / "workflows" / "workspace.md").write_text(
                "---\nname: cf-constructor-workspace\ndescription: Workspace\ntype: workflow\n---\n# Workspace\n",
                encoding="utf-8",
            )

            legacy_dir = root / ".claude" / "commands"
            legacy_dir.mkdir(parents=True)
            legacy_file = legacy_dir / "cf-constructor-generate.md"
            legacy_file.write_text(
                "# /cf-constructor-generate\n\nCustom instructions stay here.\n",
                encoding="utf-8",
            )

            result = _process_single_agent("claude", root, cpt, _default_agents_config(), None, dry_run=False)
            self.assertNotIn(
                legacy_file.relative_to(root).as_posix(),
                result.get("skills", {}).get("deleted", []),
            )
            skipped = result.get("skills", {}).get("skipped", [])
            self.assertTrue(any("missing generated marker" in item for item in skipped))
            self.assertTrue(legacy_file.exists())

    def test_claude_cleanup_ignores_non_string_output_path(self):
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)
            for workflow_name in ("generate", "analyze", "plan", "workspace"):
                (cpt / ".core" / "workflows" / f"{workflow_name}.md").write_text(
                    f"---\nname: cypilot-{workflow_name}\ndescription: {workflow_name}\n---\n# {workflow_name}\n",
                    encoding="utf-8",
                )

            cfg = _default_agents_config()
            cfg["agents"]["claude"]["skills"]["outputs"].append(
                {"path": 123, "template": ["ALWAYS open and follow `{target_path}`"]},
            )

            result = _process_single_agent("claude", root, cpt, cfg, None, dry_run=True)
            self.assertIn("skills", result)
            self.assertTrue(any("missing path" in err for err in (result.get("errors") or [])))


class TestEnsureCypilotLocalRootDirsAndFiles(unittest.TestCase):
    """Cover lines 123-127, 130-133 by patching _COPY_ROOT_DIRS/_COPY_FILES."""

    def test_copy_root_dirs_and_files(self):
        from cypilot.commands.agents import _ensure_cypilot_local
        from unittest.mock import patch

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            cypilot_root = Path(tmpdir) / "external"
            cypilot_root.mkdir()

            # Create source dirs for _COPY_DIRS
            (cypilot_root / "skills").mkdir()
            (cypilot_root / "skills" / "test.py").write_text("# s", encoding="utf-8")

            # Create a root-level dir and a file for the patched lists
            (cypilot_root / "guides").mkdir()
            (cypilot_root / "guides" / "README.md").write_text("# g", encoding="utf-8")
            (cypilot_root / "VERSION").write_text("1.0", encoding="utf-8")

            with patch("cypilot.commands.agents._COPY_ROOT_DIRS", ["guides"]), \
                 patch("cypilot.commands.agents._COPY_FILES", ["VERSION"]):
                result_path, report = _ensure_cypilot_local(cypilot_root, project_root, dry_run=False)

            self.assertEqual(report["action"], "copied")
            # guides/ should be at local root level (not under .core/)
            self.assertTrue((result_path / "guides" / "README.md").is_file())
            # VERSION should be under .core/
            self.assertTrue((result_path / ".core" / "VERSION").is_file())


class TestCypilotRalphexRegistration(unittest.TestCase):
    """Verify cypilot-ralphex is registered and discoverable by agent generation."""

    def _make_project_with_agents_toml(self, tmpdir):
        root = (Path(tmpdir) / "proj").resolve()
        root.mkdir()
        (root / ".git").mkdir()
        cpt = root / "cypilot"
        cpt.mkdir()
        core_skill = cpt / ".core" / "skills" / "cypilot"
        core_skill.mkdir(parents=True)
        # Copy the real agents.toml
        src_agents_toml = Path(__file__).parent.parent / "skills" / "cypilot" / "agents.toml"
        import shutil
        shutil.copy2(src_agents_toml, core_skill / "agents.toml")
        # Create the prompt files so validation passes (using new cf-constructor names)
        agents_dir = core_skill / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "cf-constructor-ralphex.md").write_text(
            "You are a Cyber Constructor ralphex delegation agent.\n",
            encoding="utf-8",
        )
        (agents_dir / "cf-constructor-codegen.md").write_text(
            "You are a Cyber Constructor code generator.\n",
            encoding="utf-8",
        )
        (agents_dir / "cf-constructor-pr-review.md").write_text(
            "You are a Cyber Constructor PR reviewer.\n",
            encoding="utf-8",
        )
        (agents_dir / "cf-constructor-phase-runner.md").write_text(
            "You are a Cyber Constructor phase runner.\n",
            encoding="utf-8",
        )
        (agents_dir / "cf-constructor-phase-compiler.md").write_text(
            "You are a Cyber Constructor phase compiler.\n",
            encoding="utf-8",
        )
        return root, cpt

    def _make_full_project(self, tmpdir):
        """Create project with core structure needed for _process_single_agent."""
        root, cpt = self._make_project_with_agents_toml(tmpdir)
        core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
        core_skill.write_text(
            "---\nname: cypilot\ndescription: Test skill\n---\nContent\n",
            encoding="utf-8",
        )
        (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)
        return root, cpt

    def test_ralphex_in_agents_toml(self):
        """agents.toml contains a cf-constructor-ralphex entry."""
        agents_toml = Path(__file__).parent.parent / "skills" / "cypilot" / "agents.toml"
        with open(agents_toml, "rb") as f:
            import tomllib
            data = tomllib.load(f)
        agents = data.get("agents", {})
        self.assertIn("cf-constructor-ralphex", agents)
        entry = agents["cf-constructor-ralphex"]
        self.assertEqual(entry["prompt_file"], "agents/cf-constructor-ralphex.md")
        self.assertEqual(entry["mode"], "readwrite")
        self.assertFalse(entry.get("isolation", False))

    def test_ralphex_discovered_by_kit_agents(self):
        """_discover_kit_agents finds cf-constructor-ralphex from agents.toml."""
        from cypilot.commands.agents import _discover_kit_agents

        with TemporaryDirectory() as td:
            root, cpt = self._make_project_with_agents_toml(td)
            agents = _discover_kit_agents(cpt, root)
            names = [a["name"] for a in agents]
            self.assertIn("cf-constructor-ralphex", names)
            ralphex = next(a for a in agents if a["name"] == "cf-constructor-ralphex")
            self.assertEqual(ralphex["mode"], "readwrite")
            self.assertFalse(ralphex["isolation"])
            self.assertIsNotNone(ralphex["prompt_file_abs"])

    def test_ralphex_generates_claude_subagent_proxy(self):
        """Agent generation produces a claude subagent proxy for cf-constructor-ralphex."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_full_project(td)

            cfg = _default_agents_config()
            result = _process_single_agent("claude", root, cpt, cfg, None, dry_run=False)

            subagents = result.get("subagents", {})
            all_files = subagents.get("created", []) + subagents.get("updated", [])
            ralphex_files = [f for f in all_files if "cf-constructor-ralphex" in f]
            self.assertTrue(
                len(ralphex_files) > 0,
                f"Expected cf-constructor-ralphex subagent proxy, got: {all_files}",
            )
            # Verify the generated file uses ALWAYS open and follow
            proxy_path = Path(ralphex_files[0])
            content = proxy_path.read_text(encoding="utf-8")
            self.assertIn("ALWAYS open and follow", content)
            self.assertIn("cf-constructor-ralphex", content)
            # Verify readwrite tools (not readonly)
            self.assertIn("Write", content)
            self.assertIn("Edit", content)

    def test_ralphex_generates_cursor_subagent_proxy(self):
        """Agent generation produces a cursor subagent proxy for cf-constructor-ralphex."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_full_project(td)

            cfg = _default_agents_config()
            result = _process_single_agent("cursor", root, cpt, cfg, None, dry_run=False)

            subagents = result.get("subagents", {})
            all_files = subagents.get("created", []) + subagents.get("updated", [])
            ralphex_files = [f for f in all_files if "cf-constructor-ralphex" in f]
            self.assertTrue(
                len(ralphex_files) > 0,
                f"Expected cf-constructor-ralphex cursor proxy, got: {all_files}",
            )
            proxy_path = Path(ralphex_files[0])
            content = proxy_path.read_text(encoding="utf-8")
            self.assertIn("ALWAYS open and follow", content)
            # Cursor readwrite gets edit tool
            self.assertIn("edit", content)

    def test_ralphex_generates_copilot_subagent_proxy(self):
        """Agent generation produces a copilot subagent proxy for cf-constructor-ralphex."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_full_project(td)

            cfg = _default_agents_config()
            result = _process_single_agent("copilot", root, cpt, cfg, None, dry_run=False)

            subagents = result.get("subagents", {})
            all_files = subagents.get("created", []) + subagents.get("updated", [])
            ralphex_files = [f for f in all_files if "cf-constructor-ralphex" in f]
            self.assertTrue(
                len(ralphex_files) > 0,
                f"Expected cf-constructor-ralphex copilot proxy, got: {all_files}",
            )
            proxy_path = Path(ralphex_files[0])
            content = proxy_path.read_text(encoding="utf-8")
            self.assertIn("ALWAYS open and follow", content)
            # Copilot readwrite gets wildcard tools
            self.assertIn('"*"', content)

    def test_ralphex_generates_openai_toml_entry(self):
        """Agent generation includes cf-constructor-ralphex in OpenAI TOML output."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_full_project(td)

            cfg = _default_agents_config()
            result = _process_single_agent("openai", root, cpt, cfg, None, dry_run=False)

            subagents = result.get("subagents", {})
            all_files = subagents.get("created", []) + subagents.get("updated", [])
            toml_files = [f for f in all_files if "cf-constructor-ralphex.toml" in f]
            self.assertTrue(
                len(toml_files) > 0,
                f"Expected cf-constructor-ralphex.toml, got: {all_files}",
            )
            content = Path(toml_files[0]).read_text(encoding="utf-8")
            self.assertIn("cf-constructor-ralphex", content)
            self.assertIn("ALWAYS open and follow", content)

    def test_ralphex_not_forked_per_tool(self):
        """All generated proxies point to the same canonical prompt path."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_full_project(td)

            canonical_fragment = "skills/cypilot/agents/cypilot-ralphex.md"
            for agent in ("claude", "cursor", "copilot", "openai"):
                cfg = _default_agents_config()
                result = _process_single_agent(agent, root, cpt, cfg, None, dry_run=False)
                subagents = result.get("subagents", {})
                all_files = subagents.get("created", []) + subagents.get("updated", [])
                for fpath in all_files:
                    content = Path(fpath).read_text(encoding="utf-8")
                    if "cypilot-ralphex" in fpath or "cypilot_ralphex" in content:
                        self.assertIn(
                            canonical_fragment,
                            content,
                            f"{agent} proxy does not point to canonical path",
                        )

    def test_windsurf_skill_routes_to_canonical_skill(self):
        """Windsurf skill output references the canonical SKILL.md (delegation routing)."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_full_project(td)

            cfg = _default_agents_config()
            result = _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=False)

            # Windsurf exposes capabilities through SKILL.md routing, not subagent files
            skills = result.get("skills", {})
            skill_files = skills.get("created", []) + skills.get("updated", [])
            self.assertTrue(
                len(skill_files) > 0,
                "Expected windsurf skill outputs to be generated",
            )
            # Verify at least one skill output references the canonical SKILL.md
            found_skill_ref = False
            for fpath in skill_files:
                content = Path(fpath).read_text(encoding="utf-8")
                if "ALWAYS open and follow" in content and "SKILL.md" in content:
                    found_skill_ref = True
                    break
            self.assertTrue(found_skill_ref, "Windsurf skill must reference canonical SKILL.md")

            # Windsurf does not have dedicated subagent proxy files
            subagents = result.get("subagents", {})
            self.assertTrue(
                subagents.get("skipped", False),
                "Windsurf subagents should be skipped (no subagent proxy format)",
            )


class TestReadSourceContentTrustedRoots(unittest.TestCase):
    """Cover trusted_roots parameter in _read_source_content (lines ~2468-2500)."""

    def test_path_inside_trusted_root_is_allowed(self):
        from cypilot.commands.agents import _read_source_content

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            trusted = Path(tmpdir) / "trusted_area"
            trusted.mkdir()
            src_file = trusted / "skill.md"
            src_file.write_text("Skill content here\n", encoding="utf-8")

            result = _read_source_content(
                "skill", "my-skill", str(src_file),
                project_root, cypilot_root=None,
                trusted_roots=[trusted],
            )
            self.assertIsNotNone(result)
            self.assertIn("Skill content here", result)

    def test_path_outside_project_and_trusted_roots_is_rejected(self):
        from cypilot.commands.agents import _read_source_content

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            trusted = Path(tmpdir) / "trusted_area"
            trusted.mkdir()
            untrusted = Path(tmpdir) / "untrusted"
            untrusted.mkdir()
            src_file = untrusted / "escape.md"
            src_file.write_text("escaped content\n", encoding="utf-8")

            result = _read_source_content(
                "skill", "bad-skill", str(src_file),
                project_root, cypilot_root=None,
                trusted_roots=[trusted],
            )
            self.assertIsNone(result)

    def test_path_outside_all_roots_no_trusted_roots_rejected(self):
        from cypilot.commands.agents import _read_source_content

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            src_file = outside / "file.md"
            src_file.write_text("content\n", encoding="utf-8")

            result = _read_source_content(
                "agent", "a1", str(src_file),
                project_root, cypilot_root=None,
                trusted_roots=[],
            )
            self.assertIsNone(result)


class TestCopilotDetection(unittest.TestCase):
    """Copilot agent detection must use .github/.cypilot-installed marker."""

    def test_copilot_detected_via_marker_file(self):
        """Shared _AGENT_MARKERS defines copilot via .github/.cf-constructor-installed."""
        from cypilot.commands.agents import _AGENT_MARKERS
        self.assertIn(".github/.cf-constructor-installed", _AGENT_MARKERS.get("copilot", []))

    def test_copilot_generates_repo_wide_instructions(self):
        """Copilot generation must produce .github/copilot-instructions.md (always-on)."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            (root / ".git").mkdir()
            cpt = root / "cypilot"
            cpt.mkdir()
            core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
            core_skill.parent.mkdir(parents=True)
            core_skill.write_text("---\nname: cypilot\ndescription: Test\n---\nContent\n")
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)
            cfg = _default_agents_config()
            _process_single_agent("copilot", root, cpt, cfg, None, dry_run=False)
            instructions = root / ".github" / "copilot-instructions.md"
            self.assertTrue(instructions.exists(), ".github/copilot-instructions.md must be generated")
            content = instructions.read_text(encoding="utf-8")
            self.assertNotIn("ALWAYS open and follow", content)
            # Marker file must also be created
            marker = root / ".github" / ".cf-constructor-installed"
            self.assertTrue(marker.exists(), ".github/.cf-constructor-installed marker must be created")

    def test_copilot_cleanup_removes_legacy_skill_follow_line(self):
        """Regeneration must clean the old generated follow-line from copilot-instructions.md."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            (root / ".git").mkdir()
            cpt = root / "cypilot"
            cpt.mkdir()
            core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
            core_skill.parent.mkdir(parents=True)
            core_skill.write_text("---\nname: cypilot\ndescription: Test\n---\nContent\n")
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)

            instructions = root / ".github" / "copilot-instructions.md"
            instructions.parent.mkdir(parents=True, exist_ok=True)
            instructions.write_text(
                "# Cypilot\n\nALWAYS open and follow `{cf-constructor-path}/.core/skills/cypilot/SKILL.md`\n",
                encoding="utf-8",
            )

            cfg = _default_agents_config()
            _process_single_agent("copilot", root, cpt, cfg, None, dry_run=False)

            content = instructions.read_text(encoding="utf-8")
            self.assertNotIn("ALWAYS open and follow", content)

    def test_user_authored_copilot_instructions_preserved(self):
        """User-authored copilot-instructions.md must NOT be overwritten by generation."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            (root / ".git").mkdir()
            cpt = root / "cypilot"
            cpt.mkdir()
            core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
            core_skill.parent.mkdir(parents=True)
            core_skill.write_text("---\nname: cypilot\ndescription: Test\n---\nContent\n")
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)

            # Pre-existing user-authored file (no "# Cypilot" header)
            user_content = "# My Project Instructions\nUse TypeScript.\n"
            instructions = root / ".github" / "copilot-instructions.md"
            instructions.parent.mkdir(parents=True, exist_ok=True)
            instructions.write_text(user_content, encoding="utf-8")

            cfg = _default_agents_config()
            result = _process_single_agent("copilot", root, cpt, cfg, None, dry_run=False)

            # User content must be preserved
            self.assertEqual(instructions.read_text(encoding="utf-8"), user_content)
            # Should appear in skipped
            skipped = result.get("skills", {}).get("skipped", [])
            self.assertTrue(
                any("user-authored" in s for s in skipped),
                f"Expected user-authored skip notice, got: {skipped}",
            )
            # Marker IS created even when copilot-instructions.md is user-authored,
            # because other Copilot outputs (prompts, shared skills) are still managed.
            marker = root / ".github" / ".cf-constructor-installed"
            self.assertTrue(marker.exists(),
                ".github/.cf-constructor-installed must be created even with user-authored instructions")

    def test_copilot_detected_via_prompt_file(self):
        """Copilot install detected via .github/prompts/cypilot.prompt.md when marker absent."""
        from cypilot.commands.agents import _is_agent_installed

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            prompt = root / ".github" / "prompts" / "cypilot.prompt.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text("---\nname: cypilot\n---\nALWAYS open and follow ...\n")
            self.assertTrue(_is_agent_installed("copilot", root))

    def test_legacy_windsurf_skill_detected(self):
        """Legacy .windsurf/skills/cypilot/SKILL.md with Cypilot follow-link is detected."""
        from cypilot.commands.agents import _is_agent_installed

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            legacy = root / ".windsurf" / "skills" / "cypilot" / "SKILL.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("ALWAYS open and follow `{cf-constructor-path}/.core/skills/cypilot/SKILL.md`\n")
            self.assertTrue(_is_agent_installed("windsurf", root))

    def test_legacy_cursor_rules_detected(self):
        """Legacy .cursor/rules/cypilot.mdc with Cypilot follow-link is detected."""
        from cypilot.commands.agents import _is_agent_installed

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            legacy = root / ".cursor" / "rules" / "cypilot.mdc"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("ALWAYS open and follow `{cf-constructor-path}/.core/skills/cypilot/SKILL.md`\n")
            self.assertTrue(_is_agent_installed("cursor", root))

    def test_legacy_windsurf_non_cypilot_not_detected(self):
        """Legacy .windsurf/skills/cypilot/SKILL.md without Cypilot target is not detected."""
        from cypilot.commands.agents import _is_agent_installed

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            legacy = root / ".windsurf" / "skills" / "cypilot" / "SKILL.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("# Some non-Cypilot skill content\n")
            self.assertFalse(_is_agent_installed("windsurf", root))

    def test_legacy_copilot_fallback_detection(self):
        """Shared _is_agent_installed has legacy Copilot fallback via Cypilot-managed copilot-instructions.md."""
        import importlib
        src = importlib.util.find_spec("cypilot.commands.agents").origin
        source = Path(src).read_text(encoding="utf-8")
        self.assertIn("legacy_ci", source)
        self.assertIn('startswith("# Cypilot")', source)

    def test_openai_legacy_requires_codex_agents_content(self):
        """Shared _is_agent_installed requires .codex/agents/ with content, not bare .codex/ directory."""
        import importlib
        src = importlib.util.find_spec("cypilot.commands.agents").origin
        source = Path(src).read_text(encoding="utf-8")
        self.assertIn("codex_agents", source)
        self.assertIn("codex_agents.iterdir()", source)


class TestManifestSkillOutputPaths(unittest.TestCase):
    """Manifest v2 skill output paths must use .agents/skills/ for non-Claude tools."""

    def test_non_claude_tools_use_agents_skills_path(self):
        from cypilot.commands.agents import _SKILL_OUTPUT_PATHS

        for tool in ("cursor", "copilot", "openai", "windsurf"):
            self.assertEqual(
                _SKILL_OUTPUT_PATHS[tool], ".agents/skills/{id}/SKILL.md",
                f"{tool} should use shared .agents/skills/ path",
            )

    def test_claude_uses_own_skills_path(self):
        from cypilot.commands.agents import _SKILL_OUTPUT_PATHS

        self.assertEqual(_SKILL_OUTPUT_PATHS["claude"], ".claude/skills/{id}/SKILL.md")


class TestMultiToolCoexistence(unittest.TestCase):
    """Shared .agents/skills/ files must be identical regardless of which tool writes them."""

    def _make_project(self, tmpdir):
        root = (Path(tmpdir) / "proj").resolve()
        root.mkdir()
        (root / ".git").mkdir()
        cpt = root / "cypilot"
        cpt.mkdir()
        core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
        core_skill.parent.mkdir(parents=True)
        core_skill.write_text(
            "---\nname: cypilot\ndescription: Test skill\n---\nContent\n",
            encoding="utf-8",
        )
        (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)
        return root, cpt

    def test_shared_files_identical_across_tools(self):
        """Running windsurf then cursor produces byte-identical .agents/skills/ files."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()

            _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=False)
            skill_after_windsurf = (root / ".agents" / "skills" / "cf-constructor" / "SKILL.md").read_text(encoding="utf-8")

            _process_single_agent("cursor", root, cpt, cfg, None, dry_run=False)
            skill_after_cursor = (root / ".agents" / "skills" / "cf-constructor" / "SKILL.md").read_text(encoding="utf-8")

            self.assertEqual(skill_after_windsurf, skill_after_cursor,
                             "Shared skill file must be identical across tool runs")

    def test_shared_files_no_custom_content_leak(self):
        """Shared .agents/skills/ templates must not contain {custom_content}."""
        from cypilot.commands.agents import _agents_skill_outputs

        for out in _agents_skill_outputs():
            template_text = "\n".join(out["template"])
            self.assertNotIn("{custom_content}", template_text,
                             f"Shared output {out['path']} must not reference custom_content")

    def test_second_tool_reports_shared_unchanged(self):
        """Second tool writing same shared files sees them as unchanged, not updated."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()

            _process_single_agent("openai", root, cpt, cfg, None, dry_run=False)
            r2 = _process_single_agent("cursor", root, cpt, cfg, None, dry_run=False)

            sk = r2.get("skills", {})
            # Only tool-specific files (e.g. .cursor/commands/cf-constructor.md) may be created;
            # shared .agents/skills/ files must not appear in created list
            shared_created = [f for f in sk.get("created", []) if ".agents/skills/" in f]
            self.assertEqual(len(shared_created), 0,
                             f"Shared .agents/skills/ files should not be re-created: {shared_created}")


class TestOpenAIDetection(unittest.TestCase):
    """OpenAI detection and regeneration after generate→detect→update cycle."""

    def _make_project(self, tmpdir):
        root = (Path(tmpdir) / "proj").resolve()
        root.mkdir()
        (root / ".git").mkdir()
        cpt = root / "cypilot"
        cpt.mkdir()
        core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
        core_skill.parent.mkdir(parents=True)
        core_skill.write_text(
            "---\nname: cypilot\ndescription: Test v1\n---\nContent v1\n",
            encoding="utf-8",
        )
        (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)
        agents_md = root / "AGENTS.md"
        agents_md.write_text(
            "<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = \"cypilot\"\n```\n<!-- /@cf:root-agents -->\n",
            encoding="utf-8",
        )
        return root, cpt

    def test_openai_generate_creates_codex_marker(self):
        """OpenAI generation must create .codex/ marker directory."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()
            _process_single_agent("openai", root, cpt, cfg, None, dry_run=False)
            self.assertTrue((root / ".codex").is_dir(), ".codex/ must be created as OpenAI marker")
            self.assertTrue((root / ".codex" / ".cf-constructor-installed").is_file())

    def test_openai_generate_then_detect_regen(self):
        """After generating openai, update detects via .codex/ and regenerates on content change."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config
        from cypilot.commands.update import _maybe_regenerate_agents

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()
            _process_single_agent("openai", root, cpt, cfg, None, dry_run=False)
            self.assertTrue((root / ".codex").is_dir())
            # Simulate core update
            core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
            core_skill.write_text(
                "---\nname: cypilot\ndescription: Test v2\n---\nContent v2\n",
                encoding="utf-8",
            )
            result = _maybe_regenerate_agents({"skills": "updated"}, {}, root, cpt)
            self.assertIn("openai", result)

    def test_cursor_only_does_not_detect_openai(self):
        """Cursor-only install must NOT trigger OpenAI detection/regeneration."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config
        from cypilot.commands.update import _maybe_regenerate_agents

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()
            _process_single_agent("cursor", root, cpt, cfg, None, dry_run=False)
            # .agents/skills/ exists (shared) but .codex/ does not
            self.assertTrue((root / ".agents" / "skills").is_dir())
            self.assertFalse((root / ".codex").exists())
            core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
            core_skill.write_text("---\nname: cypilot\ndescription: v2\n---\nv2\n")
            result = _maybe_regenerate_agents({"skills": "updated"}, {}, root, cpt)
            self.assertIn("cursor", result)
            self.assertNotIn("openai", result)

    def test_windsurf_only_does_not_detect_openai(self):
        """Windsurf-only install must NOT trigger OpenAI detection/regeneration."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config
        from cypilot.commands.update import _maybe_regenerate_agents

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()
            _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=False)
            self.assertTrue((root / ".agents" / "skills").is_dir())
            self.assertFalse((root / ".codex").exists())
            core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
            core_skill.write_text("---\nname: cypilot\ndescription: v2\n---\nv2\n")
            result = _maybe_regenerate_agents({"skills": "updated"}, {}, root, cpt)
            self.assertIn("windsurf", result)
            self.assertNotIn("openai", result)


class TestLegacyManifestSkillCleanup(unittest.TestCase):
    """Legacy manifest-skill files must be cleaned up when migrating to .agents/skills/."""

    def test_cursor_legacy_mdc_deleted(self):
        from cypilot.commands.agents import generate_manifest_skills
        from cypilot.utils.manifest import SkillEntry

        with TemporaryDirectory() as td:
            root = Path(td).resolve()
            legacy = root / ".cursor" / "rules" / "my-rule.mdc"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("ALWAYS open and follow `{cf-constructor-path}/.core/skills/my-rule/SKILL.md`\n")
            src = root / "skills" / "my-rule.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Rule")
            skills = {"my-rule": SkillEntry(id="my-rule", description="A rule", prompt_file="", source=str(src), agents=["cursor"])}
            r = generate_manifest_skills(skills, "cursor", root, dry_run=False)
            self.assertFalse(legacy.exists(), "Legacy .cursor/rules/my-rule.mdc should be deleted")
            # All skills go to shared .agents/skills/ (agent filtering via frontmatter)
            self.assertTrue((root / ".agents" / "skills" / "my-rule" / "SKILL.md").is_file(),
                "Skill must go to .agents/skills/my-rule/SKILL.md")
            deleted = [o["path"] for o in r.get("outputs", []) if o.get("action") == "deleted"]
            self.assertIn(".cursor/rules/my-rule.mdc", deleted)

    def test_cursor_legacy_user_customized_not_deleted(self):
        """User-customized legacy files without generated marker must NOT be deleted."""
        from cypilot.commands.agents import generate_manifest_skills
        from cypilot.utils.manifest import SkillEntry

        with TemporaryDirectory() as td:
            root = Path(td).resolve()
            legacy = root / ".cursor" / "rules" / "my-rule.mdc"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("# User-customized content without marker\n")
            src = root / "skills" / "my-rule.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Rule")
            skills = {"my-rule": SkillEntry(id="my-rule", description="A rule", prompt_file="", source=str(src), agents=["cursor"])}
            r = generate_manifest_skills(skills, "cursor", root, dry_run=False)
            self.assertTrue(legacy.exists(), "User-customized legacy file must NOT be deleted")

    def test_legacy_non_cypilot_target_not_deleted(self):
        """Legacy file with non-Cypilot follow target must NOT be deleted."""
        from cypilot.commands.agents import generate_manifest_skills
        from cypilot.utils.manifest import SkillEntry

        with TemporaryDirectory() as td:
            root = Path(td).resolve()
            legacy = root / ".cursor" / "rules" / "my-rule.mdc"
            legacy.parent.mkdir(parents=True)
            # Follow target is NOT a Cypilot path (no {cf-constructor-path}/ prefix)
            legacy.write_text("ALWAYS open and follow `some/other/tool/skill.md`\n")
            src = root / "skills" / "my-rule.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Rule")
            skills = {"my-rule": SkillEntry(id="my-rule", description="A rule", prompt_file="", source=str(src), agents=["cursor"])}
            r = generate_manifest_skills(skills, "cursor", root, dry_run=False)
            self.assertTrue(legacy.exists(), "Legacy file with non-Cypilot target must NOT be deleted")

    def test_windsurf_legacy_skill_deleted(self):
        from cypilot.commands.agents import generate_manifest_skills
        from cypilot.utils.manifest import SkillEntry

        with TemporaryDirectory() as td:
            root = Path(td).resolve()
            legacy = root / ".windsurf" / "skills" / "my-rule" / "SKILL.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("ALWAYS open and follow `{cf-constructor-path}/.core/skills/my-rule/SKILL.md`\n")
            src = root / "skills" / "my-rule.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Rule")
            skills = {"my-rule": SkillEntry(id="my-rule", description="A rule", prompt_file="", source=str(src), agents=["windsurf"])}
            r = generate_manifest_skills(skills, "windsurf", root, dry_run=False)
            self.assertFalse(legacy.exists(), "Legacy .windsurf/skills/my-rule/SKILL.md should be deleted")

    def test_cursor_legacy_generated_body_deleted(self):
        """Old generated manifest skill bodies must also be cleaned up during migration."""
        from cypilot.commands.agents import generate_manifest_skills
        from cypilot.utils.manifest import SkillEntry

        with TemporaryDirectory() as td:
            root = Path(td).resolve()
            legacy = root / ".cursor" / "rules" / "my-rule.mdc"
            legacy.parent.mkdir(parents=True)
            src = root / "skills" / "my-rule.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Rule\n", encoding="utf-8")
            # Legacy file must match the content the generator now produces
            # (frontmatter + body) so matches_generated_body triggers deletion.
            legacy.write_text(
                '---\nname: my-rule\ndescription: "A rule"\n---\n# My Rule\n',
                encoding="utf-8",
            )
            skills = {"my-rule": SkillEntry(id="my-rule", description="A rule", prompt_file="", source=str(src), agents=["cursor"])}
            r = generate_manifest_skills(skills, "cursor", root, dry_run=False)
            self.assertFalse(legacy.exists(), "Legacy generated manifest skill should be deleted")
            deleted = [o["path"] for o in r.get("outputs", []) if o.get("action") == "deleted"]
            self.assertIn(".cursor/rules/my-rule.mdc", deleted)

    def test_no_legacy_no_deletion(self):
        """When no legacy file exists, cleanup produces no deletions."""
        from cypilot.commands.agents import generate_manifest_skills
        from cypilot.utils.manifest import SkillEntry

        with TemporaryDirectory() as td:
            root = Path(td).resolve()
            src = root / "skills" / "my-rule.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Rule")
            skills = {"my-rule": SkillEntry(id="my-rule", description="A rule", prompt_file="", source=str(src), agents=["cursor"])}
            r = generate_manifest_skills(skills, "cursor", root, dry_run=False)
            deleted = [o["path"] for o in r.get("outputs", []) if o.get("action") == "deleted"]
            self.assertEqual(len(deleted), 0)

    def test_manifest_cleanup_respects_skill_agents(self):
        """Cleanup must NOT delete legacy files for skills that don't target the current agent."""
        from cypilot.commands.agents import generate_manifest_skills
        from cypilot.utils.manifest import SkillEntry

        with TemporaryDirectory() as td:
            root = Path(td).resolve()
            # Legacy copilot file for a skill that targets only openai
            legacy = root / ".github" / "skills" / "openai-only.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("ALWAYS open and follow `{cf-constructor-path}/.core/skills/openai-only/SKILL.md`\n")
            src = root / "skills" / "openai-only.md"
            src.parent.mkdir(parents=True)
            src.write_text("# OpenAI Only")
            skills = {"openai-only": SkillEntry(id="openai-only", description="OpenAI skill", prompt_file="", source=str(src), agents=["openai"])}
            r = generate_manifest_skills(skills, "copilot", root, dry_run=False)
            self.assertTrue(legacy.exists(), "Legacy file for non-targeted skill must NOT be deleted")
            deleted = [o["path"] for o in r.get("outputs", []) if o.get("action") == "deleted"]
            self.assertEqual(len(deleted), 0)


class TestAtSlashPathNotTreatedAsCypilot(unittest.TestCase):
    """Files with @/ follow-link targets must NOT be treated as Cypilot-generated."""

    def test_at_slash_target_not_deleted_by_legacy_cleanup(self):
        from cypilot.commands.agents import generate_manifest_skills
        from cypilot.utils.manifest import SkillEntry

        with TemporaryDirectory() as td:
            root = Path(td).resolve()
            # Legacy file with @/ target (project-relative, not Cypilot-specific)
            legacy = root / ".cursor" / "rules" / "my-rule.mdc"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("ALWAYS open and follow `@/docs/my-custom-skill.md`\n")
            src = root / "skills" / "my-rule.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Rule")
            skills = {"my-rule": SkillEntry(id="my-rule", description="A rule", prompt_file="", source=str(src), agents=["cursor"])}
            r = generate_manifest_skills(skills, "cursor", root, dry_run=False)
            self.assertTrue(legacy.exists(), "File with @/ target must NOT be deleted")

    def test_at_slash_target_not_detected_as_windsurf_install(self):
        from cypilot.commands.agents import _is_agent_installed

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            legacy = root / ".windsurf" / "skills" / "cypilot" / "SKILL.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("ALWAYS open and follow `@/docs/my-custom-skill.md`\n")
            self.assertFalse(_is_agent_installed("windsurf", root),
                "@/ target must not trigger windsurf detection")


class TestKitWorkflowSharedSkills(unittest.TestCase):
    """Kit workflow skills in .agents/skills/ must be generated for non-Claude agents with workflows."""

    def _make_project(self, td):
        root = (Path(td) / "proj").resolve()
        root.mkdir()
        (root / ".git").mkdir()
        cpt = root / "cypilot"
        cpt.mkdir()
        core_skill = cpt / ".core" / "skills" / "cypilot" / "SKILL.md"
        core_skill.parent.mkdir(parents=True)
        core_skill.write_text("---\nname: cypilot\ndescription: Test\n---\nContent\n")
        wf_dir = cpt / ".core" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "generate.md").write_text("---\nname: cypilot-generate\ndescription: Generate\n---\n# Gen\n")
        (wf_dir / "analyze.md").write_text("---\nname: cypilot-analyze\ndescription: Analyze\n---\n# Ana\n")
        (wf_dir / "plan.md").write_text("---\nname: cypilot-plan\ndescription: Plan\n---\n# Plan\n")
        (wf_dir / "workspace.md").write_text("---\nname: cypilot-workspace\ndescription: Workspace\n---\n# WS\n")
        return root, cpt

    def test_cursor_generates_shared_kit_workflow_skills(self):
        """Cursor must generate .agents/skills/cf-constructor-generate/SKILL.md for kit workflows."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()
            _process_single_agent("cursor", root, cpt, cfg, None, dry_run=False)
            shared_skill = root / ".agents" / "skills" / "cf-constructor-generate" / "SKILL.md"
            self.assertTrue(shared_skill.exists(),
                ".agents/skills/cf-constructor-generate/SKILL.md must be generated for cursor")

    def test_windsurf_generates_shared_kit_workflow_skills(self):
        """Windsurf must generate .agents/skills/cf-constructor-generate/SKILL.md for kit workflows."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()
            _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=False)
            shared_skill = root / ".agents" / "skills" / "cf-constructor-generate" / "SKILL.md"
            self.assertTrue(shared_skill.exists(),
                ".agents/skills/cf-constructor-generate/SKILL.md must be generated for windsurf")

    def test_copilot_generates_shared_kit_workflow_skills(self):
        """Copilot must generate .agents/skills/cf-constructor-generate/SKILL.md for kit workflows."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()
            _process_single_agent("copilot", root, cpt, cfg, None, dry_run=False)
            shared_skill = root / ".agents" / "skills" / "cf-constructor-generate" / "SKILL.md"
            self.assertTrue(shared_skill.exists(),
                ".agents/skills/cf-constructor-generate/SKILL.md must be generated for copilot")


class TestIsPureCypilotGenerated(unittest.TestCase):
    """Regression: _is_pure_cypilot_generated must distinguish pure stubs from customized files."""

    def test_pure_stub_is_detected(self):
        from cypilot.commands.agents import _is_pure_cypilot_generated

        content = (
            "---\nname: cypilot\ndescription: Cypilot skill\n---\n\n"
            "ALWAYS open and follow `{cf-constructor-path}/.core/workflows/generate.md`\n"
        )
        self.assertTrue(_is_pure_cypilot_generated(content))

    def test_stub_with_user_content_is_not_pure(self):
        from cypilot.commands.agents import _is_pure_cypilot_generated

        content = (
            "---\nname: cypilot\ndescription: Cypilot skill\n---\n\n"
            "ALWAYS open and follow `{cf-constructor-path}/.core/workflows/generate.md`\n\n"
            "## My custom notes\nSome user-authored content here.\n"
        )
        self.assertFalse(_is_pure_cypilot_generated(content))

    def test_no_follow_link_is_not_pure(self):
        from cypilot.commands.agents import _is_pure_cypilot_generated

        content = "---\nname: test\n---\n\nJust some content.\n"
        self.assertFalse(_is_pure_cypilot_generated(content))

    def test_non_cypilot_follow_link_is_not_pure(self):
        from cypilot.commands.agents import _is_pure_cypilot_generated

        content = (
            "---\nname: other\n---\n\n"
            "ALWAYS open and follow `@/some/other/path.md`\n"
        )
        self.assertFalse(_is_pure_cypilot_generated(content))


class TestLegacyCleanupPreservesCustomizedFiles(unittest.TestCase):
    """Regression: legacy cleanup must preserve files that contain a Cypilot follow-link
    plus additional user-authored content."""

    def _make_project(self, tmpdir):
        root = Path(tmpdir) / "project"
        root.mkdir()
        (root / ".git").mkdir()
        (root / "AGENTS.md").write_text(
            '<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = ".bootstrap"\n```\n',
            encoding="utf-8",
        )
        cpt = root / ".bootstrap"
        cpt.mkdir()
        core = cpt / ".core"
        core.mkdir()
        (core / "workflows").mkdir()
        (core / "workflows" / "generate.md").write_text(
            "---\ntype: workflow\ndescription: gen\n---\nContent\n", encoding="utf-8",
        )
        (core / "core.toml").write_text(
            'schema_version = "1.0"\nproject_root = ".."\n', encoding="utf-8",
        )
        return root, cpt

    def test_customized_legacy_skill_file_preserved(self):
        """A .windsurf/skills/cypilot/SKILL.md with user content must NOT be deleted."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            legacy = root / ".windsurf" / "skills" / "cypilot"
            legacy.mkdir(parents=True)
            customized_content = (
                "---\nname: cypilot\ndescription: Cypilot skill\n---\n\n"
                "ALWAYS open and follow `{cf-constructor-path}/.core/workflows/generate.md`\n\n"
                "## My team notes\nDo NOT remove — this is our custom setup.\n"
            )
            (legacy / "SKILL.md").write_text(customized_content, encoding="utf-8")

            cfg = _default_agents_config()
            result = _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=False)
            # The legacy file must still exist
            self.assertTrue((legacy / "SKILL.md").is_file(),
                "Customized legacy file must be preserved, not deleted")
            # And it must NOT appear in the deleted list
            deleted = result.get("skills", {}).get("deleted", [])
            self.assertNotIn(".windsurf/skills/cypilot/SKILL.md", deleted)


class TestOpenAIDetectionNoCypilotFalsePositive(unittest.TestCase):
    """Regression: _is_agent_installed('openai') must not trigger on non-Cypilot Codex agents."""

    def test_non_cypilot_codex_agent_not_detected(self):
        from cypilot.commands.agents import _is_agent_installed

        with TemporaryDirectory() as td:
            root = Path(td)
            agents_dir = root / ".codex" / "agents"
            agents_dir.mkdir(parents=True)
            # A non-Cypilot agent that uses a follow-link to a non-Cypilot path
            (agents_dir / "my-tool.md").write_text(
                "---\nname: my-tool\n---\n\n"
                "ALWAYS open and follow `@/tools/my-tool/instructions.md`\n",
                encoding="utf-8",
            )
            self.assertFalse(_is_agent_installed("openai", root),
                "Non-Cypilot Codex agent must not trigger OpenAI legacy detection")

    def test_cypilot_codex_agent_detected(self):
        from cypilot.commands.agents import _is_agent_installed

        with TemporaryDirectory() as td:
            root = Path(td)
            agents_dir = root / ".codex" / "agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "cypilot.md").write_text(
                "---\nname: cypilot\n---\n\n"
                "ALWAYS open and follow `{cf-constructor-path}/.core/workflows/generate.md`\n",
                encoding="utf-8",
            )
            self.assertTrue(_is_agent_installed("openai", root),
                "Cypilot Codex agent must be detected as OpenAI legacy install")


class TestCopilotCustomContent(unittest.TestCase):
    """Regression: Copilot custom_content must be properly applied to the /cypilot skill proxy."""

    def _make_project(self, tmpdir):
        root = Path(tmpdir) / "project"
        root.mkdir()
        (root / ".git").mkdir()
        (root / "AGENTS.md").write_text(
            '<!-- @cf:root-agents -->\n```toml\ncf-constructor-path = ".bootstrap"\n```\n',
            encoding="utf-8",
        )
        cpt = root / ".bootstrap"
        cpt.mkdir()
        core = cpt / ".core"
        core.mkdir()
        (core / "skills").mkdir(parents=True)
        (core / "skills" / "cypilot").mkdir()
        (core / "skills" / "cypilot" / "SKILL.md").write_text(
            "---\nname: cypilot\ndescription: Cypilot skill\n---\n\nCore skill content\n",
            encoding="utf-8",
        )
        (core / "workflows").mkdir()
        (core / "core.toml").write_text(
            'schema_version = "1.0"\nproject_root = ".."\n', encoding="utf-8",
        )
        return root, cpt

    def test_copilot_custom_content_in_skill_proxy(self):
        """Copilot custom_content must appear in .github/prompts/cypilot.prompt.md skill proxy."""
        from cypilot.commands.agents import _process_single_agent, _default_agents_config

        with TemporaryDirectory() as td:
            root, cpt = self._make_project(td)
            cfg = _default_agents_config()

            # Add custom_content to Copilot skills config
            if isinstance(cfg, dict) and isinstance(cfg.get("agents"), dict):
                if isinstance(cfg["agents"].get("copilot"), dict):
                    if isinstance(cfg["agents"]["copilot"].get("skills"), dict):
                        cfg["agents"]["copilot"]["skills"]["custom_content"] = (
                            "## Custom Copilot Instructions\nUse this for special settings.\n"
                        )

            result = _process_single_agent("copilot", root, cpt, cfg, None, dry_run=False)

            # Check that the skill proxy file was created and contains custom_content
            skill_proxy = root / ".github" / "prompts" / "cf-constructor.prompt.md"
            self.assertTrue(skill_proxy.is_file(),
                ".github/prompts/cf-constructor.prompt.md must be generated")

            content = skill_proxy.read_text(encoding="utf-8")
            self.assertIn("## Custom Copilot Instructions", content,
                "custom_content must appear in the /cypilot skill proxy")
            self.assertIn("ALWAYS open and follow", content,
                "skill proxy must contain follow-link directive")


class TestManifestSkillAgentFiltering(unittest.TestCase):
    """All manifest skills go to .agents/skills/, agent scoping via filtering logic."""

    def test_cursor_scoped_skill_not_generated_for_copilot(self):
        """A Cursor-scoped skill must not be generated when processing Copilot."""
        from cypilot.commands.agents import generate_manifest_skills

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            skill_file = root / "cursor-only-skill.md"
            skill_file.write_text("---\nname: cursor-only\n---\n\nSkill content\n")

            skill_entry = type('SkillEntry', (), {
                'agents': ['cursor'],  # Scoped to Cursor only
                'source': str(skill_file),
                'prompt_file': None,
                'description': 'Cursor-only skill',
                'append': None,
                'frontmatter': {},
            })()

            skills = {'cursor-only': skill_entry}

            # Generate for Copilot - should skip this skill
            result = generate_manifest_skills(skills, 'copilot', root, dry_run=False)

            # No files should be created
            shared_skill = root / ".agents" / "skills" / "cursor-only" / "SKILL.md"
            self.assertFalse(shared_skill.is_file(),
                "Cursor-scoped skill must not be generated for Copilot")

    def test_shared_skill_generated_for_all_agents(self):
        """A shared skill (agents=[]) must be generated for all agents."""
        from cypilot.commands.agents import generate_manifest_skills

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            skill_file = root / "shared-skill.md"
            skill_file.write_text("---\nname: shared\n---\n\nShared content\n")

            skill_entry = type('SkillEntry', (), {
                'agents': [],  # Empty = shared across all agents
                'source': str(skill_file),
                'prompt_file': None,
                'description': 'Shared skill',
                'append': None,
                'frontmatter': {},
            })()

            skills = {'shared': skill_entry}

            # Generate for Cursor
            result = generate_manifest_skills(skills, 'cursor', root, dry_run=False)

            # Should create in shared .agents/skills/
            shared_skill = root / ".agents" / "skills" / "shared" / "SKILL.md"
            self.assertTrue(shared_skill.is_file(),
                ".agents/skills/shared/SKILL.md must exist for shared skill")

    def test_manifest_skill_missing_source_skipped(self):
        """Manifest skills with no source and no prompt_file are skipped with warning."""
        from cypilot.commands.agents import generate_manifest_skills
        import sys
        from io import StringIO

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Skill with neither source nor prompt_file
            skill_entry = type('SkillEntry', (), {
                'agents': [],
                'source': None,  # No source
                'prompt_file': None,  # No prompt_file
                'description': 'Broken skill',
                'append': None,
                'frontmatter': {},
            })()

            skills = {'broken': skill_entry}

            # Capture stderr
            old_stderr = sys.stderr
            sys.stderr = StringIO()

            try:
                result = generate_manifest_skills(skills, 'cursor', root, dry_run=False)
                stderr_output = sys.stderr.getvalue()
            finally:
                sys.stderr = old_stderr

            # Should warn about missing source
            self.assertIn("WARNING", stderr_output)
            self.assertIn("broken", stderr_output)
            # No files should be created
            self.assertFalse((root / ".agents" / "skills" / "broken" / "SKILL.md").exists())


class TestWriteOrSkipPathTraversal(unittest.TestCase):
    """Cover path traversal ValueError in _write_or_skip (lines 316-320)."""

    def test_path_traversal_raises_error(self):
        from cypilot.commands.agents import _write_or_skip

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            escaped_path = project_root / ".." / "escaped"

            result = {
                "created": [],
                "updated": [],
                "unchanged": [],
                "outputs": [],
            }

            # Path that escapes project_root should raise ValueError
            with self.assertRaises(ValueError) as ctx:
                _write_or_skip(escaped_path, "content", result, project_root, dry_run=False)
            self.assertIn("path traversal", str(ctx.exception))




class TestRenderTomlAgentNonStringDescription(unittest.TestCase):
    """Cover non-string description handling in _render_toml_agent (line 493)."""

    def test_non_string_description_converted_to_string(self):
        from cypilot.commands.agents import _render_toml_agent

        agent = {
            "name": "test-agent",
            "description": 123,  # Non-string description
        }

        result = _render_toml_agent(agent, "{cf-constructor-path}/test.md")
        self.assertIn("name = ", result)
        self.assertIn('description = "123"', result)

    def test_none_description_handled(self):
        from cypilot.commands.agents import _render_toml_agent

        agent = {
            "name": "test-agent",
            "description": None,  # None description
        }

        result = _render_toml_agent(agent, "{cf-constructor-path}/test.md")
        self.assertIn('description = ""', result)


class TestExpectedClaudeLegacyTargetsNonCypilot(unittest.TestCase):
    """Cover non-cypilot skill filtering in _expected_claude_legacy_targets (line 866)."""

    def test_non_cypilot_skill_returns_empty_set(self):
        from cypilot.commands.agents import _expected_claude_legacy_targets

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cypilot_root = project_root / "cypilot"
            cypilot_root.mkdir()

            # Skill that doesn't start with "cypilot-"
            result = _expected_claude_legacy_targets("my-skill", project_root, cypilot_root)
            self.assertEqual(result, set())

            # Non-string skill
            result = _expected_claude_legacy_targets(123, project_root, cypilot_root)
            self.assertEqual(result, set())


class TestStripWrappingYamlQuotes(unittest.TestCase):
    """Cover _strip_wrapping_yaml_quotes utility function."""

    def test_strip_double_quotes_with_escapes(self):
        from cypilot.commands.agents import _strip_wrapping_yaml_quotes

        value = '"hello \\"world\\" string"'
        result = _strip_wrapping_yaml_quotes(value)
        self.assertEqual(result, 'hello "world" string')

    def test_strip_double_quotes_with_newlines(self):
        from cypilot.commands.agents import _strip_wrapping_yaml_quotes

        value = '"line1\\nline2"'
        result = _strip_wrapping_yaml_quotes(value)
        self.assertEqual(result, "line1\nline2")

    def test_strip_single_quotes(self):
        from cypilot.commands.agents import _strip_wrapping_yaml_quotes

        value = "'single quoted'"
        result = _strip_wrapping_yaml_quotes(value)
        self.assertEqual(result, "single quoted")

    def test_no_quotes_returns_unchanged(self):
        from cypilot.commands.agents import _strip_wrapping_yaml_quotes

        value = "no quotes here"
        result = _strip_wrapping_yaml_quotes(value)
        self.assertEqual(result, value)


class TestYamlDoubleQuote(unittest.TestCase):
    """Cover _yaml_double_quote utility function."""

    def test_escapes_double_quotes(self):
        from cypilot.commands.agents import _yaml_double_quote

        result = _yaml_double_quote('say "hello"')
        self.assertEqual(result, '"say \\"hello\\""')

    def test_escapes_backslashes(self):
        from cypilot.commands.agents import _yaml_double_quote

        result = _yaml_double_quote("path\\to\\file")
        self.assertEqual(result, '"path\\\\to\\\\file"')

    def test_escapes_newlines(self):
        from cypilot.commands.agents import _yaml_double_quote

        result = _yaml_double_quote("line1\nline2")
        self.assertEqual(result, '"line1\\nline2"')


class TestNormalizeAgentTargetPath(unittest.TestCase):
    """Cover target path normalization branches (lines 884-886)."""

    def test_normalize_cypilot_path_prefix(self):
        from cypilot.commands.agents import _normalize_agent_target_path

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            current_file = project_root / "skill.md"
            cypilot_root = project_root / "cypilot"

            # Path starting with {cf-constructor-path}/ should pass through
            result = _normalize_agent_target_path(
                "{cf-constructor-path}/workflows/analyze.md",
                current_file,
                project_root,
                cypilot_root,
            )
            self.assertEqual(result, "{cf-constructor-path}/workflows/analyze.md")

    def test_normalize_at_prefix(self):
        from cypilot.commands.agents import _normalize_agent_target_path

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            current_file = project_root / "skill.md"
            cypilot_root = project_root / "cypilot"

            # Path starting with @/ should pass through
            result = _normalize_agent_target_path(
                "@/workflows/test.md",
                current_file,
                project_root,
                cypilot_root,
            )
            self.assertEqual(result, "@/workflows/test.md")

    def test_normalize_absolute_path(self):
        from cypilot.commands.agents import _normalize_agent_target_path

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            current_file = project_root / "skill.md"
            cypilot_root = project_root / "cypilot"

            # Absolute path should use posix()
            result = _normalize_agent_target_path(
                "/workflows/test.md",
                current_file,
                project_root,
                cypilot_root,
            )
            self.assertEqual(result, "/workflows/test.md")

    def test_normalize_relative_path(self):
        from cypilot.commands.agents import _normalize_agent_target_path

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            current_file = project_root / "subdir" / "skill.md"
            cypilot_root = project_root / "cypilot"

            # Relative path should be normalized from current file
            result = _normalize_agent_target_path(
                "workflows/test.md",
                current_file,
                project_root,
                cypilot_root,
            )
            self.assertIn("workflows", result)


class TestLooksLikeGeneratedClaudeLegacyCommand(unittest.TestCase):
    """Cover _looks_like_generated_claude_legacy_command edge cases."""

    def test_empty_content_returns_false(self):
        from cypilot.commands.agents import _looks_like_generated_claude_legacy_command

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cypilot_root = project_root / "cypilot"

            result = _looks_like_generated_claude_legacy_command(
                "   ",  # Whitespace only
                expected_targets=set(),
                current_file=project_root / "test.md",
                project_root=project_root,
                cypilot_root=cypilot_root,
            )
            self.assertFalse(result)

    def test_mismatched_pattern_returns_false(self):
        from cypilot.commands.agents import _looks_like_generated_claude_legacy_command

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cypilot_root = project_root / "cypilot"

            # Content that doesn't match the pattern
            content = "Some random content\nNot matching"
            result = _looks_like_generated_claude_legacy_command(
                content,
                expected_targets=set(),
                current_file=project_root / "test.md",
                project_root=project_root,
                cypilot_root=cypilot_root,
            )
            self.assertFalse(result)

    def test_pattern_without_follow_link_returns_false(self):
        from cypilot.commands.agents import _looks_like_generated_claude_legacy_command

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            cypilot_root = project_root / "cypilot"

            # Has the header pattern but not the follow link
            content = "# /some/command\n\nSome content"
            result = _looks_like_generated_claude_legacy_command(
                content,
                expected_targets=set(),
                current_file=project_root / "test.md",
                project_root=project_root,
                cypilot_root=cypilot_root,
            )
            self.assertFalse(result)


class TestParsingEdgeCases(unittest.TestCase):
    """Cover parsing edge cases in agents.py."""

    def test_parse_frontmatter_with_no_closing_fence(self):
        from cypilot.commands.agents import _parse_frontmatter

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.md"
            path.write_text("---\nkey: value\nno close\n", encoding="utf-8")

            result = _parse_frontmatter(path)
            # Should return empty dict when no closing fence
            self.assertEqual(result, {})

    def test_parse_frontmatter_not_starting_with_fence(self):
        from cypilot.commands.agents import _parse_frontmatter

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.md"
            path.write_text("no fence\n---\nkey: value\n---\n", encoding="utf-8")

            result = _parse_frontmatter(path)
            # Should return empty dict when doesn't start with ---
            self.assertEqual(result, {})


class TestExtractCypilotFollowTarget(unittest.TestCase):
    """Cover _extract_cypilot_follow_target utility."""

    def test_extracts_cypilot_path_target(self):
        from cypilot.commands.agents import _extract_cypilot_follow_target

        content = "Some text\nALWAYS open and follow `{cf-constructor-path}/test.md`\n"
        result = _extract_cypilot_follow_target(content)
        self.assertEqual(result, "{cf-constructor-path}/test.md")

    def test_rejects_non_cypilot_path(self):
        from cypilot.commands.agents import _extract_cypilot_follow_target

        content = "ALWAYS open and follow `@/test.md`\n"
        result = _extract_cypilot_follow_target(content)
        self.assertIsNone(result)

    def test_no_follow_link_returns_none(self):
        from cypilot.commands.agents import _extract_cypilot_follow_target

        content = "Some text without follow link\n"
        result = _extract_cypilot_follow_target(content)
        self.assertIsNone(result)


class TestIsPureCypilotGeneratedV2(unittest.TestCase):
    """Cover _is_pure_cypilot_generated checks."""

    def test_pure_generated_with_frontmatter(self):
        from cypilot.commands.agents import _is_pure_cypilot_generated

        # Canonical frontmatter (only name + description) → pure
        content = "---\nname: test\ndescription: A skill\n---\nALWAYS open and follow `{cf-constructor-path}/test.md`\n"
        result = _is_pure_cypilot_generated(content)
        self.assertTrue(result)

    def test_custom_frontmatter_key_not_pure(self):
        from cypilot.commands.agents import _is_pure_cypilot_generated

        # Non-canonical key (type) means user-customised frontmatter → not pure
        content = "---\ntype: command\n---\nALWAYS open and follow `{cf-constructor-path}/test.md`\n"
        result = _is_pure_cypilot_generated(content)
        self.assertFalse(result)

    def test_with_user_content_not_pure(self):
        from cypilot.commands.agents import _is_pure_cypilot_generated

        content = "---\nname: test\ndescription: A skill\n---\nALWAYS open and follow `{cf-constructor-path}/test.md`\n\nUser added content here\n"
        result = _is_pure_cypilot_generated(content)
        self.assertFalse(result)

    def test_no_follow_link_not_pure(self):
        from cypilot.commands.agents import _is_pure_cypilot_generated

        content = "---\ntype: command\n---\nSome content\n"
        result = _is_pure_cypilot_generated(content)
        self.assertFalse(result)


class TestValidateAgentEntry(unittest.TestCase):
    """Cover _validate_agent_entry edge cases."""

    def test_agent_with_path_separator_returns_none(self):
        from cypilot.commands.agents import _validate_agent_entry
        import sys
        from io import StringIO

        with TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)

            # Agent name with path separator
            old_stderr = sys.stderr
            sys.stderr = StringIO()
            try:
                result = _validate_agent_entry(
                    "agent/name",  # "/" is invalid
                    {"description": "Test"},
                    source_dir,
                    set(),
                )
            finally:
                sys.stderr = old_stderr

            self.assertIsNone(result)

    def test_duplicate_agent_name_returns_none(self):
        from cypilot.commands.agents import _validate_agent_entry

        with TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)
            seen = {"test-agent"}

            # Same name already seen
            result = _validate_agent_entry(
                "test-agent",
                {"description": "Test"},
                source_dir,
                seen,
            )
            self.assertIsNone(result)

    def test_non_dict_info_returns_none(self):
        from cypilot.commands.agents import _validate_agent_entry

        with TemporaryDirectory() as tmpdir:
            source_dir = Path(tmpdir)

            # info is not a dict
            result = _validate_agent_entry(
                "test",
                "not a dict",  # Should be dict
                source_dir,
                set(),
            )
            self.assertIsNone(result)


class TestFileHasCypilotFollowLink(unittest.TestCase):
    """Cover _file_has_cypilot_follow_link checks."""

    def test_file_does_not_exist(self):
        from cypilot.commands.agents import _file_has_cypilot_follow_link

        result = _file_has_cypilot_follow_link(Path("/nonexistent/file.md"))
        self.assertFalse(result)

    def test_file_exists_with_follow_link(self):
        from cypilot.commands.agents import _file_has_cypilot_follow_link

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.md"
            path.write_text(
                "# /test\n\nALWAYS open and follow `{cf-constructor-path}/test.md`\n",
                encoding="utf-8",
            )
            result = _file_has_cypilot_follow_link(path)
            self.assertTrue(result)

    def test_file_exists_without_follow_link(self):
        from cypilot.commands.agents import _file_has_cypilot_follow_link

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.md"
            path.write_text("# /test\n\nSome content\n", encoding="utf-8")
            result = _file_has_cypilot_follow_link(path)
            self.assertFalse(result)

    def test_read_error_returns_false(self):
        from cypilot.commands.agents import _file_has_cypilot_follow_link
        from unittest.mock import patch

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.md"
            path.write_text("content", encoding="utf-8")

            # Mock read_text to raise OSError
            with patch.object(Path, "read_text", side_effect=OSError("denied")):
                result = _file_has_cypilot_follow_link(path)
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
