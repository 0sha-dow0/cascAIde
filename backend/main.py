import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.config import load_settings
from backend.container import Container, build_container
from backend.domain.constants import TARGET_PACKAGE
from backend.domain.enums import (
    FileDecisionKind,
    IncidentStatus,
    RepoAccess,
    ReviewDecision,
    StrategyKind,
    TriggerType,
)
from backend.domain.errors import Err, Ok, RepoAccessError
from backend.domain.models import (
    Advisory,
    FileContent,
    FileDecision,
    Incident,
    MitigationCardSet,
    Repo,
    SurgeryPlan,
    Transplant,
    UnderwritingReport,
)
from backend.ports.auth import AuthenticatedUser
from backend.routers.deps import http_error, require_user
from backend.services.incident_state import transition
from backend.services.upgrade import plan_upgrade

load_dotenv(Path(__file__).resolve().parent / ".env")

_STATIC = Path(__file__).resolve().parent / "static"
_FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_ECOSYSTEM = "npm"
_GENERIC_CVE = (
    "No published advisory matched the installed version; treating it as a mock incident."
)


def _lookup_advisories(
    container: Container, surgery_plan: SurgeryPlan
) -> tuple[Advisory, ...]:
    result = container.advisory.lookup(
        _ECOSYSTEM, surgery_plan.target_package, surgery_plan.target_version
    )
    if isinstance(result, Err):
        return ()
    return result.value


def _cve_summary(report: UnderwritingReport) -> str:
    if report.advisories:
        advisory = report.advisories[0]
        identifier = advisory.cve_id or advisory.ghsa_id
        return f"{identifier}: {advisory.summary}"
    return _GENERIC_CVE


def _with_real_blast_radius(
    options: MitigationCardSet, affected_file_count: int
) -> MitigationCardSet:
    label = f"{affected_file_count} file{'' if affected_file_count == 1 else 's'}"
    return options.model_copy(
        update={
            "options": tuple(
                option.model_copy(update={"blast_radius": label})
                for option in options.options
            )
        }
    )


def _discussion_issue(report: UnderwritingReport) -> tuple[str, str]:
    target = report.target_package
    title = f"cascAIde: how should we remediate the {target} vulnerability?"
    if report.advisories:
        advisories = "\n".join(
            f"- **{a.cve_id or a.ghsa_id}** ({a.severity}, CVSS {a.cvss_score}) — {a.summary}"
            for a in report.advisories
        )
    else:
        advisories = "- No published advisory matched the installed version; treated as a mock incident."
    body = (
        f"## 🔒 Security discussion — `{target}`\n\n"
        "cascAIde flagged a vulnerable dependency in this repository and mapped its blast "
        "radius. Opening this to agree on the best remediation before any code lands.\n\n"
        f"### The vulnerability\n{advisories}\n\n"
        "### Blast radius\n"
        f"- **Affected files:** {report.affected_file_count}\n"
        f"- **Tests impacted:** {len(report.failing_tests)}\n\n"
        "### Options on the table\n"
        f"- **Transplant** — rewrite `{target}` → `fetch` across every call site (permanent cure, behavioral proof)\n"
        "- **Upgrade** — bump to a patched release\n"
        "- **Shim** — quarantine the CVE behind a wrapper\n"
        "- **Accept risk** — document and monitor\n\n"
        "cascAIde can open a PR for the transplant or upgrade automatically once we decide. "
        "What direction do we want?\n\n"
        "---\n"
        "🤖 Opened by cascAIde — autonomous dependency transplant engine."
    )
    return title, body


