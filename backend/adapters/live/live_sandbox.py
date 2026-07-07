import shlex
from collections.abc import Mapping
from typing import Final

from daytona import (
    CreateSandboxFromImageParams,
    Daytona,
    DaytonaConfig,
    DaytonaError,
    DaytonaTimeoutError,
    FileUpload,
    Sandbox,
)

from backend.domain.enums import SandboxOutcome
from backend.domain.errors import (
    Err,
    Ok,
    Result,
    SandboxError,
    SandboxUnavailableError,
)
from backend.ports.sandbox import (
    SandboxCommand,
    SandboxHandle,
    SandboxResult,
    SandboxRunner,
    validate_command,
    validate_exec_timeout,
    validate_sandbox_path,
)

_DEFAULT_IMAGE: Final[str] = "node:20-alpine"
_DETAIL_CAP: Final[int] = 160


class LiveSandbox(SandboxRunner):
    def __init__(
        self,
        api_key: str,
        api_url: str,
        image: str = _DEFAULT_IMAGE,
        create_timeout_s: float = 150.0,
    ) -> None:
        self._daytona = Daytona(DaytonaConfig(api_key=api_key, api_url=api_url))
        self._image = image
        self._create_timeout_s = create_timeout_s
        self._sandboxes: dict[str, Sandbox] = {}

    def acquire(self, snapshot_id: str) -> Result[SandboxHandle, SandboxError]:
        params = CreateSandboxFromImageParams(
            image=self._image, ephemeral=True, network_block_all=True
        )
        try:
            sandbox = self._daytona.create(params, timeout=self._create_timeout_s)
        except DaytonaTimeoutError as error:
            return Err(SandboxUnavailableError("daytona create timed out", _detail(error)))
        except DaytonaError as error:
            return Err(SandboxUnavailableError("daytona create failed", _detail(error)))
        self._sandboxes[sandbox.id] = sandbox
        return Ok(SandboxHandle(id=sandbox.id))

    def write_files(
        self, h: SandboxHandle, files: Mapping[str, str]
    ) -> Result[None, SandboxError]:
        sandbox = self._sandboxes.get(h.id)
        if sandbox is None:
            return Err(SandboxUnavailableError("unknown or released handle", {"id": h.id}))
        uploads: list[FileUpload] = []
        for path, content in files.items():
            path_check = validate_sandbox_path(path)
            if isinstance(path_check, Err):
                return Err(path_check.error)
            uploads.append(FileUpload(source=content.encode("utf-8"), destination=path))
        if not uploads:
            return Ok(None)
        try:
            sandbox.fs.upload_files(uploads)
        except DaytonaError as error:
            return Err(SandboxError("daytona upload failed", _detail(error)))
        return Ok(None)

    def exec(
        self, h: SandboxHandle, cmd: SandboxCommand, timeout_s: float
    ) -> Result[SandboxResult, SandboxError]:
        sandbox = self._sandboxes.get(h.id)
        if sandbox is None:
            return Err(SandboxUnavailableError("unknown or released handle", {"id": h.id}))
        timeout_check = validate_exec_timeout(timeout_s)
        if isinstance(timeout_check, Err):
            return Err(timeout_check.error)
        command_check = validate_command(cmd)
        if isinstance(command_check, Err):
            return Err(command_check.error)
        command = shlex.join(cmd.argv)
        env = dict(cmd.env) if cmd.env else None
        cwd = cmd.cwd if cmd.cwd and cmd.cwd != "." else None
        try:
            response = sandbox.process.exec(command, cwd=cwd, env=env, timeout=int(timeout_s))
        except DaytonaTimeoutError:
            return Ok(
                SandboxResult(
                    outcome=SandboxOutcome.TIMEOUT,
                    exit_code=None,
                    stdout="",
                    stderr="",
                    duration_s=timeout_s,
                )
            )
        except DaytonaError as error:
            return Err(SandboxError("daytona exec failed", _detail(error)))
        outcome = SandboxOutcome.PASSED if response.exit_code == 0 else SandboxOutcome.FAILED
        return Ok(
            SandboxResult(
                outcome=outcome,
                exit_code=response.exit_code,
                stdout=response.result or "",
                stderr="",
                duration_s=0.0,
            )
        )

    def release(self, h: SandboxHandle) -> Result[None, SandboxError]:
        sandbox = self._sandboxes.pop(h.id, None)
        if sandbox is None:
            return Ok(None)
        try:
            self._daytona.delete(sandbox)
        except DaytonaError as error:
            return Err(SandboxError("daytona delete failed", _detail(error)))
        return Ok(None)


def _detail(error: DaytonaError) -> dict[str, str]:
    return {"detail": str(error)[:_DETAIL_CAP]}
