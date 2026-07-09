import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from backend import demo_fixtures
from backend.adapters.fake.fake_auth import FakeAuthProvider
from backend.adapters.fake.fake_code_memory import FakeCodeMemory
from backend.adapters.fake.fake_event_sink import InMemoryEventSink
from backend.adapters.fake.fake_github import FakeGitHubClient
from backend.adapters.fake.fake_graph_store import FakeGraphStore
from backend.adapters.fake.fake_llm import FakeLlmClientFactory
from backend.adapters.fake.fake_record_store import FakeRecordStore
from backend.adapters.fake.fake_repo_content import FakeRepoContentProvider
from backend.adapters.fake.fake_sandbox import FakeSandbox
from backend.adapters.live.live_advisory import GitHubAdvisoryClient
from backend.adapters.live.live_auth import LiveAuthProvider
from backend.adapters.live.live_code_memory import LiveCogneeCloudCodeMemory
from backend.adapters.live.live_github import LiveGitHubClient
from backend.adapters.live.live_github_butterbase import ButterbaseGitHubClient
from backend.adapters.live.live_graph_store import LiveGraphStore
from backend.adapters.live.caching_llm import CachingLlmClientFactory
from backend.adapters.live.live_llm import LiveLlmClientFactory
from backend.adapters.live.live_record_store import LiveRecordStore
from backend.config import Settings
from backend.domain.determinism import Clock, IdGenerator, SequentialIdGenerator, SystemClock
from backend.domain.enums import LlmRole, SandboxOutcome, StrategyKind
from backend.domain.errors import ConfigError, Err, IngestError, LlmError, Ok, Result, SandboxError
from backend.domain.models import FileContent, NormalizedOutput
from backend.ports.advisory import AdvisoryClient
from backend.ports.auth import AuthProvider
from backend.ports.code_memory import CodeMemory
from backend.ports.event_sink import EventSink
from backend.ports.github import GitHubClient
from backend.ports.graph_store import GraphStore
from backend.ports.llm import LlmClient, LlmClientFactory, LlmRequest, LlmResponse
from backend.ports.record_store import RecordStore
from backend.ports.repo_content import RepoContentProvider
from backend.adapters.live.live_repo_content import LiveRepoContentProvider
from backend.adapters.live.live_sandbox import LiveSandbox
from backend.ports.sandbox import (
    SandboxCommand,
    SandboxHandle,
    SandboxResult,
    SandboxRunner,
    validate_command,
    validate_exec_timeout,
)
from backend.services.explore import ExploreService
from backend.services.graph_builder import GraphBuilder
from backend.services.ingestion import IngestionService
from backend.services.judges import JudgePanel
from backend.services.mitigation import MitigationService
from backend.services.normalizer import normalize_output
from backend.services.orchestrator import PipelineOrchestrator
from backend.services.pull_request import PullRequestService
from backend.services.recipes import RecipeMemory
from backend.services.review import ReviewService
from backend.services.sanitizer import sanitize_evidence
from backend.services.transplant_agent import TransplantAgent
from backend.services.transplant_validators import TransplantValidator
from backend.services.underwriter import Underwriter
from backend.services.verification import VerificationEngine

_PLACEHOLDER_MARKER = "REPLACE"


def _present(value: str | None) -> bool:
    return value is not None and value.strip() != "" and _PLACEHOLDER_MARKER not in value


def _env_present(env_name: str | None) -> bool:
    if env_name is None:
        return False
    raw = os.environ.get(env_name)
    return raw is not None and raw.strip() != "" and _PLACEHOLDER_MARKER not in raw


@dataclass(frozen=True)
class Container:
    settings: Settings
    clock: Clock
    ids: IdGenerator
    ingestion: IngestionService
    underwriter: Underwriter
    mitigation: MitigationService
    explore: ExploreService
    advisory: AdvisoryClient
    code_memory: CodeMemory
    github: GitHubClient
    orchestrator: PipelineOrchestrator
    review: ReviewService
    pr: PullRequestService
    auth: AuthProvider
    store: RecordStore
    events: EventSink
    golden: Mapping[str, NormalizedOutput]
    repos_provider: RepoContentProvider


