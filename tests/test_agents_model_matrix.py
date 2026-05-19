import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))


class TestValidateAgentEntryNewFields(unittest.TestCase):
    def _validate(self, info, source_dir):
        from cypilot.commands.agents import _validate_agent_entry
        return _validate_agent_entry("a", info, source_dir, set())

    def test_defaults_when_new_fields_missing(self):
        with TemporaryDirectory() as td:
            sd = Path(td)
            entry = self._validate({"description": "x"}, sd)
            self.assertEqual(entry["role"], "any")
            self.assertEqual(entry["target"], "any")
            self.assertEqual(entry["provider"], "anthropic")
            self.assertEqual(entry["model"], "cf:inherit")
            self.assertIsNone(entry["reasoning_effort"])
            self.assertIsNone(entry["context_window"])

    def test_fast_alias_normalises_to_balanced(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"model": "fast"}, Path(td))
            self.assertEqual(entry["model"], "cf:tier:balanced")

    def test_bare_inherit_normalises_to_cf_inherit(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"model": "inherit"}, Path(td))
            self.assertEqual(entry["model"], "cf:inherit")

    def test_bare_cheap_normalises_to_cf_tier_cheap(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"model": "cheap"}, Path(td))
            self.assertEqual(entry["model"], "cf:tier:cheap")

    def test_prefixed_value_accepted_as_is(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"model": "cf:tier:expensive"}, Path(td))
            self.assertEqual(entry["model"], "cf:tier:expensive")

    def test_invalid_role_falls_back_to_any(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"role": "bogus"}, Path(td))
            self.assertEqual(entry["role"], "any")

    def test_invalid_type_falls_back_to_any(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"target": "bogus"}, Path(td))
            self.assertEqual(entry["target"], "any")

    def test_invalid_provider_falls_back_to_anthropic(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"provider": "google"}, Path(td))
            self.assertEqual(entry["provider"], "anthropic")

    def test_invalid_reasoning_effort_omitted(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"reasoning_effort": "ultra"}, Path(td))
            self.assertIsNone(entry["reasoning_effort"])

    def test_invalid_context_window_omitted(self):
        with TemporaryDirectory() as td:
            entry = self._validate({"context_window": "huge"}, Path(td))
            self.assertIsNone(entry["context_window"])

    def test_valid_values_accepted(self):
        with TemporaryDirectory() as td:
            entry = self._validate({
                "role": "generate", "target": "codebase",
                "provider": "openai", "model": "expensive",
                "reasoning_effort": "high", "context_window": "max",
            }, Path(td))
            self.assertEqual(entry["role"], "generate")
            self.assertEqual(entry["target"], "codebase")
            self.assertEqual(entry["provider"], "openai")
            self.assertEqual(entry["model"], "cf:tier:expensive")
            self.assertEqual(entry["reasoning_effort"], "high")
            self.assertEqual(entry["context_window"], "max")


