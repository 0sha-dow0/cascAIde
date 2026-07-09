from backend.domain.models import Advisory
from backend.services.cve_scoring import compute_priority


def _advisory(cvss: float) -> Advisory:
    return Advisory(
        ghsa_id="GHSA-x",
        cve_id="CVE-x",
        summary="summary",
        severity="high",
        cvss_score=cvss,
        cvss_vector=None,
        vulnerable_range="< 1.0.0",
        first_patched="1.0.0",
        url="https://example/advisory",
        published_at=None,
    )


def test_no_advisories_is_zero_and_none_band() -> None:
    assert compute_priority([], 0.9) == (0.0, "none")


def test_uses_max_cvss_across_advisories() -> None:
    # max cvss 9.8 -> (9.8/10)*0.6 = 0.588 -> 58.8
    score, band = compute_priority([_advisory(4.0), _advisory(9.8)], 0.0)
    assert score == 58.8
    assert band == "high"


def test_blends_centrality() -> None:
    # cvss 7.5 -> 0.45 ; centrality 0.67 -> 0.268 ; sum 0.718 -> 71.8
    score, band = compute_priority([_advisory(7.5)], 0.67)
    assert score == 71.8
    assert band == "high"


def test_critical_band_when_severe_and_central() -> None:
    score, band = compute_priority([_advisory(9.8)], 1.0)
    assert score == 98.8
    assert band == "critical"


def test_medium_band() -> None:
    # cvss 5.0 -> 0.30 ; centrality 0.0 -> 30.0
    score, band = compute_priority([_advisory(5.0)], 0.0)
    assert score == 30.0
    assert band == "medium"


def test_low_band_and_capped_at_100() -> None:
    assert compute_priority([_advisory(1.0)], 0.1) == (10.0, "low")
    score, _ = compute_priority([_advisory(10.0)], 1.0)
    assert score == 100.0