def _judge_response() -> LlmResponse:
    return LlmResponse(
        text='{"verdict":"approve","rationale":"Minimal axios->fetch swap; evidence supports approval."}',
        model="fake",
        finish_reason="stop",
    )


def _mitigation_response() -> LlmResponse:
    card = (
        '{{"upgrade":{{"title":"Upgrade axios","effort":"low","blast_radius":"2 files",'
        '"residual_risk":"library remains","rationale":"Dependabot handles patched versions."}},'
        '"shim":{{"title":"Wrap axios","effort":"medium","blast_radius":"2 files",'
        '"residual_risk":"CVE contained not cured","rationale":"Quarantine behind a wrapper."}},'
        '"transplant":{{"title":"Replace with fetch","effort":"high","blast_radius":"2 files",'
        '"residual_risk":"none","rationale":"Permanent cure with behavioral proof."}},'
        '"accept_risk":{{"title":"Accept risk","effort":"none","blast_radius":"2 files",'
        '"residual_risk":"full CVE exposure","rationale":"Vulnerable path stays live."}}}}'
    )
    return LlmResponse(text=card.replace("{{", "{").replace("}}", "}"), model="fake", finish_reason="stop")


def _explore_response() -> LlmResponse:
    plan = (
        '{"summary":"Replace axios with the native fetch API behind a small http helper.",'
        '"steps":['
        '{"title":"Add a fetch-based http helper",'
        '"detail":"Create src/httpClient.js exposing get and post that wrap fetch and '
        'return a response with a data field.","file_refs":["src/httpClient.js"]},'
        '{"title":"Repoint the call sites",'
        '"detail":"Swap the axios import for the new helper in src/api.js and '
        'src/userClient.js, keeping the same call shape.",'
        '"file_refs":["src/api.js","src/userClient.js"]},'
        '{"title":"Verify behavior",'
        '"detail":"Run node --check and the test suite to confirm request/response '
        'parity before opening a PR.","file_refs":[]}'
        '],'
        '"grounded_files":["src/httpClient.js","src/api.js","src/userClient.js"]}'
    )
    return LlmResponse(text=plan, model="fake", finish_reason="stop")


def _transplant_response() -> LlmResponse:
    api = (
        "const http = require('./httpClient');\n"
        "async function getUser(id) {\n"
        "  const res = await http.get(`/users/${id}`);\n"
        "  return res.data;\n"
        "}\n"
        "module.exports = { getUser };\n"
    )
    client = (
        "const http = require('./httpClient');\n"
        "async function listUsers() {\n"
        "  const res = await http.get('/users');\n"
        "  return res.data;\n"
        "}\n"
        "module.exports = { listUsers };\n"
    )
    text = (
        f'<rewritten_file path="src/api.js">\n{api}</rewritten_file>\n'
        f'<rewritten_file path="src/userClient.js">\n{client}</rewritten_file>\n'
    )
    return LlmResponse(text=text, model="fake", finish_reason="stop")


def _fake_llm_scripted() -> Mapping[LlmRole, Sequence[LlmResponse]]:
    judges = [_judge_response() for _ in range(3)]
    return {
        LlmRole.TRANSPLANT: [_transplant_response(), _transplant_response()],
        LlmRole.JUDGE_CORRECTNESS: judges,
        LlmRole.JUDGE_SECURITY: judges,
        LlmRole.JUDGE_MINIMALITY: judges,
        LlmRole.JUDGE_RECIPE: judges,
        LlmRole.MITIGATION: [_mitigation_response(), _mitigation_response()],
        LlmRole.PR_SCREEN: [_judge_response()],
        LlmRole.EXPLORE: [_explore_response(), _explore_response()],
    }


