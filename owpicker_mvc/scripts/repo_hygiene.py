#!/usr/bin/env python3
"""Repository/build hygiene cleanup for local developer artifacts."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
}

ALWAYS_REMOVE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".pytype",
    ".pyre",
    "__MACOSX",
}

BUILD_DIR_NAMES = {
    "build",
    "dist",
    ".tox",
    ".nox",
}

ALWAYS_REMOVE_FILES = {
    ".DS_Store",
    "Thumbs.db",
}

PYCACHE_FILE_SUFFIXES = (".pyc", ".pyo")


@dataclass
class CleanupStats:
    removed_dirs: int = 0
    removed_files: int = 0
    errors: int = 0

    def merge(self, other: "CleanupStats") -> None:
        self.removed_dirs += int(other.removed_dirs)
        self.removed_files += int(other.removed_files)
        self.errors += int(other.errors)


def _repo_root_from_script(script_path: Path) -> Path:
    # .../owpicker_mvc/scripts/repo_hygiene.py -> repo root is parent of owpicker_mvc
    return script_path.resolve().parents[2]


def _should_remove_dir(name: str, *, include_build: bool) -> bool:
    if name in ALWAYS_REMOVE_DIR_NAMES:
        return True
    if name.endswith(".egg-info"):
        return True
    if include_build and name in BUILD_DIR_NAMES:
        return True
    return False


def _remove_path(path: Path, *, dry_run: bool, is_dir: bool) -> tuple[bool, str]:
    action = "remove dir" if is_dir else "remove file"
    if dry_run:
        return True, f"[DRY] {action}: {path}"
    try:
        if is_dir:
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, f"removed {'dir' if is_dir else 'file'}: {path}"
    except OSError as exc:
        return False, f"error removing {path}: {exc}"


def cleanup_tree(
    root: Path,
    *,
    dry_run: bool,
    include_build: bool,
    include_logs: bool,
    include_saved_state: bool,
    include_ocr_models: bool,
) -> CleanupStats:
    stats = CleanupStats()
    root = root.resolve()

    for current_dir, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(current_dir)
        rel_current = current.relative_to(root)

        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]

        for name in list(dirnames):
            if not _should_remove_dir(name, include_build=include_build):
                continue
            target = current / name
            ok, line = _remove_path(target, dry_run=dry_run, is_dir=True)
            print(line)
            if ok:
                stats.removed_dirs += 1
            else:
                stats.errors += 1
            dirnames.remove(name)

        for filename in filenames:
            full_path = current / filename
            rel_path = full_path.relative_to(root)
            rel_posix = rel_path.as_posix()
            remove = False

            if filename in ALWAYS_REMOVE_FILES:
                remove = True
            elif filename.endswith(PYCACHE_FILE_SUFFIXES):
                remove = True
            elif include_logs and rel_posix.startswith("owpicker_mvc/logs/") and filename.endswith(".log"):
                remove = True
            elif include_saved_state and rel_posix == "owpicker_mvc/saved_state.json":
                remove = True
            elif include_build and rel_current.as_posix().startswith("owpicker_mvc/build"):
                remove = True
            elif include_build and rel_current.as_posix().startswith("owpicker_mvc/dist"):
                remove = True
            elif include_ocr_models and rel_posix.startswith("owpicker_mvc/EasyOCR/"):
                remove = True

            if not remove:
                continue

            ok, line = _remove_path(full_path, dry_run=dry_run, is_dir=False)
            print(line)
            if ok:
                stats.removed_files += 1
            else:
                stats.errors += 1

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cleanup repository/build artifacts.")
    parser.add_argument(
        "--path",
        default=None,
        help="Root directory to clean (default: repository root).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be removed.",
    )
    parser.add_argument(
        "--include-build",
        action="store_true",
        help="Also remove build/distribution folders (build, dist, .tox, .nox).",
    )
    parser.add_argument(
        "--include-logs",
        action="store_true",
        help="Also remove runtime log files in owpicker_mvc/logs/*.log.",
    )
    parser.add_argument(
        "--include-saved-state",
        action="store_true",
        help="Also remove owpicker_mvc/saved_state.json.",
    )
    parser.add_argument(
        "--include-ocr-models",
        action="store_true",
        help="Also remove bundled OCR model files in owpicker_mvc/EasyOCR/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_path = Path(__file__)
    default_root = _repo_root_from_script(script_path)
    root = Path(args.path).expanduser().resolve() if args.path else default_root

    if not root.exists():
        print(f"path does not exist: {root}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"path is not a directory: {root}", file=sys.stderr)
        return 2

    stats = cleanup_tree(
        root,
        dry_run=bool(args.dry_run),
        include_build=bool(args.include_build),
        include_logs=bool(args.include_logs),
        include_saved_state=bool(args.include_saved_state),
        include_ocr_models=bool(args.include_ocr_models),
    )

    action = "would remove" if bool(args.dry_run) else "removed"
    print(
        f"{action}: {stats.removed_dirs} dirs, {stats.removed_files} files, errors={stats.errors}"
    )
    return 1 if stats.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
