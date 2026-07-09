from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final

import httpx

from backend.domain.errors import AuthError, Err, Ok, Result
from backend.ports.auth import AuthenticatedUser, AuthProvider

_HEADER_AUTHORIZATION: Final = "Authorization"
_BEARER_PREFIX: Final = "Bearer "

_FIELD_ID: Final = "id"
_FIELD_SUB: Final = "sub"
_FIELD_EMAIL: Final = "email"
_FIELD_LOGIN: Final = "login"
_FIELD_DISPLAY_NAME: Final = "display_name"
_FIELD_AVATAR: Final = "avatar_url"

_EMPTY_TOKEN_MESSAGE: Final = "bearer token is empty"
_TIMEOUT_MESSAGE: Final = "butterbase auth request timed out"
_TRANSPORT_MESSAGE: Final = "butterbase auth transport failure"
_INVALID_TOKEN_MESSAGE: Final = "invalid token"
_MALFORMED_MESSAGE: Final = "butterbase auth returned a malformed response"


def _field(mapping: Mapping[object, object], key: str) -> str | None:
    value = mapping.get(key)
    if isinstance(value, str) and value != "":
        return value
    return None


def _to_authenticated_user(parsed: object) -> Result[AuthenticatedUser, AuthError]:
    if not isinstance(parsed, dict):
        return Err(AuthError(_MALFORMED_MESSAGE))
    # Butterbase /me returns the profile at the top level or under a "user" key.
    inner = parsed.get("user")
    mapping: dict[object, object] = inner if isinstance(inner, dict) else parsed
    identifier = _field(mapping, _FIELD_ID) or _field(mapping, _FIELD_SUB)
    if identifier is None:
        return Err(AuthError(_MALFORMED_MESSAGE))
    email = _field(mapping, _FIELD_EMAIL)
    if email is None:
        return Err(AuthError(_MALFORMED_MESSAGE))
    return Ok(
        AuthenticatedUser(
            id=identifier,
            email=email,
            login=_field(mapping, _FIELD_LOGIN),
            display_name=_field(mapping, _FIELD_DISPLAY_NAME),
            avatar_url=_field(mapping, _FIELD_AVATAR),
        )
    )


class LiveAuthProvider(AuthProvider):
    """Verifies a Butterbase session JWT via GET {base_url}/auth/{app_id}/me."""

    def __init__(
        self, base_url: str, app_id: str, service_key: str, timeout_s: float = 10.0
    ) -> None:
        self._base_url: str = base_url.rstrip("/")
        self._app_id: str = app_id
        self._service_key: str = service_key
        self._timeout_s: float = timeout_s

    def _me_url(self) -> str:
        return f"{self._base_url}/auth/{self._app_id}/me"

    def verify(self, bearer_token: str) -> Result[AuthenticatedUser, AuthError]:
        if bearer_token.strip() == "":
            return Err(AuthError(_EMPTY_TOKEN_MESSAGE))
        headers = {_HEADER_AUTHORIZATION: f"{_BEARER_PREFIX}{bearer_token}"}
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                response = client.get(self._me_url(), headers=headers)
        except httpx.TimeoutException:
            return Err(AuthError(_TIMEOUT_MESSAGE))
        except httpx.HTTPError:
            return Err(AuthError(_TRANSPORT_MESSAGE))
        if not response.is_success:
            return Err(
                AuthError(_INVALID_TOKEN_MESSAGE, {"status": str(response.status_code)})
            )
        try:
            parsed: object = response.json()
        except json.JSONDecodeError:
            return Err(AuthError(_MALFORMED_MESSAGE))
        return _to_authenticated_user(parsed)


__all__ = ("LiveAuthProvider",)