_LIVE_JUDGE_ROLES: frozenset[LlmRole] = frozenset(
    {
        LlmRole.TRANSPLANT,
        LlmRole.JUDGE_CORRECTNESS,
        LlmRole.JUDGE_SECURITY,
        LlmRole.JUDGE_MINIMALITY,
        LlmRole.JUDGE_RECIPE,
        LlmRole.EXPLORE,
    }
)


class CompositeRepoContentProvider(RepoContentProvider):
    def __init__(
        self,
        seeded: RepoContentProvider,
        live: RepoContentProvider,
        seeded_urls: frozenset[str],
    ) -> None:
        self._seeded = seeded
        self._live = live
        self._seeded_urls = seeded_urls

    def _pick(self, repo_url: str) -> RepoContentProvider:
        return self._seeded if repo_url in self._seeded_urls else self._live

    def fetch(self, repo_url: str) -> Result[tuple[FileContent, ...], IngestError]:
        return self._pick(repo_url).fetch(repo_url)

    def read_manifest(self, repo_url: str) -> Result[FileContent, IngestError]:
        return self._pick(repo_url).read_manifest(repo_url)

    def read_lockfile(self, repo_url: str) -> Result[FileContent | None, IngestError]:
        return self._pick(repo_url).read_lockfile(repo_url)


class LenientSandbox(SandboxRunner):
    def __init__(self, scripted: Mapping[tuple[str, ...], SandboxResult], capacity: int = 16) -> None:
        self._inner = FakeSandbox(scripted, capacity=capacity)
        self._scripted = frozenset(scripted.keys())

    def acquire(self, snapshot_id: str) -> Result[SandboxHandle, SandboxError]:
        return self._inner.acquire(snapshot_id)

    def write_files(
        self, h: SandboxHandle, files: Mapping[str, str]
    ) -> Result[None, SandboxError]:
        return self._inner.write_files(h, files)

    def release(self, h: SandboxHandle) -> Result[None, SandboxError]:
        return self._inner.release(h)

    def exec(
        self, h: SandboxHandle, cmd: SandboxCommand, timeout_s: float
    ) -> Result[SandboxResult, SandboxError]:
        if cmd.argv in self._scripted:
            return self._inner.exec(h, cmd, timeout_s)
        timeout_check = validate_exec_timeout(timeout_s)
        if isinstance(timeout_check, Err):
            return Err(timeout_check.error)
        command_check = validate_command(cmd)
        if isinstance(command_check, Err):
            return Err(command_check.error)
        return Ok(
            SandboxResult(
                outcome=SandboxOutcome.PASSED,
                exit_code=0,
                stdout="",
                stderr="",
                duration_s=0.01,
            )
        )


class HybridLlmClientFactory(LlmClientFactory):
    def __init__(
        self,
        live: LlmClientFactory,
        fake: LlmClientFactory,
        live_roles: frozenset[LlmRole],
    ) -> None:
        self._live = live
        self._fake = fake
        self._live_roles = live_roles

    def for_role(self, role: LlmRole) -> Result[LlmClient, ConfigError]:
        if role in self._live_roles:
            return self._live.for_role(role)
        return self._fake.for_role(role)


class _RepeatingLlmClient(LlmClient):
    def __init__(self, response: LlmResponse) -> None:
        self._response = response

    def complete(self, req: LlmRequest) -> Result[LlmResponse, LlmError]:
        return Ok(self._response)


class _RepeatingLlmClientFactory(LlmClientFactory):
    def __init__(self, responses: Mapping[LlmRole, LlmResponse]) -> None:
        self._responses = responses

    def for_role(self, role: LlmRole) -> Result[LlmClient, ConfigError]:
        response = self._responses.get(role)
        if response is None:
            return Err(ConfigError("no scripted response for role", {"role": role.value}))
        return Ok(_RepeatingLlmClient(response))


