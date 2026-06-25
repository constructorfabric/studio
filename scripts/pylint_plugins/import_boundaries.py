"""Pylint checker for studio/proxy import boundary violations."""

from __future__ import annotations

from pathlib import PurePosixPath

from astroid import nodes
from pylint.checkers import BaseChecker

_PROXY_PATH_SEQUENCES = (
    ("src", "studio_proxy"),
)
_PROXY_RELATIVE_ROOTS = (
    ("studio_proxy",),
)
_STUDIO_PATH_SEQUENCES = (
    ("skills", "studio", "scripts", "studio"),
)
_STUDIO_RELATIVE_ROOTS = (
    ("studio",),
)


def _module_path(node: nodes.NodeNG) -> str:
    root = node.root()
    file_path = getattr(root, "file", None)
    return str(file_path or "").replace("\\", "/")


def _path_has_sequence(path: str, sequence: tuple[str, ...]) -> bool:
    parts = PurePosixPath(path).parts
    window = len(sequence)
    return any(parts[index:index + window] == sequence for index in range(len(parts) - window + 1))


def _path_starts_with_sequence(path: str, sequence: tuple[str, ...]) -> bool:
    parts = PurePosixPath(path).parts
    return parts[:len(sequence)] == sequence


def _is_proxy_module(node: nodes.NodeNG) -> bool:
    path = _module_path(node)
    return (
        any(_path_has_sequence(path, sequence) for sequence in _PROXY_PATH_SEQUENCES)
        or any(_path_starts_with_sequence(path, sequence) for sequence in _PROXY_RELATIVE_ROOTS)
    )


def _is_studio_module(node: nodes.NodeNG) -> bool:
    path = _module_path(node)
    return (
        any(_path_has_sequence(path, sequence) for sequence in _STUDIO_PATH_SEQUENCES)
        or any(_path_starts_with_sequence(path, sequence) for sequence in _STUDIO_RELATIVE_ROOTS)
    )


def _import_name(node: nodes.NodeNG) -> str | None:
    if isinstance(node, nodes.Import):
        if not node.names:
            return None
        return node.names[0][0]
    if isinstance(node, nodes.ImportFrom):
        return node.modname
    return None


def _imports_proxy(import_name: str | None) -> bool:
    return bool(import_name) and (import_name == "studio_proxy" or import_name.startswith("studio_proxy."))


def _imports_studio(import_name: str | None) -> bool:
    return bool(import_name) and (import_name == "studio" or import_name.startswith("studio."))


class ImportBoundariesChecker(BaseChecker):
    """Forbid imports between studio_proxy and studio packages."""

    name = "studio-import-boundaries"
    msgs = {
        "W9005": (
            "studio_proxy must not import studio package modules",
            "proxy-imports-studio",
            "Used when code under src/studio_proxy imports the studio skill-engine package.",
        ),
        "W9006": (
            "studio package must not import studio_proxy modules",
            "studio-imports-proxy",
            "Used when code under skills/studio/scripts/studio imports the studio_proxy package.",
        ),
    }

    def visit_import(self, node: nodes.Import) -> None:
        """Check plain import statements against the package boundary."""
        self._check_import(node)

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Check from-import statements against the package boundary."""
        self._check_import(node)

    def _check_import(self, node: nodes.NodeNG) -> None:
        import_name = _import_name(node)
        if _is_proxy_module(node) and _imports_studio(import_name):
            self.add_message("proxy-imports-studio", node=node)
        elif _is_studio_module(node) and _imports_proxy(import_name):
            self.add_message("studio-imports-proxy", node=node)


def register(linter) -> None:
    """Register the checker once."""
    for checkers in getattr(linter, "_checkers", {}).values():
        for checker in checkers:
            if getattr(checker, "name", "") == ImportBoundariesChecker.name:
                return
    linter.register_checker(ImportBoundariesChecker(linter))
