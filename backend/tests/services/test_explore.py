"""Tests for backend.services.explore.ExploreService.

Binds to the real parsing contract in services/explore.py:

* the model must return a single JSON object with "summary", "steps", and
  "grounded_files"; each step needs "title", "detail", and "file_refs";
* at least one well-formed step is required, else LlmMalformedOutputError;
* incident_id is threaded onto the plan (id == plan-{incident_id});
* for_role(EXPLORE) absent -> ConfigError;
* finish_reason == "length" and malformed JSON -> LlmMalformedOutputError;
* the code memory is indexed before recall, and markdown fences are stripped.
"""

from __future__ import annotations

import json
from typing import Literal

from backend.adapters.fake.fake_code_memory import FakeCodeMemory
from backend.adapters.fake.fake_llm import FakeLlmClientFactory
from backend.domain.enums import LlmRole, StrategyKind
from backend.domain.errors import (
    ConfigError,
    DepCoverError,
    Err,
    LlmMalformedOutputError,
    Ok,
    Result,
)
from backend.domain.models import (
    CallSite,
    FileContent,
    ImplementationPlan,
    MemorySnippet,
    SurgeryPlan,
)
from backend.ports.llm import LlmResponse
from backend.services.explore import ExploreService

_INCIDENT_ID = "incident-EXP"
_REPO_URL = "https://github.com/demo/repo"
_TARGET = "axios"


def _surgery_plan() -> SurgeryPlan:
    call_site = CallSite(
        file_path="src/api.js",
        line=1,
        symbol="axios.get",
        is_aliased=False,
        alias=None,
        snippet="axios.get('/x')",
    )
    return SurgeryPlan(
        target_package=_TARGET,
        call_sites=(call_site,),
        affected_files=("src/api.js",),
    )


def _files() -> tuple[FileContent, ...]:
    return (
        FileContent(path="src/api.js", text="const axios = require('axios');"),
        FileContent(path="package.json", text='{"dependencies":{"axios":"0.21.1"}}'),
    )


def _valid_json() -> str:
    return json.dumps(
        {
            "summary": "Replace axios with the native fetch API.",
            "steps": [
                {
                    "title": "Add a fetch helper",
                    "detail": "Create src/httpClient.js wrapping fetch.",
                    "file_refs": ["src/httpClient.js"],
                },
                {
                    "title": "Repoint call sites",
                    "detail": "Swap the axios import in src/api.js.",
                    "file_refs": ["src/api.js"],
                },
            ],
            "grounded_files": ["src/httpClient.js", "src/api.js"],
        }
    )


def _response(
    text: str, finish_reason: Literal["stop", "length"] = "stop"
) -> LlmResponse:
    return LlmResponse(text=text, model="fake-explore", finish_reason=finish_reason)


def _service(
    response: LlmResponse | None, code_memory: FakeCodeMemory | None = None
) -> ExploreService:
    roles = {LlmRole.EXPLORE: (response,)} if response is not None else {}
    factory = FakeLlmClientFactory(roles)
    return ExploreService(factory, code_memory or FakeCodeMemory())


def _plan(
    service: ExploreService, strategy: StrategyKind = StrategyKind.TRANSPLANT
) -> Result[ImplementationPlan, DepCoverError]:
    return service.plan(
        incident_id=_INCIDENT_ID,
        strategy=strategy,
        repo_url=_REPO_URL,
        surgery_plan=_surgery_plan(),
        advisories=(),
        files=_files(),
    )


def _ok(result: Result[ImplementationPlan, DepCoverError]) -> ImplementationPlan:
    assert isinstance(result, Ok), f"expected Ok, got {result!r}"
    return result.value


def _err(result: Result[ImplementationPlan, DepCoverError]) -> DepCoverError:
    assert isinstance(result, Err), f"expected Err, got {result!r}"
    return result.error


def test_happy_path_parses_plan() -> None:
    plan = _ok(_plan(_service(_response(_valid_json()))))
    assert plan.id == f"plan-{_INCIDENT_ID}"
    assert plan.incident_id == _INCIDENT_ID
    assert plan.strategy is StrategyKind.TRANSPLANT
    assert len(plan.steps) == 2
    assert plan.steps[0].title == "Add a fetch helper"
    assert plan.steps[0].file_refs == ("src/httpClient.js",)
    assert plan.grounded_files == ("src/httpClient.js", "src/api.js")
    assert plan.summary != ""


def test_incident_id_is_threaded() -> None:
    plan = _ok(_plan(_service(_response(_valid_json()))))
    assert plan.incident_id == _INCIDENT_ID
    assert plan.id == f"plan-{_INCIDENT_ID}"


def test_index_is_ensured_before_recall() -> None:
    memory = FakeCodeMemory()
    _ok(_plan(_service(_response(_valid_json()), memory)))
    assert _REPO_URL in memory.indexed


def test_markdown_fenced_json_is_ok() -> None:
    fenced = "```json\n" + _valid_json() + "\n```"
    plan = _ok(_plan(_service(_response(fenced))))
    assert len(plan.steps) == 2


def test_grounded_files_default_to_step_refs() -> None:
    payload = {
        "summary": "x",
        "steps": [
            {"title": "a", "detail": "b", "file_refs": ["src/api.js"]},
            {"title": "c", "detail": "d", "file_refs": ["src/api.js", "src/two.js"]},
        ],
    }
    plan = _ok(_plan(_service(_response(json.dumps(payload)))))
    assert plan.grounded_files == ("src/api.js", "src/two.js")


def test_missing_explore_role_is_config_error() -> None:
    error = _err(_plan(_service(None)))
    assert isinstance(error, ConfigError)


def test_truncated_response_is_malformed_output_error() -> None:
    error = _err(_plan(_service(_response(_valid_json(), finish_reason="length"))))
    assert isinstance(error, LlmMalformedOutputError)


def test_non_json_is_malformed_output_error() -> None:
    error = _err(_plan(_service(_response("not json at all"))))
    assert isinstance(error, LlmMalformedOutputError)


def test_no_steps_is_malformed_output_error() -> None:
    payload = json.dumps({"summary": "x", "steps": [], "grounded_files": []})
    error = _err(_plan(_service(_response(payload))))
    assert isinstance(error, LlmMalformedOutputError)


def test_seeded_snippets_are_recalled() -> None:
    seeded = FakeCodeMemory(
        {_REPO_URL: (MemorySnippet(path="src/api.js", text="axios usage", score=0.9),)}
    )
    plan = _ok(_plan(_service(_response(_valid_json()), seeded)))
    assert plan.strategy is StrategyKind.TRANSPLANT
