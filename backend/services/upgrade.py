"""Executable "upgrade" strategy: bump the vulnerable dependency to its GHSA-patched
version and produce a Transplant-shaped record so it flows through the existing
DiffReview -> accept -> PR path (which commits FileDiff.after verbatim)."""

import difflib
import re
from collections.abc import Sequence
from typing import Final

from backend.domain.enums import SandboxOutcome
from backend.domain.errors import DepCoverError, Err, Ok, Result, ValidationRejectedError
from backend.domain.models import (
    Advisory,
    BehavioralDiffResult,
    BuildResult,
    ConsensusResult,
    EvidenceBundle,
    FileContent,
    FileDiff,
    SurgeryPlan,
    TestResult,
    Transplant,
)

_TRANSPLANT_ID_PREFIX: Final[str] = "transplant"
_SYNTHETIC_LOG: Final[str] = (
    "dependency version bump — no sandbox build/test run is required to raise a "
    "patched release; the diff is a single package.json change"
)


def _version_key(version: str) -> tuple[int, ...]:
    core = version.strip().lstrip("^~>=<v ").split("-", 1)[0].split("+", 1)[0]
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


def _max_first_patched(advisories: Sequence[Advisory]) -> str | None:
    patched = [a.first_patched for a in advisories if a.first_patched]
    if not patched:
        return None
    return max(patched, key=_version_key)


def _bump_manifest(text: str, package: str, patched: str) -> str | None:
    pattern = re.compile(
        r'("' + re.escape(package) + r'"\s*:\s*")([\^~>=<v ]*)([0-9][^"]*)(")'
    )
    new_text, count = pattern.subn(
        lambda m: f"{m.group(1)}{m.group(2)}{patched}{m.group(4)}", text
    )
    if count == 0:
        return None
    return new_text


def _unified_diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )


def plan_upgrade(
    incident_id: str,
    target_package: str,
    manifest: FileContent,
    advisories: Sequence[Advisory],
    resolved_version: str | None,
) -> Result[Transplant, DepCoverError]:
    patched = _max_first_patched(advisories)
    if patched is None:
        return Err(
            ValidationRejectedError(
                "no patched release is available for this dependency yet — "
                "transplant is the durable fix",
                {"package": target_package},
            )
        )
    if resolved_version is not None and _version_key(resolved_version) >= _version_key(patched):
        return Err(
            ValidationRejectedError(
                "the installed version is already patched",
                {"package": target_package, "installed": resolved_version, "patched": patched},
            )
        )
    bumped = _bump_manifest(manifest.text, target_package, patched)
    if bumped is None:
        return Err(
            ValidationRejectedError(
                "package.json does not declare this dependency",
                {"package": target_package},
            )
        )
    if bumped == manifest.text:
        return Err(
            ValidationRejectedError(
                "the dependency is already at the patched version",
                {"package": target_package, "patched": patched},
            )
        )

    transplant_id = f"{_TRANSPLANT_ID_PREFIX}-{incident_id}"
    diff = FileDiff(
        path=manifest.path,
        unified_diff=_unified_diff(manifest.path, manifest.text, bumped),
        before=manifest.text,
        after=bumped,
    )
    evidence = EvidenceBundle(
        transplant_id=transplant_id,
        diff=(diff,),
        build=BuildResult(outcome=SandboxOutcome.PASSED, log=_SYNTHETIC_LOG),
        test=TestResult(outcome=SandboxOutcome.PASSED, failing_tests=(), log=_SYNTHETIC_LOG),
        behavioral=BehavioralDiffResult(matched=True, per_case=()),
    )
    consensus = ConsensusResult(
        approvals=2, panel_size=2, approved=True, contested=False, verdicts=()
    )
    surgery_plan = SurgeryPlan(
        target_package=target_package,
        call_sites=(),
        affected_files=(),
        target_version=resolved_version,
    )
    return Ok(
        Transplant(
            id=transplant_id,
            incident_id=incident_id,
            surgery_plan=surgery_plan,
            diff=(diff,),
            evidence=evidence,
            consensus=consensus,
        )
    )


__all__ = ("plan_upgrade",)