def _run_upgrade(container: Container, incident: Incident, chosen: Incident) -> JSONResponse:
    now = container.clock.now()
    saved = container.store.update_incident(chosen, incident.status)
    if isinstance(saved, Err):
        raise http_error(saved.error)
    repo = container.store.get_repo(incident.repo_id)
    if isinstance(repo, Err):
        raise http_error(repo.error)
    underwriting = container.store.get_underwriting(incident.repo_id)
    if isinstance(underwriting, Err):
        raise http_error(underwriting.error)
    report = underwriting.value
    manifest = container.repos_provider.read_manifest(repo.value.url)
    if isinstance(manifest, Err):
        raise http_error(manifest.error)
    planned = plan_upgrade(
        incident.id, TARGET_PACKAGE, manifest.value, report.advisories, report.resolved_version
    )
    if isinstance(planned, Err):
        raise http_error(planned.error)
    stored = container.store.save_transplant(planned.value)
    if isinstance(stored, Err):
        raise http_error(stored.error)
    running = transition(saved.value, IncidentStatus.RUNNING, now)
    if isinstance(running, Err):
        raise http_error(running.error)
    running_saved = container.store.update_incident(running.value, saved.value.status)
    if isinstance(running_saved, Err):
        raise http_error(running_saved.error)
    review_ready = transition(running_saved.value, IncidentStatus.AWAITING_REVIEW, now)
    if isinstance(review_ready, Err):
        raise http_error(review_ready.error)
    final = container.store.update_incident(review_ready.value, running_saved.value.status)
    if isinstance(final, Err):
        raise http_error(final.error)
    return JSONResponse(final.value.model_dump(mode="json"))


def _bootstrap_container() -> Container:
    settings_result = load_settings()
    if isinstance(settings_result, Err):
        raise RuntimeError(f"config error: {settings_result.error}")
    built = build_container(settings_result.value)
    if isinstance(built, Err):
        raise RuntimeError(f"container error: {built.error}")
    return built.value


class RegisterRepoRequest(BaseModel):
    url: str
    owner: str


class FireIncidentRequest(BaseModel):
    repo_id: str


class ChooseStrategyRequest(BaseModel):
    strategy: StrategyKind


class DiscussRequest(BaseModel):
    kind: str = "issue"  # "issue" | "discussion"


class FileDecisionIn(BaseModel):
    path: str
    kind: str
    reason: str | None = None


class ReviewRequest(BaseModel):
    decision: str
    per_file: list[FileDecisionIn]
    reason: str | None = None


