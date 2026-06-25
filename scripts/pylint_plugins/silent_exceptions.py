"""Pylint checker for silently swallowed exceptions."""

from __future__ import annotations

from astroid import nodes
from pylint.checkers import BaseChecker

_EXEMPT_EXCEPTION_NAMES = frozenset({
    "EOFError",
    "GeneratorExit",
    "KeyboardInterrupt",
    "StopIteration",
})

_VISIBLE_SIGNAL_NAMES = frozenset({
    "critical",
    "error",
    "exception",
    "fail",
    "fatal",
    "info",
    "print",
    "result",
    "substep",
    "warn",
    "warning",
})

_VISIBLE_SIGNAL_WRAPPER_PREFIXES = frozenset({
    "emit_",
    "log_",
    "report_",
    "show_",
    "write_",
})

_VISIBLE_SIGNAL_WRAPPER_SUFFIXES = frozenset({
    "_error",
    "_errors",
    "_fail",
    "_message",
    "_messages",
    "_result",
    "_results",
    "_warn",
    "_warning",
    "_warnings",
})

_MUTATING_SIGNAL_METHODS = frozenset({
    "append",
    "extend",
    "setdefault",
    "update",
})

_DIAGNOSTIC_KEYS = frozenset({
    "error",
    "errors",
    "fail",
    "level",
    "message",
    "messages",
    "status",
    "warning",
    "warnings",
})

_PASSIVE_CALL_NAMES = frozenset({
    "append",
    "extend",
    "write",
    "writelines",
})


def _exception_names(type_node: nodes.NodeNG | None) -> set[str]:
    """Return the exception type names referenced by an except handler."""
    if type_node is None:
        return set()
    if isinstance(type_node, nodes.Name):
        return {type_node.name}
    if isinstance(type_node, nodes.Attribute):
        return {type_node.attrname}
    if isinstance(type_node, nodes.Tuple):
        names: set[str] = set()
        for item in type_node.elts:
            names.update(_exception_names(item))
        return names
    return set()


def _is_silent_value(value: nodes.NodeNG | None, silent_names: set[str] | None = None) -> bool:
    """Return whether a node evaluates to a sentinel fallback value."""
    if value is None:
        return True
    if isinstance(value, nodes.Name):
        return value.name in (silent_names or set())
    if isinstance(value, nodes.Const):
        return value.value in (None, False, 0, "", b"")
    if isinstance(value, (nodes.List, nodes.Set, nodes.Tuple)):
        return not value.elts
    if isinstance(value, nodes.Dict):
        return not value.items
    return False


def _is_silent_return(stmt: nodes.Return, silent_names: set[str] | None = None) -> bool:
    """Return whether a return statement only yields a sentinel fallback."""
    return _is_silent_value(stmt.value, silent_names)


def _is_silent_statement(stmt: nodes.NodeNG, silent_names: set[str] | None = None) -> bool:
    """Return whether a statement suppresses control flow without surfacing the error."""
    return (
        isinstance(stmt, (nodes.Pass, nodes.Continue, nodes.Break))
        or isinstance(stmt, nodes.Return) and _is_silent_return(stmt, silent_names)
    )


def _is_passive_assignment(stmt: nodes.NodeNG) -> bool:
    """Return whether an assignment is local bookkeeping, not error surfacing."""
    return isinstance(stmt, (nodes.Assign, nodes.AnnAssign, nodes.AugAssign))


def _assigned_silent_names(handler: nodes.ExceptHandler) -> set[str]:
    """Return local names assigned sentinel values inside an except handler."""
    names: set[str] = set()
    for stmt in handler.body:
        if isinstance(stmt, nodes.Assign):
            if _is_silent_value(stmt.value, names):
                for target in stmt.targets:
                    if isinstance(target, nodes.AssignName):
                        names.add(target.name)
        elif isinstance(stmt, nodes.AnnAssign):
            if isinstance(stmt.target, nodes.AssignName) and _is_silent_value(stmt.value, names):
                names.add(stmt.target.name)
    return names


def _callee_name(call: nodes.Call) -> str | None:
    """Return the simple callee name for a call expression."""
    func = call.func
    if isinstance(func, nodes.Name):
        return func.name
    if isinstance(func, nodes.Attribute):
        return func.attrname
    return None


def _is_visible_signal_name(name: str | None) -> bool:
    """Return whether a callee name obviously surfaces the exception."""
    if not name:
        return False
    normalized = name.lstrip("_")
    if normalized in _VISIBLE_SIGNAL_NAMES:
        return True
    if normalized.startswith("stderr_"):
        return True
    if any(normalized.endswith(suffix) for suffix in _VISIBLE_SIGNAL_WRAPPER_SUFFIXES):
        return True
    for prefix in _VISIBLE_SIGNAL_WRAPPER_PREFIXES:
        if not normalized.startswith(prefix):
            continue
        remainder = normalized[len(prefix):]
        if remainder in _VISIBLE_SIGNAL_NAMES or remainder.startswith("stderr"):
            return True
    return False


