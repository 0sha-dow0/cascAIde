from __future__ import annotations

from collections.abc import Mapping

from backend.domain.errors import CodeMemoryError, Ok, Result
from backend.domain.models import FileContent, MemorySnippet
from backend.ports.code_memory import CodeMemory

__all__ = ("FakeCodeMemory",)

_DEFAULT_SNIPPET = MemorySnippet(
    path="src/api.js",
    text="const axios = require('axios');\nasync function getUser(id) { return (await axios.get(`/users/${id}`)).data; }",
    score=1.0,
)


class FakeCodeMemory(CodeMemory):
    """Deterministic code memory for tests and no-credentials mode.

    ``ensure_indexed`` is a no-op; ``recall`` returns seeded snippets for a repo,
    or a single generic snippet so the explore flow can still proceed.
    """

    def __init__(
        self, snippets: Mapping[str, tuple[MemorySnippet, ...]] | None = None
    ) -> None:
        self._snippets: dict[str, tuple[MemorySnippet, ...]] = dict(snippets or {})
        self.indexed: set[str] = set()

    def ensure_indexed(
        self, repo_url: str, files: tuple[FileContent, ...]
    ) -> Result[None, CodeMemoryError]:
        self.indexed.add(repo_url)
        return Ok(None)

    def recall(
        self, repo_url: str, query: str, k: int = 8
    ) -> Result[tuple[MemorySnippet, ...], CodeMemoryError]:
        seeded = self._snippets.get(repo_url)
        if seeded is not None:
            return Ok(seeded[:k])
        return Ok((_DEFAULT_SNIPPET,))
