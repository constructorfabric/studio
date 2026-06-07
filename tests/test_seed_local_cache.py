"""Tests for scripts/seed_local_cache.py."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.seed_local_cache import BUNDLE_ITEMS, seed_cache


def test_seed_cache_fails_when_critical_skills_bundle_missing():
    with TemporaryDirectory() as td:
        root = Path(td)
        source_root = root / "source"
        source_root.mkdir()
        for item in BUNDLE_ITEMS:
            if item != "skills":
                (source_root / item).mkdir()
        cache_dir = root / "cache"

        with patch("scripts.seed_local_cache.get_cache_dir", return_value=cache_dir):
            with pytest.raises(RuntimeError) as exc_info:
                seed_cache(source_root)

        message = str(exc_info.value)
        assert "skills" in message
        assert str(source_root) in message
        assert str(cache_dir) in message
