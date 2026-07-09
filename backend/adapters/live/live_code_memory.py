from __future__ import annotations

import hashlib
import time
from typing import Final

import httpx

from backend.domain.errors import CodeMemoryError, Err, Ok, Result
from backend.domain.models import FileContent, MemorySnippet
from backend.ports.code_memory import CodeMemory

__all__ = ("LiveCogneeCloudCodeMemory",)

_REMEMBER_PATH: Final[str] = "/api/v1/remember"
_RECALL_PATH: Final[str] = "/api/v1/recall"
_STATUS_PATH: Final[str] = "/api/v1/datasets/status"
_NODE_SET: Final[str] = "code"
_HEADER_API_KEY: Final[str] = "X-Api-Key"

# Free-tier guards: cap what we send to a single cognify so it stays small + cheap.
_MAX_FILES: Final[int] = 12
_MAX_TOTAL_CHARS: Final[int] = 60_000
_MAX_SNIPPET_CHARS: Final[int] = 4_000

_INDEX_TIMEOUT_S: Final[float] = 30.0
_RECALL_TIMEOUT_S: Final[float] = 30.0
_STATUS_TIMEOUT_S: Final[float] = 10.0
_COGNIFY_DEADLINE_S: Final[float] = 90.0
_POLL_INTERVAL_S: Final[float] = 3.0


def _dataset_name(repo_url: str) -> str:
    digest = hashlib.sha1(repo_url.encode("utf-8")).hexdigest()[:12]
    return f"cascaide-{digest}"


def _corpus(files: tuple[FileContent, ...]) -> str:
    """Concatenate the affected files into one small, labeled blob for a single cognify."""
    parts: list[str] = []
    total = 0
    for file in files[:_MAX_FILES]:
        body = file.text[:_MAX_SNIPPET_CHARS]
        block = f"// FILE: {file.path}\n{body}\n"
        if total + len(block) > _MAX_TOTAL_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts)


class LiveCogneeCloudCodeMemory(CodeMemory):
    """Code memory backed by a Cognee Cloud tenant over its REST API.

    Indexing POSTs the affected files to ``/api/v1/remember`` (one cognify per repo,
    cached in-process); recall queries ``/api/v1/recall`` scoped to the repo's dataset.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._indexed: set[str] = set()

    def _headers(self) -> dict[str, str]:
        return {_HEADER_API_KEY: self._api_key}

    def ensure_indexed(
        self, repo_url: str, files: tuple[FileContent, ...]
    ) -> Result[None, CodeMemoryError]:
        dataset = _dataset_name(repo_url)
        if dataset in self._indexed:
            return Ok(None)
        corpus = _corpus(files)
        if corpus.strip() == "":
            return Err(CodeMemoryError("no code to index", {"repo_url": repo_url}))
        try:
            with httpx.Client(timeout=_INDEX_TIMEOUT_S) as client:
                response = client.post(
                    f"{self._base_url}{_REMEMBER_PATH}",
                    headers=self._headers(),
                    data={
                        "datasetName": dataset,
                        "node_set": _NODE_SET,
                        "run_in_background": "true",
                    },
                    files={"data": (f"{dataset}.txt", corpus, "text/plain")},
                )
        except httpx.HTTPError as error:
            return Err(
                CodeMemoryError("cognee remember transport failure", {"error": str(error)})
            )
        if not response.is_success:
            return Err(
                CodeMemoryError(
                    "cognee remember failed",
                    {"status": str(response.status_code), "body": response.text[:200]},
                )
            )
        dataset_id = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                dataset_id = str(payload.get("dataset_id") or "")
        except (ValueError, httpx.HTTPError):
            dataset_id = ""
        outcome = self._wait_for_cognify(dataset_id)
        # A timeout is non-fatal: the graph may still answer, or the plan can lean on
        # the surgery plan. Only cache the repo as indexed once cognify is confirmed done.
        if outcome == "completed":
            self._indexed.add(dataset)
        return Ok(None)

    def _wait_for_cognify(self, dataset_id: str) -> str:
        if dataset_id == "":
            return "unknown"
        url = f"{self._base_url}{_STATUS_PATH}"
        deadline = time.monotonic() + _COGNIFY_DEADLINE_S
        while True:
            status = ""
            try:
                with httpx.Client(timeout=_STATUS_TIMEOUT_S) as client:
                    response = client.get(
                        url,
                        headers=self._headers(),
                        params={"dataset": dataset_id, "pipeline": "cognify_pipeline"},
                    )
                if response.is_success:
                    parsed = response.json()
                    if isinstance(parsed, dict):
                        val = parsed.get(dataset_id)
                        if val is None and len(parsed) == 1:
                            val = next(iter(parsed.values()))
                        if isinstance(val, dict):
                            val = val.get("cognify_pipeline")
                        status = str(val or "").upper()
            except (httpx.HTTPError, ValueError):
                pass  # transient — keep polling until the deadline
            if status.endswith("COMPLETED"):
                return "completed"
            if status.endswith("ERRORED"):
                return "errored"
            if time.monotonic() >= deadline:
                return "timeout"
            time.sleep(_POLL_INTERVAL_S)

    def recall(
        self, repo_url: str, query: str, k: int = 8
    ) -> Result[tuple[MemorySnippet, ...], CodeMemoryError]:
        dataset = _dataset_name(repo_url)
        try:
            with httpx.Client(timeout=_RECALL_TIMEOUT_S) as client:
                response = client.post(
                    f"{self._base_url}{_RECALL_PATH}",
                    headers=self._headers(),
                    json={
                        "query": query,
                        "top_k": k,
                        "only_context": True,
                        "datasets": [dataset],
                    },
                )
        except httpx.HTTPError as error:
            return Err(
                CodeMemoryError("cognee recall transport failure", {"error": str(error)})
            )
        if not response.is_success:
            return Err(
                CodeMemoryError(
                    "cognee recall failed",
                    {"status": str(response.status_code), "body": response.text[:200]},
                )
            )
        try:
            payload = response.json()
        except ValueError as error:
            return Err(CodeMemoryError("cognee recall returned invalid JSON", {"error": str(error)}))
        items = payload if isinstance(payload, list) else [payload]
        snippets: list[MemorySnippet] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or text.strip() == "":
                continue
            raw_score = item.get("score")
            score = float(raw_score) if isinstance(raw_score, (int, float)) else 0.0
            name = item.get("dataset_name")
            path = name if isinstance(name, str) and name != "" else dataset
            snippets.append(
                MemorySnippet(path=path, text=text[:_MAX_SNIPPET_CHARS], score=score)
            )
        return Ok(tuple(snippets))