def create_app(container: Container) -> FastAPI:
    app = FastAPI(title="DepCover")
    pipeline_tasks: set[asyncio.Task[Any]] = set()
    user_dep = require_user(container)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "use_fakes": container.settings.use_fakes}

    @app.get("/config")
    def config() -> dict[str, Any]:
        s = container.settings
        host = s.butterbase_base_url
        app_id = s.butterbase_app_id
        live = (
            not s.use_fakes
            and host is not None
            and app_id is not None
            and "REPLACE" not in host
            and "REPLACE" not in app_id
        )
        return {
            "auth_required": bool(live),
            "butterbase_host": host if live else None,
            "app_id": app_id if live else None,
        }

    assets = _FRONTEND / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        built = _FRONTEND / "index.html"
        return FileResponse(built if built.is_file() else _STATIC / "index.html")

    @app.get("/legacy")
    def legacy() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    @app.post("/repos")
    def register_repo(
        body: RegisterRepoRequest, user: AuthenticatedUser = Depends(user_dep)
    ) -> JSONResponse:
        repo = Repo(
            id=container.ids.new_id("repo"),
            url=body.url,
            owner=body.owner,
            registered_at=container.clock.now(),
        )
        scan = container.ingestion.scan(repo, TARGET_PACKAGE)
        if isinstance(scan, Err):
            raise http_error(scan.error)
        surgery_plan, layout, centrality, warnings = scan.value
        advisories = _lookup_advisories(container, surgery_plan)
        underwriting = container.underwriter.run(
            repo, surgery_plan, centrality, layout, warnings, advisories
        )
        if isinstance(underwriting, Err):
            raise http_error(underwriting.error)
        return JSONResponse(
            {
                "repo": repo.model_dump(mode="json"),
                "surgery_plan": surgery_plan.model_dump(mode="json"),
                "graph_layout": layout.model_dump(mode="json"),
                "underwriting": underwriting.value.model_dump(mode="json"),
            }
        )

    @app.post("/incidents")
    def fire_incident(
        body: FireIncidentRequest, user: AuthenticatedUser = Depends(user_dep)
    ) -> JSONResponse:
        repo = container.store.get_repo(body.repo_id)
        if isinstance(repo, Err):
            raise http_error(repo.error)
        access = container.github.permission(repo.value.url, user.id)
        if isinstance(access, Err):
            raise http_error(access.error)
        if access.value is RepoAccess.NONE:
            raise http_error(
                RepoAccessError(
                    "You don't have access to this repository on GitHub",
                    {"repo": repo.value.url},
                )
            )
        now = container.clock.now()
        incident = Incident(
            id=container.ids.new_id("incident"),
            repo_id=body.repo_id,
            trigger_type=TriggerType.MOCK_CVE,
            chosen_strategy=None,
            status=IncidentStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        created = container.store.create_incident(incident)
        if isinstance(created, Err):
            raise http_error(created.error)
        underwriting = container.store.get_underwriting(body.repo_id)
        if isinstance(underwriting, Err):
            raise http_error(underwriting.error)
        report = underwriting.value
        options = container.mitigation.options(incident.id, report, _cve_summary(report))
        if isinstance(options, Err):
            raise http_error(options.error)
        options_value = _with_real_blast_radius(options.value, report.affected_file_count)
        return JSONResponse(
            {
                "incident": created.value.model_dump(mode="json"),
                "options": options_value.model_dump(mode="json"),
            }
        )

    @app.post("/incidents/{incident_id}/strategy")
    async def choose_strategy(
        incident_id: str,
        body: ChooseStrategyRequest,
        user: AuthenticatedUser = Depends(user_dep),
    ) -> JSONResponse:
        loaded = container.store.get_incident(incident_id)
        if isinstance(loaded, Err):
            raise http_error(loaded.error)
        incident = loaded.value
        chosen = incident.model_copy(update={"chosen_strategy": body.strategy})
        if body.strategy is StrategyKind.UPGRADE:
            return _run_upgrade(container, incident, chosen)
        if body.strategy is not StrategyKind.TRANSPLANT:
            terminal = transition(chosen, IncidentStatus.COMPLETED, container.clock.now())
            if isinstance(terminal, Err):
                raise http_error(terminal.error)
            saved = container.store.update_incident(terminal.value, incident.status)
            if isinstance(saved, Err):
                raise http_error(saved.error)
            return JSONResponse(saved.value.model_dump(mode="json"))

        saved = container.store.update_incident(chosen, incident.status)
        if isinstance(saved, Err):
            raise http_error(saved.error)
        repo = container.store.get_repo(incident.repo_id)
        if isinstance(repo, Err):
            raise http_error(repo.error)
        scan = container.ingestion.scan(repo.value, TARGET_PACKAGE)
        if isinstance(scan, Err):
            raise http_error(scan.error)
        surgery_plan, _layout, _centrality, _warnings = scan.value
        files = container.repos_provider.fetch(repo.value.url)
        if isinstance(files, Err):
            raise http_error(files.error)
        by_path: dict[str, FileContent] = {f.path: f for f in files.value}
        affected = tuple(by_path[p] for p in surgery_plan.affected_files if p in by_path)
        task = asyncio.create_task(
            container.orchestrator.run(saved.value, surgery_plan, affected, container.golden)
        )
        pipeline_tasks.add(task)
        task.add_done_callback(pipeline_tasks.discard)
        return JSONResponse(saved.value.model_dump(mode="json"))

    @app.post("/incidents/{incident_id}/explore")
    def explore_strategy(
        incident_id: str,
        body: ChooseStrategyRequest,
        user: AuthenticatedUser = Depends(user_dep),
    ) -> JSONResponse:
        loaded = container.store.get_incident(incident_id)
        if isinstance(loaded, Err):
            raise http_error(loaded.error)
        incident = loaded.value
        repo = container.store.get_repo(incident.repo_id)
        if isinstance(repo, Err):
            raise http_error(repo.error)
        scan = container.ingestion.scan(repo.value, TARGET_PACKAGE)
        if isinstance(scan, Err):
            raise http_error(scan.error)
        surgery_plan, _layout, _centrality, _warnings = scan.value
        files = container.repos_provider.fetch(repo.value.url)
        if isinstance(files, Err):
            raise http_error(files.error)
        underwriting = container.store.get_underwriting(incident.repo_id)
        advisories = underwriting.value.advisories if isinstance(underwriting, Ok) else ()
        plan = container.explore.plan(
            incident_id=incident_id,
            strategy=body.strategy,
            repo_url=repo.value.url,
            surgery_plan=surgery_plan,
            advisories=advisories,
            files=files.value,
        )
        if isinstance(plan, Err):
            raise http_error(plan.error)
        return JSONResponse(plan.value.model_dump(mode="json"))

    @app.post("/incidents/{incident_id}/discuss")
    def discuss(
        incident_id: str, req: DiscussRequest, user: AuthenticatedUser = Depends(user_dep)
    ) -> JSONResponse:
        loaded = container.store.get_incident(incident_id)
        if isinstance(loaded, Err):
            raise http_error(loaded.error)
        incident = loaded.value
        repo = container.store.get_repo(incident.repo_id)
        if isinstance(repo, Err):
            raise http_error(repo.error)
        access = container.github.permission(repo.value.url, user.id)
        if isinstance(access, Err):
            raise http_error(access.error)
        if access.value is RepoAccess.NONE:
            raise http_error(
                RepoAccessError(
                    "You don't have access to this repository on GitHub",
                    {"repo": repo.value.url},
                )
            )
        underwriting = container.store.get_underwriting(incident.repo_id)
        if isinstance(underwriting, Err):
            raise http_error(underwriting.error)
        title, issue_body = _discussion_issue(underwriting.value)
        if req.kind == "discussion":
            base = repo.value.url.rstrip("/")
            if base.endswith(".git"):
                base = base[: -len(".git")]
            url = f"{base}/discussions/new?title={quote(title)}&body={quote(issue_body)}"
            return JSONResponse({"kind": "discussion", "number": None, "url": url})
        issue = container.github.open_issue(repo.value.url, title, issue_body, user.id)
        if isinstance(issue, Err):
            raise http_error(issue.error)
        return JSONResponse(
            {"kind": "issue", "number": issue.value.number, "url": issue.value.url}
        )

    @app.get("/incidents/{incident_id}/stream")
    async def stream(incident_id: str) -> EventSourceResponse:
        async def generator() -> AsyncIterator[dict[str, str]]:
            seen: set[int] = set()
            replay = container.events.replay(incident_id)
            if isinstance(replay, Ok):
                for event in replay.value:
                    seen.add(event.seq)
                    yield {"data": event.model_dump_json()}
                    if event.terminal:
                        return
            async for event in container.events.subscribe(incident_id):
                if event.seq in seen:
                    continue
                yield {"data": event.model_dump_json()}
                if event.terminal:
                    return

        return EventSourceResponse(generator())

    @app.get("/transplants/{transplant_id}")
    def get_transplant(
        transplant_id: str, user: AuthenticatedUser = Depends(user_dep)
    ) -> JSONResponse:
        result = container.store.get_transplant(transplant_id)
        if isinstance(result, Err):
            raise http_error(result.error)
        return JSONResponse(result.value.model_dump(mode="json"))

    @app.post("/transplants/{transplant_id}/review")
    def submit_review(
        transplant_id: str,
        body: ReviewRequest,
        user: AuthenticatedUser = Depends(user_dep),
    ) -> JSONResponse:
        loaded = container.store.get_transplant(transplant_id)
        if isinstance(loaded, Err):
            raise http_error(loaded.error)
        transplant: Transplant = loaded.value
        decision = _parse_decision(body.decision)
        per_file = tuple(
            FileDecision(path=d.path, kind=_parse_file_kind(d.kind), reason=d.reason)
            for d in body.per_file
        )
        submitted = container.review.submit(user, transplant, decision, per_file)
        if isinstance(submitted, Err):
            raise http_error(submitted.error)
        review, status = submitted.value
        pull_request: dict[str, Any] | None = None
        if status is IncidentStatus.COMPLETED:
            incident = container.store.get_incident(transplant.incident_id)
            if isinstance(incident, Ok):
                repo = container.store.get_repo(incident.value.repo_id)
                if isinstance(repo, Ok):
                    opened = container.pr.open_for(
                        repo.value, transplant, review, acting_user_id=user.id
                    )
                    if isinstance(opened, Ok):
                        pull_request = opened.value.model_dump(mode="json")
        return JSONResponse(
            {
                "review": review.model_dump(mode="json"),
                "status": status.value,
                "pull_request": pull_request,
            }
        )

    return app


def _parse_decision(raw: str) -> ReviewDecision:
    return ReviewDecision(raw)


def _parse_file_kind(raw: str) -> FileDecisionKind:
    return FileDecisionKind(raw)


container_instance = _bootstrap_container()
app = create_app(container_instance)


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"code": "internal_error", "message": str(exc)})
