import re
from dataclasses import dataclass
from pathlib import Path

from gauntlet.errors import GauntletError
from gauntlet.process import run


@dataclass(frozen=True)
class Comparison:
    base_sha: str
    head_sha: str
    merge_base_sha: str
    files: list[str]


def resolve_commit(directory: Path, ref: str) -> str:
    result = run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"], directory
    )
    if result.exit_code or result.timed_out:
        raise GauntletError(f"Cannot resolve Git commit {ref!r}; fetch its history first", 4)
    return result.stdout.strip()


def compare(directory: Path, base: str) -> Comparison:
    """Select committed changes from the merge base to the checked-out HEAD."""
    status = run(["git", "status", "--porcelain=v1", "--untracked-files=no"], directory)
    if status.exit_code or status.timed_out:
        raise GauntletError("Git could not inspect the working tree", 1)
    if status.stdout:
        raise GauntletError(
            "--base requires a clean tracked working tree; commit or stash changes", 4
        )
    base_sha, head_sha = resolve_commit(directory, base), resolve_commit(directory, "HEAD")
    ancestor = run(["git", "merge-base", "--all", base_sha, head_sha], directory)
    ancestors = ancestor.stdout.splitlines()
    if ancestor.exit_code or ancestor.timed_out or len(ancestors) != 1:
        raise GauntletError(
            "Git comparison needs one merge base; fetch complete base/head history", 4
        )
    merge_base = ancestors[0]
    result = run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--name-only",
            "--diff-filter=ACMRT",
            "-z",
            merge_base,
            head_sha,
            "--",
        ],
        directory,
    )
    if result.exit_code or result.timed_out:
        raise GauntletError("Git could not enumerate committed changes", 1)
    files = sorted(
        {name for name in result.stdout.split("\0") if name and (directory / name).is_file()}
    )
    return Comparison(base_sha, head_sha, merge_base, files)


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


def changed_lines(
    directory: Path, files: list[str], base: str | None = None
) -> dict[str, list[tuple[int, int]]]:
    head = run(["git", "rev-parse", "--verify", "HEAD"], directory)
    ranges = {}
    for name in files:
        tracked = run(["git", "ls-files", "--error-unmatch", "--", name], directory)
        if head.exit_code or tracked.exit_code:
            ranges[name] = [(1, len((directory / name).read_bytes().splitlines()) + 1)]
            continue
        comparison = [base, "HEAD"] if base else ["HEAD"]
        diff = run(
            [
                "git",
                "diff",
                *comparison,
                "--unified=0",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--",
                name,
            ],
            directory,
        )
        if diff.exit_code or diff.timed_out:
            raise GauntletError("Git could not compute changed line ranges", 1)
        ranges[name] = []
        for match in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff.stdout, re.M):
            start, count = int(match[1]), int(match[2] or 1)
            ranges[name].append((max(1, start), max(1, start + count - 1)))
    return ranges
