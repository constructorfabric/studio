"""Integration tests for the local silent-exception Pylint checker."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.pylint_plugin_fakes import (
    AnnAssign,
    Assign,
    AssignName,
    Attribute,
    Call,
    Const,
    ExceptHandler,
    Name,
    Pass,
    Raise,
    Return,
    Try,
    Tuple,
    load_plugin_module,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHONPATH = os.pathsep.join([
    str(REPO_ROOT / "src"),
    str(REPO_ROOT / "skills" / "studio" / "scripts"),
])


def _run_pylint(code: str) -> subprocess.CompletedProcess[str]:
    with TemporaryDirectory() as td:
        target = Path(td) / "sample.py"
        target.write_text(textwrap.dedent(code), encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = PYTHONPATH
        return subprocess.run(
            [
                "pipx",
                "run",
                "--spec",
                "pylint",
                "pylint",
                "--score=n",
                "--disable=all",
                "--enable=silent-exception-swallowed",
                str(target),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )


class TestSilentExceptionSwallowedChecker(unittest.TestCase):
    """Exercise the local Pylint checker on temporary files."""

    def test_helper_functions_cover_exception_names_and_silent_values(self) -> None:
        module = load_plugin_module("silent_exceptions")

        self.assertEqual(module._exception_names(None), set())
        self.assertEqual(module._exception_names(Name("OSError")), {"OSError"})
        self.assertEqual(module._exception_names(Attribute(Name("mod"), "CustomError")), {"CustomError"})
        self.assertEqual(module._exception_names(Tuple([Name("OSError"), Attribute(Name("mod"), "CustomError")])), {"OSError", "CustomError"})
        self.assertEqual(module._exception_names(Const("unexpected")), set())
        self.assertTrue(module._is_silent_value(None))
        self.assertTrue(module._is_silent_value(Name("fallback"), {"fallback"}))
        self.assertTrue(module._is_silent_value(Const("")))
        self.assertTrue(module._is_silent_value(module.nodes.List([])))
        self.assertTrue(module._is_silent_value(module.nodes.Dict([])))
        self.assertFalse(module._is_silent_value(Const(1)))
        self.assertFalse(module._is_silent_value(Call(Name("work"))))
        self.assertTrue(module._is_silent_return(Return(Const(False))))
        self.assertTrue(module._is_silent_statement(Pass()))
        self.assertTrue(module._is_passive_assignment(AnnAssign(AssignName("value"), Const(None))))

    def test_checker_helper_and_register_paths(self) -> None:
        module = load_plugin_module("silent_exceptions")
        handler = ExceptHandler(
            type=Name("OSError"),
            name="exc",
            body=[
                Assign([AssignName("fallback")], Const(None)),
                AnnAssign(AssignName("typed_fallback"), Name("fallback")),
                Return(Name("fallback")),
            ],
        )
        used_handler = ExceptHandler(
            type=Name("OSError"),
            name=AssignName("exc"),
            body=[Call(Name("print"), args=[Name("exc")])],
        )

        self.assertEqual(module._assigned_silent_names(handler), {"fallback", "typed_fallback"})
        self.assertEqual(module._handler_exception_name(handler), "exc")
        self.assertTrue(module._has_visible_signal(Raise()))
        self.assertTrue(module._has_visible_signal(Call(Attribute(Name("ui"), "warn"))))
        self.assertTrue(module._is_visible_signal_name("_warn"))
        self.assertTrue(module._is_visible_signal_name("_log_error"))
        self.assertTrue(module._is_visible_signal_name("_chunk_input_error"))
        self.assertTrue(module._is_visible_signal_name("write_stderr_warning"))
        self.assertEqual(module._callee_name(Call(Attribute(Name("ui"), "warn"))), "warn")
        self.assertIsNone(module._callee_name(Call(Const("unknown"))))
        self.assertFalse(module._is_passive_statement(Call(Name("work"))))
        self.assertTrue(module._is_passive_statement(Call(Attribute(Name("errors"), "append"), args=[Const("x")])))
        self.assertTrue(
            module._call_surfaces_error(
                Call(
                    Attribute(Name("result"), "update"),
                    args=[module.nodes.Dict([(Const("message"), Const("x"))])],
                )
            )
        )
        self.assertTrue(
            module._call_surfaces_error(
                Call(
                    Attribute(Name("checks"), "append"),
                    args=[module.nodes.Dict([(Const("level"), Const("FAIL")), (Const("message"), Const("x"))])],
                )
            )
        )

        checker = module.SilentExceptionSwallowedChecker(linter=None)
        messages: list[str] = []
        checker.add_message = lambda msgid, node=None: messages.append(msgid)
        checker.visit_try(
            Try([
                ExceptHandler(type=Name("KeyboardInterrupt"), body=[Return(Const(False))]),
                ExceptHandler(type=Name("OSError"), body=[]),
                used_handler,
                ExceptHandler(type=Name("OSError"), body=[Raise()]),
                handler,
            ])
        )
        self.assertEqual(messages, ["silent-exception-swallowed"])

        existing = type("Existing", (), {"name": module.SilentExceptionSwallowedChecker.name})()
        linter = type(
            "Linter",
            (),
            {"_checkers": {"astroid": [existing]}, "register_checker": lambda self, checker: (_ for _ in ()).throw(AssertionError)},
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
        self.assertIsInstance(recorded[0], module.SilentExceptionSwallowedChecker)

    def test_flags_except_pass(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError:
                    pass
            """
        )
        self.assertIn("silent-exception-swallowed", result.stdout)

    def test_flags_sentinel_return(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError:
                    return None
            """
        )
        self.assertIn("silent-exception-swallowed", result.stdout)

    def test_flags_assignment_then_empty_dict_return(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError:
                    data = {}
                    return data
            """
        )
        self.assertIn("silent-exception-swallowed", result.stdout)

    def test_allows_visible_error_reporting(self) -> None:
        result = _run_pylint(
            """
            class Logger:
                def warning(self, message, exc):
                    return message, exc

            logger = Logger()

            def run():
                try:
                    work()
                except OSError as exc:
                    logger.warning("fallback", exc)
                    return None
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)

    def test_allows_printed_warning_then_fallback(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError:
                    print("warning: fallback")
                    return {}
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)

    def test_allows_local_warn_wrapper_then_fallback(self) -> None:
        result = _run_pylint(
            """
            def _warn(message):
                print(message)

            def run():
                try:
                    work()
                except OSError as exc:
                    _warn(str(exc))
                    return None
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)

    def test_allows_diagnostic_result_update_then_return(self) -> None:
        result = _run_pylint(
            """
            def run():
                result = {}
                try:
                    work()
                except OSError as exc:
                    result.update({"status": "FAIL", "message": str(exc)})
                    return result
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)

    def test_allows_appending_structured_failure_record(self) -> None:
        result = _run_pylint(
            """
            def run(checks):
                try:
                    work()
                except OSError as exc:
                    checks.append({"level": "FAIL", "message": str(exc)})
                    return checks
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)

    def test_allows_setting_error_field_then_return_none(self) -> None:
        result = _run_pylint(
            """
            def run(result):
                try:
                    work()
                except OSError as exc:
                    result["error"] = str(exc)
                    return None
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)

    def test_flags_list_append_then_silent_return(self) -> None:
        result = _run_pylint(
            """
            def run(errors):
                try:
                    work()
                except OSError as exc:
                    errors.append(str(exc))
                    return None
            """
        )
        self.assertIn("silent-exception-swallowed", result.stdout)

    def test_flags_exception_string_assignment_then_silent_return(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except OSError as exc:
                    message = str(exc)
                    return None
            """
        )
        self.assertIn("silent-exception-swallowed", result.stdout)

    def test_allows_keyboard_interrupt_short_circuit(self) -> None:
        result = _run_pylint(
            """
            def run():
                try:
                    work()
                except KeyboardInterrupt:
                    return False
            """
        )
        self.assertNotIn("silent-exception-swallowed", result.stdout)


if __name__ == "__main__":
    unittest.main()
