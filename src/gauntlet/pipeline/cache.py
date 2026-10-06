"""Conservative local mutation evidence cache. Opaque test commands always rerun."""

import hashlib
import json
import os
import shlex
import shutil
import time
from pathlib import Path

from gauntlet.discovery import SKIP
from gauntlet.models import RunContext
from gauntlet.process import run

PRUNE = SKIP - {"tests", "test", "spec", "specs", "__tests__"} | {".pytest_cache", ".ruff_cache"}
IGNORE = {".coverage", "coverage.lcov", "coverage.out"}
LIMIT = 128 * 1024 * 1024

# Executed only in already installed Python runtimes. No imports of project code or downloads.
RUNTIME_SCRIPT = r"""
import hashlib, importlib.metadata as m, json, os, sys
from pathlib import Path
h=hashlib.sha256(); total=0; seen=set()
def add(path):
    global total
    path=path.resolve()
    if path in seen or not path.is_file(): return
    seen.add(path); total+=path.stat().st_size
    if total > 134217728: raise ValueError('runtime too large to fingerprint')
    h.update(str(path).encode()); h.update(path.read_bytes())
add(Path(sys.executable))
# The pinned analyzers load grammars from a separate on-disk cache. Reading its
# location does not fetch a parser. Include the relevant Python grammar bytes.
try:
    import tree_sitter_language_pack as pack
except ImportError:
    pass
else:
    grammar=Path(pack.cache_dir())
    if not list(grammar.glob('*python*')): raise ValueError('Python grammar unavailable')
    add(grammar.parent/'manifest.json')
    for path in sorted(grammar.glob('*python*')): add(path)
for dist in sorted(m.distributions(),key=lambda d:d.metadata['Name'] or ''):
    if dist.files is None: raise ValueError('distribution has no file inventory')
    for file in sorted(dist.files or [],key=str):
        if '__pycache__' not in str(file): add(Path(dist.locate_file(file)))
    direct=dist.read_text('direct_url.json')
    if direct and json.loads(direct).get('dir_info',{}).get('editable'):
        from urllib.parse import unquote, urlparse
        root=Path(unquote(urlparse(json.loads(direct)['url']).path))
        for directory,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=sorted(d for d in dirs if d not in {
                '.git','.venv','venv','target','dist','build','node_modules',
                '.gauntlet','.metrics','__pycache__','.pytest_cache','.ruff_cache'})
            for name in sorted(files):
                if name not in {'.coverage','coverage.out','coverage.lcov'}:
                    path=Path(directory)/name
                    if path.is_symlink(): raise ValueError('editable symlink')
                    add(path)
h.update(sys.version.encode()); print(h.hexdigest())
"""


def python_for(command: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if len(tokens) < 3 or tokens[1] != "-m" or tokens[2] not in {"pytest", "unittest"}:
        return None
    if any(token in {"&&", ";", "|", "||", "&"} for token in tokens):
        return None
    executable = shutil.which(tokens[0])
    if not executable or not Path(executable).name.startswith("python"):
        return None
    return executable


def tool_python(executable: str) -> str | None:
    try:
        with Path(executable).open("rb") as stream:
            header = stream.readline(4096).decode("utf-8").strip()
        if not header.startswith("#!"):
            return None
        tokens = shlex.split(header[2:])
        interpreter = shutil.which(tokens[1]) if tokens[0].endswith("/env") else tokens[0]
        return interpreter if interpreter and Path(interpreter).name.startswith("python") else None
    except (OSError, ValueError, IndexError):
        return None


def runtime_hash(interpreter: str | None, root: Path, deadline: float | None = None) -> str | None:
    if not interpreter or (deadline is not None and time.monotonic() >= deadline):
        return None
    timeout = min(30, deadline - time.monotonic()) if deadline is not None else 30
    result = run([interpreter, "-c", RUNTIME_SCRIPT], root, timeout=max(0.001, timeout))
    value = result.stdout.strip()
    return value if result.exit_code == 0 and not result.timed_out and len(value) == 64 else None


def repository_hashes(root: Path, deadline: float | None = None) -> tuple[str, str] | None:
    all_files, tests, total = hashlib.sha256(), hashlib.sha256(), 0
    try:
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in PRUNE)
            if any((Path(directory) / d).is_symlink() for d in dirs):
                return None
            for name in sorted(names):
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                if name in IGNORE or name.endswith((".pyc", ".pyo")):
                    continue
                path = Path(directory) / name
                if path.is_symlink():
                    return None
                total += path.stat().st_size
                if total > LIMIT:
                    return None
                relative = path.relative_to(root).as_posix()
                blob = relative.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest()
                all_files.update(blob)
                if (
                    any(
                        part in {"tests", "test", "spec", "specs", "__tests__"}
                        for part in path.relative_to(root).parts
                    )
                    or "test" in name
                ):
                    tests.update(blob)
        return all_files.hexdigest(), tests.hexdigest()
    except OSError:
        return None


