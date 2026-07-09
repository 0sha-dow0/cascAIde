"""Composite CVE priority = how-bad (CVSS severity) x how-wired-in (graph centrality).

The score blends the highest CVSS score across matching advisories (60%) with the
target package's normalized degree centrality (40%), scaled to 0-100. With no known
advisory there is nothing to prioritize, so the score is 0 and the band is "none".
"""

from collections.abc import Sequence
from typing import Final

from backend.domain.models import Advisory

_CVSS_WEIGHT: Final[float] = 0.6
_CENTRALITY_WEIGHT: Final[float] = 0.4

_BAND_CRITICAL: Final[float] = 75.0
_BAND_HIGH: Final[float] = 50.0
_BAND_MEDIUM: Final[float] = 25.0

_BAND_NONE: Final[str] = "none"


def _band(score: float) -> str:
    if score >= _BAND_CRITICAL:
        return "critical"
    if score >= _BAND_HIGH:
        return "high"
    if score >= _BAND_MEDIUM:
        return "medium"
    return "low"


def compute_priority(
    advisories: Sequence[Advisory], centrality: float
) -> tuple[float, str]:
    """Return (score 0-100, band). No advisories -> (0.0, "none")."""
    if not advisories:
        return 0.0, _BAND_NONE
    max_cvss = max(advisory.cvss_score for advisory in advisories)
    blended = (max_cvss / 10.0) * _CVSS_WEIGHT + centrality * _CENTRALITY_WEIGHT
    score = round(max(0.0, min(1.0, blended)) * 100.0, 1)
    return score, _band(score)


__all__ = ("compute_priority",)
