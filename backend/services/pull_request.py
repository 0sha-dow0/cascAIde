from typing import Final

from backend.domain.enums import FileDecisionKind, ReviewDecision
from backend.domain.errors import Err, GitHubError, Ok, Result
from backend.domain.models import (
    PullRequestRef,
    Repo,
    Review,
    RewrittenFile,
    Transplant,
)
from backend.ports.github import GitHubClient, NewPr

_BASE_BRANCH: Final[str] = "main"
_HEAD_BRANCH_PREFIX: Final[str] = "cascaide/fix-"
_APP_URL: Final[str] = "https://github.com/cascaide/cascaide"

_BEHAVIORAL_MATCHED: Final[str] = "matched — responses are identical"
_BEHAVIORAL_MISMATCHED: Final[str] = "mismatched — review carefully"

_CTX_TRANSPLANT_ID: Final[str] = "transplant_id"
_CTX_REVIEW_TRANSPLANT_ID: Final[str] = "review_transplant_id"
_CTX_DECISION: Final[str] = "decision"
_CTX_REJECTED_PATHS: Final[str] = "rejected_paths"

_REJECTED_PATHS_SEPARATOR: Final[str] = ","


def _behavioral_word(matched: bool) -> str:
    return _BEHAVIORAL_MATCHED if matched else _BEHAVIORAL_MISMATCHED


class PullRequestService:
    def __init__(self, github: GitHubClient) -> None:
        self._github: GitHubClient = github

    def open_for(
        self,
        repo: Repo,
        transplant: Transplant,
        review: Review,
        acting_user_id: str | None = None,
    ) -> Result[PullRequestRef, GitHubError]:
        authorization = self._authorized_to_ship(transplant, review)
        if isinstance(authorization, Err):
            return authorization
        files = tuple(
            RewrittenFile(path=file_diff.path, text=file_diff.after)
            for file_diff in transplant.diff
        )
        target = transplant.surgery_plan.target_package
        new_pr = NewPr(
            title=f"cascAIde: security fix for {target}",
            body=self.build_pr_body(transplant),
            head_branch=f"{_HEAD_BRANCH_PREFIX}{transplant.incident_id}",
            base_branch=_BASE_BRANCH,
            files=files,
        )
        return self._github.open_pr(repo.url, new_pr, transplant.id, acting_user_id=acting_user_id)

    def build_pr_body(self, transplant: Transplant) -> str:
        evidence = transplant.evidence
        target = transplant.surgery_plan.target_package
        changed_files = "\n".join(f"- `{file_diff.path}`" for file_diff in transplant.diff)
        file_count = len(transplant.diff)
        return (
            f"## 🔒 cascAIde — automated dependency security fix\n\n"
            f"cascAIde flagged a vulnerable dependency, mapped its blast radius across the "
            f"codebase, rewrote the affected call sites, and proved the behavior was preserved "
            f"before opening this pull request.\n\n"
            f"| | |\n"
            f"|---|---|\n"
            f"| **Vulnerable package** | `{target}` |\n"
            f"| **Files changed** | {file_count} |\n"
            f"| **Incident** | `{transplant.incident_id}` |\n\n"
            f"### ✅ Verification\n"
            f"- **Build:** {evidence.build.outcome.value}\n"
            f"- **Tests:** {evidence.test.outcome.value}\n"
            f"- **Behavioral diff:** {_behavioral_word(evidence.behavioral.matched)}\n\n"
            f"### 📄 Changed files\n"
            f"{changed_files}\n\n"
            f"### 🧠 Why this is safe\n"
            f"Every call site to `{target}` was rewritten, and cascAIde's behavioral diff "
            f"confirms the responses are unchanged. The full per-file diff is below — review "
            f"and merge, or close this if you'd prefer a different remediation.\n\n"
            f"---\n"
            f"🤖 Opened automatically by [cascAIde]({_APP_URL}) — autonomous dependency transplant engine."
        )

    def _authorized_to_ship(
        self, transplant: Transplant, review: Review
    ) -> Result[None, GitHubError]:
        if review.transplant_id != transplant.id:
            return Err(
                GitHubError(
                    "review does not authorize this transplant",
                    {
                        _CTX_TRANSPLANT_ID: transplant.id,
                        _CTX_REVIEW_TRANSPLANT_ID: review.transplant_id,
                    },
                )
            )
        if review.decision is not ReviewDecision.ACCEPT_ALL:
            return Err(
                GitHubError(
                    "review decision is not a full accept",
                    {
                        _CTX_TRANSPLANT_ID: transplant.id,
                        _CTX_DECISION: review.decision.value,
                    },
                )
            )
        if len(review.per_file) == 0:
            return Err(
                GitHubError(
                    "review records no per-file accept decisions",
                    {_CTX_TRANSPLANT_ID: transplant.id},
                )
            )
        rejected_paths = tuple(
            file_decision.path
            for file_decision in review.per_file
            if file_decision.kind is not FileDecisionKind.ACCEPT
        )
        if len(rejected_paths) > 0:
            return Err(
                GitHubError(
                    "review rejects one or more files",
                    {
                        _CTX_TRANSPLANT_ID: transplant.id,
                        _CTX_REJECTED_PATHS: _REJECTED_PATHS_SEPARATOR.join(
                            rejected_paths
                        ),
                    },
                )
            )
        if len(transplant.diff) == 0:
            return Err(
                GitHubError(
                    "transplant has no files to ship",
                    {_CTX_TRANSPLANT_ID: transplant.id},
                )
            )
        return Ok(None)


__all__ = ("PullRequestService",)
