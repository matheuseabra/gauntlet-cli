import os
from contextlib import contextmanager
from pathlib import Path

from gauntlet.errors import GauntletError


@contextmanager
def repository_lock(root: Path):
    path = root / ".gauntlet/run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise GauntletError(
            "Another Gauntlet run holds .gauntlet/run.lock. If a previous run "
            "was killed, confirm it has stopped before removing that lock.",
            1,
        ) from exc
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)
