from __future__ import annotations

import base64
from typing import Final

import httpx

from backend.domain.enums import RepoAccess
from backend.domain.errors import (
    Err,
    GitHubError,
    IntegrationNotConnectedError,
    Ok,
    RepoAccessError,
    Result,
)
from backend.domain.models import FileContent, PullRequestRef
from backend.ports.github import GitHubClient, NewPr, PrSummary

__all__ = ("ButterbaseGitHubClient",)

_TIMEOUT_S: Final[float] = 45.0
_NOT_CONNECTED_MARKERS: Final[tuple[str, ...]] = (
    "not_connected",
    "not connected",
    "no connected account",
    "integrations_not_connected",
)

# Composio GitHub tool slugs.
_T_GET_REPO: Final[str] = "GITHUB_GET_A_REPOSITORY"
_T_GET_REF: Final[str] = "GITHUB_GET_A_REFERENCE"
_T_CREATE_REF: Final[str] = "GITHUB_CREATE_A_REFERENCE"
_T_PUT_FILE: Final[str] = "GITHUB_CREATE_OR_UPDATE_FILE_CONTENTS"
_T_CREATE_PR: Final[str] = "GITHUB_CREATE_A_PULL_REQUEST"
_T_CREATE_FORK: Final[str] = "GITHUB_CREATE_A_FORK"
_T_GET_ME: Final[str] = "GITHUB_GET_THE_AUTHENTICATED_USER"
_T_LIST_PRS: Final[str] = "GITHUB_LIST_PULL_REQUESTS"
_T_CREATE_ISSUE: Final[str] = "GITHUB_CREATE_AN_ISSUE"
_T_LIST_ISSUES: Final[str] = "GITHUB_LIST_REPOSITORY_ISSUES"


def _parse_owner_repo(repo_url: str) -> tuple[str, str] | None:
    trimmed = repo_url.strip().rstrip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[: -len(".git")]
    marker = "github.com/"
    index = trimmed.find(marker)
    if index < 0:
        return None
    parts = trimmed[index + len(marker) :].split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def _dig(data: object, *keys: str) -> object:
    """Walk nested dicts; Composio nests the GitHub payload under data (sometimes data.response_data)."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _extract_list(data: object, key: str) -> list[object] | None:
    """Composio nests list results under a named key (pull_requests/issues) or response_data."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for candidate in (data.get(key), _dig(data, "response_data", key), data.get("response_data")):
            if isinstance(candidate, list):
                return candidate
    return None