def _dict_has_diagnostic_keys(node: nodes.NodeNG) -> bool:
    """Return whether a dict literal carries obvious diagnostic fields."""
    if not isinstance(node, nodes.Dict):
        return False
    for key_node, _value_node in node.items:
        if isinstance(key_node, nodes.Const) and isinstance(key_node.value, str):
            if key_node.value in _DIAGNOSTIC_KEYS:
                return True
    return False


def _assignment_surfaces_error(stmt: nodes.NodeNG) -> bool:
    """Return whether an assignment stores an explicit diagnostic field."""
    if not isinstance(stmt, nodes.Assign):
        return False
    subscript_node = getattr(nodes, "Subscript", None)
    if subscript_node is None:
        return False
    for target in stmt.targets:
        if not isinstance(target, subscript_node):
            continue
        index = getattr(target, "slice", None)
        if isinstance(index, nodes.Const) and isinstance(index.value, str):
            if index.value in _DIAGNOSTIC_KEYS or index.value.endswith(("_error", "_errors", "_warning", "_warnings")):
                return True
    return False


def _call_surfaces_error(call: nodes.Call) -> bool:
    """Return whether a call obviously surfaces the exception."""
    callee_name = _callee_name(call)
    if _is_visible_signal_name(callee_name):
        return True
    if callee_name not in _MUTATING_SIGNAL_METHODS:
        return False
    for arg in call.args:
        if _dict_has_diagnostic_keys(arg):
            return True
        if isinstance(arg, nodes.Call) and _is_visible_signal_name(_callee_name(arg)):
            return True
    return False


def _has_visible_signal(stmt: nodes.NodeNG) -> bool:
    """Return whether a statement visibly surfaces an error."""
    if isinstance(stmt, nodes.Raise):
        return True
    if _assignment_surfaces_error(stmt):
        return True
    for call in stmt.nodes_of_class(nodes.Call):
        if _call_surfaces_error(call):
            return True
    return False


def _is_passive_statement(stmt: nodes.NodeNG, silent_names: set[str] | None = None) -> bool:
    """Return whether a statement only mutates local control/data before a silent fallback."""
    if _is_silent_statement(stmt, silent_names) or _is_passive_assignment(stmt):
        return True
    if _has_visible_signal(stmt):
        return False
    call: nodes.Call | None = None
    expr_node = getattr(nodes, "Expr", None)
    if expr_node is not None and isinstance(stmt, expr_node) and isinstance(stmt.value, nodes.Call):
        call = stmt.value
    elif isinstance(stmt, nodes.Call):
        call = stmt
    return _callee_name(call) in _PASSIVE_CALL_NAMES if call is not None else False


def _handler_exception_name(handler: nodes.ExceptHandler) -> str | None:
    """Return the bound exception variable name, if any."""
    name = handler.name
    if name is None:
        return None
    if isinstance(name, nodes.AssignName):
        return name.name
    return str(name)


class SilentExceptionSwallowedChecker(BaseChecker):
    """Flag except handlers that silently swallow failures."""

    name = "studio-silent-exception-swallowed"
    msgs = {
        "W9001": (
            "Exception is swallowed silently; surface it via logging, status reporting, or re-raise",
            "silent-exception-swallowed",
            "Used when an except handler suppresses an exception with pass, continue, break, "
            "or a sentinel fallback return without exposing the failure to callers or users.",
        ),
    }

    def visit_try(self, node: nodes.Try) -> None:
        """Check except handlers for silent swallowing."""
        for handler in node.handlers:
            exception_names = _exception_names(handler.type)
            if exception_names and exception_names.issubset(_EXEMPT_EXCEPTION_NAMES):
                continue
            if not handler.body:
                continue
            if any(_has_visible_signal(stmt) for stmt in handler.body):
                continue
            silent_names = _assigned_silent_names(handler)
            if not any(_is_silent_statement(stmt, silent_names) for stmt in handler.body):
                continue
            if all(_is_passive_statement(stmt, silent_names) for stmt in handler.body):
                self.add_message("silent-exception-swallowed", node=handler)


def register(linter) -> None:
    """Register the checker."""
    for checkers in getattr(linter, "_checkers", {}).values():
        for checker in checkers:
            if getattr(checker, "name", "") == SilentExceptionSwallowedChecker.name:
                return
    linter.register_checker(SilentExceptionSwallowedChecker(linter))
