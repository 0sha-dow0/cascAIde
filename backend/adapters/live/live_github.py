import base64
from typing import Final

import httpx

from backend.domain.enums import RepoAccess
from backend.domain.errors import Err, GitHubError, Ok, RateLimitError, Result
from backend.domain.models import FileContent, PullRequestRef, RewrittenFile
from backend.ports.github import GitHubClient, NewPr, PrSummary

_API_ROOT: Final[str] = "https://api.github.com"
_ACCEPT: Final[str] = "application/vnd.github+json"
_COMMIT_PREFIX: Final[str] = "depcover: transplant "
_DETAIL_CAP: Final[int] = 200


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


class LiveGitHubClient(GitHubClient):
    def __init__(self, token: str, timeout_s: float = 30.0) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._timeout_s = timeout_s

    def _request(
        self, method: str, url: str, json_body: dict[str, object] | None = None
    ) -> Result[httpx.Response, GitHubError]:
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                response = client.request(method, url, headers=self._headers, json=json_body)
        except httpx.TimeoutException:
            return Err(GitHubError("github request timed out", {"url": _tail(url)}))
        except httpx.HTTPError as error:
            return Err(GitHubError("github transport failure", {"detail": str(error)[:_DETAIL_CAP]}))
        if response.status_code == 403 and "rate limit" in response.text.lower():
            return Err(RateLimitError("github rate limit", {"url": _tail(url)}))
        return Ok(response)

    def permission(
        self, repo_url: str, acting_user_id: str | None
    ) -> Result[RepoAccess, GitHubError]:
        parsed = _parse_owner_repo(repo_url)
        if parsed is None:
            return Err(GitHubError("unparseable repo url", {"url": repo_url}))
        owner, repo = parsed
        result = self._request("GET", f"{_API_ROOT}/repos/{owner}/{repo}")
        if isinstance(result, Err):
            return Err(result.error)
        response = result.value
        if response.status_code == 404:
            return Ok(RepoAccess.NONE)
        if response.status_code != 200:
            return Err(_status_error("resolve repo", response))
        perms = response.json().get("permissions")
        perms = perms if isinstance(perms, dict) else {}
        if perms.get("push") or perms.get("admin") or perms.get("maintain"):
            return Ok(RepoAccess.WRITE)
        return Ok(RepoAccess.READ)

    def open_issue(
        self, repo_url: str, title: str, body: str, acting_user_id: str | None = None
    ) -> Result[PullRequestRef, GitHubError]:
        parsed = _parse_owner_repo(repo_url)
        if parsed is None:
            return Err(GitHubError("unparseable repo url", {"url": repo_url}))
        owner, repo = parsed
        result = self._request(
            "POST", f"{_API_ROOT}/repos/{owner}/{repo}/issues", {"title": title, "body": body}
        )
        if isinstance(result, Err):
            return Err(result.error)
        response = result.value
        if response.status_code not in (200, 201):
            return Err(_status_error("open issue", response))
        data = response.json()
        number = data.get("number")
        url = data.get("html_url")
        if not isinstance(number, int) or not isinstance(url, str):
            return Err(GitHubError("issue created but response was unparseable"))
        return Ok(PullRequestRef(number=number, url=url))

    def _default_branch(self, owner: str, repo: str) -> Result[str, GitHubError]:
        result = self._request("GET", f"{_API_ROOT}/repos/{owner}/{repo}")
        if isinstance(result, Err):
            return Err(result.error)
        response = result.value
        if response.status_code != 200:
            return Err(_status_error("resolve repo", response))
        branch = response.json().get("default_branch")
        if not isinstance(branch, str) or not branch:
            return Err(GitHubError("repo has no default branch", {"repo": repo}))
        return Ok(branch)

    def _base_sha(self, owner: str, repo: str, base: str) -> Result[str, GitHubError]:
        result = self._request("GET", f"{_API_ROOT}/repos/{owner}/{repo}/git/ref/heads/{base}")
        if isinstance(result, Err):
            return Err(result.error)
        response = result.value
        if response.status_code != 200:
            return Err(_status_error("resolve base branch", response))
        sha = response.json().get("object", {}).get("sha")
        if not isinstance(sha, str) or not sha:
            return Err(GitHubError("base branch has no sha", {"base": base}))
        return Ok(sha)

    def _ensure_branch(self, owner: str, repo: str, head: str, sha: str) -> Result[None, GitHubError]:
        result = self._request(
            "POST",
            f"{_API_ROOT}/repos/{owner}/{repo}/git/refs",
            {"ref": f"refs/heads/{head}", "sha": sha},
        )
        if isinstance(result, Err):
            return Err(result.error)
        response = result.value
        if response.status_code in (200, 201) or response.status_code == 422:
            return Ok(None)
        return Err(_status_error("create branch", response))

    def _file_sha(self, owner: str, repo: str, path: str, branch: str) -> str | None:
        result = self._request(
            "GET", f"{_API_ROOT}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
        )
        if isinstance(result, Err) or result.value.status_code != 200:
            return None
        sha = result.value.json().get("sha")
        return sha if isinstance(sha, str) else None

    def _commit_file(
        self, owner: str, repo: str, file: RewrittenFile, branch: str
    ) -> Result[None, GitHubError]:
        body: dict[str, object] = {
            "message": f"{_COMMIT_PREFIX}{file.path}",
            "content": base64.b64encode(file.text.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        existing = self._file_sha(owner, repo, file.path, branch)
        if existing is not None:
            body["sha"] = existing
        result = self._request(
            "PUT", f"{_API_ROOT}/repos/{owner}/{repo}/contents/{file.path}", body
        )
        if isinstance(result, Err):
            return Err(result.error)
        if result.value.status_code not in (200, 201):
            return Err(_status_error("commit file", result.value))
        return Ok(None)

    def _existing_pr(
        self, owner: str, repo: str, head: str, base: str
    ) -> Result[PullRequestRef | None, GitHubError]:
        result = self._request(
            "GET", f"{_API_ROOT}/repos/{owner}/{repo}/pulls?head={owner}:{head}&base={base}&state=open"
        )
        if isinstance(result, Err):
            return Err(result.error)
        if result.value.status_code != 200:
            return Err(_status_error("list pulls", result.value))
        pulls = result.value.json()
        if isinstance(pulls, list) and pulls:
            first = pulls[0]
            return Ok(PullRequestRef(number=int(first["number"]), url=str(first["html_url"])))
        return Ok(None)

    def open_pr(
        self, repo_url: str, pr: NewPr, idempotency_key: str, acting_user_id: str | None = None
    ) -> Result[PullRequestRef, GitHubError]:
        if not idempotency_key:
            return Err(GitHubError("open_pr requires a non-empty idempotency_key", {}))
        owner_repo = _parse_owner_repo(repo_url)
        if owner_repo is None:
            return Err(GitHubError("unparseable github repo url", {"url": repo_url}))
        owner, repo = owner_repo
        base_result = self._default_branch(owner, repo) if not pr.base_branch else Ok(pr.base_branch)
        if isinstance(base_result, Err):
            return Err(base_result.error)
        base = base_result.value
        head = pr.head_branch or f"depcover/{idempotency_key}"

        existing = self._existing_pr(owner, repo, head, base)
        if isinstance(existing, Err):
            return Err(existing.error)
        if existing.value is not None:
            return Ok(existing.value)

        sha_result = self._base_sha(owner, repo, base)
        if isinstance(sha_result, Err):
            return Err(sha_result.error)
        branch_result = self._ensure_branch(owner, repo, head, sha_result.value)
        if isinstance(branch_result, Err):
            return Err(branch_result.error)
        for file in pr.files:
            committed = self._commit_file(owner, repo, file, head)
            if isinstance(committed, Err):
                return Err(committed.error)

        create = self._request(
            "POST",
            f"{_API_ROOT}/repos/{owner}/{repo}/pulls",
            {"title": pr.title, "head": head, "base": base, "body": pr.body},
        )
        if isinstance(create, Err):
            return Err(create.error)
        if create.value.status_code == 422:
            retry = self._existing_pr(owner, repo, head, base)
            if isinstance(retry, Err):
                return Err(retry.error)
            if retry.value is not None:
                return Ok(retry.value)
            return Err(_status_error("create pull request", create.value))
        if create.value.status_code not in (200, 201):
            return Err(_status_error("create pull request", create.value))
        created = create.value.json()
        return Ok(PullRequestRef(number=int(created["number"]), url=str(created["html_url"])))

    def list_open_prs(self, repo_url: str) -> Result[tuple[PrSummary, ...], GitHubError]:
        owner_repo = _parse_owner_repo(repo_url)
        if owner_repo is None:
            return Err(GitHubError("unparseable github repo url", {"url": repo_url}))
        owner, repo = owner_repo
        result = self._request("GET", f"{_API_ROOT}/repos/{owner}/{repo}/pulls?state=open")
        if isinstance(result, Err):
            return Err(result.error)
        if result.value.status_code != 200:
            return Err(_status_error("list pulls", result.value))
        summaries = tuple(
            PrSummary(
                number=int(item["number"]),
                head_sha=str(item.get("head", {}).get("sha", "")),
                changed_files=(),
            )
            for item in result.value.json()
        )
        return Ok(summaries)

    def get_pr_files(
        self, repo_url: str, number: int
    ) -> Result[tuple[FileContent, ...], GitHubError]:
        owner_repo = _parse_owner_repo(repo_url)
        if owner_repo is None:
            return Err(GitHubError("unparseable github repo url", {"url": repo_url}))
        owner, repo = owner_repo
        result = self._request(
            "GET", f"{_API_ROOT}/repos/{owner}/{repo}/pulls/{number}/files"
        )
        if isinstance(result, Err):
            return Err(result.error)
        if result.value.status_code != 200:
            return Err(_status_error("list pr files", result.value))
        files = tuple(
            FileContent(path=str(item["filename"]), text=str(item.get("patch", "")))
            for item in result.value.json()
        )
        return Ok(files)

    def post_comment(
        self, repo_url: str, number: int, body: str, idempotency_key: str
    ) -> Result[None, GitHubError]:
        if not idempotency_key:
            return Err(GitHubError("post_comment requires a non-empty idempotency_key", {}))
        owner_repo = _parse_owner_repo(repo_url)
        if owner_repo is None:
            return Err(GitHubError("unparseable github repo url", {"url": repo_url}))
        owner, repo = owner_repo
        result = self._request(
            "POST",
            f"{_API_ROOT}/repos/{owner}/{repo}/issues/{number}/comments",
            {"body": f"{body}\n\n<!-- depcover:{idempotency_key} -->"},
        )
        if isinstance(result, Err):
            return Err(result.error)
        if result.value.status_code not in (200, 201):
            return Err(_status_error("post comment", result.value))
        return Ok(None)


def _status_error(action: str, response: httpx.Response) -> GitHubError:
    return GitHubError(
        f"github {action} failed",
        {"status": str(response.status_code), "body": response.text[:_DETAIL_CAP]},
    )


def _tail(url: str) -> str:
    return url[len(_API_ROOT) :] if url.startswith(_API_ROOT) else url
