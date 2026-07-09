from typing import Protocol

from backend.domain.errors import CodeMemoryError, Result
from backend.domain.models import FileContent, MemorySnippet


class CodeMemory(Protocol):
    """Semantic "code memory" over a scanned repo — index once, recall relevant chunks.

    Backed by Cognee Cloud in production; a deterministic fake in tests / no-creds mode.
    """

    def ensure_indexed(
        self, repo_url: str, files: tuple[FileContent, ...]
    ) -> Result[None, CodeMemoryError]:
        """Index the repo's code into the store (cached — a no-op once already indexed)."""
        ...

    def recall(
        self, repo_url: str, query: str, k: int = 8
    ) -> Result[tuple[MemorySnippet, ...], CodeMemoryError]:
        """Return the top-k code chunks most relevant to the query."""
        ...


__all__ = ("CodeMemory",)
