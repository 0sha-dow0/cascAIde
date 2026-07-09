import pytest

import backend.adapters.live.live_advisory as live_advisory
from backend.adapters.live.live_advisory import (
    GitHubAdvisoryClient,
    _parse_advisory,
    _version_in_range,
)
from backend.domain.errors import Err, Ok


def test_version_in_range_and_or_bounds() -> None:
    assert _version_in_range("0.21.1", "< 0.21.2")
    assert not _version_in_range("0.21.1", ">= 1.0.0, < 1.16.0")
    assert _version_in_range("0.21.1", ">= 0.8.1, < 1.6.0")
    assert _version_in_range("0.21.1", "<= 0.31.1")
    assert _version_in_range("1.2.3", "")  # unknown range -> keep (conservative)
    assert not _version_in_range("2.0.0", "< 1.0.0")


def test_parse_advisory_matches_the_named_package() -> None:
    item: dict[str, object] = {
        "ghsa_id": "GHSA-abc",
        "cve_id": "CVE-2021-3749",
        "summary": "ReDoS",
        "severity": "high",
        "cvss": {"score": 7.5, "vector_string": "CVSS:3.1/AV:N"},
        "vulnerabilities": [
            {"package": {"name": "other"}, "vulnerable_version_range": "< 9"},
            {
                "package": {"name": "axios"},
                "vulnerable_version_range": "< 0.21.2",
                "first_patched_version": {"identifier": "0.21.2"},
            },
        ],
        "html_url": "https://example/GHSA-abc",
        "published_at": "2021-08-31T00:00:00Z",
    }
    advisory = _parse_advisory(item, "axios")
    assert advisory is not None
    assert advisory.cve_id == "CVE-2021-3749"
    assert advisory.cvss_score == 7.5
    assert advisory.vulnerable_range == "< 0.21.2"
    assert advisory.first_patched == "0.21.2"
    assert advisory.published_at is not None


def test_parse_advisory_falls_back_to_cvss_severities() -> None:
    item: dict[str, object] = {
        "ghsa_id": "GHSA-x",
        "cve_id": None,
        "summary": "s",
        "severity": "critical",
        "cvss": {"score": None, "vector_string": None},
        "cvss_severities": {"cvss_v3": {"score": 9.1, "vector_string": "vec"}},
        "vulnerabilities": [],
        "html_url": "",
        "published_at": None,
    }
    advisory = _parse_advisory(item, "axios")
    assert advisory is not None
    assert advisory.cvss_score == 9.1
    assert advisory.cve_id is None
    assert advisory.url == "https://github.com/advisories/GHSA-x"


class _FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status_code = status
        self._payload = payload
        self.text = ""

    def json(self) -> object:
        return self._payload


class _FakeClient:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self._status = status

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(self, url: str, headers: object = None, params: object = None) -> _FakeResponse:
        return _FakeResponse(self._status, self._payload)


def _vuln(name: str, version_range: str) -> dict[str, object]:
    return {"package": {"name": name}, "vulnerable_version_range": version_range}


def _item(ghsa: str, cve: str, cvss: float, version_range: str) -> dict[str, object]:
    return {
        "ghsa_id": ghsa,
        "cve_id": cve,
        "summary": "s",
        "severity": "high",
        "cvss": {"score": cvss, "vector_string": "v"},
        "vulnerabilities": [_vuln("axios", version_range)],
        "html_url": f"https://example/{ghsa}",
        "published_at": None,
    }


def test_lookup_filters_by_version_and_sorts_by_cvss(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        _item("G1", "CVE-1", 7.5, "< 0.21.2"),
        _item("G2", "CVE-2", 9.0, "<= 0.31.1"),
        _item("G3", "CVE-3", 8.0, ">= 1.0.0, < 1.16.0"),
    ]
    monkeypatch.setattr(live_advisory.httpx, "Client", lambda timeout=None: _FakeClient(payload))
    result = GitHubAdvisoryClient(None).lookup("npm", "axios", "0.21.1")
    assert isinstance(result, Ok)
    # G3 excluded (1.x range); higher CVSS first.
    assert [a.cve_id for a in result.value] == ["CVE-2", "CVE-1"]


def test_lookup_non_200_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        live_advisory.httpx, "Client", lambda timeout=None: _FakeClient([], status=403)
    )
    result = GitHubAdvisoryClient(None).lookup("npm", "axios", "0.21.1")
    assert isinstance(result, Err)
    assert result.error.code == "advisory_error"