class MutationCache:
    def __init__(self, context: RunContext, executable: str, deadline: float | None = None):
        self.root, self.namespace = context.root, None
        self.reason = "unverified runtime or opaque test command; rerun"
        if not context.config.tools["mutator"].cache:
            self.reason = "cache disabled"
            return
        coordinator = Path(__file__).resolve().parents[1]
        python_paths = os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if any(
            value
            and not (
                Path(value).resolve().is_relative_to(context.root.resolve())
                or Path(value).resolve() == coordinator.parent
            )
            for value in python_paths
        ):
            self.reason = "external PYTHONPATH cannot be conservatively fingerprinted; rerun"
            return
        interpreter = python_for(context.config.commands.get("test", ""))
        if not interpreter or any(Path(f).suffix != ".py" for f in context.selected_files):
            return
        repository = repository_hashes(context.root, deadline)
        project_runtime = runtime_hash(interpreter, context.root, deadline)
        tool_runtime = runtime_hash(tool_python(executable), context.root, deadline)
        if repository and project_runtime and tool_runtime:
            import dataclasses

            from gauntlet.pipeline.coverage import artifacts

            coverage_hashes = {
                str(path.relative_to(context.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in artifacts(context.root)
            }
            coordinator_hashes = {
                str(path.relative_to(coordinator)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in coordinator.rglob("*.py")
            }
            payload = {
                "cache_version": 1,
                "coverage": coverage_hashes,
                "coordinator": coordinator_hashes,
                "repository_hash": repository[0],
                "test_content_hash": repository[1],
                "project_runtime": project_runtime,
                "tool_runtime": tool_runtime,
                "tool": Path(executable).read_bytes().hex(),
                "config": dataclasses.asdict(context.config),
                "environment": dict(os.environ),
            }
            self.namespace = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest()
            self.reason = "content, tests, config, environment and installed runtimes fingerprinted"

    def path(self, file: str) -> Path:
        key = hashlib.sha256((str(self.namespace) + "\0" + file).encode()).hexdigest()
        return self.root / ".gauntlet/mutation-cache" / f"{key}.json"

    def get(self, file: str) -> dict | None:
        if self.namespace is None:
            return None
        try:
            path = self.path(file)
            if path.stat().st_size > 10 * 1024 * 1024:
                return None
            data = json.loads(path.read_text())
            payload = data["payload"]
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            if data["digest"] != digest or payload["version"] != 1 or payload["file"] != file:
                return None
            if type(payload["inventory"]) is not int or payload["inventory"] < 0:
                return None
            if not isinstance(payload["snapshots"], list):
                return None
            return payload
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def put(self, file: str, inventory: int, snapshots: list[dict]) -> None:
        if self.namespace is None:
            return
        payload = {"version": 1, "file": file, "inventory": inventory, "snapshots": snapshots}
        data = {
            "payload": payload,
            "digest": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        }
        # Cache payloads are raw evidence; policy and acceptance are reapplied on every run.
        path = self.path(file)
        path.parent.mkdir(parents=True, exist_ok=True)
        import tempfile

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, sort_keys=True)
            os.replace(temporary, path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
