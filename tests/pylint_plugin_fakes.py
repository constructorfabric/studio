from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from typing import Any

#: The real ``$HOME``, read at import time -- which is collection, before the autouse
#: fixture in ``conftest.py`` moves ``$HOME`` to a temp directory for each test.
#:
#: That fixture is right to move it: the brand directory hangs off ``Path.home()``, and
#: tests that make ``Path.home()`` itself raise need the real seam intact. But Python also
#: derives the *user* site-packages directory from ``$HOME``, so a subprocess started under
#: the moved one cannot import anything installed with ``pip install --user`` -- including
#: ``pipx``, which every test in this family shells out through. The failure has no
#: fingerprints: ``pipx`` dies on ``ModuleNotFoundError``, the subprocess yields empty
#: output, and 21 assertions fail claiming a checker never emitted its message.
_REAL_HOME = os.environ.get("HOME")

#: The other two variables that decide where a child resolves user-installed packages, and
#: whether it resolves them at all. Restoring ``$HOME`` alone is not enough: ``PYTHONUSERBASE``
#: redirects the user-site base to any path regardless of ``$HOME``, and ``PYTHONNOUSERSITE``
#: switches user-site off entirely. Either one reproduces the same unimportable-``pipx``
#: failure with ``$HOME`` perfectly correct, so they are removed rather than passed through.
#: Raised in review, and the reason the first test here was weak: ``site.getusersitepackages()``
#: computes its answer whether or not user-site is enabled, so asserting on that path alone
#: passes under ``PYTHONNOUSERSITE=1`` while a real ``pipx`` would still fail.
_USER_SITE_REDIRECTS = ("PYTHONNOUSERSITE", "PYTHONUSERBASE")


def subprocess_env(**extra: str) -> dict:
    """The environment for a subprocess that resolves its own imports.

    Restores the real ``$HOME``, drops the two other variables that steer user-site
    resolution, and applies ``extra`` on top. Use this rather than ``dict(os.environ)`` for
    any child process that has to find an installed program.

    ``HOME`` in ``extra`` raises rather than winning. No caller needs it, and a silent
    override would undo the one thing this function exists to do -- the failure it produces
    is the fingerprint-free one described above, so it is refused where it is visible rather
    than debugged later. Raised in review.

    When ``$HOME`` was unset at import there is nothing to restore, so it is *removed* from
    the child's environment rather than left carrying the moved value. The previous version
    skipped the assignment and passed the temp ``$HOME`` straight through, which is the
    opposite of what its docstring promised. Also raised in review.
    """
    if "HOME" in extra:
        raise ValueError(
            "subprocess_env restores HOME; passing it as an extra would silently undo that. "
            "Set it on the returned dict if you really mean to override it."
        )
    env = dict(os.environ)
    if _REAL_HOME is None:
        env.pop("HOME", None)
    else:
        env["HOME"] = _REAL_HOME
    for name in _USER_SITE_REDIRECTS:
        env.pop(name, None)
    env.update(extra)
    return env


#: The repository root, and the import path every pylint-family test needs on it.
REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_PYTHONPATH = os.pathsep.join([
    str(REPO_ROOT / "src"),
    str(REPO_ROOT / "skills" / "studio" / "scripts"),
])


def run_pylint(code: str, *, enable: str,
               relative_path: str = "sample.py") -> subprocess.CompletedProcess:
    """Run the local checkers over ``code`` in a throwaway file.

    One launcher instead of four. The four pylint-family test modules each carried an
    identical copy of this -- the same `pipx` argument list, the same `PYTHONPATH`, the same
    temp-file handling -- differing only in `--enable=` and the target path. The `$HOME` bug
    those four shared is the argument: a fix applied to a launcher has to be applied four
    times, and this family has already lost one repair that way. Raised in review.
    """
    with TemporaryDirectory() as td:
        target = Path(td) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(code), encoding="utf-8")
        return subprocess.run(
            ["pipx", "run", "--spec", "pylint", "pylint",
             "--score=n", "--disable=all", f"--enable={enable}", str(target)],
            cwd=REPO_ROOT, env=subprocess_env(PYTHONPATH=PLUGIN_PYTHONPATH),
            text=True, capture_output=True, check=False,
            # Bounded. None of the four copies this replaces passed a timeout, so a `pipx`
            # that hung -- fetching a spec on a cold cache, say -- stopped the whole suite
            # rather than failing one test, which reads as CI being broken. Generous enough
            # for a first-run download and still finite. One launcher means one bound; that
            # is the argument for the consolidation, made by the first thing it fixed.
            timeout=600,
        )


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
