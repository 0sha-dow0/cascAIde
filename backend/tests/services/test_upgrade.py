from backend.domain.enums import SandboxOutcome
from backend.domain.errors import Err, Ok
from backend.domain.models import Advisory, FileContent
from backend.services.upgrade import plan_upgrade


def _adv(cve: str, first_patched: str | None, cvss: float = 7.5) -> Advisory:
    return Advisory(
        ghsa_id="GHSA-x",
        cve_id=cve,
        summary="s",
        severity="high",
        cvss_score=cvss,
        cvss_vector=None,
        vulnerable_range="< 1",
        first_patched=first_patched,
        url="https://example/advisory",
        published_at=None,
    )


_MANIFEST = FileContent(
    path="package.json",
    text=(
        '{\n  "name": "victim",\n  "dependencies": {\n'
        '    "axios": "^0.21.1",\n    "express": "^4.18.0"\n  }\n}\n'
    ),
)


def test_bump_to_max_first_patched_preserves_operator() -> None:
    advisories = (_adv("CVE-2021-3749", "0.21.2"), _adv("CVE-2026-44492", "0.32.0", 8.6))
    result = plan_upgrade("incident-1", "axios", _MANIFEST, advisories, "0.21.1")
    assert isinstance(result, Ok)
    transplant = result.value
    assert transplant.id == "transplant-incident-1"
    after = transplant.diff[0].after
    assert transplant.diff[0].path == "package.json"
    assert '"axios": "^0.32.0"' in after  # max first_patched, caret preserved
    assert '"axios": "^0.21.1"' not in after
    assert '"express": "^4.18.0"' in after  # untouched
    assert transplant.consensus.approved is True
    assert transplant.consensus.panel_size == 2
    assert transplant.consensus.verdicts == ()
    assert transplant.evidence.build.outcome is SandboxOutcome.PASSED


def test_no_first_patched_is_err() -> None:
    result = plan_upgrade("incident-1", "axios", _MANIFEST, (_adv("CVE-x", None),), "0.21.1")
    assert isinstance(result, Err)


def test_already_patched_is_err() -> None:
    result = plan_upgrade("incident-1", "axios", _MANIFEST, (_adv("CVE-x", "0.21.2"),), "0.32.0")
    assert isinstance(result, Err)


def test_missing_package_is_err() -> None:
    manifest = FileContent(path="package.json", text='{"dependencies": {"express": "^4.18.0"}}')
    result = plan_upgrade("incident-1", "axios", manifest, (_adv("CVE-x", "0.32.0"),), "0.21.1")
    assert isinstance(result, Err)


def test_bump_without_operator() -> None:
    manifest = FileContent(path="package.json", text='{"dependencies": {"axios": "0.21.1"}}')
    result = plan_upgrade("incident-1", "axios", manifest, (_adv("CVE-x", "0.32.0"),), "0.21.1")
    assert isinstance(result, Ok)
    assert '"axios": "0.32.0"' in result.value.diff[0].after
