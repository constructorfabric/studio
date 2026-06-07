#!/usr/bin/env python3
"""Seed the Constructor Studio cache from a local source tree.

This is the self-hosted development equivalent of the proxy cache installer:
it copies only the runtime bundle needed by project bootstrap, then writes the
same cache metadata files that `cfs --version` reads.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from studio_proxy.resolve import get_cache_dir, get_cache_provenance_file, get_version_file


BUNDLE_ITEMS = ("requirements", "schemas", "workflows", "skills", "architecture")
VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']')


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_local_version(source_root: Path) -> str:
    init_file = source_root / "skills" / "studio" / "scripts" / "studio" / "__init__.py"
    if not init_file.is_file():
        return "local"
    try:
        for line in init_file.read_text(encoding="utf-8").splitlines():
            match = VERSION_RE.match(line.strip())
            if match:
                return match.group(1)
    except OSError:
        return "local"
    return "local"


def seed_cache(source_root: Path) -> str:
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise ValueError(f"Source directory not found: {source_root}")

    cache_dir = get_cache_dir()
    missing_items = [
        name
        for name in BUNDLE_ITEMS
        if not (source_root / name).is_dir() and not (source_root / name).is_file()
    ]
    if source_root.joinpath("skills").is_dir() is False:
        raise RuntimeError(
            f"Critical bundle item missing: skills at {source_root / 'skills'} "
            f"(source_root={source_root}, cache_dir={cache_dir})"
        )
    if missing_items:
        missing = ", ".join(missing_items)
        raise RuntimeError(
            f"Bundle item(s) missing: {missing} "
            f"(source_root={source_root}, cache_dir={cache_dir})"
        )

    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    for name in BUNDLE_ITEMS:
        src = source_root / name
        if src.is_dir():
            shutil.copytree(src, cache_dir / name)
        elif src.is_file():
            shutil.copy2(src, cache_dir / name)

    whatsnew = source_root / "whatsnew.toml"
    if whatsnew.is_file():
        shutil.copy2(whatsnew, cache_dir / "whatsnew.toml")

    kits_src = source_root / ".bootstrap" / "config" / "kits"
    if kits_src.is_dir():
        kits_dst = cache_dir / "kits"
        kits_dst.mkdir(parents=True, exist_ok=True)
        for item in kits_src.iterdir():
            dst = kits_dst / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            elif item.is_file():
                shutil.copy2(item, dst)

    local_version = _read_local_version(source_root)
    display_version = f"local:{local_version}"
    get_version_file().write_text(display_version, encoding="utf-8")
    get_cache_provenance_file().write_text(
        json.dumps(
            {
                "source_type": "local_path",
                "installed_version": display_version,
                "requested_ref": "local",
                "resolved_ref": local_version,
                "resolver_mode": "local_path",
                "resolution_basis": "local_path",
                "canonical_source": source_root.as_posix(),
                "effective_source": source_root.as_posix(),
                "verified": "unknown",
                "freshness": "local",
                "resolved_at": _utc_now_iso(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return display_version


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    source_root = Path(args[0]) if args else Path.cwd()
    try:
        version = seed_cache(source_root)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"seed-cache failed: {exc}", file=sys.stderr)
        return 1
    print(f"Seeded Constructor Studio cache: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
