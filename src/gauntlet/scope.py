"""File selection only; analyzers retain ownership of source analysis."""

import fnmatch
from functools import cache, lru_cache
from pathlib import Path

from gauntlet.config import Config
from gauntlet.discovery import source_file
from gauntlet.errors import GauntletError


def matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(_match_parts(tuple(path.split("/")), tuple(p.split("/"))) for p in patterns)


@lru_cache(maxsize=512)
def _match_parts(path: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    @cache
    def visit(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern):
            return path_index == len(path)
        if pattern[pattern_index] == "**":
            return visit(path_index, pattern_index + 1) or (
                path_index < len(path) and visit(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path)
            and fnmatch.fnmatchcase(path[path_index], pattern[pattern_index])
            and visit(path_index + 1, pattern_index + 1)
        )

    return visit(0, 0)


def included(path: str, config: Config) -> bool:
    return (not config.include or matches(path, config.include)) and not matches(
        path, config.exclude
    )


def select(root: Path, files: list[str], config: Config, paths: list[str]) -> list[str]:
    root = root.resolve()
    limits = []
    for raw in paths:
        path = Path(raw).resolve()
        if not path.exists() or not path.is_relative_to(root):
            raise GauntletError(f"Analysis path must exist inside the repository: {raw}", 4)
        limits.append(path)
    selected = []
    for name in files:
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            continue
        if limits and not any(path == limit or path.is_relative_to(limit) for limit in limits):
            continue
        if source_file(name) and included(name, config):
            selected.append(name)
    return sorted(set(selected))
