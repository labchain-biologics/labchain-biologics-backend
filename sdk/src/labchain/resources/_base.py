"""Shared helpers for API resources."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from labchain._http import Transport
from labchain.models import RequestModel

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)
R = TypeVar("R", bound=RequestModel)

CHUNK_SIZE = 1024 * 1024


class Resource:
    def __init__(self, http: Transport) -> None:
        self._http = http


def parse(model: type[M], data: Any) -> M:
    return model.model_validate(data)


def parse_list(model: type[M], data: Any) -> list[M]:
    return [model.model_validate(item) for item in data]


def build(model: type[R], data: R | None, fields: dict[str, Any]) -> R:
    """Accept either a request model or keyword fields (``sample_code=...``), not both."""
    if data is not None:
        if fields:
            raise TypeError(f"Pass a {model.__name__} or keyword fields, not both")
        return data
    return model(**fields)


def paginate(fetch: Callable[[int, int], list[T]], page_size: int) -> Iterator[T]:
    """Walk a limit/offset listing until a short page."""
    offset = 0
    while True:
        page = fetch(page_size, offset)
        yield from page
        if len(page) < page_size:
            return
        offset += page_size


def file_md5(path: Path) -> tuple[str, int]:
    """MD5 hex digest and size of a file, read in chunks."""
    digest = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size