def _repeating_responses() -> Mapping[LlmRole, LlmResponse]:
    judge = _judge_response()
    return {
        LlmRole.TRANSPLANT: _transplant_response(),
        LlmRole.JUDGE_CORRECTNESS: judge,
        LlmRole.JUDGE_SECURITY: judge,
        LlmRole.JUDGE_MINIMALITY: judge,
        LlmRole.JUDGE_RECIPE: judge,
        LlmRole.MITIGATION: _mitigation_response(),
        LlmRole.PR_SCREEN: judge,
        LlmRole.EXPLORE: _explore_response(),
    }


def _build_llm(settings: Settings) -> LlmClientFactory:
    deterministic = _RepeatingLlmClientFactory(_repeating_responses())
    if settings.use_fakes:
        return deterministic
    # Memoize live LLM calls so repeated transplant runs on the same repo don't re-hit the API.
    live = HybridLlmClientFactory(LiveLlmClientFactory(settings), deterministic, _LIVE_JUDGE_ROLES)
    return CachingLlmClientFactory(live)


def _build_graph_store(settings: Settings) -> GraphStore:
    if (
        not settings.use_fakes
        and _present(settings.neo4j_uri)
        and settings.neo4j_user is not None
        and _env_present(settings.neo4j_password_env)
        and settings.neo4j_password_env is not None
    ):
        password = os.environ[settings.neo4j_password_env]
        return LiveGraphStore(settings.neo4j_uri or "", settings.neo4j_user, password)
    return FakeGraphStore()


def _build_record_store(settings: Settings, clock: Clock) -> RecordStore:
    # Live Butterbase persistence (LiveRecordStore) rewrite is pending (Phase 3). Gate it behind an
    # explicit opt-in so the auth cutover (Butterbase base_url) does not activate the old live store.
    store_enabled = os.environ.get("DEPCOVER_BUTTERBASE_STORE", "").strip().lower() in _TRUE_TOKENS
    if (
        store_enabled
        and not settings.use_fakes
        and _present(settings.butterbase_base_url)
        and _env_present(settings.butterbase_key_env)
        and settings.butterbase_key_env is not None
    ):
        key = os.environ[settings.butterbase_key_env]
        return LiveRecordStore(settings.butterbase_base_url or "", key)
    return FakeRecordStore(clock)


_DAYTONA_DEFAULT_URL: Final[str] = "https://app.daytona.io/api"
_TRUE_TOKENS: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


def _daytona_enabled() -> bool:
    return os.environ.get("DEPCOVER_USE_DAYTONA", "").strip().lower() in _TRUE_TOKENS


def _build_validator_sandbox(settings: Settings, fallback: SandboxRunner) -> SandboxRunner:
    if settings.use_fakes or not _daytona_enabled():
        return fallback
    api_key = os.environ.get("DAYTONA_API_KEY")
    if not _env_present("DAYTONA_API_KEY") or api_key is None:
        return fallback
    api_url = os.environ.get("DEPCOVER_DAYTONA_API_URL") or _DAYTONA_DEFAULT_URL
    return LiveSandbox(api_key, api_url)


def _build_github(settings: Settings) -> GitHubClient:
    # Preferred: act as the signed-in user via Butterbase's GitHub Integration (real PRs, permission gate).
    if _butterbase_ready(settings) and settings.butterbase_app_id is not None:
        key = os.environ[settings.butterbase_key_env or ""]
        return ButterbaseGitHubClient(settings.butterbase_base_url or "", settings.butterbase_app_id, key)
    token_env = settings.github_token_env
    if not settings.use_fakes and token_env is not None and _env_present(token_env):
        return LiveGitHubClient(os.environ[token_env])
    return FakeGitHubClient(demo_fixtures.github_seed(), auto_create_repos=True)


def _build_advisory(settings: Settings) -> AdvisoryClient:
    # Advisories are always live GitHub Advisory Database — no fake fallback.
    # A token lifts the rate limit; unauthenticated still returns real data.
    token_env = settings.github_token_env
    token = (
        os.environ[token_env]
        if token_env is not None and _env_present(token_env)
        else None
    )
    return GitHubAdvisoryClient(token)


