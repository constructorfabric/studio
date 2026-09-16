import importlib
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest


MODULE_PATH = "studio.utils._tomllib_compat"


def _reload_module(request):
    # Ensure fresh import
    sys.modules.pop(MODULE_PATH, None)
    module = importlib.import_module(MODULE_PATH)
    # This reload executes _tomllib_compat's `import tomllib` line while
    # sys.modules["tomllib"] is monkeypatched to a dummy -- the *compat*
    # module then caches that dummy as its own `tomllib` attribute. Popping
    # it from sys.modules here (after this test's monkeypatch has reverted
    # sys.modules["tomllib"] to the real module) forces the next real
    # importer to re-resolve against the genuine tomllib, instead of every
    # later consumer in this same pytest-xdist worker (toml_utils.py,
    # manifest.py, adapter_info.py, ...) silently getting this test's dummy
    # forever.
    request.addfinalizer(lambda: sys.modules.pop(MODULE_PATH, None))
    return module


def test_stdlib_tomllib(monkeypatch, request):
    dummy = types.ModuleType("tomllib")
    dummy.DUMMY_FLAG = "stdlib"

    # Simulate Python >= 3.11 and a stdlib tomllib present
    monkeypatch.setitem(sys.modules, "tomllib", dummy)
    monkeypatch.setattr(sys, "version_info", (3, 11))

    mod = _reload_module(request)
    assert hasattr(mod, "tomllib")
    assert mod.tomllib is dummy
    assert mod.__all__ == ["tomllib"]


def test_tomli_fallback(monkeypatch, request):
    dummy = types.ModuleType("tomli")
    dummy.DUMMY_FLAG = "tomli"

    # Simulate Python < 3.11 and tomli installed
    monkeypatch.setattr(sys, "version_info", (3, 10))
    monkeypatch.setitem(sys.modules, "tomli", dummy)

    mod = _reload_module(request)
    assert hasattr(mod, "tomllib")
    # When tomli is used, the compat module aliases it as tomllib
    assert mod.tomllib is dummy
    assert mod.__all__ == ["tomllib"]


def test_no_tomli_exits_with_error(monkeypatch, capsys):
    # Simulate Python < 3.11 and tomli NOT installed
    monkeypatch.setattr(sys, "version_info", (3, 10))
    # Ensure tomli and tomllib are not present
    monkeypatch.delitem(sys.modules, "tomli", raising=False)
    monkeypatch.delitem(sys.modules, "tomllib", raising=False)
    # Also ensure our target module is not cached
    sys.modules.pop(MODULE_PATH, None)
    # Force ImportError for tomli/tomllib even if installed in this environment
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in ("tomli", "tomllib"):
            raise ImportError
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(SystemExit) as ei:
        importlib.import_module(MODULE_PATH)

    # The compat module calls sys.exit(1) on missing dependency
    assert ei.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR: tomllib/tomli not available" in captured.err


def test_stdlib_reload_does_not_leak_the_dummy_to_a_later_test(tmp_path):
    """Regression: _reload_module's fresh import (triggered while
    sys.modules["tomllib"] is monkeypatched to a dummy) used to leave that
    dummy permanently cached as the compat module's own `tomllib`
    attribute in sys.modules, with no cleanup registered anywhere. Any
    later, unrelated consumer of `from studio.utils._tomllib_compat import
    tomllib` in the same process (toml_utils.py, manifest.py,
    adapter_info.py, ...) would then silently get that dummy (no real
    `.load()`) forever, instead of the genuine tomllib -- this is exactly
    what surfaced as `AttributeError: module 'tomllib' has no attribute
    'load'` in CI once enough test files shifted pytest-xdist's worker
    scheduling for this pair to land in the same worker.

    Runs a two-test scenario (mirroring test_stdlib_tomllib, then a "later
    consumer") in a real, separate pytest process, so the first test's
    finalizer genuinely completes before the second test runs -- calling
    _reload_module directly from here couldn't observe its own finalizer.
    """
    script = tmp_path / "test_isolated.py"
    script.write_text(
        "import sys, types, importlib\n"
        f"MODULE_PATH = {MODULE_PATH!r}\n"
        "\n"
        "def test_1_corrupt(monkeypatch, request):\n"
        "    dummy = types.ModuleType('tomllib')\n"
        "    monkeypatch.setitem(sys.modules, 'tomllib', dummy)\n"
        "    monkeypatch.setattr(sys, 'version_info', (3, 11))\n"
        "    sys.modules.pop(MODULE_PATH, None)\n"
        "    mod = importlib.import_module(MODULE_PATH)\n"
        "    assert mod.tomllib is dummy\n"
        "    request.addfinalizer(lambda: sys.modules.pop(MODULE_PATH, None))\n"
        "\n"
        "def test_2_consumes_after():\n"
        "    assert MODULE_PATH not in sys.modules\n",
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[1]
    studio_scripts_dir = repo_root / "skills" / "studio" / "scripts"
    env = {**os.environ, "PYTHONPATH": str(studio_scripts_dir)}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(script), "-q"],
        capture_output=True, text=True, check=False, env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr

