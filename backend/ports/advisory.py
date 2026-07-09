from typing import Protocol

from backend.domain.errors import AdvisoryError, Result
from backend.domain.models import Advisory


class AdvisoryClient(Protocol):
    """Looks up published security advisories for an installed dependency version."""

    def lookup(
        self, ecosystem: str, name: str, version: str | None
    ) -> Result[tuple[Advisory, ...], AdvisoryError]: ...


__all__ = ("AdvisoryClient",)
