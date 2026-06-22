"""Integration tests for the user-facing error surface Pylint checker."""

from __future__ import annotations

import os
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.pylint_plugin_fakes import (
    Attribute,
    Call,
    Const,
    Dict,
    ExceptHandler,
    Keyword,
    Name,
    Try,
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
                "--enable=user-facing-error-without-log",
                str(target),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )


class TestErrorSurfacesChecker(unittest.TestCase):
    """Exercise user-facing error surfacing requirements."""

    def test_helper_functions_cover_name_keyword_and_status_paths(self) -> None:
        module = load_plugin_module("error_surfaces")
        ui_error = Call(Attribute(Name("ui"), "error"))
        bare_call = Call(Name("work"))
        other_call = Call(Const("not callable"))
        payload = Dict([(Const("status"), Const("FAIL"))])
        call_with_keyword = Call(Name("render"), keywords=[Keyword("payload", payload)])

        self.assertEqual(module._call_attr_name(ui_error), "error")
        self.assertEqual(module._call_attr_name(bare_call), "work")
        self.assertIsNone(module._call_attr_name(other_call))
        self.assertEqual(module._call_base_name(ui_error), "ui")
        self.assertIsNone(module._call_base_name(bare_call))
        self.assertIs(module._keyword_value(call_with_keyword, "payload"), payload)
        self.assertIsNone(module._keyword_value(call_with_keyword, "missing"))
        self.assertEqual(module._dict_status_string(payload), "FAIL")
        self.assertIsNone(module._dict_status_string(Const("nope")))
        self.assertIsNone(module._dict_status_string(Dict([(Const("status"), Const(1))])))

    def test_ui_and_logger_detection_helpers(self) -> None:
        module = load_plugin_module("error_surfaces")

        self.assertTrue(module._is_user_facing_ui_call(Call(Attribute(Name("ui"), "warn"))))
        self.assertTrue(
            module._is_user_facing_ui_call(
                Call(Attribute(Name("ui"), "result"), args=[Dict([(Const("status"), Const("ABORTED"))])])
            )
        )
        self.assertFalse(module._is_user_facing_ui_call(Call(Attribute(Name("ui"), "result"))))
        self.assertFalse(
            module._is_user_facing_ui_call(
                Call(Attribute(Name("ui"), "result"), args=[Dict([(Const("status"), Const("OK"))])])
            )
        )
        self.assertFalse(module._is_user_facing_ui_call(Call(Attribute(Name("view"), "error"))))
        self.assertTrue(module._is_logger_call(Call(Attribute(Name("logger"), "critical"))))
        self.assertFalse(module._is_logger_call(Call(Attribute(Name("logger"), "info"))))

    def test_checker_and_register_paths(self) -> None:
        module = load_plugin_module("error_surfaces")
        checker = module.ErrorSurfacingChecker(linter=None)
        messages: list[str] = []
        checker.add_message = lambda msgid, node=None: messages.append(msgid)

        checker.visit_try(
            Try([
                ExceptHandler(body=[Call(Attribute(Name("ui"), "error"))]),
                ExceptHandler(body=[Call(Attribute(Name("logger"), "exception")), Call(Attribute(Name("ui"), "error"))]),
            ])
        )

        self.assertEqual(messages, ["user-facing-error-without-log"])

        existing = type("Existing", (), {"name": module.ErrorSurfacingChecker.name})()
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
        self.assertIsInstance(recorded[0], module.ErrorSurfacingChecker)

    def test_flags_ui_error_without_logger_in_except(self) -> None:
        result = _run_pylint(
            """
            class UI:
                def error(self, message):
                    return message

            ui = UI()

            def run():
                try:
                    work()
                except OSError:
                    ui.error("failed")
            """
        )
        self.assertIn("user-facing-error-without-log", result.stdout)

    def test_flags_ui_result_error_without_logger_in_except(self) -> None:
        result = _run_pylint(
            """
            class UI:
                def result(self, payload):
                    return payload

            ui = UI()

            def run():
                try:
                    work()
                except OSError:
                    ui.result({"status": "ERROR", "message": "failed"})
            """
        )
        self.assertIn("user-facing-error-without-log", result.stdout)

    def test_allows_ui_error_with_logger_exception(self) -> None:
        result = _run_pylint(
            """
            class UI:
                def error(self, message):
                    return message

            class Logger:
                def exception(self, message):
                    return message

            ui = UI()
            logger = Logger()

            def run():
                try:
                    work()
                except OSError:
                    logger.exception("failed to run")
                    ui.error("failed")
            """
        )
        self.assertNotIn("user-facing-error-without-log", result.stdout)

    def test_ignores_ui_info_outside_error_surface(self) -> None:
        result = _run_pylint(
            """
            class UI:
                def info(self, message):
                    return message

            ui = UI()

            def run():
                try:
                    work()
                except OSError:
                    ui.info("retrying")
            """
        )
        self.assertNotIn("user-facing-error-without-log", result.stdout)


if __name__ == "__main__":
    unittest.main()
