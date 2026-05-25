"""
Tests for generate_manifest_agents() — the manifest v2.0 agent file generation function.

Covers generate_manifest_agents() implemented in agents.py for manifest v2.0
[[agents]] components. Symmetric counterpart to generate_manifest_skills().

@cpt-algo:cpt-cypilot-algo-project-extensibility-generate-agents:p1
@cpt-dod:cpt-cypilot-dod-project-extensibility-agents-generation:p1
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.commands.agents import generate_manifest_agents
from studio.utils.manifest import AgentEntry
from _test_helpers import _make_agent


# ---------------------------------------------------------------------------
# Test: agent generated for matching target (claude)
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsBasic(unittest.TestCase):

    def test_agent_generated_for_matching_target_claude(self):
        """Agent is generated when target is in agents list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Agent\nDo something useful.", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="A test agent",
                    source=str(src),
                    agents=["claude"],
                )
            }
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            self.assertGreater(len(result["created"]) + len(result["updated"]), 0)
            out_path = project_root / ".claude" / "agents" / "my-agent.md"
            self.assertTrue(out_path.exists(), f"Expected {out_path} to exist")

    def test_agent_not_generated_for_non_matching_target(self):
        """Agent is skipped when target is not in agents list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Agent", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["cursor"],  # only cursor, not claude
                )
            }
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            self.assertEqual(len(result["created"]), 0)
            self.assertEqual(len(result["updated"]), 0)

    def test_agent_skipped_when_translate_returns_skip_true(self):
        """Windsurf target causes translate_agent_schema to return skip=True — agent skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Agent", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["windsurf"],
                )
            }
            result = generate_manifest_agents(agents, "windsurf", project_root, dry_run=False)
            self.assertEqual(len(result["created"]), 0)
            self.assertEqual(len(result["updated"]), 0)

    def test_claude_mcp_only_skip_removes_stale_generated_broad_agent(self):
        """MCP-only Claude entries skip generation and remove stale broad-access output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "mcp-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("Use the manifest-declared MCP tool.", encoding="utf-8")

            broad_agents = {
                "mcp-agent": _make_agent(
                    id="mcp-agent",
                    description="MCP agent",
                    source=str(src),
                    agents=["claude"],
                    tools=[],
                )
            }
            generate_manifest_agents(broad_agents, "claude", project_root, dry_run=False)
            stale_out = project_root / ".claude" / "agents" / "mcp-agent.md"
            self.assertTrue(stale_out.exists())
            self.assertIn("tools: Bash, Read, Write, Edit, Glob, Grep", stale_out.read_text(encoding="utf-8"))

            mcp_only_agents = {
                "mcp-agent": _make_agent(
                    id="mcp-agent",
                    description="MCP agent",
                    source=str(src),
                    agents=["claude"],
                    tools=["mcp__standctl__standctl_deploy"],
                )
            }
            result = generate_manifest_agents(mcp_only_agents, "claude", project_root, dry_run=False)

            self.assertFalse(stale_out.exists())
            self.assertEqual(result["created"], [])
            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["deleted"]), 1)
            self.assertEqual(result["outputs"][0]["action"], "deleted")
            self.assertEqual(result["outputs"][0]["reason"], "skipped_agent_stale_artifact")

    def test_claude_mixed_mcp_skip_removes_stale_generated_filtered_tools_agent(self):
        """Mixed MCP tools skip generation and remove prior filtered generated output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "mcp-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("Use the manifest-declared tools.", encoding="utf-8")

            filtered_agents = {
                "mcp-agent": _make_agent(
                    id="mcp-agent",
                    description="MCP agent",
                    source=str(src),
                    agents=["claude"],
                    tools=["Bash", "Read"],
                )
            }
            generate_manifest_agents(filtered_agents, "claude", project_root, dry_run=False)
            stale_out = project_root / ".claude" / "agents" / "mcp-agent.md"
            self.assertTrue(stale_out.exists())
            self.assertIn("tools: Bash, Read", stale_out.read_text(encoding="utf-8"))

            mixed_mcp_agents = {
                "mcp-agent": _make_agent(
                    id="mcp-agent",
                    description="MCP agent",
                    source=str(src),
                    agents=["claude"],
                    tools=["Bash", "mcp__standctl__standctl_deploy", "Read"],
                )
            }
            result = generate_manifest_agents(mixed_mcp_agents, "claude", project_root, dry_run=False)

            self.assertFalse(stale_out.exists())
            self.assertEqual(result["created"], [])
            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["deleted"]), 1)
            self.assertEqual(result["outputs"][0]["action"], "deleted")
            self.assertEqual(result["outputs"][0]["reason"], "skipped_agent_stale_artifact")

    def test_claude_mixed_mcp_skip_removes_stale_generated_filtered_disallowed_agent(self):
        """Mixed MCP disallowed tools skip generation and remove prior filtered generated output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "mcp-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("Avoid the manifest-declared tools.", encoding="utf-8")

            filtered_agents = {
                "mcp-agent": _make_agent(
                    id="mcp-agent",
                    description="MCP agent",
                    source=str(src),
                    agents=["claude"],
                    disallowed_tools=["Write"],
                )
            }
            generate_manifest_agents(filtered_agents, "claude", project_root, dry_run=False)
            stale_out = project_root / ".claude" / "agents" / "mcp-agent.md"
            self.assertTrue(stale_out.exists())
            self.assertIn("disallowedTools: Write", stale_out.read_text(encoding="utf-8"))

            mixed_mcp_agents = {
                "mcp-agent": _make_agent(
                    id="mcp-agent",
                    description="MCP agent",
                    source=str(src),
                    agents=["claude"],
                    disallowed_tools=["Write", "mcp__standctl__standctl_deploy"],
                )
            }
            result = generate_manifest_agents(mixed_mcp_agents, "claude", project_root, dry_run=False)

            self.assertFalse(stale_out.exists())
            self.assertEqual(result["created"], [])
            self.assertEqual(result["updated"], [])
            self.assertEqual(len(result["deleted"]), 1)
            self.assertEqual(result["outputs"][0]["action"], "deleted")
            self.assertEqual(result["outputs"][0]["reason"], "skipped_agent_stale_artifact")

    def test_claude_mcp_only_skip_preserves_diverged_marker_owned_agent(self):
        """Skipped Claude entries must not delete locally customized generated output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "mcp-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("Use the manifest-declared MCP tool.", encoding="utf-8")

            stale_out = project_root / ".claude" / "agents" / "mcp-agent.md"
            stale_out.parent.mkdir(parents=True)
            stale_out.write_text(
                "---\n"
                "name: mcp-agent\n"
                'description: "MCP agent"\n'
                "---\n"
                "<!-- Generated by cf-constructor agents -- do not edit -->\n"
                "stale generated content with local drift\n",
                encoding="utf-8",
            )

            mcp_only_agents = {
                "mcp-agent": _make_agent(
                    id="mcp-agent",
                    description="MCP agent",
                    source=str(src),
                    agents=["claude"],
                    tools=["mcp__standctl__standctl_deploy"],
                )
            }
            result = generate_manifest_agents(mcp_only_agents, "claude", project_root, dry_run=False)

            self.assertTrue(stale_out.exists())
            self.assertIn("local drift", stale_out.read_text(encoding="utf-8"))
            self.assertEqual(result["created"], [])
            self.assertEqual(result["updated"], [])
            self.assertEqual(result["deleted"], [])
            self.assertEqual(result["outputs"], [])

    def test_claude_mcp_skip_warns_when_stale_payload_cannot_be_rebuilt(self):
        """Skipped Claude cleanup must surface unverifiable generated files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            stale_out = project_root / ".claude" / "agents" / "mcp-agent.md"
            stale_out.parent.mkdir(parents=True)
            stale_out.write_text(
                "---\n"
                "name: mcp-agent\n"
                'description: "MCP agent"\n'
                "---\n"
                "<!-- Generated by cf-constructor agents -- do not edit -->\n"
                "stale generated content\n",
                encoding="utf-8",
            )

            agents = {
                "mcp-agent": _make_agent(
                    id="mcp-agent",
                    description="MCP agent",
                    source=str(project_root / "agents" / "missing.md"),
                    agents=["claude"],
                    tools=["mcp__standctl__standctl_deploy"],
                )
            }
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)

            self.assertTrue(stale_out.exists())
            self.assertEqual(result["deleted"], [])
            preserved = [o for o in result["outputs"] if o.get("action") == "preserved"]
            self.assertEqual(len(preserved), 1)
            self.assertEqual(preserved[0]["path"], ".claude/agents/mcp-agent.md")
            self.assertEqual(
                preserved[0]["reason"],
                "unverifiable_skipped_agent_stale_artifact",
            )
            self.assertEqual(result.get("warnings"), preserved)


# ---------------------------------------------------------------------------
# Test: Correct output paths per target
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsOutputPaths(unittest.TestCase):

    def _run_with_target(self, target: str, tmpdir: str) -> Path:
        project_root = Path(tmpdir)
        src = project_root / "agents" / "my-agent.md"
        src.parent.mkdir(parents=True)
        src.write_text("# My Agent", encoding="utf-8")

        agents = {
            "my-agent": _make_agent(
                id="my-agent",
                source=str(src),
                agents=[target],
            )
        }
        generate_manifest_agents(agents, target, project_root, dry_run=False)
        return project_root

    def test_output_path_claude(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = self._run_with_target("claude", tmpdir)
            out_path = project_root / ".claude" / "agents" / "my-agent.md"
            self.assertTrue(out_path.exists(), f"Expected {out_path} to exist")

    def test_output_path_cursor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = self._run_with_target("cursor", tmpdir)
            out_path = project_root / ".cursor" / "agents" / "my-agent.mdc"
            self.assertTrue(out_path.exists(), f"Expected {out_path} to exist")

    def test_output_path_copilot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = self._run_with_target("copilot", tmpdir)
            out_path = project_root / ".github" / "agents" / "my-agent.md"
            self.assertTrue(out_path.exists(), f"Expected {out_path} to exist")

    def test_output_path_openai(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = self._run_with_target("openai", tmpdir)
            out_path = project_root / ".codex" / "agents" / "my-agent.toml"
            self.assertTrue(out_path.exists(), f"Expected {out_path} to exist")


# ---------------------------------------------------------------------------
# Test: created/updated/unchanged tracking
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsTracking(unittest.TestCase):

    def test_result_dict_has_required_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            result = generate_manifest_agents({}, "claude", project_root, dry_run=False)
            self.assertIn("created", result)
            self.assertIn("updated", result)
            self.assertIn("unchanged", result)
            self.assertIn("outputs", result)
            self.assertIn("deleted", result)

    def test_created_tracking(self):
        """New agent file is tracked in created list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Agent", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["claude"],
                )
            }
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            self.assertEqual(len(result["created"]), 1)
            self.assertEqual(len(result["updated"]), 0)

    def test_updated_tracking(self):
        """Existing agent file with changed content is tracked in updated list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Agent", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["claude"],
                )
            }
            # First run — creates
            generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            # Modify source so content changes
            src.write_text("# My Agent Updated", encoding="utf-8")
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            self.assertEqual(len(result["updated"]), 1)
            self.assertEqual(len(result["created"]), 0)

    def test_unchanged_tracking(self):
        """Existing agent file with identical content is tracked in unchanged list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Agent", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["claude"],
                )
            }
            # First run — creates
            generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            # Second run — unchanged
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            self.assertEqual(len(result["unchanged"]), 1)
            self.assertEqual(len(result["created"]), 0)
            self.assertEqual(len(result["updated"]), 0)


