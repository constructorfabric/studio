"""Pylint checker for enforcing ui/logger output channels."""

from __future__ import annotations

from astroid import nodes
from pylint.checkers import BaseChecker

_STDOUT_METHODS = frozenset({"write", "writelines", "flush"})
_STDERR_METHODS = frozenset({"write", "writelines", "flush"})
_SUBPROCESS_STREAM_KWARGS = frozenset({"stdout", "stderr"})
_ALLOWED_STDOUT_MODULE_SUFFIXES = (
    "skills/studio/scripts/studio/utils/ui.py",
    "studio/utils/ui.py",
)
_ALLOWED_PROXY_STDOUT_MODULE_PREFIXES = (
    "src/studio_proxy/",
    "studio_proxy/",
)


def _module_path(node: nodes.NodeNG) -> str:
    root = node.root()
    file_path = getattr(root, "file", None)
    return str(file_path or "")


def _is_ui_module(node: nodes.NodeNG) -> bool:
    path = _module_path(node).replace("\\", "/")
    return any(path.endswith(suffix) for suffix in _ALLOWED_STDOUT_MODULE_SUFFIXES)


def _is_proxy_module(node: nodes.NodeNG) -> bool:
    path = _module_path(node).replace("\\", "/")
    return any(prefix in path for prefix in _ALLOWED_PROXY_STDOUT_MODULE_PREFIXES)


def _allows_stdout_bypass(node: nodes.NodeNG) -> bool:
    return _is_ui_module(node) or _is_proxy_module(node)


def _attribute_chain(node: nodes.NodeNG) -> list[str] | None:
    if isinstance(node, nodes.Name):
        return [node.name]
    if isinstance(node, nodes.Attribute):
        base = _attribute_chain(node.expr)
        if base is None:
            return None
        return [*base, node.attrname]
    return None


def _is_sys_stream(node: nodes.NodeNG, stream_name: str) -> bool:
    chain = _attribute_chain(node)
    return chain == ["sys", stream_name]


def _is_print_call(node: nodes.Call) -> bool:
    return isinstance(node.func, nodes.Name) and node.func.name == "print"


def _keyword_value(node: nodes.Call, keyword_name: str) -> nodes.NodeNG | None:
    for keyword in node.keywords or []:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


class OutputChannelsChecker(BaseChecker):
    """Flag writes to stdout/stderr that bypass ui or logger."""

    name = "studio-output-channels"
    msgs = {
        "W9002": (
            "Direct stdout write bypasses studio ui output API",
            "stdout-bypass",
            "Used when code writes to stdout directly instead of routing user-visible output via studio.utils.ui.",
        ),
        "W9003": (
            "Direct stderr write bypasses logger output API",
            "stderr-bypass",
            "Used when code writes to stderr directly instead of routing diagnostics via logging.",
        ),
    }

    def visit_call(self, node: nodes.Call) -> None:
        """Check calls that can write directly to stdout/stderr."""
        if _is_print_call(node):
            self._check_print_call(node)
            return
        self._check_stream_method_call(node)
        self._check_subprocess_stream_passthrough(node)

    def _check_print_call(self, node: nodes.Call) -> None:
        target = _keyword_value(node, "file")
        if target is None:
            if not _allows_stdout_bypass(node):
                self.add_message("stdout-bypass", node=node)
            return
        if _is_sys_stream(target, "stdout") and not _allows_stdout_bypass(node):
            self.add_message("stdout-bypass", node=node)
        elif _is_sys_stream(target, "stderr"):
            self.add_message("stderr-bypass", node=node)

    def _check_stream_method_call(self, node: nodes.Call) -> None:
        if not isinstance(node.func, nodes.Attribute):
            return
        attr = node.func.attrname
        target = node.func.expr
        if attr in _STDOUT_METHODS and _is_sys_stream(target, "stdout") and not _allows_stdout_bypass(node):
            self.add_message("stdout-bypass", node=node)
        elif attr in _STDERR_METHODS and _is_sys_stream(target, "stderr"):
            self.add_message("stderr-bypass", node=node)

    def _check_subprocess_stream_passthrough(self, node: nodes.Call) -> None:
        for keyword in node.keywords or []:
            if keyword.arg not in _SUBPROCESS_STREAM_KWARGS:
                continue
            if (
                _is_sys_stream(keyword.value, "stdout")
                and keyword.arg == "stdout"
                and not _is_proxy_module(node)
            ):
                self.add_message("stdout-bypass", node=keyword.value)
            elif _is_sys_stream(keyword.value, "stderr") and keyword.arg == "stderr":
                self.add_message("stderr-bypass", node=keyword.value)


def register(linter) -> None:
    """Register the checker once."""
    for checkers in getattr(linter, "_checkers", {}).values():
        for checker in checkers:
            if getattr(checker, "name", "") == OutputChannelsChecker.name:
                return
    linter.register_checker(OutputChannelsChecker(linter))
