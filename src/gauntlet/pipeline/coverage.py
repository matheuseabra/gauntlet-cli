import shutil
from pathlib import Path

from gauntlet.discovery import LANGUAGES
from gauntlet.errors import GauntletError
from gauntlet.models import RunContext


def artifacts(root: Path) -> list[Path]:
    paths = set(root.glob("target/coverage/**/lcov.info"))
    paths.update(root.glob("coverage/**/lcov.info"))
    for pattern in (
        "coverage.lcov",
        "coverage.out",
        "target/coverage/coverage.out",
        "target/coverage/go/coverage.out",
        "*/target/coverage/go/coverage.out",
        "*/*/target/coverage/go/coverage.out",
        "target/site/jacoco/jacoco.xml",
        "*/target/site/jacoco/jacoco.xml",
        "*/*/target/site/jacoco/jacoco.xml",
        "target/coverage/**/*.html",
    ):
        paths.update(root.glob(pattern))
    return sorted(path for path in paths if path.is_file() and path.stat().st_size)


def require(context: RunContext) -> list[Path]:
    reports = artifacts(context.root)
    languages = {LANGUAGES[Path(name).suffix] for name in context.selected_files}
    lcov = any(p.suffix == ".lcov" or p.name == "lcov.info" for p in reports)
    available = {
        "python": lcov,
        "typescript": lcov,
        "javascript": lcov,
        "rust": lcov,
        "go": any(p.name == "coverage.out" for p in reports),
        "java": any(p.name == "jacoco.xml" for p in reports),
        "clojure": lcov or any(p.suffix == ".html" for p in reports),
    }
    missing = sorted(lang for lang in languages if not available.get(lang, False))
    if missing:
        raise GauntletError(
            f"Coverage artifact missing for {', '.join(missing)}. Configure commands.coverage "
            "to generate LCOV (coverage/lcov.info or target/coverage/<language>/lcov.info), "
            "Go coverage.out, or JaCoCo target/site/jacoco/jacoco.xml. Use scan for "
            "coverage-free inspection.",
            5,
            "coverage",
        )
    # Upstream readers do not search root-level coverage.lcov. Bridge the artifact
    # byte-for-byte without implementing a coverage parser.
    lcov_source = context.root / "coverage.lcov"
    if lcov_source in reports:
        target = context.root / "target/coverage/gauntlet/lcov.info"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lcov_source, target)
    return reports
