"""EDN decoding and contract validation, separate from policy."""

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

from edn_format import Keyword, loads_all

from gauntlet.errors import GauntletError


def plain(value):
    if isinstance(value, Keyword):
        return value.name
    if isinstance(value, Mapping):
        return {plain(key): plain(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [plain(item) for item in value]
    return value


def decode(text: str) -> dict:
    try:
        values = loads_all(text)
        if len(values) != 1 or not isinstance(values[0], Mapping):
            raise ValueError("expected one EDN map")
        return plain(values[0])
    except Exception as exc:
        raise GauntletError(f"Malformed tool EDN: {exc}", 1) from exc


def read(path: Path) -> dict:
    try:
        return decode(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise GauntletError(f"Cannot read tool report {path.name}: {exc}", 1) from exc


def rows(data: dict, key: str) -> list[dict]:
    values = data.get(key)
    if not isinstance(values, list) or not all(isinstance(row, dict) for row in values):
        raise GauntletError(f"Tool report requires an array of maps: {key}", 1)
    return values


def text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise GauntletError(f"Tool report requires non-empty string: {name}", 1)
    return value


def number(value: object, name: str, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise GauntletError(f"Tool report requires non-negative finite number: {name}", 1)
    return value


def integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise GauntletError(f"Tool report requires integer >= {minimum}: {name}", 1)
    return value


def relative(value: object, root: Path) -> str:
    raw = text(value, "file")
    root = root.resolve()
    path = (root / raw).resolve()
    if not path.is_relative_to(root):
        raise GauntletError("Tool report refers to a file outside the repository", 1)
    return path.relative_to(root).as_posix()
