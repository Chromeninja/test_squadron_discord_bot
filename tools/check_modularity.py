#!/usr/bin/env python3
"""Enforce modularity thresholds for Python files.

This checker is intended for pre-commit and CI. It only evaluates file paths provided
as arguments, so existing legacy monoliths are not blocked until they are touched.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

# Legacy monolith ceilings allow incremental decomposition without permitting growth.
LEGACY_FILE_CEILINGS: dict[str, int] = {
    "services/voice_service.py": 4169,
    "services/internal_api.py": 2884,
    "services/metrics_service.py": 2009,
    "services/ticket_service.py": 1659,
    "services/db/database.py": 1553,
    "web/backend/routes/guilds.py": 1561,
    "web/backend/core/dependencies.py": 1399,
    "helpers/ticket_views.py": 1391,
    "web/backend/core/guild_settings.py": 1285,
    "helpers/views.py": 1265,
    "web/backend/routes/voice.py": 1164,
    "services/ticket_form_service.py": 1117,
}


@dataclass(slots=True)
class FileStats:
    path: Path
    lines: int
    functions: int
    classes: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Python modularity thresholds")
    parser.add_argument("files", nargs="*", help="Python files to check")
    parser.add_argument("--warn-lines", type=int, default=500)
    parser.add_argument("--fail-lines", type=int, default=700)
    parser.add_argument("--warn-funcs", type=int, default=15)
    parser.add_argument("--warn-classes", type=int, default=4)
    return parser.parse_args()


def collect_stats(path: Path) -> FileStats:
    source = path.read_text(encoding="utf-8")
    line_count = source.count("\n") + (0 if not source else 1)

    tree = ast.parse(source)
    functions = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )
    classes = sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))

    return FileStats(path=path, lines=line_count, functions=functions, classes=classes)


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    skip_dirs = {
        ".venv",
        ".git",
        "__pycache__",
        "logs",
        "test_squadron_discord_bot.egg-info",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "htmlcov",
    }
    if parts & skip_dirs:
        return True

    path_text = path.as_posix()
    return path_text.startswith("tests/") or path_text.startswith("web/backend/tests/")


def main() -> int:
    args = parse_args()

    candidates = [Path(file_name) for file_name in args.files if file_name.endswith(".py")]
    candidates = [path for path in candidates if path.exists() and not should_skip(path)]

    if not candidates:
        print("[modularity] No eligible Python files to check.")
        return 0

    warnings: list[str] = []
    failures: list[str] = []

    for path in candidates:
        try:
            stats = collect_stats(path)
        except SyntaxError as error:
            failures.append(f"{path}: parse error at line {error.lineno} ({error.msg})")
            continue
        except OSError as error:
            failures.append(f"{path}: unable to read file ({error})")
            continue

        if stats.lines > args.fail_lines:
            relative_path = path.as_posix()
            ceiling = LEGACY_FILE_CEILINGS.get(relative_path)
            if ceiling is None:
                failures.append(
                    f"{stats.path}: {stats.lines} lines exceeds fail threshold {args.fail_lines}"
                )
            elif stats.lines > ceiling:
                failures.append(
                    f"{stats.path}: {stats.lines} lines exceeds legacy ceiling {ceiling}"
                )
            else:
                warnings.append(
                    f"{stats.path}: legacy monolith at {stats.lines} lines (ceiling {ceiling}); continue decomposition"
                )
        elif stats.lines > args.warn_lines:
            warnings.append(
                f"{stats.path}: {stats.lines} lines exceeds warn threshold {args.warn_lines}"
            )

        if stats.functions > args.warn_funcs:
            warnings.append(
                f"{stats.path}: {stats.functions} functions exceeds warn threshold {args.warn_funcs}"
            )

        if stats.classes > args.warn_classes:
            warnings.append(
                f"{stats.path}: {stats.classes} classes exceeds warn threshold {args.warn_classes}"
            )

    for warning in warnings:
        print(f"[modularity][warn] {warning}")

    for failure in failures:
        print(f"[modularity][fail] {failure}")

    if failures:
        print("[modularity] Check failed.")
        return 1

    print("[modularity] Check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
