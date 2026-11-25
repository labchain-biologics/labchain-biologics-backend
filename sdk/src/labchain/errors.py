"""Exceptions raised by the SDK."""

from __future__ import annotations

from typing import Any


class LabChainError(Exception):
    """Base class of every error raised by the SDK."""


class ConfigurationError(LabChainError):
    """The client is missing something it needs (base URL, token, workspace)."""


class APIConnectionError(LabChainError):
    """The API could not be reached (DNS, refused connection, timeout)."""


class APIError(LabChainError):
    """The API answered with an error status. ``detail`` is the server's ``detail`` field."""

    def __init__(self, status_code: int, detail: Any, *, method: str, path: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.method = method
        self.path = path
        super().__init__(f"{method} {path} -> {status_code}: {_format_detail(detail)}")


class BadRequestError(APIError):
    """400: the request is malformed (e.g. missing workspace header, wrong file type)."""


class AuthenticationError(APIError):
    """401: missing, invalid, expired or revoked credentials."""


class PermissionDeniedError(APIError):
    """403: your role in this workspace does not allow the action."""


class NotFoundError(APIError):
    """404: the resource does not exist, or belongs to a workspace you are not a member of."""


class ConflictError(APIError):
    """409: the action conflicts with the current state (duplicate, already revoked...)."""


class UnprocessableError(APIError):
    """422: the request was understood but its content is invalid."""


class ServerError(APIError):
    """5xx: the server or one of its dependencies (object storage, AWS Batch) failed."""


class ChecksumMismatchError(LabChainError):
    """A file's MD5 does not match the expected checksum."""


class ExecutionDisabledError(LabChainError):
    """
    The run was recorded but will never execute: pipeline execution is disabled on this
    server (``executionSubmitted`` is false). Waiting for it would never end.
    """


class RunFailedError(LabChainError):
    """The run ended with status ``failed`` or ``cancelled``."""

    def __init__(self, run_id: str, status: str, message: str | None) -> None:
        self.run_id = run_id
        self.status = status
        suffix = f": {message}" if message else ""
        super().__init__(f"Run {run_id} ended with status {status}{suffix}")


class RunTimeoutError(LabChainError, TimeoutError):
    """The run did not finish within the requested time. It keeps running on the server."""


_STATUS_ERRORS: dict[int, type[APIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableError,
}


def error_for_status(status_code: int, detail: Any, *, method: str, path: str) -> APIError:
    if status_code >= 500:
        cls: type[APIError] = ServerError
    else:
        cls = _STATUS_ERRORS.get(status_code, APIError)
    return cls(status_code, detail, method=method, path=path)


def _format_detail(detail: Any) -> str:
    """FastAPI validation errors are a list of {loc, msg}; render them on one line."""
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict) and "msg" in item:
                location = ".".join(str(part) for part in item.get("loc", []) if part != "body")
                parts.append(f"{location}: {item['msg']}" if location else str(item["msg"]))
            else:
                parts.append(str(item))
        return "; ".join(parts)
    return str(detail)
