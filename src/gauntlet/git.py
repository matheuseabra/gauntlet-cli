import re
from pathlib import Path

from gauntlet.errors import GauntletError
from gauntlet.process import run


def root(directory: Path) -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], directory)
    if result.exit_code or result.timed_out:
        raise GauntletError(
            "Not inside a Git repository. Run git init or use a repository checkout.", 4
        )
    return Path(result.stdout.strip()).resolve()


def parse_changed(stdout: str) -> list[str]:
    # --no-renames represents moves as additions/deletions; -z preserves spaces/newlines.
    return sorted(
        {entry[3:] for entry in stdout.split("\0") if len(entry) >= 4 and "D" not in entry[:2]}
    )


def changed_files(directory: Path) -> list[str]:
    result = run(
        ["git", "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all"],
        directory,
    )
    if result.exit_code or result.timed_out:
        raise GauntletError("Git could not enumerate changed files", 1)
    return [name for name in parse_changed(result.stdout) if (directory / name).is_file()]


def changed_lines(directory: Path, files: list[str]) -> dict[str, list[tuple[int, int]]]:
    head = run(["git", "rev-parse", "--verify", "HEAD"], directory)
    ranges = {}
    for name in files:
        tracked = run(["git", "ls-files", "--error-unmatch", "--", name], directory)
        if head.exit_code or tracked.exit_code:
            ranges[name] = [(1, len((directory / name).read_bytes().splitlines()) + 1)]
            continue
        diff = run(
            ["git", "diff", "HEAD", "--unified=0", "--no-ext-diff", "--no-textconv", "--", name],
            directory,
        )
        if diff.exit_code or diff.timed_out:
            raise GauntletError("Git could not compute changed line ranges", 1)
        ranges[name] = []
        for match in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff.stdout, re.M):
            start, count = int(match[1]), int(match[2] or 1)
            ranges[name].append((max(1, start), max(1, start + count - 1)))
    return ranges
