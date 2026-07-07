import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from backend.domain.errors import Err, IngestError, Ok, Result
from backend.domain.models import FileContent
from backend.ports.repo_content import RepoContentProvider

_CODE_SUFFIXES: Final[frozenset[str]] = frozenset({".js", ".mjs", ".cjs", ".ts", ".json"})
_MANIFEST_NAME: Final[str] = "package.json"
_LOCKFILE_NAMES: Final[tuple[str, ...]] = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
)
_SKIP_DIRS: Final[frozenset[str]] = frozenset({".git", "node_modules", "dist", "build", ".next"})
_ALLOWED_SCHEMES: Final[tuple[str, ...]] = ("https://", "http://")


class LiveRepoContentProvider(RepoContentProvider):
    def __init__(
        self, timeout_s: float = 60.0, max_files: int = 600, max_bytes: int = 300_000
    ) -> None:
        self._timeout_s = timeout_s
        self._max_files = max_files
        self._max_bytes = max_bytes

    def _clone_and_read(self, repo_url: str) -> Result[tuple[FileContent, ...], IngestError]:
        if not repo_url.startswith(_ALLOWED_SCHEMES):
            return Err(IngestError("only http(s) repo urls are allowed", {"url": repo_url}))
        workdir = tempfile.mkdtemp(prefix="depcover-clone-")
        try:
            completed = subprocess.run(  # noqa: S603
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "clone",
                    "--depth",
                    "1",
                    "--no-tags",
                    "--quiet",
                    repo_url,
                    workdir,
                ],
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
            if completed.returncode != 0:
                return Err(IngestError("git clone failed", {"url": repo_url}))
            files = self._read_tree(Path(workdir))
            if not files:
                return Err(IngestError("no readable source files in repo", {"url": repo_url}))
            return Ok(tuple(sorted(files, key=lambda f: f.path)))
        except subprocess.TimeoutExpired:
            return Err(IngestError("git clone timed out", {"url": repo_url}))
        except OSError as error:
            return Err(IngestError("clone io error", {"url": repo_url, "detail": str(error)}))
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _read_tree(self, root: Path) -> list[FileContent]:
        files: list[FileContent] = []
        for path in root.rglob("*"):
            if len(files) >= self._max_files:
                break
            relative = path.relative_to(root)
            if any(part in _SKIP_DIRS for part in relative.parts):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if path.name != _MANIFEST_NAME and path.suffix not in _CODE_SUFFIXES:
                continue
            try:
                if path.stat().st_size > self._max_bytes:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            files.append(FileContent(path=relative.as_posix(), text=text))
        return files

    def fetch(self, repo_url: str) -> Result[tuple[FileContent, ...], IngestError]:
        return self._clone_and_read(repo_url)

    def read_manifest(self, repo_url: str) -> Result[FileContent, IngestError]:
        fetched = self._clone_and_read(repo_url)
        if isinstance(fetched, Err):
            return fetched
        return _first_named(fetched.value, (_MANIFEST_NAME,), repo_url)

    def read_lockfile(self, repo_url: str) -> Result[FileContent | None, IngestError]:
        fetched = self._clone_and_read(repo_url)
        if isinstance(fetched, Err):
            return fetched
        match = _first_named(fetched.value, _LOCKFILE_NAMES, repo_url)
        if isinstance(match, Err):
            return Ok(None)
        return Ok(match.value)


def _first_named(
    files: Sequence[FileContent], names: tuple[str, ...], repo_url: str
) -> Result[FileContent, IngestError]:
    for name in names:
        for file in files:
            if file.path == name or file.path.endswith("/" + name):
                return Ok(file)
    return Err(IngestError("file not found in repo", {"url": repo_url, "names": ",".join(names)}))
