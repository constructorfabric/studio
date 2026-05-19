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
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_TOML = REPO_ROOT / "skills" / "cypilot" / "agents.toml"

# Agents now at cf:tier:balanced (sonnet-tier)
_BALANCED_AGENTS = (
    "cf-constructor-pr-review",
    "cf-constructor-migrate-planner",
)

# Agents now at cf:tier:cheap (haiku-tier)
_CHEAP_AGENTS = (
    "cf-constructor-migrate-scanner",
    "cf-constructor-migrate-migrator",
    "cf-constructor-migrate-verifier",
)

_INHERIT_AGENTS = (
    "cf-constructor-codegen",
    "cf-constructor-ralphex",
    "cf-constructor-phase-runner",
    "cf-constructor-phase-compiler",
)

# All tuned agents (balanced + cheap) — used for meta-field checks
_TUNED_AGENTS = _BALANCED_AGENTS + _CHEAP_AGENTS + _INHERIT_AGENTS


class TestExistingAgentsSnapshot(unittest.TestCase):
    def _load_agents(self):
        import tomllib
        with open(AGENTS_TOML, "rb") as f:
            data = tomllib.load(f)
        from cypilot.commands.agents import _validate_agent_entry
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
        from cypilot.commands.agents import _resolve_model_id
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

    def test_balanced_agents_emit_sonnet_on_claude(self):
        """spec §7: Claude proxy for balanced agents emits model: sonnet."""
        from cypilot.commands.agents import _agent_template_claude
        agents = self._load_agents()
        for name in _BALANCED_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_claude(entry))
            self.assertIn("model: sonnet", out, f"{name}: claude balanced → sonnet")

    def test_balanced_agents_emit_sonnet_on_cursor(self):
        """spec §7: Cursor proxy for balanced agents emits model: claude-sonnet-4-6."""
        from cypilot.commands.agents import _agent_template_cursor
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
        from cypilot.commands.agents import _agent_template_copilot
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
        from cypilot.commands.agents import _resolve_model_id
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
        from cypilot.commands.agents import _agent_template_claude
        agents = self._load_agents()
        for name in _CHEAP_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_claude(entry))
            self.assertIn("model: haiku", out, f"{name}: claude cheap → haiku")

    def test_cheap_agents_emit_haiku_on_cursor(self):
        """spec §11: Cursor proxy for cheap agents emits model: claude-haiku-4-5."""
        from cypilot.commands.agents import _agent_template_cursor
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
        from cypilot.commands.agents import _agent_template_copilot
        agents = self._load_agents()
        for name in _CHEAP_AGENTS:
            entry = agents[name]
            out = "\n".join(_agent_template_copilot(entry))
            self.assertIn(
                "model: Claude Haiku 4.5", out,
                f"{name}: copilot cheap → Claude Haiku 4.5",
            )

    # ------------------------------------------------------------------
    # Inherit agents — no model line emitted
    # ------------------------------------------------------------------

    def test_inherit_agents_emit_no_codex_model_line(self):
        """spec §7: inherit agents must not emit a model = line in Codex TOML."""
        from cypilot.commands.agents import _render_toml_agent
        agents = self._load_agents()
        for name in _INHERIT_AGENTS:
            entry = agents[name]
            self.assertEqual(
                entry["model"], "cf:inherit",
                f"{name}: model must be cf:inherit",
            )
            out = _render_toml_agent(entry, "p")
            self.assertNotIn("model =", out, f"{name}: codex inherit must omit model line")

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
            "cf-constructor-codegen":          ("generate", "codebase", "medium", "high"),
            "cf-constructor-pr-review":        ("analyze",  "any",      "high",   "high"),
            "cf-constructor-ralphex":          ("any",      "any",      "medium", "medium"),
            "cf-constructor-phase-runner":     ("generate", "any",      "high",   "high"),
            "cf-constructor-phase-compiler":   ("planning", "artifacts","high",   "medium"),
            "cf-constructor-migrate-scanner":  ("analyze",  "any",      "low",    "high"),
            "cf-constructor-migrate-planner":  ("planning", "any",      "high",   "medium"),
            "cf-constructor-migrate-migrator": ("generate", "any",      "low",    "medium"),
            "cf-constructor-migrate-verifier": ("analyze",  "any",      "low",    "high"),
        }
        for name, (role, target, effort, context) in expected.items():
            entry = agents[name]
            self.assertEqual(entry["role"], role, f"{name}: role")
            self.assertEqual(entry["target"], target, f"{name}: type")
            self.assertEqual(entry["reasoning_effort"], effort, f"{name}: reasoning_effort")
            self.assertEqual(entry["context_window"], context, f"{name}: context_window")


if __name__ == "__main__":
    unittest.main()
