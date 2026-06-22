"""Pylint checker for user-facing error surfacing without diagnostic logging."""

from __future__ import annotations

from astroid import nodes
from pylint.checkers import BaseChecker

_UI_METHODS = frozenset({"error", "warn", "result"})
_LOGGER_METHODS = frozenset({"warning", "error", "exception", "critical"})
_ERROR_STATUSES = frozenset({"ERROR", "FAIL", "ABORTED"})


def _call_attr_name(call: nodes.Call) -> str | None:
    func = call.func
    if isinstance(func, nodes.Attribute):
        return func.attrname
    if isinstance(func, nodes.Name):
        return func.name
    return None


def _call_base_name(call: nodes.Call) -> str | None:
    func = call.func
    if isinstance(func, nodes.Attribute) and isinstance(func.expr, nodes.Name):
        return func.expr.name
    return None


def _keyword_value(call: nodes.Call, keyword_name: str) -> nodes.NodeNG | None:
    for keyword in call.keywords or []:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


def _dict_status_string(node: nodes.NodeNG) -> str | None:
    if not isinstance(node, nodes.Dict):
        return None
    for key, value in node.items:
        if not isinstance(key, nodes.Const) or key.value != "status":
            continue
        if isinstance(value, nodes.Const) and isinstance(value.value, str):
            return value.value
    return None


def _is_user_facing_ui_call(call: nodes.Call) -> bool:
    if _call_base_name(call) != "ui":
        return False
    attr = _call_attr_name(call)
    if attr in {"error", "warn"}:
        return True
    if attr != "result" or not call.args:
        return False
    status = _dict_status_string(call.args[0])
    return status in _ERROR_STATUSES


def _is_logger_call(call: nodes.Call) -> bool:
    return _call_base_name(call) == "logger" and _call_attr_name(call) in _LOGGER_METHODS


class ErrorSurfacingChecker(BaseChecker):
    """Require diagnostic logging when an except block surfaces a user-facing error."""

    name = "studio-error-surfaces"
    msgs = {
        "W9004": (
            "User-facing error is surfaced without diagnostic logging in except block",
            "user-facing-error-without-log",
            "Used when an except handler reports an error or warning through ui but "
            "does not emit a diagnostic logger entry for debugging.",
        ),
    }

    def visit_try(self, node: nodes.Try) -> None:
        """Check except handlers for ui-facing errors without logger diagnostics."""
        for handler in node.handlers:
            has_user_facing_surface = False
            has_diagnostic_log = False
            for stmt in handler.body:
                for call in stmt.nodes_of_class(nodes.Call):
                    if _is_user_facing_ui_call(call):
                        has_user_facing_surface = True
                    if _is_logger_call(call):
                        has_diagnostic_log = True
            if has_user_facing_surface and not has_diagnostic_log:
                self.add_message("user-facing-error-without-log", node=handler)


def register(linter) -> None:
    """Register the checker once."""
    for checkers in getattr(linter, "_checkers", {}).values():
        for checker in checkers:
            if getattr(checker, "name", "") == ErrorSurfacingChecker.name:
                return
    linter.register_checker(ErrorSurfacingChecker(linter))
