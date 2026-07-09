from collections import OrderedDict
from typing import Final, Protocol

from backend.domain.enums import LlmRole
from backend.domain.errors import ConfigError, Err, LlmError, Ok, Result
from backend.ports.llm import LlmClient, LlmClientFactory, LlmRequest, LlmResponse

_MAX_ENTRIES: Final[int] = 512


class LlmResponseCache(Protocol):
    """Pluggable store for memoized LLM responses (in-process bounded, or Redis-backed)."""

    def get(self, req: LlmRequest) -> LlmResponse | None: ...

    def put(self, req: LlmRequest, response: LlmResponse) -> None: ...


class _BoundedCache:
    """Best-effort in-process LRU of LLM responses, keyed by the (hashable, frozen) request.

    Bounded so memory can't grow without limit; best-effort under concurrency (a rare
    double-miss just recomputes — harmless).
    """

    def __init__(self, capacity: int = _MAX_ENTRIES) -> None:
        self._store: OrderedDict[LlmRequest, LlmResponse] = OrderedDict()
        self._capacity = capacity

    def get(self, req: LlmRequest) -> LlmResponse | None:
        value = self._store.get(req)
        if value is not None:
            self._store.move_to_end(req)
        return value

    def put(self, req: LlmRequest, response: LlmResponse) -> None:
        self._store[req] = response
        self._store.move_to_end(req)
        while len(self._store) > self._capacity:
            self._store.popitem(last=False)


class CachingLlmClient(LlmClient):
    """Wraps an LlmClient so identical requests return a cached response (no API call)."""

    def __init__(self, inner: LlmClient, cache: LlmResponseCache) -> None:
        self._inner = inner
        self._cache = cache

    def complete(self, req: LlmRequest) -> Result[LlmResponse, LlmError]:
        cached = self._cache.get(req)
        if cached is not None:
            return Ok(cached)
        result = self._inner.complete(req)
        if isinstance(result, Ok):
            self._cache.put(req, result.value)  # only successful responses; errors stay retryable
        return result


class CachingLlmClientFactory(LlmClientFactory):
    """Wraps a factory so every role's client memoizes on the request, sharing one cache.

    Pass a Redis-backed cache for durability across restarts; defaults to in-process bounded.
    """

    def __init__(self, inner: LlmClientFactory, cache: LlmResponseCache | None = None) -> None:
        self._inner = inner
        self._cache: LlmResponseCache = cache if cache is not None else _BoundedCache()

    def for_role(self, role: LlmRole) -> Result[LlmClient, ConfigError]:
        built = self._inner.for_role(role)
        if isinstance(built, Err):
            return Err(built.error)
        return Ok(CachingLlmClient(built.value, self._cache))


__all__ = ("CachingLlmClient", "CachingLlmClientFactory", "LlmResponseCache")