class ButterbaseGitHubClient(GitHubClient):
    """Opens PRs + checks repo permission as the signed-in user, via Butterbase's GitHub Integration."""

    def __init__(self, base_url: str, app_id: str, service_key: str) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/{app_id}/integrations/execute"
        self._service_key = service_key

    def _execute(
        self, tool_name: str, params: dict[str, object], user_id: str | None
    ) -> Result[object, GitHubError]:
        if not user_id:
            return Err(IntegrationNotConnectedError("no acting user for GitHub action"))
        body: dict[str, object] = {"toolName": tool_name, "params": params, "userId": user_id}
        try:
            with httpx.Client(timeout=_TIMEOUT_S) as client:
                response = client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._service_key}"},
                    json=body,
                )
        except httpx.HTTPError as error:
            return Err(GitHubError("butterbase execute transport failure", {"error": str(error)}))
        if not response.is_success:
            text = response.text[:200]
            if any(marker in text.lower() for marker in _NOT_CONNECTED_MARKERS):
                return Err(IntegrationNotConnectedError("GitHub is not connected for this user"))
            return Err(
                GitHubError("butterbase execute failed", {"status": str(response.status_code), "body": text})
            )
        try:
            payload = response.json()
        except ValueError:
            return Err(GitHubError("butterbase execute returned invalid JSON"))
        if not isinstance(payload, dict):
            return Err(GitHubError("butterbase execute returned an unexpected shape"))
        error_text = str(payload.get("error") or "")
        if payload.get("successful") is False or error_text:
            if any(marker in error_text.lower() for marker in _NOT_CONNECTED_MARKERS):
                return Err(IntegrationNotConnectedError("GitHub is not connected for this user"))
            return Err(GitHubError("GitHub action failed", {"error": error_text[:200] or tool_name}))
        return Ok(payload.get("data"))

    def _repo(self, owner: str, repo: str, user_id: str | None) -> Result[dict[str, object], GitHubError]:
        result = self._execute(_T_GET_REPO, {"owner": owner, "repo": repo}, user_id)
        if isinstance(result, Err):
            return Err(result.error)
        data = result.value
        inner = _dig(data, "response_data")
        repo_obj = inner if isinstance(inner, dict) else data
        if not isinstance(repo_obj, dict):
            return Err(GitHubError("unexpected repository payload"))
        return Ok(repo_obj)

    def permission(
        self, repo_url: str, acting_user_id: str | None
    ) -> Result[RepoAccess, GitHubError]:
        parsed = _parse_owner_repo(repo_url)
        if parsed is None:
            return Ok(RepoAccess.NONE)
        owner, repo = parsed
        repo_result = self._repo(owner, repo, acting_user_id)
        if isinstance(repo_result, Err):
            # A repo the user cannot see reads as "no access", not a hard error.
            if isinstance(repo_result.error, IntegrationNotConnectedError):
                return Err(repo_result.error)
            return Ok(RepoAccess.NONE)
        perms = repo_result.value.get("permissions")
        perms = perms if isinstance(perms, dict) else {}
        if perms.get("push") or perms.get("admin") or perms.get("maintain"):
            return Ok(RepoAccess.WRITE)
        return Ok(RepoAccess.READ)

    def open_pr(
        self, repo_url: str, pr: NewPr, idempotency_key: str, acting_user_id: str | None = None
    ) -> Result[PullRequestRef, GitHubError]:
        parsed = _parse_owner_repo(repo_url)
        if parsed is None:
            return Err(GitHubError("unparseable repo url", {"url": repo_url}))
        upstream_owner, repo = parsed
        repo_result = self._repo(upstream_owner, repo, acting_user_id)
        if isinstance(repo_result, Err):
            return Err(repo_result.error)
        repo_obj = repo_result.value
        default_branch = repo_obj.get("default_branch")
        base = default_branch if isinstance(default_branch, str) and default_branch else pr.base_branch
        perms = repo_obj.get("permissions")
        perms = perms if isinstance(perms, dict) else {}
        can_write = bool(perms.get("push") or perms.get("admin") or perms.get("maintain"))

        # Where the branch + files live: the repo itself (write) or the user's fork (read-only).
        if can_write:
            head_owner = upstream_owner
        else:
            fork = self._fork_owner(upstream_owner, repo, acting_user_id)
            if isinstance(fork, Err):
                return Err(fork.error)
            head_owner = fork.value

        # Idempotent: if a PR for this head branch is already open, reuse it (no duplicates).
        existing = self._find_open_pr(upstream_owner, repo, head_owner, pr.head_branch, acting_user_id)
        if isinstance(existing, Err):
            return Err(existing.error)
        if existing.value is not None:
            return Ok(existing.value)

        base_sha = self._ref_sha(head_owner, repo, base, acting_user_id)
        if isinstance(base_sha, Err):
            return Err(base_sha.error)
        created = self._execute(
            _T_CREATE_REF,
            {"owner": head_owner, "repo": repo, "ref": f"refs/heads/{pr.head_branch}", "sha": base_sha.value},
            acting_user_id,
        )
        if isinstance(created, Err):
            return Err(created.error)
        for file in pr.files:
            put = self._execute(
                _T_PUT_FILE,
                {
                    "owner": head_owner,
                    "repo": repo,
                    "path": file.path,
                    "message": f"depcover: {file.path}",
                    "content": base64.b64encode(file.text.encode("utf-8")).decode("ascii"),
                    "branch": pr.head_branch,
                },
                acting_user_id,
            )
            if isinstance(put, Err):
                return Err(put.error)
        head = pr.head_branch if can_write else f"{head_owner}:{pr.head_branch}"
        pr_result = self._execute(
            _T_CREATE_PR,
            {"owner": upstream_owner, "repo": repo, "title": pr.title, "head": head, "base": base, "body": pr.body},
            acting_user_id,
        )
        if isinstance(pr_result, Err):
            return Err(pr_result.error)
        number = _dig(pr_result.value, "number") or _dig(pr_result.value, "response_data", "number")
        url = _dig(pr_result.value, "html_url") or _dig(pr_result.value, "response_data", "html_url")
        if not isinstance(number, int) or not isinstance(url, str):
            return Err(GitHubError("pull request created but response was unparseable"))
        return Ok(PullRequestRef(number=number, url=url))

    def open_issue(
        self, repo_url: str, title: str, body: str, acting_user_id: str | None = None
    ) -> Result[PullRequestRef, GitHubError]:
        parsed = _parse_owner_repo(repo_url)
        if parsed is None:
            return Err(GitHubError("unparseable repo url", {"url": repo_url}))
        owner, repo = parsed
        existing = self._find_open_issue(owner, repo, title, acting_user_id)
        if isinstance(existing, Err):
            return Err(existing.error)
        if existing.value is not None:
            return Ok(existing.value)
        result = self._execute(
            _T_CREATE_ISSUE, {"owner": owner, "repo": repo, "title": title, "body": body}, acting_user_id
        )
        if isinstance(result, Err):
            return Err(result.error)
        number = _dig(result.value, "number") or _dig(result.value, "response_data", "number")
        url = _dig(result.value, "html_url") or _dig(result.value, "response_data", "html_url")
        if not isinstance(number, int) or not isinstance(url, str):
            return Err(GitHubError("issue created but response was unparseable"))
        return Ok(PullRequestRef(number=number, url=url))

    def _find_open_issue(
        self, owner: str, repo: str, title: str, user_id: str | None
    ) -> Result[PullRequestRef | None, GitHubError]:
        result = self._execute(_T_LIST_ISSUES, {"owner": owner, "repo": repo, "state": "open"}, user_id)
        if isinstance(result, Err):
            return Err(result.error)
        items = _extract_list(result.value, "issues")
        if items is None:
            return Ok(None)
        for item in items:
            if isinstance(item, dict) and item.get("title") == title and "pull_request" not in item:
                num = item.get("number")
                url = item.get("html_url")
                if isinstance(num, int) and isinstance(url, str):
                    return Ok(PullRequestRef(number=num, url=url))
        return Ok(None)

    def _fork_owner(self, owner: str, repo: str, user_id: str | None) -> Result[str, GitHubError]:
        forked = self._execute(_T_CREATE_FORK, {"owner": owner, "repo": repo}, user_id)
        if isinstance(forked, Err):
            return Err(forked.error)
        login = _dig(forked.value, "owner", "login") or _dig(forked.value, "response_data", "owner", "login")
        if isinstance(login, str) and login:
            return Ok(login)
        me = self._execute(_T_GET_ME, {}, user_id)
        if isinstance(me, Err):
            return Err(me.error)
        me_login = _dig(me.value, "login") or _dig(me.value, "response_data", "login")
        if isinstance(me_login, str) and me_login:
            return Ok(me_login)
        return Err(GitHubError("could not resolve fork owner login"))

    def _find_open_pr(
        self, owner: str, repo: str, head_owner: str, branch: str, user_id: str | None
    ) -> Result[PullRequestRef | None, GitHubError]:
        result = self._execute(
            _T_LIST_PRS,
            {"owner": owner, "repo": repo, "head": f"{head_owner}:{branch}", "state": "open"},
            user_id,
        )
        if isinstance(result, Err):
            return Err(result.error)
        items = _extract_list(result.value, "pull_requests")
        if not items:
            return Ok(None)
        first = items[0]
        if not isinstance(first, dict):
            return Ok(None)
        number = first.get("number")
        url = first.get("html_url")
        if isinstance(number, int) and isinstance(url, str):
            return Ok(PullRequestRef(number=number, url=url))
        return Ok(None)

    def _ref_sha(self, owner: str, repo: str, branch: str, user_id: str | None) -> Result[str, GitHubError]:
        ref = self._execute(_T_GET_REF, {"owner": owner, "repo": repo, "ref": f"heads/{branch}"}, user_id)
        if isinstance(ref, Err):
            return Err(ref.error)
        sha = _dig(ref.value, "object", "sha") or _dig(ref.value, "response_data", "object", "sha")
        if isinstance(sha, str) and sha:
            return Ok(sha)
        return Err(GitHubError("could not resolve base ref sha", {"branch": branch}))

    # The read-only methods below aren't used by the transplant→PR flow; provide safe defaults.
    def list_open_prs(self, repo_url: str) -> Result[tuple[PrSummary, ...], GitHubError]:
        return Ok(())

    def get_pr_files(self, repo_url: str, number: int) -> Result[tuple[FileContent, ...], GitHubError]:
        return Ok(())

    def post_comment(
        self, repo_url: str, number: int, body: str, idempotency_key: str
    ) -> Result[None, GitHubError]:
        return Ok(None)
