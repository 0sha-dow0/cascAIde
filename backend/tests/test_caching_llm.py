from backend.adapters.live.caching_llm import CachingLlmClientFactory
from backend.domain.enums import LlmRole
from backend.domain.errors import ConfigError, Err, LlmError, Ok, Result
from backend.ports.llm import LlmClient, LlmClientFactory, LlmMessage, LlmRequest, LlmResponse


def _req(text: str, role: LlmRole = LlmRole.TRANSPLANT) -> LlmRequest:
    return LlmRequest(
        role=role,
        messages=(LlmMessage(role="user", content=text),),
        temperature=0.0,
        max_tokens=100,
    )


class _CountingClient(LlmClient):
    def __init__(self, response: LlmResponse) -> None:
        self.response = response
        self.calls = 0

    def complete(self, req: LlmRequest) -> Result[LlmResponse, LlmError]:
        self.calls += 1
        return Ok(self.response)


class _StaticFactory(LlmClientFactory):
    def __init__(self, client: LlmClient) -> None:
        self.client = client

    def for_role(self, role: LlmRole) -> Result[LlmClient, ConfigError]:
        return Ok(self.client)


def test_identical_request_served_from_cache() -> None:
    inner = _CountingClient(LlmResponse(text="cached", model="m", finish_reason="stop"))
    built = CachingLlmClientFactory(_StaticFactory(inner)).for_role(LlmRole.TRANSPLANT)
    assert isinstance(built, Ok)
    client = built.value

    first = client.complete(_req("hello"))
    second = client.complete(_req("hello"))

    assert isinstance(first, Ok) and first.value.text == "cached"
    assert isinstance(second, Ok) and second.value.text == "cached"
    assert inner.calls == 1  # second call was a cache hit — no inner call


def test_different_requests_each_reach_inner() -> None:
    inner = _CountingClient(LlmResponse(text="x", model="m", finish_reason="stop"))
    built = CachingLlmClientFactory(_StaticFactory(inner)).for_role(LlmRole.TRANSPLANT)
    assert isinstance(built, Ok)
    built.value.complete(_req("a"))
    built.value.complete(_req("b"))
    assert inner.calls == 2


class _FailThenOk(LlmClient):
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, req: LlmRequest) -> Result[LlmResponse, LlmError]:
        self.calls += 1
        if self.calls == 1:
            return Err(LlmError("boom", {}))
        return Ok(LlmResponse(text="ok", model="m", finish_reason="stop"))


def test_errors_are_not_cached() -> None:
    inner = _FailThenOk()
    built = CachingLlmClientFactory(_StaticFactory(inner)).for_role(LlmRole.TRANSPLANT)
    assert isinstance(built, Ok)
    first = built.value.complete(_req("q"))
    second = built.value.complete(_req("q"))
    assert isinstance(first, Err)
    assert isinstance(second, Ok) and second.value.text == "ok"
    assert inner.calls == 2  # the failed call was retried, not served from cache


def test_config_error_passes_through() -> None:
    class _FailingFactory(LlmClientFactory):
        def for_role(self, role: LlmRole) -> Result[LlmClient, ConfigError]:
            return Err(ConfigError("no role", {"role": role.value}))

    built = CachingLlmClientFactory(_FailingFactory()).for_role(LlmRole.TRANSPLANT)
    assert isinstance(built, Err)