class TestResolveModelId(unittest.TestCase):
    def test_inherit_returns_none(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertIsNone(_resolve_model_id("claude", "anthropic", "inherit", "any", "any"))

    def test_auto_on_cursor_returns_auto(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(_resolve_model_id("cursor", "anthropic", "auto", "any", "any"), "auto")

    def test_auto_on_copilot_returns_auto(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(_resolve_model_id("copilot", "anthropic", "auto", "any", "any"), "auto")

    def test_auto_on_claude_returns_none(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertIsNone(_resolve_model_id("claude", "anthropic", "auto", "any", "any"))

    def test_auto_on_codex_returns_none(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertIsNone(_resolve_model_id("codex", "openai", "auto", "any", "any"))

    def test_claude_balanced_default_is_sonnet(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(_resolve_model_id("claude", "anthropic", "balanced", "any", "any"), "sonnet")

    def test_claude_cheap_codebase_generate_stays_haiku(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("claude", "anthropic", "cheap", "generate", "codebase"),
            "haiku",
        )

    def test_claude_cheap_codebase_analyze_bumps_to_sonnet(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("claude", "anthropic", "cheap", "analyze", "codebase"),
            "sonnet",
        )

    def test_codex_balanced_generate_codebase_picks_codex_standard(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("codex", "openai", "balanced", "generate", "codebase"),
            "gpt-5.3-codex",
        )

    def test_codex_balanced_planning_codebase_stays_gpt54(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("codex", "openai", "balanced", "planning", "codebase"),
            "gpt-5.4",
        )

    def test_codex_cheap_generate_codebase_stays_mini(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("codex", "openai", "cheap", "generate", "codebase"),
            "gpt-5.4-mini",
        )

    def test_codex_cheap_analyze_codebase_bumps_to_gpt54(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("codex", "openai", "cheap", "analyze", "codebase"),
            "gpt-5.4",
        )

    def test_cursor_anthropic_balanced(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("cursor", "anthropic", "balanced", "any", "any"),
            "claude-sonnet-4-6",
        )

    def test_cursor_openai_balanced_codebase_generate_codex(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("cursor", "openai", "balanced", "generate", "codebase"),
            "gpt-5.3-codex",
        )

    def test_copilot_anthropic_expensive(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("copilot", "anthropic", "expensive", "any", "any"),
            "Claude Opus 4.7",
        )

    def test_copilot_openai_balanced_codebase_generate_stays_gpt54(self):
        from cypilot.commands.agents import _resolve_model_id
        # Copilot picker does not expose gpt-5.3-codex → balanced stays on GPT-5.4
        self.assertEqual(
            _resolve_model_id("copilot", "openai", "balanced", "generate", "codebase"),
            "GPT-5.4",
        )

    def test_passthrough_unknown_tier(self):
        from cypilot.commands.agents import _resolve_model_id
        self.assertEqual(
            _resolve_model_id("claude", "anthropic", "claude-opus-4-7", "any", "any"),
            "claude-opus-4-7",
        )

    def test_provider_fallback_for_unsupported(self):
        from cypilot.commands.agents import _resolve_model_id
        # codex tool with anthropic provider → falls back to openai
        self.assertEqual(
            _resolve_model_id("codex", "anthropic", "balanced", "any", "any"),
            "gpt-5.4",
        )


class TestResolveModelIdCrossProduct(unittest.TestCase):
    """Smoke test: every (tool, provider, tier, role, type) combination produces
    a non-None string for non-inherit tiers, or None for inherit on every tool."""

    def test_every_combination_resolves(self):
        from cypilot.commands.agents import (
            _resolve_model_id, _MODEL_MATRIX, _VALID_AGENT_ROLES, _VALID_AGENT_TARGETS,
        )
        for (tool, provider), cell in _MODEL_MATRIX.items():
            for tier in cell["base"]:
                for role in _VALID_AGENT_ROLES:
                    for target in _VALID_AGENT_TARGETS:
                        got = _resolve_model_id(tool, provider, tier, role, target)
                        self.assertIsInstance(
                            got, str,
                            f"({tool}, {provider}, {tier}, {role}, {target}) → {got!r}",
                        )

    def test_inherit_always_none(self):
        from cypilot.commands.agents import _resolve_model_id
        for tool in ("claude", "codex", "cursor", "copilot"):
            for provider in ("anthropic", "openai"):
                self.assertIsNone(
                    _resolve_model_id(tool, provider, "inherit", "any", "any"),
                )


class TestCodexContextTokens(unittest.TestCase):
    def test_context_window_to_int(self):
        from cypilot.commands.agents import _CODEX_CONTEXT_TOKENS
        self.assertEqual(_CODEX_CONTEXT_TOKENS["low"], 200_000)
        self.assertEqual(_CODEX_CONTEXT_TOKENS["medium"], 400_000)
        self.assertEqual(_CODEX_CONTEXT_TOKENS["high"], 600_000)
        self.assertEqual(_CODEX_CONTEXT_TOKENS["max"], 1_050_000)

    def test_codex_effort_max_maps_to_xhigh(self):
        from cypilot.commands.agents import _CODEX_EFFORT_MAP
        self.assertEqual(_CODEX_EFFORT_MAP["max"], "xhigh")
        self.assertEqual(_CODEX_EFFORT_MAP["high"], "high")
        self.assertEqual(_CODEX_EFFORT_MAP["medium"], "medium")
        self.assertEqual(_CODEX_EFFORT_MAP["low"], "low")


class TestClaudeTemplateNewFields(unittest.TestCase):
    def _build(self, **overrides):
        from cypilot.commands.agents import _agent_template_claude
        base = {
            "name": "x", "description": "d", "mode": "readwrite",
            "isolation": False, "model": "cf:inherit",
            "role": "any", "target": "any", "provider": "anthropic",
            "reasoning_effort": None, "context_window": None,
        }
        base.update(overrides)
        return "\n".join(_agent_template_claude(base))

    def test_inherit_omits_model_line(self):
        out = self._build()
        self.assertNotIn("model:", out)

    def test_balanced_emits_sonnet(self):
        out = self._build(model="balanced")
        self.assertIn("model: sonnet", out)

    def test_cheap_codebase_analyze_bumps_to_sonnet(self):
        out = self._build(model="cheap", role="analyze", **{"target": "codebase"})
        self.assertIn("model: sonnet", out)

    def test_cheap_codebase_generate_stays_haiku(self):
        out = self._build(model="cheap", role="generate", **{"target": "codebase"})
        self.assertIn("model: haiku", out)

    def test_context_window_max_adds_1m_suffix(self):
        out = self._build(model="expensive", context_window="max")
        self.assertIn("model: opus[1m]", out)

    def test_context_window_high_no_suffix(self):
        out = self._build(model="expensive", context_window="high")
        self.assertIn("model: opus", out)
        self.assertNotIn("opus[1m]", out)

    def test_reasoning_effort_emits_effort_line(self):
        out = self._build(reasoning_effort="high")
        self.assertIn("effort: high", out)

    def test_reasoning_effort_max_passes_through(self):
        out = self._build(reasoning_effort="max")
        self.assertIn("effort: max", out)

    def test_no_effort_line_when_unset(self):
        out = self._build()
        self.assertNotIn("effort:", out)


class TestCursorTemplateNewFields(unittest.TestCase):
    def _build(self, **overrides):
        from cypilot.commands.agents import _agent_template_cursor
        base = {
            "name": "x", "description": "d", "mode": "readwrite",
            "isolation": False, "model": "cf:inherit",
            "role": "any", "target": "any", "provider": "anthropic",
            "reasoning_effort": None, "context_window": None,
        }
        base.update(overrides)
        return "\n".join(_agent_template_cursor(base))

    def test_inherit_omits_model_line(self):
        out = self._build()
        # The 'model:' field should not appear in YAML frontmatter
        # (Cursor doesn't strictly require it, and our selector returns None for inherit)
        self.assertNotIn("\nmodel:", "\n" + out)

    def test_balanced_anthropic_emits_sonnet_4_6(self):
        out = self._build(model="balanced")
        self.assertIn("model: claude-sonnet-4-6", out)

    def test_balanced_openai_codebase_generate_emits_codex_standard(self):
        out = self._build(model="balanced", provider="openai",
                          role="generate", **{"target": "codebase"})
        self.assertIn("model: gpt-5.3-codex", out)

    def test_auto_emits_auto(self):
        out = self._build(model="auto")
        self.assertIn("model: auto", out)

    def test_reasoning_effort_inserts_html_comment(self):
        out = self._build(reasoning_effort="high")
        self.assertIn(
            "<!-- reasoning_effort=high",
            out,
        )

    def test_context_window_inserts_html_comment(self):
        out = self._build(context_window="max")
        self.assertIn("context_window=max", out)

    def test_no_comment_when_both_unset(self):
        out = self._build()
        self.assertNotIn("reasoning_effort", out)
        self.assertNotIn("context_window", out)

    def test_comment_placed_after_closing_frontmatter(self):
        out = self._build(reasoning_effort="high")
        # Find the second --- (closing fence) and the comment; comment must be after.
        frontmatter_close = out.rfind("\n---\n")
        comment_pos = out.find("<!--")
        self.assertGreater(comment_pos, frontmatter_close)


class TestCopilotTemplateNewFields(unittest.TestCase):
    def _build(self, **overrides):
        from cypilot.commands.agents import _agent_template_copilot
        base = {
            "name": "x", "description": "d", "mode": "readwrite",
            "isolation": False, "model": "cf:inherit",
            "role": "any", "target": "any", "provider": "anthropic",
            "reasoning_effort": None, "context_window": None,
        }
        base.update(overrides)
        return "\n".join(_agent_template_copilot(base))

    def test_inherit_omits_model_line(self):
        out = self._build()
        self.assertNotIn("\nmodel:", "\n" + out)

    def test_balanced_anthropic_emits_claude_sonnet(self):
        out = self._build(model="balanced")
        self.assertIn("model: Claude Sonnet 4.6", out)

    def test_balanced_openai_codebase_generate_stays_gpt54(self):
        out = self._build(model="balanced", provider="openai",
                          role="generate", **{"target": "codebase"})
        self.assertIn("model: GPT-5.4", out)

    def test_auto_emits_auto(self):
        out = self._build(model="auto")
        self.assertIn("model: auto", out)

    def test_reasoning_effort_inserts_html_comment(self):
        out = self._build(reasoning_effort="high")
        self.assertIn("reasoning_effort=high", out)


class TestCodexTomlRender(unittest.TestCase):
    def _render(self, **overrides):
        from cypilot.commands.agents import _render_toml_agent
        base = {
            "name": "x", "description": "d", "mode": "readwrite",
            "isolation": False, "model": "cf:inherit",
            "role": "any", "target": "any", "provider": "openai",
            "reasoning_effort": None, "context_window": None,
        }
        base.update(overrides)
        return _render_toml_agent(base, "target/path.md")

    def test_inherit_omits_model_line(self):
        out = self._render()
        self.assertNotIn("model =", out)

    def test_balanced_emits_model_line(self):
        out = self._render(model="cf:tier:balanced")
        self.assertIn('model = "gpt-5.4"', out)

    def test_balanced_codebase_generate_emits_codex_standard(self):
        out = self._render(model="cf:tier:balanced", role="generate", **{"target": "codebase"})
        self.assertIn('model = "gpt-5.3-codex"', out)

    def test_reasoning_effort_emits_field(self):
        out = self._render(reasoning_effort="high")
        self.assertIn('model_reasoning_effort = "high"', out)

    def test_reasoning_effort_max_maps_to_xhigh(self):
        out = self._render(reasoning_effort="max")
        self.assertIn('model_reasoning_effort = "xhigh"', out)

    def test_context_window_max_emits_int(self):
        out = self._render(context_window="max")
        self.assertIn("model_context_window = 1050000", out)

    def test_context_window_medium_emits_int(self):
        out = self._render(context_window="medium")
        self.assertIn("model_context_window = 400000", out)

    def test_no_effort_line_when_unset(self):
        out = self._render()
        self.assertNotIn("model_reasoning_effort", out)

    def test_codex_anthropic_provider_falls_back_to_openai_silently(self):
        # No explicit provider in `info` → silent fallback; model resolves on openai
        out = self._render(model="cf:tier:balanced", provider="anthropic")
        self.assertIn('model = "gpt-5.4"', out)


if __name__ == "__main__":
    unittest.main()
