import re
from typing import Final

from backend.domain.enums import LlmRole
from backend.domain.errors import (
    DepCoverError,
    Err,
    LlmMalformedOutputError,
    Ok,
    Result,
)
from backend.domain.models import (
    RewrittenFile,
    TransplantOutput,
    TransplantRequest,
)
from backend.ports.llm import LlmClientFactory, LlmRequest
from backend.services.transplant_prompt import build_transplant_messages

_TRANSPLANT_TEMPERATURE: Final[float] = 0.0
_TRANSPLANT_MAX_TOKENS: Final[int] = 4096
_TRUNCATED_FINISH_REASON: Final = "length"
_BLOCK_RE: Final = re.compile(
    r'<rewritten_file\s+path="([^"]*)"\s*>(.*?)</rewritten_file>', re.DOTALL
)

_NEWLINE: Final[str] = "\n"
_OPEN_PREFIX: Final[str] = '<rewritten_file path="'
_OPEN_SUFFIX: Final[str] = '">'
_CLOSE_MARKER: Final[str] = "</rewritten_file>"
_OPEN_MIN_LENGTH: Final[int] = len(_OPEN_PREFIX) + len(_OPEN_SUFFIX)

_PATH_SEPARATOR: Final[str] = ", "
_EMPTY_PLACEHOLDER: Final[str] = "none"

_CTX_FINISH_REASON: Final[str] = "finish_reason"
_CTX_PATH: Final[str] = "path"
_CTX_DUPLICATED: Final[str] = "duplicated"
_CTX_MISSING: Final[str] = "missing"
_CTX_EXTRA: Final[str] = "extra"

_TRUNCATED_MESSAGE: Final[str] = (
    "transplant response was truncated before completion"
)
_UNCLOSED_MESSAGE: Final[str] = (
    "transplant response opened a rewritten_file block that was never closed"
)
_DUPLICATE_MESSAGE: Final[str] = (
    "transplant response emitted the same file path more than once"
)
_MISMATCH_MESSAGE: Final[str] = (
    "transplant response file paths do not match the requested file set"
)


def _open_marker_path(line: str) -> str | None:
    if not line.startswith(_OPEN_PREFIX):
        return None
    if not line.endswith(_OPEN_SUFFIX):
        return None
    if len(line) < _OPEN_MIN_LENGTH:
        return None
    return line[len(_OPEN_PREFIX) : -len(_OPEN_SUFFIX)]


def _format_paths(paths: list[str]) -> str:
    return _PATH_SEPARATOR.join(paths) if paths else _EMPTY_PLACEHOLDER


def _by_path(file: RewrittenFile) -> str:
    return file.path


def _parse_rewritten_files(
    text: str,
) -> Result[tuple[RewrittenFile, ...], LlmMalformedOutputError]:
    collected: list[RewrittenFile] = []
    for match in _BLOCK_RE.finditer(text):
        path = match.group(1).strip()
        body = match.group(2)
        if body.startswith(_NEWLINE):
            body = body[len(_NEWLINE) :]
        if body.endswith(_NEWLINE):
            body = body[: -len(_NEWLINE)]
        collected.append(RewrittenFile(path=path, text=body))
    return Ok(tuple(collected))


def _normalize(path: str) -> str:
    stripped = path.strip()
    while stripped.startswith("./"):
        stripped = stripped[2:]
    return stripped.lstrip("/")


def _reconcile_files(
    files: tuple[RewrittenFile, ...], request: TransplantRequest
) -> Result[tuple[RewrittenFile, ...], LlmMalformedOutputError]:
    canonical_by_norm = {_normalize(file.path): file.path for file in request.files}
    matched: dict[str, RewrittenFile] = {}
    for file in files:
        canonical = canonical_by_norm.get(_normalize(file.path))
        if canonical is None:
            continue
        matched[canonical] = RewrittenFile(path=canonical, text=file.text)
    if not matched:
        return Err(
            LlmMalformedOutputError(
                _MISMATCH_MESSAGE,
                {
                    _CTX_EXTRA: _format_paths(sorted({file.path for file in files})),
                    _CTX_MISSING: _format_paths(sorted(canonical_by_norm.values())),
                },
            )
        )
    return Ok(tuple(sorted(matched.values(), key=_by_path)))


class TransplantAgent:
    def __init__(self, llm: LlmClientFactory) -> None:
        self._llm: LlmClientFactory = llm

    def run(
        self, request: TransplantRequest, attempt: int
    ) -> Result[TransplantOutput, DepCoverError]:
        messages_result = build_transplant_messages(request)
        if isinstance(messages_result, Err):
            return messages_result
        client_result = self._llm.for_role(LlmRole.TRANSPLANT)
        if isinstance(client_result, Err):
            return Err(client_result.error)
        payload = LlmRequest(
            role=LlmRole.TRANSPLANT,
            messages=messages_result.value,
            temperature=_TRANSPLANT_TEMPERATURE,
            max_tokens=_TRANSPLANT_MAX_TOKENS,
        )
        completion = client_result.value.complete(payload)
        if isinstance(completion, Err):
            return Err(completion.error)
        response = completion.value
        if response.finish_reason == _TRUNCATED_FINISH_REASON:
            return Err(
                LlmMalformedOutputError(
                    _TRUNCATED_MESSAGE,
                    {_CTX_FINISH_REASON: response.finish_reason},
                )
            )
        parse_result = _parse_rewritten_files(response.text)
        if isinstance(parse_result, Err):
            return Err(parse_result.error)
        reconciled = _reconcile_files(parse_result.value, request)
        if isinstance(reconciled, Err):
            return Err(reconciled.error)
        return Ok(
            TransplantOutput(
                attempt=attempt,
                files=reconciled.value,
                raw_model_text=response.text,
            )
        )


__all__ = ("TransplantAgent",)
