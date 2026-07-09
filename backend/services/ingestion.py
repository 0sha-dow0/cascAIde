from collections.abc import Sequence

from backend.domain.determinism import Clock, IdGenerator
from backend.domain.errors import DepCoverError, Err, Ok, Result
from backend.domain.models import (
    CentralityScore,
    GraphLayout,
    LockfileWarning,
    Repo,
    SurgeryPlan,
)
from backend.ports.record_store import RecordStore
from backend.ports.repo_content import RepoContentProvider
from backend.services.call_site_scanner import scan_call_sites
from backend.services.graph_builder import GraphBuilder
from backend.services.manifest_parser import DependencyEntry, parse_manifest

type ScanOutcome = tuple[
    SurgeryPlan,
    GraphLayout,
    tuple[CentralityScore, ...],
    tuple[LockfileWarning, ...],
]

_SPEC_OPERATORS: str = "^~>=<v "


def _clean_spec(version_spec: str) -> str | None:
    tokens = version_spec.strip().split()
    if not tokens:
        return None
    cleaned = tokens[0].lstrip(_SPEC_OPERATORS).strip()
    return cleaned or None


def _target_version(
    dependencies: Sequence[DependencyEntry], target_package: str
) -> str | None:
    for dependency in dependencies:
        if dependency.name == target_package:
            return dependency.resolved or _clean_spec(dependency.version_spec)
    return None


class IngestionService:
    def __init__(
        self,
        repos: RepoContentProvider,
        builder: GraphBuilder,
        store: RecordStore,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._repos = repos
        self._builder = builder
        self._store = store
        self._clock = clock
        self._ids = ids

    def scan(
        self, repo: Repo, target_package: str
    ) -> Result[ScanOutcome, DepCoverError]:
        fetched = self._repos.fetch(repo.url)
        if isinstance(fetched, Err):
            return Err(fetched.error)
        files = fetched.value

        manifest = self._repos.read_manifest(repo.url)
        if isinstance(manifest, Err):
            return Err(manifest.error)

        lockfile = self._repos.read_lockfile(repo.url)
        if isinstance(lockfile, Err):
            return Err(lockfile.error)

        parsed = parse_manifest(manifest.value, lockfile.value)
        if isinstance(parsed, Err):
            return Err(parsed.error)

        call_sites = scan_call_sites(files, target_package)
        if isinstance(call_sites, Err):
            return Err(call_sites.error)

        built = self._builder.build(files, call_sites.value, target_package)
        if isinstance(built, Err):
            return Err(built.error)
        surgery_plan, centrality, layout = built.value
        surgery_plan = surgery_plan.model_copy(
            update={
                "target_version": _target_version(
                    parsed.value.dependencies, target_package
                )
            }
        )

        persisted = self._store.create_repo(repo)
        if isinstance(persisted, Err):
            return Err(persisted.error)

        return Ok((surgery_plan, layout, centrality, parsed.value.warnings))


__all__ = ("IngestionService", "ScanOutcome")