def _build_code_memory(settings: Settings) -> CodeMemory:
    if (
        not settings.use_fakes
        and _present(settings.cognee_base_url)
        and _env_present(settings.cognee_api_key_env)
        and settings.cognee_api_key_env is not None
    ):
        key = os.environ[settings.cognee_api_key_env]
        return LiveCogneeCloudCodeMemory(settings.cognee_base_url or "", key)
    return FakeCodeMemory()


def _butterbase_ready(settings: Settings) -> bool:
    return (
        not settings.use_fakes
        and _present(settings.butterbase_base_url)
        and _present(settings.butterbase_app_id)
        and _env_present(settings.butterbase_key_env)
        and settings.butterbase_key_env is not None
    )


def _build_auth(settings: Settings) -> AuthProvider:
    if _butterbase_ready(settings) and settings.butterbase_app_id is not None:
        key = os.environ[settings.butterbase_key_env or ""]
        return LiveAuthProvider(settings.butterbase_base_url or "", settings.butterbase_app_id, key)
    return FakeAuthProvider(demo_fixtures.auth_tokens_seed())


def _build_golden() -> Result[dict[str, NormalizedOutput], ConfigError]:
    golden: dict[str, NormalizedOutput] = {}
    for case_id, raw in demo_fixtures.golden_raw().items():
        normalized = normalize_output(case_id, raw)
        if isinstance(normalized, Err):
            return Err(ConfigError("golden normalization failed", {"case_id": case_id}))
        golden[case_id] = normalized.value
    return Ok(golden)


def build_container(settings: Settings) -> Result[Container, ConfigError]:
    clock: Clock = SystemClock()
    ids: IdGenerator = SequentialIdGenerator()
    golden_result = _build_golden()
    if isinstance(golden_result, Err):
        return golden_result

    llm: LlmClientFactory = _build_llm(settings)
    graph_store: GraphStore = _build_graph_store(settings)
    store: RecordStore = _build_record_store(settings, clock)
    auth: AuthProvider = _build_auth(settings)
    seed = demo_fixtures.victim_repos_seed()
    repos: RepoContentProvider = CompositeRepoContentProvider(
        FakeRepoContentProvider(seed),
        LiveRepoContentProvider(),
        frozenset(seed.keys()),
    )
    sandbox: SandboxRunner = LenientSandbox(demo_fixtures.scripted_sandbox(), capacity=32)
    events: EventSink = InMemoryEventSink(clock)
    github: GitHubClient = _build_github(settings)
    advisory: AdvisoryClient = _build_advisory(settings)
    code_memory: CodeMemory = _build_code_memory(settings)

    builder = GraphBuilder(graph_store)
    ingestion = IngestionService(repos, builder, store, clock, ids)
    underwriter = Underwriter(sandbox, store, settings, clock, ids)
    mitigation = MitigationService(llm)
    explore = ExploreService(llm, code_memory)
    agent = TransplantAgent(llm)
    validator = TransplantValidator(_build_validator_sandbox(settings, sandbox), settings)
    verifier = VerificationEngine(sandbox, settings)
    panel = JudgePanel(llm, settings)
    recipes = RecipeMemory(store)
    orchestrator = PipelineOrchestrator(
        agent,
        validator,
        verifier,
        sanitize_evidence,
        panel,
        recipes,
        store,
        events,
        clock,
        ids,
        settings,
    )
    review = ReviewService(store, clock)
    pull_request = PullRequestService(github)

    return Ok(
        Container(
            settings=settings,
            clock=clock,
            ids=ids,
            ingestion=ingestion,
            underwriter=underwriter,
            mitigation=mitigation,
            explore=explore,
            advisory=advisory,
            code_memory=code_memory,
            github=github,
            orchestrator=orchestrator,
            review=review,
            pr=pull_request,
            auth=auth,
            store=store,
            events=events,
            golden=golden_result.value,
            repos_provider=repos,
        )
    )