# ---------------------------------------------------------------------------
# Test: dry_run mode
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsDryRun(unittest.TestCase):

    def test_dry_run_does_not_write_files(self):
        """dry_run=True computes actions but does not write files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Agent", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["claude"],
                )
            }
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=True)
            out_path = project_root / ".claude" / "agents" / "my-agent.md"
            self.assertFalse(out_path.exists(), "dry_run=True must not write files")
            # Still tracks the would-be created action
            self.assertEqual(len(result["created"]), 1)


# ---------------------------------------------------------------------------
# Test: missing prompt_file handled gracefully
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsMissingSource(unittest.TestCase):

    def test_agent_with_no_source_or_prompt_file_skipped(self):
        """Agent with no source or prompt_file is skipped gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            agents = {
                "no-source": _make_agent(
                    id="no-source",
                    source="",
                    prompt_file="",
                    agents=["claude"],
                )
            }
            # Should not raise — just skip
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            self.assertEqual(len(result["created"]), 0)

    def test_agent_with_missing_prompt_file_skipped(self):
        """Agent with nonexistent prompt_file path is skipped gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            agents = {
                "missing-file": _make_agent(
                    id="missing-file",
                    source="",
                    prompt_file="agents/does-not-exist.md",
                    agents=["claude"],
                )
            }
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            self.assertEqual(len(result["created"]), 0)


# ---------------------------------------------------------------------------
# Test: assembled file contains frontmatter
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsFileContent(unittest.TestCase):

    def test_assembled_file_contains_yaml_frontmatter(self):
        """Output file contains YAML frontmatter block with name and description."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("# My Agent\nDo something.", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="A described agent",
                    source=str(src),
                    agents=["claude"],
                )
            }
            generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            out_path = project_root / ".claude" / "agents" / "my-agent.md"
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("---", content)
            self.assertIn("name:", content)
            self.assertIn("description:", content)

    def test_assembled_file_contains_prompt_body(self):
        """Output file contains the original prompt content after frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("My unique prompt content.", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["claude"],
                )
            }
            generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            out_path = project_root / ".claude" / "agents" / "my-agent.md"
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("My unique prompt content.", content)

    def test_claude_output_contains_generator_ownership_marker(self):
        """Claude manifest-generated agent output is durably marked as generator-owned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("Prompt.", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["claude"],
                )
            }
            generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            out_path = project_root / ".claude" / "agents" / "my-agent.md"
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("<!-- Generated by cf-constructor agents -- do not edit -->", content)

    def test_assembled_file_uses_prompt_file_fallback(self):
        """Output file uses prompt_file when source is not set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("Prompt file content.", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source="",
                    prompt_file=str(src),
                    agents=["claude"],
                )
            }
            generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            out_path = project_root / ".claude" / "agents" / "my-agent.md"
            self.assertTrue(out_path.exists())
            content = out_path.read_text(encoding="utf-8")
            self.assertIn("Prompt file content.", content)

    def test_body_prefix_injected_when_memory_dir_set(self):
        """When Claude translation produces body_prefix (memory_dir), it appears in output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("Prompt.", encoding="utf-8")

            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    source=str(src),
                    agents=["claude"],
                    memory_dir=".memory/my-agent",
                )
            }
            generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            out_path = project_root / ".claude" / "agents" / "my-agent.md"
            content = out_path.read_text(encoding="utf-8")
            self.assertIn(".memory/my-agent", content)


