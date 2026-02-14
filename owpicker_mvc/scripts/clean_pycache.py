#!/usr/bin/env python3
"""Delete Python cache artifacts (__pycache__, .pyc, .pyo)."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


DEFAULT_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
}


def remove_pycache_artifacts(root: Path, *, dry_run: bool, skip_dirs: set[str]) -> tuple[int, int, int]:
    removed_dirs = 0
    removed_files = 0
    errors = 0

    for current_dir, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [name for name in dirnames if name not in skip_dirs]

        if "__pycache__" in dirnames:
            pycache_dir = Path(current_dir) / "__pycache__"
            if dry_run:
                print(f"[DRY] remove dir: {pycache_dir}")
                removed_dirs += 1
            else:
                try:
                    shutil.rmtree(pycache_dir)
                    print(f"removed dir: {pycache_dir}")
                    removed_dirs += 1
                except OSError as exc:
                    print(f"error removing dir {pycache_dir}: {exc}", file=sys.stderr)
                    errors += 1
            dirnames.remove("__pycache__")

        for filename in filenames:
            if not filename.endswith((".pyc", ".pyo")):
                continue
            cached_file = Path(current_dir) / filename
            if dry_run:
                print(f"[DRY] remove file: {cached_file}")
                removed_files += 1
                continue
            try:
                cached_file.unlink()
                print(f"removed file: {cached_file}")
                removed_files += 1
            except OSError as exc:
                print(f"error removing file {cached_file}: {exc}", file=sys.stderr)
                errors += 1

    return removed_dirs, removed_files, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete Python cache artifacts in a folder tree.")
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root folder to clean (default: current directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting anything.",
    )
    parser.add_argument(
        "--include-venv",
        action="store_true",
        help="Also scan common virtual-env directories (.venv/venv/env).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"path does not exist: {root}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"path is not a directory: {root}", file=sys.stderr)
        return 2

    skip_dirs = set(DEFAULT_SKIP_DIRS)
    if args.include_venv:
        skip_dirs -= {".venv", "venv", "env"}

    removed_dirs, removed_files, errors = remove_pycache_artifacts(
        root,
        dry_run=bool(args.dry_run),
        skip_dirs=skip_dirs,
    )
    action = "would remove" if args.dry_run else "removed"
    print(f"{action}: {removed_dirs} __pycache__ dirs, {removed_files} cache files")
    if errors:
        print(f"errors: {errors}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
