from backend.adapters.live.redis_llm_cache import RedisResponseCache
from backend.domain.enums import LlmRole
from backend.ports.llm import LlmMessage, LlmRequest, LlmResponse


def _req(text: str) -> LlmRequest:
    return LlmRequest(
        role=LlmRole.TRANSPLANT,
        messages=(LlmMessage(role="user", content=text),),
        temperature=0.0,
        max_tokens=100,
    )


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def get(self, key: str) -> object:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> object:
        self.store[key] = value.encode("utf-8")
        return True


class _BrokenRedis:
    def get(self, key: str) -> object:
        raise ConnectionError("redis down")

    def set(self, key: str, value: str, ex: int | None = None) -> object:
        raise ConnectionError("redis down")


def test_put_then_get_roundtrips() -> None:
    cache = RedisResponseCache(_FakeRedis())
    assert cache.get(_req("q")) is None  # miss
    cache.put(_req("q"), LlmResponse(text="hi", model="m", finish_reason="stop"))
    got = cache.get(_req("q"))
    assert got is not None
    assert (got.text, got.model, got.finish_reason) == ("hi", "m", "stop")


def test_redis_error_is_a_miss_not_a_crash() -> None:
    cache = RedisResponseCache(_BrokenRedis())
    assert cache.get(_req("q")) is None  # error swallowed → miss
    cache.put(_req("q"), LlmResponse(text="x", model="m", finish_reason="stop"))  # no raise


def test_keys_are_request_specific() -> None:
    redis = _FakeRedis()
    cache = RedisResponseCache(redis)
    cache.put(_req("a"), LlmResponse(text="A", model="m", finish_reason="stop"))
    cache.put(_req("b"), LlmResponse(text="B", model="m", finish_reason="stop"))
    assert len(redis.store) == 2  # different requests → different keys
    a = cache.get(_req("a"))
    b = cache.get(_req("b"))
    assert a is not None and a.text == "A"
    assert b is not None and b.text == "B"
