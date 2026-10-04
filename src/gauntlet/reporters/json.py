import json
import os
import tempfile
from pathlib import Path

from gauntlet.models import Results


def render(results: Results) -> str:
    return json.dumps(results.to_dict(), indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def write(results: Results, path: Path) -> None:
    """Atomic replacement prevents readers from observing half a report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(render(results))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
