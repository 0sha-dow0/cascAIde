import hashlib
import json
from typing import Final, Protocol

from backend.ports.llm import LlmRequest, LlmResponse

_KEY_PREFIX: Final = "cascaide:llm:"
_DEFAULT_TTL_S: Final = 7 * 24 * 3600  # 7 days


class RedisLike(Protocol):
    """The subset of a redis client we use (so tests can inject a fake)."""

    def get(self, key: str) -> object: ...

    def set(self, key: str, value: str, ex: int | None = None) -> object: ...


def _key(req: LlmRequest) -> str:
    material = json.dumps(
        {
            "role": req.role.value,
            "messages": [[m.role, m.content] for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
        },
        sort_keys=True,
    )
    return _KEY_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()


class RedisResponseCache:
    """Durable LLM response cache backed by Redis. Any Redis failure is treated as a cache
    miss (or a no-op on write), so the transplant pipeline is never affected if Redis is down.
    """

    def __init__(self, client: RedisLike, ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._client = client
        self._ttl = ttl_s

    def get(self, req: LlmRequest) -> LlmResponse | None:
        try:
            raw = self._client.get(_key(req))
        except Exception:  # noqa: BLE001 — any redis/transport error is just a miss
            return None
        if raw is None:
            return None
        try:
            payload = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
            data = json.loads(payload)
            return LlmResponse(
                text=str(data["text"]),
                model=str(data["model"]),
                finish_reason=data["finish_reason"],
            )
        except (ValueError, KeyError, TypeError):
            return None

    def put(self, req: LlmRequest, response: LlmResponse) -> None:
        try:
            payload = json.dumps(
                {
                    "text": response.text,
                    "model": response.model,
                    "finish_reason": response.finish_reason,
                }
            )
            self._client.set(_key(req), payload, ex=self._ttl)
        except Exception:  # noqa: BLE001 — best-effort write; never break the pipeline
            return


__all__ = ("RedisLike", "RedisResponseCache")
