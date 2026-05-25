"""Golden-snapshot test: feed the real skills/cypilot/agents.toml through
the new pipeline and assert per-tool output for each existing agent.

This test pins the deliberate behaviour changes documented in spec §7 and §11:
  (a) Codex .toml now emits `model = "..."` for non-inherit agents.
  (b) `fast` agents resolve to gpt-5.4 (not gpt-5.4-mini) on Codex — balanced tier.
  (c) Post-§11 tuning: scanner/migrator/verifier are now cf:tier:cheap (haiku);
      pr-review and migrate-planner remain cf:tier:balanced (sonnet).
All other per-tool output stays byte-identical to today.
"""
import sys
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_TOML = REPO_ROOT / "skills" / "studio" / "agents.toml"

_BALANCED_AGENTS = (
    "cf-pr-review",
    "cf-ralphex",
    "cf-phase-runner",
    "cf-phase-compiler",
    "cf-migrate-planner",
    "cf-semantic-reviewer-artifact",
    "cf-semantic-reviewer-code",
    "cf-code-bug-finder",
    "cf-semantic-reviewer-prompt",
    "cf-prompt-bug-finder",
    "cf-pdsl-author",
    "cf-pdsl-transformer",
    "cf-pdsl-reviewer",
    "cf-semantic-reviewer-consistency",
    "cf-brainstorm-facilitator",
    "cf-brainstorm-expert",
    "cf-generate-author-middle",
    "cf-generate-author-senior",
    "cf-generate-prompt-engineer-smart",
)

_BALANCED_CODEGEN_AGENTS = (
    "cf-codegen",
    "cf-generate-coder-smart",
)

# Agents at cf:tier:cheap that resolve to the base (haiku-tier) model id.
# These do NOT hit the (cheap, analyze|planning, codebase) override because
# their target is "any" or their role is "generate".
_CHEAP_AGENTS = (
    "cf-migrate-migrator",
    "cf-deterministic-validator",
    "cf-generate-collector",
    "cf-diff-scope-resolver",
    "cf-analyze-planner",
    "cf-generate-planner",
    "cf-generate-author",
    "cf-generate-author-junior",
    "cf-generate-coder-casual",
    "cf-generate-prompt-engineer-casual",
)

# Agents at cf:tier:cheap whose (role, target) combination triggers the
# matrix override (cheap, analyze, codebase) → sonnet-equivalent. They are
# intentionally upgraded away from haiku because they read project source
# files and haiku-tier models miss residual matches.
_CHEAP_OVERRIDE_AGENTS = (
    "cf-migrate-scanner",
    "cf-migrate-verifier",
)

# Union for meta-field invariants (all cheap-tier agents, however they resolve).
_ALL_CHEAP_AGENTS = _CHEAP_AGENTS + _CHEAP_OVERRIDE_AGENTS

_EXPENSIVE_AGENTS = (
    "cf-generate-author-lead",
)

_INHERIT_AGENTS = (
)

# All tuned agents (balanced + cheap) — used for meta-field checks
_TUNED_AGENTS = (
    _BALANCED_AGENTS
    + _BALANCED_CODEGEN_AGENTS
    + _ALL_CHEAP_AGENTS
    + _EXPENSIVE_AGENTS
    + _INHERIT_AGENTS
)


