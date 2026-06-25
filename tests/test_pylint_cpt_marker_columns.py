"""Tests for the CPT marker over single-call Pylint checker."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.pylint_plugin_fakes import load_plugin_module

class TestCptMarkerColumnsChecker(unittest.TestCase):
    """Exercise invalid CPT marker placement over single call-like statements."""

    def test_helper_flags_single_return_call(self) -> None:
        module = load_plugin_module("cpt_marker_columns")
        findings = module.find_call_wrapped_marker_columns([
            "# @cpt-begin:a",
            "# @cpt-begin:b",
            "# @cpt-begin:c",
            "return work()",
            "# @cpt-end:c",
            "# @cpt-end:b",
            "# @cpt-end:a",
        ])
        self.assertEqual(findings, [1, 2, 3])

    def test_helper_ignores_function_definition_block(self) -> None:
        module = load_plugin_module("cpt_marker_columns")
        findings = module.find_call_wrapped_marker_columns([
            "# @cpt-begin:a",
            "# @cpt-begin:b",
            "# @cpt-begin:c",
            "def helper():",
            "    return work()",
            "# @cpt-end:c",
            "# @cpt-end:b",
            "# @cpt-end:a",
        ])
        self.assertEqual(findings, [])

    def test_helper_ignores_multi_statement_block_after_call_assignment(self) -> None:
        module = load_plugin_module("cpt_marker_columns")
        findings = module.find_call_wrapped_marker_columns([
            "# @cpt-begin:inst-extract-title",
            "frontmatter = _parse_toml_frontmatter(phase_content)",
            "phase_meta = frontmatter.get(\"phase\", {})",
            "title = phase_meta.get(\"title\", f\"Phase {phase_num}\")",
            "# @cpt-end:inst-extract-title",
        ])
        self.assertEqual(findings, [])

    def test_helper_ignores_multi_statement_validation_block(self) -> None:
        module = load_plugin_module("cpt_marker_columns")
        findings = module.find_call_wrapped_marker_columns([
            "# @cpt-begin:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-agent-fields",
            "value = agent_config.get(key, raw.get(key))",
            "if value is None:",
            "    return None",
            "if not isinstance(value, str):",
            "    raise ValueError(f\"Field '{key}' must be a string\")",
            "cleaned = value.strip()",
            "return cleaned or None",
            "# @cpt-end:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-agent-fields",
        ])
        self.assertEqual(findings, [])

    def test_helper_ignores_outer_marker_when_inner_marker_wraps_single_call(self) -> None:
        module = load_plugin_module("cpt_marker_columns")
        findings = module.find_call_wrapped_marker_columns([
            "# @cpt-begin:outer",
            "result = prepare()",
            "# @cpt-begin:inner",
            "return work()",
            "# @cpt-end:inner",
            "return result",
            "# @cpt-end:outer",
        ])
        self.assertEqual(findings, [3])

    def test_register_paths(self) -> None:
        module = load_plugin_module("cpt_marker_columns")
        existing = type("Existing", (), {"name": module.CptMarkerColumnsChecker.name})()
        linter = type(
            "Linter",
            (),
            {"_checkers": {"raw": [existing]}, "register_checker": lambda self, checker: (_ for _ in ()).throw(AssertionError)},
        )()
        module.register(linter)

        recorded: list[object] = []
        fresh_linter = type(
            "Linter",
            (),
            {"_checkers": {}, "register_checker": lambda self, checker: recorded.append(checker)},
        )()
        module.register(fresh_linter)
        self.assertEqual(len(recorded), 1)
        self.assertIsInstance(recorded[0], module.CptMarkerColumnsChecker)

    def test_process_module_flags_single_marker_over_call_assignment(self) -> None:
        module = load_plugin_module("cpt_marker_columns")
        checker = module.CptMarkerColumnsChecker(linter=None)
        messages: list[tuple[str, int | None]] = []
        checker.add_message = lambda msgid, node=None, line=None: messages.append((msgid, line))
        with TemporaryDirectory() as td:
            target = Path(td) / "sample.py"
            target.write_text(
                "\n".join([
                    "def run():",
                    "    # @cpt-begin:a",
                    "    value = build()",
                    "    # @cpt-end:a",
                    "    return value",
                ]),
                encoding="utf-8",
            )
            checker.process_module(type("Module", (), {"file": str(target)})())
        self.assertEqual(messages, [("stacked-cpt-begin-column", 2)])

    def test_process_module_ignores_real_branch(self) -> None:
        module = load_plugin_module("cpt_marker_columns")
        checker = module.CptMarkerColumnsChecker(linter=None)
        messages: list[tuple[str, int | None]] = []
        checker.add_message = lambda msgid, node=None, line=None: messages.append((msgid, line))
        with TemporaryDirectory() as td:
            target = Path(td) / "sample.py"
            target.write_text(
                "\n".join([
                    "def run(flag):",
                    "    # @cpt-begin:a",
                    "    # @cpt-begin:b",
                    "    # @cpt-begin:c",
                    "    if flag:",
                    "        return build()",
                    "    return None",
                    "    # @cpt-end:c",
                    "    # @cpt-end:b",
                    "    # @cpt-end:a",
                ]),
                encoding="utf-8",
            )
            checker.process_module(type("Module", (), {"file": str(target)})())
        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()
