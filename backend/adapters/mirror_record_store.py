from collections.abc import Callable, Sequence

from backend.domain.enums import IncidentStatus
from backend.domain.errors import Ok, RecordStoreError, Result
from backend.domain.models import (
    Incident,
    JudgeVerdict,
    Recipe,
    Repo,
    Review,
    Transplant,
    UnderwritingReport,
)
from backend.ports.record_store import RecordStore


class MirroringRecordStore(RecordStore):
    """Keeps ``primary`` (in-memory) authoritative for all reads and returned values, while
    best-effort mirroring every successful write to ``mirror`` (Butterbase Postgres) so real
    records land in the database. A mirror failure is swallowed — the pipeline is never affected.
    """

    def __init__(self, primary: RecordStore, mirror: RecordStore) -> None:
        self._primary = primary
        self._mirror = mirror

    def _also(self, call: Callable[[RecordStore], object]) -> None:
        try:
            call(self._mirror)
        except Exception:  # noqa: BLE001 — best-effort; the primary is the source of truth
            pass

    # --- writes: primary is authoritative; mirror only when it succeeded ---

    def create_repo(self, repo: Repo) -> Result[Repo, RecordStoreError]:
        result = self._primary.create_repo(repo)
        if isinstance(result, Ok):
            self._also(lambda m: m.create_repo(repo))
        return result

    def save_underwriting(
        self, report: UnderwritingReport
    ) -> Result[UnderwritingReport, RecordStoreError]:
        result = self._primary.save_underwriting(report)
        if isinstance(result, Ok):
            self._also(lambda m: m.save_underwriting(report))
        return result

    def create_incident(self, incident: Incident) -> Result[Incident, RecordStoreError]:
        result = self._primary.create_incident(incident)
        if isinstance(result, Ok):
            self._also(lambda m: m.create_incident(incident))
        return result

    def update_incident(
        self, incident: Incident, expected_status: IncidentStatus
    ) -> Result[Incident, RecordStoreError]:
        result = self._primary.update_incident(incident, expected_status)
        if isinstance(result, Ok):
            self._also(lambda m: m.update_incident(incident, expected_status))
        return result

    def save_transplant(self, transplant: Transplant) -> Result[Transplant, RecordStoreError]:
        result = self._primary.save_transplant(transplant)
        if isinstance(result, Ok):
            self._also(lambda m: m.save_transplant(transplant))
        return result

    def save_verdicts(self, verdicts: Sequence[JudgeVerdict]) -> Result[None, RecordStoreError]:
        result = self._primary.save_verdicts(verdicts)
        if isinstance(result, Ok):
            self._also(lambda m: m.save_verdicts(verdicts))
        return result

    def save_review(self, review: Review) -> Result[Review, RecordStoreError]:
        result = self._primary.save_review(review)
        if isinstance(result, Ok):
            self._also(lambda m: m.save_review(review))
        return result

    def upsert_recipe(self, recipe: Recipe) -> Result[Recipe, RecordStoreError]:
        result = self._primary.upsert_recipe(recipe)
        if isinstance(result, Ok):
            self._also(lambda m: m.upsert_recipe(recipe))
        return result

    # --- reads: always from the authoritative in-memory store ---

    def get_repo(self, repo_id: str) -> Result[Repo, RecordStoreError]:
        return self._primary.get_repo(repo_id)

    def get_underwriting(self, repo_id: str) -> Result[UnderwritingReport, RecordStoreError]:
        return self._primary.get_underwriting(repo_id)

    def get_incident(self, incident_id: str) -> Result[Incident, RecordStoreError]:
        return self._primary.get_incident(incident_id)

    def get_transplant(self, transplant_id: str) -> Result[Transplant, RecordStoreError]:
        return self._primary.get_transplant(transplant_id)

    def find_recipe(self, library_pair: str) -> Result[Recipe | None, RecordStoreError]:
        return self._primary.find_recipe(library_pair)


__all__ = ("MirroringRecordStore",)
