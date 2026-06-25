from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import ModuleType
from typing import Any


class NodeNG:
    def __init__(self) -> None:
        self._root = self

    def root(self) -> Any:
        return self._root

    def _iter_children(self) -> list[Any]:
        return []

    def nodes_of_class(self, klass: type[Any]):
        if isinstance(self, klass):
            yield self
        for child in self._iter_children():
            if isinstance(child, klass):
                yield child
            if hasattr(child, "nodes_of_class"):
                yield from child.nodes_of_class(klass)


class Name(NodeNG):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class Attribute(NodeNG):
    def __init__(self, expr: NodeNG, attrname: str) -> None:
        super().__init__()
        self.expr = expr
        self.attrname = attrname

    def _iter_children(self) -> list[Any]:
        return [self.expr]


class Const(NodeNG):
    def __init__(self, value: Any) -> None:
        super().__init__()
        self.value = value


class Keyword(NodeNG):
    def __init__(self, arg: str | None, value: NodeNG) -> None:
        super().__init__()
        self.arg = arg
        self.value = value

    def _iter_children(self) -> list[Any]:
        return [self.value]


class Call(NodeNG):
    def __init__(
        self,
        func: NodeNG,
        args: list[NodeNG] | None = None,
        keywords: list[Keyword] | None = None,
    ) -> None:
        super().__init__()
        self.func = func
        self.args = args or []
        self.keywords = keywords or []

    def _iter_children(self) -> list[Any]:
        return [self.func, *self.args, *self.keywords]


class Dict(NodeNG):
    def __init__(self, items: list[tuple[NodeNG, NodeNG]]) -> None:
        super().__init__()
        self.items = items

    def _iter_children(self) -> list[Any]:
        children: list[Any] = []
        for key, value in self.items:
            children.extend([key, value])
        return children


class Import(NodeNG):
    def __init__(self, names: list[tuple[str, str | None]]) -> None:
        super().__init__()
        self.names = names


class ImportFrom(NodeNG):
    def __init__(self, modname: str) -> None:
        super().__init__()
        self.modname = modname


class Pass(NodeNG):
    pass


class Continue(NodeNG):
    pass


class Break(NodeNG):
    pass


class Raise(NodeNG):
    pass


class Return(NodeNG):
    def __init__(self, value: NodeNG | None = None) -> None:
        super().__init__()
        self.value = value

    def _iter_children(self) -> list[Any]:
        return [] if self.value is None else [self.value]


class AssignName(NodeNG):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class Assign(NodeNG):
    def __init__(self, targets: list[AssignName], value: NodeNG) -> None:
        super().__init__()
        self.targets = targets
        self.value = value

    def _iter_children(self) -> list[Any]:
        return [*self.targets, self.value]


class AnnAssign(NodeNG):
    def __init__(self, target: AssignName, value: NodeNG | None) -> None:
        super().__init__()
        self.target = target
        self.value = value

    def _iter_children(self) -> list[Any]:
        return [self.target] if self.value is None else [self.target, self.value]


class AugAssign(NodeNG):
    def __init__(self, target: NodeNG, value: NodeNG) -> None:
        super().__init__()
        self.target = target
        self.value = value

    def _iter_children(self) -> list[Any]:
        return [self.target, self.value]


class Tuple(NodeNG):
    def __init__(self, elts: list[NodeNG]) -> None:
        super().__init__()
        self.elts = elts

    def _iter_children(self) -> list[Any]:
        return list(self.elts)


class List(NodeNG):
    def __init__(self, elts: list[NodeNG]) -> None:
        super().__init__()
        self.elts = elts

    def _iter_children(self) -> list[Any]:
        return list(self.elts)


class Set(NodeNG):
    def __init__(self, elts: list[NodeNG]) -> None:
        super().__init__()
        self.elts = elts

    def _iter_children(self) -> list[Any]:
        return list(self.elts)


class ExceptHandler(NodeNG):
    def __init__(
        self,
        type: NodeNG | None = None,
        body: list[NodeNG] | None = None,
        name: AssignName | str | None = None,
    ) -> None:
        super().__init__()
        self.type = type
        self.body = body or []
        self.name = name

    def _iter_children(self) -> list[Any]:
        children: list[Any] = []
        if self.type is not None:
            children.append(self.type)
        children.extend(self.body)
        return children


class Try(NodeNG):
    def __init__(self, handlers: list[ExceptHandler]) -> None:
        super().__init__()
        self.handlers = handlers

    def _iter_children(self) -> list[Any]:
        return list(self.handlers)


class FunctionDef(NodeNG):
    def __init__(self, name: str, body: list[NodeNG] | None = None) -> None:
        super().__init__()
        self.name = name
        self.body = body or []

    def _iter_children(self) -> list[Any]:
        return list(self.body)


class ClassDef(NodeNG):
    def __init__(self, name: str, body: list[NodeNG] | None = None) -> None:
        super().__init__()
        self.name = name
        self.body = body or []

    def _iter_children(self) -> list[Any]:
        return list(self.body)


class BaseChecker:
    def __init__(self, linter: Any | None = None) -> None:
        self.linter = linter

    def add_message(self, msgid: str, node: Any | None = None) -> None:
        raise NotImplementedError


class BaseRawFileChecker(BaseChecker):
    pass


class FakeRoot:
    def __init__(self, file_path: str) -> None:
        self.file = file_path


def set_root(node: Any, file_path: str) -> Any:
    root = FakeRoot(file_path)

    def _apply(current: Any) -> None:
        if isinstance(current, NodeNG):
            current._root = root
            for child in current._iter_children():
                _apply(child)

    _apply(node)
    return node


def _install_fake_dependencies() -> None:
    astroid_module = ModuleType("astroid")
    nodes_module = ModuleType("astroid.nodes")
    pylint_module = ModuleType("pylint")
    checkers_module = ModuleType("pylint.checkers")

    for cls in [
        AnnAssign,
        Assign,
        AssignName,
        Attribute,
        AugAssign,
        Break,
        Call,
        Const,
        Continue,
        Dict,
        ExceptHandler,
        Import,
        ImportFrom,
        List,
        Name,
        NodeNG,
        Pass,
        Raise,
        Return,
        Set,
        Try,
        Tuple,
    ]:
        setattr(nodes_module, cls.__name__, cls)

    astroid_module.nodes = nodes_module
    checkers_module.BaseChecker = BaseChecker
    checkers_module.BaseRawFileChecker = BaseRawFileChecker
    pylint_module.checkers = checkers_module

    sys.modules["astroid"] = astroid_module
    sys.modules["astroid.nodes"] = nodes_module
    sys.modules["pylint"] = pylint_module
    sys.modules["pylint.checkers"] = checkers_module


def load_plugin_module(module_basename: str):
    _install_fake_dependencies()
    repo_root = Path(__file__).resolve().parents[1]
    file_path = (
        repo_root / "scripts" / "pylint_plugins" / f"{module_basename}.py"
    )
    full_name = f"tests._pylint_plugin_{module_basename}"
    sys.modules.pop(full_name, None)
    spec = importlib.util.spec_from_file_location(full_name, file_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module