class TestExistingAgentsSnapshot(unittest.TestCase):
    def _load_agents(self):
        import tomllib
        with open(AGENTS_TOML, "rb") as f:
            data = tomllib.load(f)
        from studio.commands.agents import _validate_agent_entry
        out = {}
        for name, info in data.get("agents", {}).items():
            entry = _validate_agent_entry(name, info, AGENTS_TOML.parent, set())
            if entry is not None:
                out[name] = entry
        return out

    # ------------------------------------------------------------------
    # Balanced agents (pr-review, migrate-planner) — sonnet-tier
    # ------------------------------------------------------------------

    def test_balanced_agents_resolve_to_gpt_5_4_on_codex(self):
        """spec §7 delta (b): balanced tier → gpt-5.4 on Codex."""
        from studio.commands.agents import _resolve_model_id
        agents = self._load_agents()
        for name in _BALANCED_AGENTS:
            entry = agents[name]
            self.assertEqual(
                entry["model"], "cf:tier:balanced",
                f"{name}: expected cf:tier:balanced",
            )
            got = _resolve_model_id(
                "codex", "openai", entry["model"], entry["role"], entry["target"]
            )
            self.assertEqual(got, "gpt-5.4", f"{name}: codex balanced → gpt-5.4")

    def test_balanced_codegen_agents_resolve_to_gpt_5_3_codex(self):
        """spec §11: balanced generate/codebase agents use Codex-specialized model."""
        from studio.commands.agents import _resolve_model_id
        agents = self._load_agents()
        for name in _BALANCED_CODEGEN_AGENTS:
            entry = agents[name]
            self.assertEqual(
                entry["model"], "cf:tier:balanced",
                f"{name}: expected cf:tier:balanced",
            )
            got = _resolve_model_id(
                "codex", "openai", entry["model"], entry["role"], entry["target"]
            )
            self.assertEqual(
                got, "gpt-5.3-codex",
                f"{name}: codex balanced generate/codebase → gpt-5.3-codex",
            )

    def test_balanced_agents_emit_sonnet_on_claude(self):
        """spec §7: Claude proxy for balanced agents emits model: sonnet."""
        from studio.commands.agents import _agent_template_claude
        agents = self._load_agents()
        for name in _BALANCED_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_claude(entry))
            self.assertIn("model: sonnet", out, f"{name}: claude balanced → sonnet")

    def test_balanced_agents_emit_sonnet_on_cursor(self):
        """spec §7: Cursor proxy for balanced agents emits model: claude-sonnet-4-6."""
        from studio.commands.agents import _agent_template_cursor
        agents = self._load_agents()
        for name in _BALANCED_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_cursor(entry))
            self.assertIn(
                "model: claude-sonnet-4-6", out,
                f"{name}: cursor balanced → claude-sonnet-4-6",
            )

    def test_balanced_agents_emit_sonnet_on_copilot(self):
        """spec §7: Copilot proxy for balanced agents emits model: Claude Sonnet 4.6."""
        from studio.commands.agents import _agent_template_copilot
        agents = self._load_agents()
        for name in _BALANCED_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_copilot(entry))
            self.assertIn(
                "model: Claude Sonnet 4.6", out,
                f"{name}: copilot balanced → Claude Sonnet 4.6",
            )

    # ------------------------------------------------------------------
    # Cheap agents (scanner, migrator, verifier) — haiku-tier
    # ------------------------------------------------------------------

    def test_cheap_agents_resolve_to_gpt_5_4_mini_on_codex(self):
        """spec §11: cheap tier → gpt-5.4-mini on Codex."""
        from studio.commands.agents import _resolve_model_id
        agents = self._load_agents()
        for name in _CHEAP_AGENTS:
            entry = agents[name]
            self.assertEqual(
                entry["model"], "cf:tier:cheap",
                f"{name}: expected cf:tier:cheap",
            )
            got = _resolve_model_id(
                "codex", "openai", entry["model"], entry["role"], entry["target"]
            )
            self.assertEqual(got, "gpt-5.4-mini", f"{name}: codex cheap → gpt-5.4-mini")

    def test_cheap_agents_emit_haiku_on_claude(self):
        """spec §11: Claude proxy for cheap agents emits model: haiku."""
        from studio.commands.agents import _agent_template_claude
        agents = self._load_agents()
        for name in _CHEAP_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_claude(entry))
            self.assertIn("model: haiku", out, f"{name}: claude cheap → haiku")

    def test_cheap_agents_emit_haiku_on_cursor(self):
        """spec §11: Cursor proxy for cheap agents emits model: claude-haiku-4-5."""
        from studio.commands.agents import _agent_template_cursor
        agents = self._load_agents()
        for name in _CHEAP_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_cursor(entry))
            self.assertIn(
                "model: claude-haiku-4-5", out,
                f"{name}: cursor cheap → claude-haiku-4-5",
            )

    def test_cheap_agents_emit_haiku_on_copilot(self):
        """spec §11: Copilot proxy for cheap agents emits model: Claude Haiku 4.5."""
        from studio.commands.agents import _agent_template_copilot
        agents = self._load_agents()
        for name in _CHEAP_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_copilot(entry))
            self.assertIn(
                "model: Claude Haiku 4.5", out,
                f"{name}: copilot cheap → Claude Haiku 4.5",
            )

    # ------------------------------------------------------------------
    # Cheap agents that hit the (cheap, analyze, codebase) override —
    # intentionally upgraded to the sonnet-equivalent for codebase-reading
    # analyze work (scanner, verifier). Documented in skills/cypilot/agents.toml.
    # ------------------------------------------------------------------

    def test_cheap_override_agents_emit_sonnet_on_claude(self):
        from studio.commands.agents import _agent_template_claude
        agents = self._load_agents()
        for name in _CHEAP_OVERRIDE_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_claude(entry))
            self.assertIn(
                "model: sonnet", out,
                f"{name}: claude (cheap, analyze, codebase) → sonnet",
            )

    def test_cheap_override_agents_emit_sonnet_on_cursor(self):
        from studio.commands.agents import _agent_template_cursor
        agents = self._load_agents()
        for name in _CHEAP_OVERRIDE_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_cursor(entry))
            self.assertIn(
                "model: claude-sonnet-4-6", out,
                f"{name}: cursor (cheap, analyze, codebase) → claude-sonnet-4-6",
            )

    def test_cheap_override_agents_emit_sonnet_on_copilot(self):
        from studio.commands.agents import _agent_template_copilot
        agents = self._load_agents()
        for name in _CHEAP_OVERRIDE_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_copilot(entry))
            self.assertIn(
                "model: Claude Sonnet 4.6", out,
                f"{name}: copilot (cheap, analyze, codebase) → Claude Sonnet 4.6",
            )

    def test_cheap_override_agents_resolve_to_gpt_5_4_on_codex(self):
        from studio.commands.agents import _resolve_model_id
        agents = self._load_agents()
        for name in _CHEAP_OVERRIDE_AGENTS:
            entry = agents[name]
            got = _resolve_model_id(
                "codex", "openai", entry["model"], entry["role"], entry["target"],
            )
            self.assertEqual(
                got, "gpt-5.4",
                f"{name}: codex (cheap, analyze, codebase) → gpt-5.4",
            )

    # ------------------------------------------------------------------
    # Inherit agents — no model line emitted
    # ------------------------------------------------------------------

    def test_inherit_agents_emit_no_codex_model_line(self):
        """spec §7: inherit agents must not emit a model = line in Codex TOML."""
        from studio.commands.agents import _render_toml_agent
        agents = self._load_agents()
        for name in _INHERIT_AGENTS:
            entry = agents[name]
            self.assertEqual(
                entry["model"], "cf:inherit",
                f"{name}: model must be cf:inherit",
            )
            out = _render_toml_agent(entry, "p")
            self.assertNotIn("model =", out, f"{name}: codex inherit must omit model line")

    def test_manifest_codex_agent_uses_top_level_schema(self):
        """Manifest-generated Codex agents must use top-level role-file fields."""
        import tomllib
        from studio.commands.agents import _build_openai_agent_file

        agent = SimpleNamespace(
            id="cf-constructor-brainstorm-expert",
            description="Brainstorm expert.",
            append="",
        )
        translated = {
            "sandbox_mode": "workspace-write",
            "model": "gpt-5.4",
            "model_reasoning_effort": "medium",
            "model_context_window": 128000,
        }

        content, rel_out = _build_openai_agent_file(
            "cf-constructor-brainstorm-expert",
            agent,
            translated,
            "Follow the expert prompt.",
            ".codex/agents/{id}.toml",
            variables=None,
        )

        self.assertEqual(rel_out, ".codex/agents/cf-constructor-brainstorm-expert.toml")
        self.assertNotIn("[agents.", content)
        data = tomllib.loads(content)
        self.assertEqual(data["name"], "cf-constructor-brainstorm-expert")
        self.assertEqual(data["description"], "Brainstorm expert.")
        self.assertEqual(data["sandbox_mode"], "workspace-write")
        self.assertEqual(data["model"], "gpt-5.4")
        self.assertEqual(data["model_reasoning_effort"], "medium")
        self.assertEqual(data["model_context_window"], 128000)
        self.assertEqual(data["developer_instructions"], "Follow the expert prompt.\n")

    def test_manifest_codex_agent_resolves_context_window_low(self):
        """Codex agents with cf:tier:cheap context window resolve to 200000."""
        import tomllib
        from studio.commands.agents import _build_openai_agent_file, _CODEX_CONTEXT_TOKENS

        agent = SimpleNamespace(
            id="cf-constructor-test-agent",
            description="Test agent.",
            append="",
        )
        translated = {
            "sandbox_mode": "workspace-write",
            "model": "gpt-5.4",
            "model_reasoning_effort": "low",
            "model_context_window": _CODEX_CONTEXT_TOKENS["low"],
        }

        content, _ = _build_openai_agent_file(
            "cf-constructor-test-agent",
            agent,
            translated,
            "Test prompt.",
            ".codex/agents/{id}.toml",
            variables=None,
        )

        data = tomllib.loads(content)
        self.assertEqual(data["model_context_window"], _CODEX_CONTEXT_TOKENS["low"])

    def test_manifest_codex_agent_resolves_context_window_high(self):
        """Codex agents with cf:tier:balanced context window resolve to 600000."""
        import tomllib
        from studio.commands.agents import _build_openai_agent_file, _CODEX_CONTEXT_TOKENS

        agent = SimpleNamespace(
            id="cf-constructor-test-agent",
            description="Test agent.",
            append="",
        )
        translated = {
            "sandbox_mode": "workspace-write",
            "model": "gpt-5.4",
            "model_reasoning_effort": "medium",
            "model_context_window": _CODEX_CONTEXT_TOKENS["high"],
        }

        content, _ = _build_openai_agent_file(
            "cf-constructor-test-agent",
            agent,
            translated,
            "Test prompt.",
            ".codex/agents/{id}.toml",
            variables=None,
        )

        data = tomllib.loads(content)
        self.assertEqual(data["model_context_window"], _CODEX_CONTEXT_TOKENS["high"])

    def test_legacy_openai_cleanup_preserves_diverged_marker_file(self):
        """Marker-bearing legacy files are preserved when content has diverged."""
        from studio.commands.agents import _delete_generated_legacy_file, _build_legacy_openai_agent_file
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            legacy = project_root / ".agents" / "my-agent" / "agent.toml"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                "# Generated by cf agents -- do not edit\n"
                "[agents.my_agent]\n"
                'description = "user edited this generated copy"\n',
                encoding="utf-8",
            )
            result = {"outputs": []}

            # Build expected legacy content using the production function
            agent = SimpleNamespace(
                id="my-agent",
                description="Test agent",
                append="",
            )
            source_content = "Agent prompt content.\n"
            expected_legacy = _build_legacy_openai_agent_file(
                "my-agent",
                agent,
                {
                    "sandbox_mode": "workspace-write",
                },
                source_content,
                variables=None,
            )

            deleted = _delete_generated_legacy_file(
                legacy,
                "my-agent",
                result,
                project_root,
                dry_run=False,
                expected_content=expected_legacy,
            )

            self.assertFalse(deleted)
            self.assertTrue(legacy.exists())
            self.assertEqual(result.get("deleted", []), [])
            self.assertTrue(result.get("warnings"), "preserved diverged file must be surfaced")

    def test_human_formatter_surfaces_all_v2_agent_outputs_and_warnings(self):
        """Human agent setup output includes preserved/deleted v2 outcomes."""
        from studio.commands.agents import _human_generate_agents_ok
        from studio.utils.ui import set_json_mode

        buf = io.StringIO()
        set_json_mode(False)
        try:
            with redirect_stderr(buf):
                _human_generate_agents_ok(
                    {"status": "PASS"},
                    ["claude"],
                    {
                        "claude": {
                            "status": "PASS",
                            "workflows": {"created": [], "updated": [], "counts": {}},
                            "skills": {"created": [], "updated": [], "counts": {}},
                            "subagents": {"created": [], "updated": [], "counts": {}},
                            "v2_agents": {
                                "created": [],
                                "updated": [],
                                "deleted": ["/tmp/project/.claude/agents/old.md"],
                                "outputs": [
                                    {
                                        "path": ".claude/agents/old.md",
                                        "action": "deleted",
                                        "reason": "skipped_agent_stale_artifact",
                                    },
                                    {
                                        "path": ".claude/agents/custom.md",
                                        "action": "preserved",
                                        "reason": "unverifiable_skipped_agent_stale_artifact",
                                    },
                                ],
                                "warnings": [
                                    {
                                        "path": ".claude/agents/custom.md",
                                        "action": "preserved",
                                        "reason": "unverifiable_skipped_agent_stale_artifact",
                                    },
                                ],
                            },
                        }
                    },
                    dry_run=False,
                )
        finally:
            set_json_mode(True)

        out = buf.getvalue()
        self.assertIn("old.md", out)
        self.assertIn("deleted", out)
        self.assertIn("custom.md", out)
        self.assertIn("preserved", out)
        self.assertIn("unverifiable_skipped_agent_stale_artifact", out)

    def test_subagent_stale_toml_cleanup_preserves_non_owned_file(self):
        """Stale Codex TOML cleanup must not delete prefix-matching user files."""
        from studio.commands.agents import _process_subagents

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / ".codex" / "agents"
            output_dir.mkdir(parents=True)

            prompt = project_root / ".cf-constructor" / "agents" / "worker.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text("# worker", encoding="utf-8")

            stale = output_dir / "cf-constructor-user-custom.toml"
            stale.write_text(
                'name = "cf-constructor-user-custom"\n'
                'description = "User file"\n'
                'developer_instructions = """\n'
                "custom instructions\n"
                '"""\n',
                encoding="utf-8",
            )

            with patch(
                "studio.commands.agents._discover_kit_agents",
                return_value=[
                    {
                        "name": "worker",
                        "description": "Worker",
                        "prompt_file_abs": prompt,
                    }
                ],
            ):
                result = _process_subagents(
                    "openai",
                    project_root,
                    project_root,
                    {},
                    None,
                    dry_run=False,
                )

            self.assertTrue(stale.exists())
            self.assertEqual(result["deleted"], [])
            preserved = [
                o
                for o in result["outputs"]
                if o.get("action") == "preserved"
                and o.get("reason") == "stale_subagent_toml_not_owned"
            ]
            self.assertEqual(len(preserved), 1)

    def test_subagent_stale_toml_cleanup_deletes_owned_matching_file(self):
        """Stale Codex TOML cleanup deletes only canonical generator-owned files."""
        from studio.commands.agents import _process_subagents, _render_toml_agent

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / ".codex" / "agents"
            output_dir.mkdir(parents=True)

            prompt = project_root / "agents" / "worker.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text(
                "---\n"
                'description: "Worker"\n'
                "---\n"
                "# worker\n",
                encoding="utf-8",
            )

            stale_prompt = project_root / "agents" / "cf-constructor-stale.md"
            stale_prompt.write_text(
                "---\n"
                'description: "Stale"\n'
                "---\n"
                "# stale\n",
                encoding="utf-8",
            )

            stale = output_dir / "cf-constructor-stale.toml"
            stale.write_text(
                _render_toml_agent(
                    {"name": "cf-constructor-stale", "description": "Stale"},
                    "{cf-studio-path}/agents/cf-constructor-stale.md",
                ),
                encoding="utf-8",
            )

            with patch(
                "studio.commands.agents._discover_kit_agents",
                return_value=[
                    {
                        "name": "worker",
                        "description": "Worker",
                        "prompt_file_abs": prompt,
                    }
                ],
            ):
                result = _process_subagents(
                    "openai",
                    project_root,
                    project_root,
                    {},
                    None,
                    dry_run=False,
                )

            self.assertFalse(stale.exists())
            deleted_paths = {Path(path).resolve().as_posix() for path in result["deleted"]}
            self.assertIn(stale.resolve().as_posix(), deleted_paths)
            deleted = [
                o
                for o in result["outputs"]
                if o.get("action") == "deleted"
                and o.get("reason") == "stale_subagent_toml_cleanup"
            ]
            self.assertEqual(len(deleted), 1)

    def test_subagent_stale_toml_cleanup_deletes_owned_file_with_model_field(self):
        """Stale Codex TOML with permitted extra fields (model) is still deleted when owned."""
        from studio.commands.agents import _process_subagents, _render_toml_agent

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / ".codex" / "agents"
            output_dir.mkdir(parents=True)

            prompt = project_root / "agents" / "worker.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text(
                "---\n"
                'description: "Worker"\n'
                "---\n"
                "# worker\n",
                encoding="utf-8",
            )

            stale_prompt = project_root / "agents" / "cf-constructor-stale.md"
            stale_prompt.write_text(
                "---\n"
                'description: "Stale"\n'
                "---\n"
                "# stale\n",
                encoding="utf-8",
            )

            # Build TOML with model field appended
            base_toml = _render_toml_agent(
                {"name": "cf-constructor-stale", "description": "Stale"},
                "{cf-studio-path}/agents/cf-constructor-stale.md",
            )
            stale_toml_content = base_toml.rstrip("\n") + "\n" + 'model = "gpt-5.4"\n'

            stale = output_dir / "cf-constructor-stale.toml"
            stale.write_text(stale_toml_content, encoding="utf-8")

            with patch(
                "studio.commands.agents._discover_kit_agents",
                return_value=[
                    {
                        "name": "worker",
                        "description": "Worker",
                        "prompt_file_abs": prompt,
                    }
                ],
            ):
                result = _process_subagents(
                    "openai",
                    project_root,
                    project_root,
                    {},
                    None,
                    dry_run=False,
                )

            self.assertFalse(stale.exists())
            deleted_paths = {Path(path).resolve().as_posix() for path in result["deleted"]}
            self.assertIn(stale.resolve().as_posix(), deleted_paths)
            deleted = [
                o
                for o in result["outputs"]
                if o.get("action") == "deleted"
                and o.get("reason") == "stale_subagent_toml_cleanup"
            ]
            self.assertEqual(len(deleted), 1)

    def test_subagent_stale_toml_cleanup_preserves_unsupported_model_field_type(self):
        """Unsupported optional TOML field values are treated as local drift."""
        from studio.commands.agents import _process_subagents, _render_toml_agent

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / ".codex" / "agents"
            output_dir.mkdir(parents=True)

            prompt = project_root / "agents" / "worker.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text(
                "---\n"
                'description: "Worker"\n'
                "---\n"
                "# worker\n",
                encoding="utf-8",
            )

            stale_prompt = project_root / "agents" / "cf-constructor-stale.md"
            stale_prompt.write_text(
                "---\n"
                'description: "Stale"\n'
                "---\n"
                "# stale\n",
                encoding="utf-8",
            )

            base_toml = _render_toml_agent(
                {"name": "cf-constructor-stale", "description": "Stale"},
                "{cf-studio-path}/agents/cf-constructor-stale.md",
            )
            stale = output_dir / "cf-constructor-stale.toml"
            stale.write_text(
                base_toml.rstrip("\n") + "\nmodel_context_window = 1.5\n",
                encoding="utf-8",
            )

            with patch(
                "studio.commands.agents._discover_kit_agents",
                return_value=[
                    {
                        "name": "worker",
                        "description": "Worker",
                        "prompt_file_abs": prompt,
                    }
                ],
            ):
                result = _process_subagents(
                    "openai",
                    project_root,
                    project_root,
                    {},
                    None,
                    dry_run=False,
                )

            self.assertTrue(stale.exists())
            deleted_paths = {Path(path).resolve().as_posix() for path in result["deleted"]}
            self.assertNotIn(stale.resolve().as_posix(), deleted_paths)

    def test_subagent_stale_toml_cleanup_preserves_marker_file_with_local_drift(self):
        """Marker-bearing stale Codex TOML with local drift must be preserved."""
        from studio.commands.agents import _process_subagents

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / ".codex" / "agents"
            output_dir.mkdir(parents=True)

            prompt = project_root / ".cf-constructor" / "agents" / "worker.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text("# worker", encoding="utf-8")

            stale = output_dir / "cf-constructor-stale.toml"
            stale.write_text(
                "# Generated by cf-constructor agents -- do not edit\n"
                'name = "cf-constructor-stale"\n'
                'description = "locally edited stale description"\n'
                'model_reasoning_effort = "high"\n'
                'developer_instructions = """\n'
                "ALWAYS open and follow `{cf-studio-path}/agents/stale.md`\n"
                '"""\n',
                encoding="utf-8",
            )

            with patch(
                "studio.commands.agents._discover_kit_agents",
                return_value=[
                    {
                        "name": "worker",
                        "description": "Worker",
                        "prompt_file_abs": prompt,
                    }
                ],
            ):
                result = _process_subagents(
                    "openai",
                    project_root,
                    project_root,
                    {},
                    None,
                    dry_run=False,
                )

            self.assertTrue(stale.exists())
            self.assertEqual(result["deleted"], [])
            preserved = [
                o
                for o in result["outputs"]
                if o.get("action") == "preserved"
                and o.get("reason") == "stale_subagent_toml_not_owned"
            ]
            self.assertEqual(len(preserved), 1)

    def test_subagent_stale_toml_cleanup_preserves_marker_file_without_expected_payload(self):
        """Stale Codex TOML is preserved when canonical content is unavailable."""
        from studio.commands.agents import _process_subagents

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / ".codex" / "agents"
            output_dir.mkdir(parents=True)

            prompt = project_root / ".cf-constructor" / "agents" / "worker.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text("# worker", encoding="utf-8")

            stale = output_dir / "cf-constructor-stale.toml"
            stale.write_text(
                "# Generated by cf-constructor agents -- do not edit\n"
                'name = "cf-constructor-stale"\n'
                'description = "stale"\n'
                'developer_instructions = """\n'
                "ALWAYS open and follow `{cf-studio-path}/agents/stale.md`\n"
                '"""\n',
                encoding="utf-8",
            )

            with patch(
                "studio.commands.agents._discover_kit_agents",
                return_value=[
                    {
                        "name": "worker",
                        "description": "Worker",
                        "prompt_file_abs": prompt,
                    }
                ],
            ):
                result = _process_subagents(
                    "openai",
                    project_root,
                    project_root,
                    {},
                    None,
                    dry_run=False,
                )

            self.assertTrue(stale.exists())
            self.assertNotIn(stale.as_posix(), result["deleted"])
            preserved = [
                o
                for o in result["outputs"]
                if o.get("action") == "preserved"
                and o.get("reason") == "stale_subagent_toml_not_owned"
            ]
            self.assertEqual(len(preserved), 1)
            self.assertEqual(result["errors"], [])

    # ------------------------------------------------------------------
    # §11 meta-field checks: all tuned agents carry role/type/effort/context
    # ------------------------------------------------------------------

    def test_all_agents_have_tuned_meta_fields(self):
        """spec §11: every agent in agents.toml declares role, type, reasoning_effort, context_window."""
        agents = self._load_agents()
        for name in _TUNED_AGENTS:
            entry = agents[name]
            self.assertIn(
                entry["role"], {"generate", "analyze", "planning", "any"},
                f"{name}: unexpected role {entry['role']!r}",
            )
            self.assertIn(
                entry["target"], {"codebase", "artifacts", "any"},
                f"{name}: unexpected target {entry['target']!r}",
            )
            self.assertIsNotNone(
                entry["reasoning_effort"],
                f"{name}: reasoning_effort must be set",
            )
            self.assertIsNotNone(
                entry["context_window"],
                f"{name}: context_window must be set",
            )

    def test_tuning_table_exact_values(self):
        """spec §11 tuning table: verify exact (role, type, effort, context) per agent."""
        agents = self._load_agents()
        expected = {
            "cf-codegen":          ("generate", "codebase", "medium", "high"),
            "cf-pr-review":        ("analyze",  "any",      "high",   "high"),
            "cf-ralphex":          ("any",      "any",      "medium", "medium"),
            "cf-phase-runner":     ("generate", "any",      "high",   "high"),
            "cf-phase-compiler":   ("planning", "artifacts","high",   "medium"),
            "cf-migrate-scanner":  ("analyze",  "codebase", "low",    "high"),
            "cf-migrate-planner":  ("planning", "any",      "high",   "medium"),
            "cf-migrate-migrator": ("generate", "any",      "low",    "medium"),
            "cf-migrate-verifier": ("analyze",  "codebase", "low",    "high"),
            "cf-diff-scope-resolver":        ("analyze",  "any",      "low",    "medium"),
            "cf-deterministic-validator":     ("analyze",  "any",      "low",    "medium"),
            "cf-semantic-reviewer-artifact":  ("analyze",  "artifacts","high",   "high"),
            "cf-semantic-reviewer-code":      ("analyze",  "codebase", "high",   "high"),
            "cf-code-bug-finder":             ("analyze",  "codebase", "high",   "high"),
            "cf-semantic-reviewer-prompt":    ("analyze",  "any",      "high",   "high"),
            "cf-prompt-bug-finder":           ("analyze",  "any",      "high",   "high"),
            "cf-pdsl-author":       ("generate", "any",      "high",   "high"),
            "cf-pdsl-transformer":  ("generate", "any",      "high",   "high"),
            "cf-pdsl-reviewer":     ("analyze",  "any",      "high",   "high"),
            "cf-semantic-reviewer-consistency": ("analyze","any",      "medium", "high"),
            "cf-brainstorm-facilitator":      ("planning", "any",      "medium", "medium"),
            "cf-brainstorm-expert":           ("planning", "any",      "medium", "medium"),
            "cf-brainstorm-panel":            ("planning", "any",      "medium", "high"),
            "cf-generate-collector":          ("planning", "any",      "low",    "medium"),
            "cf-analyze-planner":             ("planning", "any",      "medium", "medium"),
            "cf-generate-planner":            ("planning", "any",      "medium", "medium"),
            "cf-generate-author":             ("planning", "any",      "low",    "medium"),
            "cf-generate-author-junior":      ("generate", "any",      "low",    "medium"),
            "cf-generate-author-middle":      ("generate", "any",      "medium", "high"),
            "cf-generate-author-senior":      ("generate", "any",      "high",   "high"),
            "cf-generate-author-lead":        ("generate", "any",      "high",   "high"),
            "cf-generate-coder-casual":       ("generate", "codebase", "medium", "medium"),
            "cf-generate-coder-smart":        ("generate", "codebase", "high",   "high"),
            "cf-generate-prompt-engineer-casual": ("generate", "any",  "medium", "medium"),
            "cf-generate-prompt-engineer-smart":  ("generate", "any",  "high",   "high"),
            "storytelling-preflight":                         ("planning", "any",  "low",    "medium"),
            "storytelling-gate":                              ("planning", "any",  "medium", "medium"),
            "storytelling-context-pack":                      ("planning", "any",  "medium", "high"),
            "storytelling-wrap":                              ("analyze",  "any",  "medium", "medium"),
            "storytelling-export":                            ("generate", "any",  "low",    "medium"),
        }
        for name, (role, target, effort, context) in expected.items():
            entry = agents[name]
            self.assertEqual(entry["role"], role, f"{name}: role")
            self.assertEqual(entry["target"], target, f"{name}: type")
            self.assertEqual(entry["reasoning_effort"], effort, f"{name}: reasoning_effort")
            self.assertEqual(entry["context_window"], context, f"{name}: context_window")
        extra = set(agents.keys()) - set(expected.keys())
        self.assertFalse(extra, f"agents.toml has agents not covered by tuning table: {sorted(extra)}")
        missing = set(expected.keys()) - set(agents.keys())
        self.assertFalse(missing, f"tuning table has stale entries not in agents.toml: {sorted(missing)}")

    def test_all_agents_have_existing_prompt_file(self):
        """Every registered agent's prompt_file resolves to an existing file on disk."""
        agents = self._load_agents()
        for name, entry in agents.items():
            prompt_abs = entry.get("prompt_file_abs")
            self.assertIsNotNone(prompt_abs, f"{name}: prompt_file_abs must be set")
            self.assertTrue(
                Path(prompt_abs).is_file(),
                f"{name}: prompt_file {prompt_abs!r} does not resolve to a file on disk",
            )

    def test_subagent_stale_toml_with_dotdot_in_follow_target_preserves_file(self):
        """A stale TOML whose follow_target contains `..` must not be auto-cleaned (defense-in-depth)."""
        from studio.commands.agents import _process_subagents, _render_toml_agent

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_dir = project_root / ".codex" / "agents"
            output_dir.mkdir(parents=True)

            prompt = project_root / ".cf-constructor" / "agents" / "worker.md"
            prompt.parent.mkdir(parents=True)
            prompt.write_text(
                "---\n"
                'description: "Worker"\n'
                "---\n"
                "# worker\n",
                encoding="utf-8",
            )

            # Stale TOML whose developer_instructions reference a path with `..`
            # This must be preserved because the path-traversal check should reject it
            stale_prompt = project_root / ".cf-constructor" / "agents" / "cf-constructor-victim.md"
            stale_prompt.write_text(
                "---\n"
                'description: "Victim"\n'
                "---\n"
                "# cf-constructor-victim\n",
                encoding="utf-8",
            )

            # Build TOML with canonical marker but malicious follow_target
            base_toml = _render_toml_agent(
                {"name": "cf-constructor-victim", "description": "Victim"},
                "{cf-studio-path}/../agents/cf-constructor-victim.md",
            )
            stale = output_dir / "cf-constructor-victim.toml"
            stale.write_text(base_toml, encoding="utf-8")

            with patch(
                "studio.commands.agents._discover_kit_agents",
                return_value=[
                    {
                        "name": "worker",
                        "description": "Worker",
                        "prompt_file_abs": prompt,
                    }
                ],
            ):
                result = _process_subagents(
                    "openai",
                    project_root,
                    project_root,
                    {},
                    None,
                    dry_run=False,
                )

            # File must be preserved because the `..` in follow_target triggers path-traversal defense
            self.assertTrue(stale.exists())
            deleted_paths = {Path(path).resolve().as_posix() for path in result["deleted"]}
            self.assertNotIn(stale.resolve().as_posix(), deleted_paths)
            preserved = [
                o
                for o in result["outputs"]
                if o.get("action") == "preserved"
                and o.get("reason") == "stale_subagent_toml_not_owned"
            ]
            self.assertEqual(len(preserved), 1)


if __name__ == "__main__":
    unittest.main()
