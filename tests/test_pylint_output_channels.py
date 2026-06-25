"""Integration tests for the local output-channel Pylint checker."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.pylint_plugin_fakes import (
    Attribute,
    Call,
    Const,
    Keyword,
    Name,
    load_plugin_module,
    set_root,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHONPATH = os.pathsep.join([
    str(REPO_ROOT / "src"),
    str(REPO_ROOT / "skills" / "studio" / "scripts"),
])


def _run_pylint(code: str, *, relative_path: str = "sample.py") -> subprocess.CompletedProcess[str]:
    with TemporaryDirectory() as td:
        target = Path(td) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
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
                "--enable=stdout-bypass,stderr-bypass",
                str(target),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )


def _assert_pylint_ran(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode in (0, 4, 16):
        return
    raise AssertionError(
        "pylint invocation failed unexpectedly:\n"
        f"returncode={result.returncode}\n"
        f"stdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )


class TestOutputChannelsChecker(unittest.TestCase):
    """Exercise the local Pylint checker on temporary files."""

    def test_helper_functions_cover_attribute_and_stream_detection(self) -> None:
        module = load_plugin_module("output_channels")
        sys_stdout = Attribute(Name("sys"), "stdout")
        sys_stderr = Attribute(Name("sys"), "stderr")
        call = Call(Name("print"), keywords=[Keyword("file", sys_stdout)])
        broken_attr = Attribute(Const("x"), "stdout")

        self.assertEqual(module._attribute_chain(sys_stdout), ["sys", "stdout"])
        self.assertIsNone(module._attribute_chain(broken_attr))
        self.assertIsNone(module._attribute_chain(Const("x")))
        self.assertTrue(module._is_sys_stream(sys_stdout, "stdout"))
        self.assertFalse(module._is_sys_stream(sys_stderr, "stdout"))
        self.assertTrue(module._is_print_call(call))
        self.assertIs(module._keyword_value(call, "file"), sys_stdout)
        self.assertIsNone(module._keyword_value(call, "missing"))
        self.assertTrue(module._is_ui_module(set_root(Call(Name("noop")), "skills/studio/scripts/studio/utils/ui.py")))
        self.assertTrue(module._is_proxy_module(set_root(Call(Name("noop")), "src/studio_proxy/cli.py")))

    def test_checker_covers_print_stream_subprocess_and_register_paths(self) -> None:
        module = load_plugin_module("output_channels")
        checker = module.OutputChannelsChecker(linter=None)
        messages: list[str] = []
        checker.add_message = lambda msgid, node=None: messages.append(msgid)

        checker.visit_call(set_root(Call(Name("print")), "pkg/sample.py"))
        checker.visit_call(
            set_root(Call(Name("print"), keywords=[Keyword("file", Attribute(Name("sys"), "stderr"))]), "pkg/sample.py")
        )
        checker.visit_call(
            set_root(Call(Name("print"), keywords=[Keyword("file", Attribute(Name("sys"), "stdout"))]), "pkg/sample.py")
        )
        checker.visit_call(
            set_root(Call(Attribute(Attribute(Name("sys"), "stdout"), "write")), "pkg/sample.py")
        )
        checker.visit_call(
            set_root(Call(Attribute(Attribute(Name("sys"), "stderr"), "write")), "pkg/sample.py")
        )
        checker.visit_call(
            set_root(
                Call(
                    Name("run"),
                    keywords=[
                        Keyword("stdout", Attribute(Name("sys"), "stdout")),
                        Keyword("stdin", Attribute(Name("sys"), "stdin")),
                    ],
                ),
                "pkg/sample.py",
            )
        )
        checker.visit_call(
            set_root(
                Call(
                    Name("run"),
                    keywords=[Keyword("stderr", Attribute(Name("sys"), "stderr"))],
                ),
                "pkg/sample.py",
            )
        )
        checker.visit_call(
            set_root(
                Call(
                    Name("run"),
                    keywords=[Keyword("stdout", Attribute(Name("sys"), "stdout"))],
                ),
                "src/studio_proxy/cli.py",
            )
        )
        checker.visit_call(set_root(Call(Const("not a function")), "pkg/sample.py"))

        self.assertEqual(
            messages,
            [
                "stdout-bypass",
                "stderr-bypass",
                "stdout-bypass",
                "stdout-bypass",
                "stderr-bypass",
                "stdout-bypass",
                "stderr-bypass",
            ],
        )

        existing = type("Existing", (), {"name": module.OutputChannelsChecker.name})()
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
        self.assertIsInstance(recorded[0], module.OutputChannelsChecker)

    def test_flags_plain_print_to_stdout(self) -> None:
        result = _run_pylint(
            """
            def run():
                print("hello")
            """
        )
        _assert_pylint_ran(result)
        self.assertIn("stdout-bypass", result.stdout)

    def test_flags_sys_stdout_write(self) -> None:
        result = _run_pylint(
            """
            import sys

            def run():
                sys.stdout.write("hello\\n")
            """
        )
        _assert_pylint_ran(result)
        self.assertIn("stdout-bypass", result.stdout)

    def test_flags_print_to_stderr(self) -> None:
        result = _run_pylint(
            """
            import sys

            def run():
                print("bad", file=sys.stderr)
            """
        )
        _assert_pylint_ran(result)
        self.assertIn("stderr-bypass", result.stdout)

    def test_flags_subprocess_passthrough_to_stderr(self) -> None:
        result = _run_pylint(
            """
            import subprocess
            import sys

            def run():
                subprocess.run(["echo", "hello"], stderr=sys.stderr, check=False)
            """
        )
        _assert_pylint_ran(result)
        self.assertIn("stderr-bypass", result.stdout)

    def test_allows_logger_usage(self) -> None:
        result = _run_pylint(
            """
            import logging

            logger = logging.getLogger(__name__)

            def run():
                logger.warning("bad")
            """
        )
        _assert_pylint_ran(result)
        self.assertNotIn("stdout-bypass", result.stdout)
        self.assertNotIn("stderr-bypass", result.stdout)

    def test_allows_stdout_inside_ui_module(self) -> None:
        result = _run_pylint(
            """
            import sys

            def render():
                sys.stdout.write("ok\\n")
            """,
            relative_path="skills/studio/scripts/studio/utils/ui.py",
        )
        _assert_pylint_ran(result)
        self.assertNotIn("stdout-bypass", result.stdout)

    def test_allows_stdout_inside_proxy_module(self) -> None:
        result = _run_pylint(
            """
            import subprocess
            import sys

            def render():
                print("ok")
                sys.stdout.write("still ok\\n")
                subprocess.run(["echo", "hello"], stdout=sys.stdout, check=False)
            """,
            relative_path="src/studio_proxy/cli.py",
        )
        _assert_pylint_ran(result)
        self.assertNotIn("stdout-bypass", result.stdout)

    def test_still_forbids_stderr_inside_ui_module(self) -> None:
        result = _run_pylint(
            """
            import sys

            def render():
                sys.stderr.write("bad\\n")
            """,
            relative_path="skills/studio/scripts/studio/utils/ui.py",
        )
        _assert_pylint_ran(result)
        self.assertIn("stderr-bypass", result.stdout)

    def test_still_forbids_stderr_inside_proxy_module(self) -> None:
        result = _run_pylint(
            """
            import sys

            def render():
                sys.stderr.write("bad\\n")
            """,
            relative_path="src/studio_proxy/cli.py",
        )
        _assert_pylint_ran(result)
        self.assertIn("stderr-bypass", result.stdout)


if __name__ == "__main__":
    unittest.main()