# ---------------------------------------------------------------------------
# Test: path traversal prevention in _write_or_skip
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsPathTraversal(unittest.TestCase):

    def test_path_traversal_agent_id_skipped(self):
        """Agent ID with ../ sequences is skipped due to invalid TOML key validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "bad.md"
            src.parent.mkdir(parents=True)
            src.write_text("content", encoding="utf-8")
            agents = {
                "../../../outside": _make_agent(
                    id="../../../outside",
                    description="bad agent",
                    source=str(src),
                    agents=["openai"],
                    model="claude-opus",
                )
            }
            result = generate_manifest_agents(agents, "openai", project_root, dry_run=False)
            # Agent should be skipped — no outputs generated
            self.assertEqual(result["created"], [])
            self.assertEqual(result["outputs"], [])

    def test_openai_unsafe_agent_ids_are_skipped_without_output(self):
        """OpenAI output rejects every unsafe ID shape before path construction."""
        unsafe_ids = [
            "",
            "/absolute-agent",
            "folder/agent",
            "folder\\agent",
            "bad agent",
            "bad:agent",
        ]
        for unsafe_id in unsafe_ids:
            with self.subTest(unsafe_id=unsafe_id):
                with tempfile.TemporaryDirectory() as tmpdir:
                    project_root = Path(tmpdir)
                    src = project_root / "agents" / "bad.md"
                    src.parent.mkdir(parents=True)
                    src.write_text("content", encoding="utf-8")
                    agents = {
                        unsafe_id: _make_agent(
                            id=unsafe_id,
                            description="bad agent",
                            source=str(src),
                            agents=["openai"],
                        )
                    }

                    result = generate_manifest_agents(
                        agents, "openai", project_root, dry_run=False,
                    )

                    self.assertEqual(result["created"], [])
                    self.assertEqual(result["updated"], [])
                    self.assertEqual(result["outputs"], [])
                    self.assertFalse((project_root / ".codex").exists())

    def test_workflow_rename_outside_absolute_follow_link_warns_without_abort(self):
        """Malformed absolute workflow follow-links are reported without aborting."""
        from studio.commands.agents import _default_agents_config, _process_single_agent

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outside:
            project_root = Path(tmpdir)
            cypilot_root = project_root
            (project_root / ".git").mkdir()
            workflows = cypilot_root / "workflows"
            workflows.mkdir()
            (workflows / "generate.md").write_text(
                "---\n"
                "type: workflow\n"
                "name: generate\n"
                "description: Generate\n"
                "---\n"
                "# Generate\n",
                encoding="utf-8",
            )
            workflow_dir = project_root / ".windsurf" / "workflows"
            workflow_dir.mkdir(parents=True)
            malformed = workflow_dir / "cf-constructor-old.md"
            malformed.write_text(
                "# /cf-constructor-old\n\n"
                f"ALWAYS open and follow `{Path(outside) / 'not-owned.md'}`\n",
                encoding="utf-8",
            )

            result = _process_single_agent(
                "windsurf",
                project_root,
                cypilot_root,
                _default_agents_config(),
                None,
                dry_run=False,
            )

            self.assertEqual(result["status"], "PARTIAL")
            errors = result["workflows"]["errors"]
            self.assertEqual(len(errors), 1)
            self.assertIn("outside project_root and cypilot_root", errors[0])
            self.assertTrue(malformed.exists())


# ---------------------------------------------------------------------------
# Test: OpenAI/Codex TOML format edge cases
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsOpenAI(unittest.TestCase):

    def _make_src(self, project_root: Path) -> Path:
        src = project_root / "agents" / "my-agent.md"
        src.parent.mkdir(parents=True)
        src.write_text("Agent prompt content.", encoding="utf-8")
        return src

    def test_openai_model_written_when_set(self):
        """OpenAI TOML output includes model line when agent.model is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = self._make_src(project_root)
            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="Test agent",
                    source=str(src),
                    agents=["openai"],
                    model="claude-opus-4",
                )
            }
            generate_manifest_agents(agents, "openai", project_root, dry_run=False)
            out = project_root / ".codex" / "agents" / "my-agent.toml"
            self.assertTrue(out.exists())
            content = out.read_text()
            self.assertIn('model = "claude-opus-4"', content)

    def test_openai_variables_substituted(self):
        """OpenAI TOML output substitutes layer variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "sub-agent.md"
            src.parent.mkdir(parents=True)
            src.write_text("Hello {project_name}.", encoding="utf-8")
            agents = {
                "sub-agent": _make_agent(
                    id="sub-agent",
                    description="Agent with {project_name}",
                    source=str(src),
                    agents=["openai"],
                )
            }
            generate_manifest_agents(
                agents, "openai", project_root, dry_run=False,
                variables={"project_name": "MyProject"},
            )
            out = project_root / ".codex" / "agents" / "sub-agent.toml"
            content = out.read_text()
            self.assertIn("MyProject", content)

    def test_openai_developer_instructions_contains_source_body(self):
        """OpenAI TOML developer_instructions must contain the source prompt body, not just description."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "my-agent.md"
            src.parent.mkdir(parents=True)
            prompt_body = "You are an expert code reviewer.\nAnalyze all files carefully."
            src.write_text(prompt_body, encoding="utf-8")
            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="Code review agent",
                    source=str(src),
                    agents=["openai"],
                )
            }
            generate_manifest_agents(agents, "openai", project_root, dry_run=False)
            out = project_root / ".codex" / "agents" / "my-agent.toml"
            self.assertTrue(out.exists())
            content = out.read_text()
            # The source prompt body must appear in developer_instructions, not just the description
            self.assertIn("You are an expert code reviewer.", content)
            self.assertIn("Analyze all files carefully.", content)

    def test_openai_append_included_in_output(self):
        """OpenAI TOML output includes agent.append content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = self._make_src(project_root)
            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="Test agent",
                    source=str(src),
                    agents=["openai"],
                    append="# extra section",
                )
            }
            generate_manifest_agents(agents, "openai", project_root, dry_run=False)
            out = project_root / ".codex" / "agents" / "my-agent.toml"
            content = out.read_text()
            self.assertIn("# extra section", content)

    def test_openai_output_contains_generator_ownership_marker(self):
        """OpenAI manifest-generated agent output is durably marked as generator-owned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = self._make_src(project_root)
            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="Test agent",
                    source=str(src),
                    agents=["openai"],
                )
            }

            generate_manifest_agents(agents, "openai", project_root, dry_run=False)

            out = project_root / ".codex" / "agents" / "my-agent.toml"
            content = out.read_text(encoding="utf-8")
            self.assertIn("# Generated by cf-constructor agents -- do not edit", content)

    def test_openai_removes_generator_owned_legacy_agents_path(self):
        """OpenAI generation removes old-format generator-owned .agents/{id}/agent.toml output.

        The legacy file is seeded with old-format content — has the _GENERATED_MARKER_TOML line
        but lacks new fields like model_reasoning_effort — to exercise the marker-presence ownership
        path introduced by _delete_generated_legacy_file.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = self._make_src(project_root)
            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="Test agent",
                    source=str(src),
                    agents=["openai"],
                )
            }

            # Seed the legacy path with old-format content: has the marker and section header
            # but lacks new fields (model_reasoning_effort) and matches no new-format byte equality.
            old_format_content = (
                "# Generated by cf-constructor agents -- do not edit\n"
                "[agents.my_agent]\n"
                'description = "Test agent"\n'
                'sandbox_mode = "workspace-write"\n'
                'developer_instructions = """\n'
                "Agent prompt content.\n"
                '"""\n'
            )
            current_out = project_root / ".codex" / "agents" / "my-agent.toml"
            legacy_out = project_root / ".agents" / "my-agent" / "agent.toml"
            legacy_out.parent.mkdir(parents=True)
            legacy_out.write_text(old_format_content, encoding="utf-8")

            result = generate_manifest_agents(agents, "openai", project_root, dry_run=False)

            self.assertTrue(current_out.exists())
            self.assertFalse(legacy_out.exists())
            self.assertEqual(len(result["deleted"]), 1)
            deleted_outputs = [o for o in result["outputs"] if o.get("action") == "deleted"]
            self.assertEqual(len(deleted_outputs), 1)
            self.assertEqual(deleted_outputs[0]["path"], ".agents/my-agent/agent.toml")
            self.assertEqual(deleted_outputs[0]["reason"], "migrated_openai_agent_output")

    def test_openai_does_not_delete_unrelated_legacy_file(self):
        """OpenAI generation does NOT delete a hand-written legacy file with no marker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = self._make_src(project_root)
            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="Test agent",
                    source=str(src),
                    agents=["openai"],
                )
            }

            # Hand-written file: no marker line, not byte-equal to new-format output.
            hand_written_content = (
                "[agents.my_agent]\n"
                'description = "My custom hand-written agent config"\n'
                'sandbox_mode = "workspace-write"\n'
            )
            legacy_out = project_root / ".agents" / "my-agent" / "agent.toml"
            legacy_out.parent.mkdir(parents=True)
            legacy_out.write_text(hand_written_content, encoding="utf-8")

            result = generate_manifest_agents(agents, "openai", project_root, dry_run=False)

            # Hand-written file must be preserved
            self.assertTrue(legacy_out.exists())
            self.assertIn("My custom hand-written agent config", legacy_out.read_text(encoding="utf-8"))
            self.assertEqual(result.get("deleted", []), [])

    def test_openai_preserves_marker_owned_legacy_agents_path_when_content_diverged(self):
        """OpenAI legacy cleanup preserves diverged marker-bearing legacy files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = self._make_src(project_root)
            agents = {
                "my-agent": _make_agent(
                    id="my-agent",
                    description="Test agent",
                    source=str(src),
                    agents=["openai"],
                )
            }

            legacy_out = project_root / ".agents" / "my-agent" / "agent.toml"
            legacy_out.parent.mkdir(parents=True)
            legacy_out.write_text(
                "# Generated by cf-constructor agents -- do not edit\n"
                "[agents.my_agent]\n"
                'description = "stale hand-edited generated copy"\n',
                encoding="utf-8",
            )

            result = generate_manifest_agents(agents, "openai", project_root, dry_run=False)

            # Marker + section header is not enough after ownership hardening: diverged file is preserved.
            self.assertTrue(legacy_out.exists())
            self.assertEqual(result.get("deleted", []), [])
            warning_outputs = [o for o in result["outputs"] if o.get("action") == "preserved"]
            self.assertEqual(len(warning_outputs), 1)
            self.assertEqual(warning_outputs[0]["path"], ".agents/my-agent/agent.toml")
            self.assertEqual(
                warning_outputs[0]["reason"],
                "diverged_legacy_openai_agent_output",
            )


# ---------------------------------------------------------------------------
# Test: translate_agent_schema ValueError is caught and logged
# ---------------------------------------------------------------------------

class TestGenerateManifestAgentsTranslateError(unittest.TestCase):

    def test_conflicting_tools_skips_agent(self):
        """Agent with both tools and disallowed_tools is skipped (ValueError caught)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            src = project_root / "agents" / "conflict.md"
            src.parent.mkdir(parents=True)
            src.write_text("content", encoding="utf-8")
            agents = {
                "conflict": _make_agent(
                    id="conflict",
                    description="conflicting agent",
                    source=str(src),
                    agents=["claude"],
                    tools=["read"],
                    disallowed_tools=["write"],
                )
            }
            result = generate_manifest_agents(agents, "claude", project_root, dry_run=False)
            # No file should be created — agent was skipped
            self.assertEqual(result["created"], [])
            self.assertIn("errors", result)


if __name__ == "__main__":
    unittest.main()
