import re
from collections.abc import Mapping
from datetime import datetime
from typing import Final

import httpx

from backend.domain.errors import AdvisoryError, Err, Ok, Result
from backend.domain.models import Advisory
from backend.ports.advisory import AdvisoryClient

_API: Final[str] = "https://api.github.com/advisories"
_ACCEPT: Final[str] = "application/vnd.github+json"
_DETAIL_CAP: Final[int] = 200
_SUMMARY_CAP: Final[int] = 400
_PER_PAGE: Final[str] = "40"


class GitHubAdvisoryClient(AdvisoryClient):
    """Reads the GitHub Advisory Database (GHSA) for advisories affecting an installed version.

    Works unauthenticated (60 req/hr); pass a token to lift the limit to 5000/hr.
    """

    def __init__(self, token: str | None, timeout_s: float = 20.0) -> None:
        self._headers = {"Accept": _ACCEPT, "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._timeout_s = timeout_s

    def lookup(
        self, ecosystem: str, name: str, version: str | None
    ) -> Result[tuple[Advisory, ...], AdvisoryError]:
        affects = f"{name}@{version}" if version else name
        params = {
            "ecosystem": ecosystem,
            "affects": affects,
            "type": "reviewed",
            "per_page": _PER_PAGE,
        }
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                response = client.get(_API, headers=self._headers, params=params)
        except httpx.HTTPError as error:
            return Err(AdvisoryError("advisory request failed", {"detail": str(error)[:_DETAIL_CAP]}))
        if response.status_code != 200:
            return Err(
                AdvisoryError(
                    "advisory lookup returned non-200",
                    {"status": str(response.status_code), "body": response.text[:_DETAIL_CAP]},
                )
            )
        try:
            payload = response.json()
        except ValueError:
            return Err(AdvisoryError("advisory response was not JSON", {}))
        if not isinstance(payload, list):
            return Err(AdvisoryError("advisory response was not a list", {}))
        parsed = [advisory for advisory in (_parse_advisory(item, name) for item in payload) if advisory]
        if version:
            # GitHub's `affects=name@version` filters by package, not version, so it
            # returns advisories for unrelated version lines. Keep only the ones whose
            # vulnerable range actually covers the installed version.
            parsed = [a for a in parsed if _version_in_range(version, a.vulnerable_range)]
        parsed.sort(key=lambda advisory: advisory.cvss_score, reverse=True)
        return Ok(tuple(parsed))


_COMPARATOR_RE: Final = re.compile(r"^\s*(<=|>=|<|>|==|=)?\s*v?([0-9][0-9A-Za-z.\-+]*)\s*$")


def _version_tuple(raw: str) -> tuple[int, ...]:
    core = raw.split("-", 1)[0].split("+", 1)[0]
    parts: list[int] = []
    for segment in core.split("."):
        digits = ""
        for char in segment:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def _compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    for index in range(max(len(left), len(right))):
        lhs = left[index] if index < len(left) else 0
        rhs = right[index] if index < len(right) else 0
        if lhs != rhs:
            return -1 if lhs < rhs else 1
    return 0


def _satisfies(version: str, comparator: str) -> bool:
    match = _COMPARATOR_RE.match(comparator)
    if not match:
        return True
    op = match.group(1) or "="
    order = _compare(_version_tuple(version), _version_tuple(match.group(2)))
    if op == "<":
        return order < 0
    if op == "<=":
        return order <= 0
    if op == ">":
        return order > 0
    if op == ">=":
        return order >= 0
    return order == 0


def _version_in_range(version: str, vulnerable_range: str) -> bool:
    if not vulnerable_range:
        return True
    comparators = [part.strip() for part in vulnerable_range.split(",") if part.strip()]
    if not comparators:
        return True
    return all(_satisfies(version, comparator) for comparator in comparators)


def _parse_advisory(item: object, package_name: str) -> Advisory | None:
    if not isinstance(item, dict):
        return None
    ghsa = item.get("ghsa_id")
    if not isinstance(ghsa, str) or not ghsa:
        return None
    vuln = _match_vulnerability(item.get("vulnerabilities"), package_name)
    cvss_score, cvss_vector = _cvss(item)
    cve_id = item.get("cve_id")
    summary = item.get("summary")
    severity = item.get("severity")
    html_url = item.get("html_url")
    return Advisory(
        ghsa_id=ghsa,
        cve_id=cve_id if isinstance(cve_id, str) and cve_id else None,
        summary=(str(summary) if summary else ghsa)[:_SUMMARY_CAP],
        severity=str(severity) if severity else "unknown",
        cvss_score=cvss_score,
        cvss_vector=cvss_vector,
        vulnerable_range=_string(vuln.get("vulnerable_version_range")) if vuln else "",
        first_patched=_first_patched(vuln),
        url=str(html_url) if html_url else f"https://github.com/advisories/{ghsa}",
        published_at=_parse_datetime(item.get("published_at")),
    )


def _match_vulnerability(
    vulnerabilities: object, package_name: str
) -> dict[str, object] | None:
    if not isinstance(vulnerabilities, list):
        return None
    fallback: dict[str, object] | None = None
    for entry in vulnerabilities:
        if not isinstance(entry, dict):
            continue
        if fallback is None:
            fallback = entry
        package = entry.get("package")
        if isinstance(package, dict) and package.get("name") == package_name:
            return entry
    return fallback


def _cvss(item: Mapping[str, object]) -> tuple[float, str | None]:
    cvss = item.get("cvss")
    if isinstance(cvss, dict):
        score = cvss.get("score")
        vector = cvss.get("vector_string")
        if isinstance(score, (int, float)) and score:
            return float(score), vector if isinstance(vector, str) else None
    severities = item.get("cvss_severities")
    if isinstance(severities, dict):
        for key in ("cvss_v4", "cvss_v3"):
            entry = severities.get(key)
            if isinstance(entry, dict) and isinstance(entry.get("score"), (int, float)) and entry.get("score"):
                vector = entry.get("vector_string")
                return float(entry["score"]), vector if isinstance(vector, str) else None
    return 0.0, None


def _first_patched(vuln: Mapping[str, object] | None) -> str | None:
    if not vuln:
        return None
    patched = vuln.get("first_patched_version")
    if isinstance(patched, str) and patched:
        return patched
    if isinstance(patched, dict):
        identifier = patched.get("identifier")
        return identifier if isinstance(identifier, str) and identifier else None
    return None


def _string(value: object) -> str:
    return str(value) if value else ""


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


__all__ = ("GitHubAdvisoryClient",)
