"""Sequencing runs and FASTQ files."""

from __future__ import annotations

import builtins
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from titerlane.errors import ChecksumMismatchError
from titerlane.models import (
    FastqFile,
    FastqRegisterRequest,
    FastqRegistration,
    FastqVerification,
    FastqVerificationStatus,
    SequencingRun,
    SequencingRunCreate,
)
from titerlane.resources._base import Resource, build, file_md5, paginate, parse, parse_list

MAX_PAGE_SIZE = 1000
# The server signs FASTQ upload URLs for this content type; the upload must send exactly it.


class SequencingRuns(Resource):
    def list(self, *, limit: int = 100, offset: int = 0) -> builtins.list[SequencingRun]:
        params = {"limit": limit, "offset": offset}
        data = self._http.request("GET", "/sequencing-runs", params=params)
        return parse_list(SequencingRun, data)

    def iter(self, *, page_size: int = MAX_PAGE_SIZE) -> Iterator[SequencingRun]:
        return paginate(lambda limit, offset: self.list(limit=limit, offset=offset), page_size)

    def get(self, run_id: uuid.UUID | str) -> SequencingRun:
        return parse(SequencingRun, self._http.request("GET", f"/sequencing-runs/{run_id}"))

    def create(self, run: SequencingRunCreate | None = None, /, **fields: Any) -> SequencingRun:
        """Record a sequencing run: ``create(run_name="NovaSeq-2026-11-25")``."""
        body = build(SequencingRunCreate, run, fields).to_json()
        return parse(SequencingRun, self._http.request("POST", "/sequencing-runs", json=body))


class Fastq(Resource):
    def list(
        self,
        *,
        sample_id: uuid.UUID | str | None = None,
        sequencing_run_id: uuid.UUID | str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> builtins.list[FastqFile]:
        params = {
            "sampleId": sample_id,
            "sequencingRunId": sequencing_run_id,
            "limit": limit,
            "offset": offset,
        }
        return parse_list(FastqFile, self._http.request("GET", "/fastq", params=params))

    def iter(
        self,
        *,
        sample_id: uuid.UUID | str | None = None,
        sequencing_run_id: uuid.UUID | str | None = None,
        page_size: int = MAX_PAGE_SIZE,
    ) -> Iterator[FastqFile]:
        return paginate(
            lambda limit, offset: self.list(
                sample_id=sample_id,
                sequencing_run_id=sequencing_run_id,
                limit=limit,
                offset=offset,
            ),
            page_size,
        )

    def get(self, fastq_id: uuid.UUID | str) -> FastqFile:
        return parse(FastqFile, self._http.request("GET", f"/fastq/{fastq_id}"))

    def register(
        self, request: FastqRegisterRequest | None = None, /, **fields: Any
    ) -> FastqRegistration:
        """
        Record a FASTQ file and get a signed ``upload_url``. Most callers want :meth:`upload`,
        which also sends the file and verifies it.
        """
        body = build(FastqRegisterRequest, request, fields).to_json()
        return parse(FastqRegistration, self._http.request("POST", "/fastq/register", json=body))

    def verify(self, fastq_id: uuid.UUID | str) -> FastqVerification:
        """Have the server compute the MD5 of the stored object and compare it."""
        return parse(FastqVerification, self._http.request("POST", f"/fastq/{fastq_id}/verify"))

    def upload(
        self,
        path: str | Path,
        *,
        sample_id: uuid.UUID | str | None = None,
        sequencing_run_id: uuid.UUID | str | None = None,
        read_pair: str | None = None,
        expected_md5: str | None = None,
    ) -> FastqFile:
        """
        Register, upload and verify a gzipped FASTQ file in one call.

        The MD5 is computed locally (or taken from ``expected_md5``, e.g. from the sequencing
        provider's manifest) and the server checks the stored object against it.

        Raises:
            ChecksumMismatchError: the stored object does not match the expected MD5. The
                record stays in the workspace with status ``mismatch``.
        """
        file_path = Path(path)
        local_md5, size = file_md5(file_path)
        check_manifest(file_path, local_md5, expected_md5)
        registration = self.register(
            filename=file_path.name,
            size_bytes=size,
            expected_md5=local_md5,
            sample_id=sample_id,
            sequencing_run_id=sequencing_run_id,
            read_pair=read_pair,
        )
        with file_path.open("rb") as handle:
            self._http.storage_put(
                registration.upload_url, handle, upload_headers(registration, size)
            )
        verification = self.verify(registration.id)
        check_verification(file_path, local_md5, registration, verification)
        return self.get(registration.id)


# --- Shared with the async client ------------------------------------------------------------


def check_manifest(path: Path, local_md5: str, expected_md5: str | None) -> None:
    if expected_md5 is not None and expected_md5.lower() != local_md5:
        raise ChecksumMismatchError(
            f"{path.name}: local MD5 {local_md5} differs from expected {expected_md5}; "
            "nothing was uploaded"
        )


def upload_headers(registration: FastqRegistration, size: int) -> dict[str, str]:
    """The signed headers the server returned, plus the length of the body."""
    return {**registration.upload_headers, "Content-Length": str(size)}


def check_verification(
    path: Path,
    local_md5: str,
    registration: FastqRegistration,
    verification: FastqVerification,
) -> None:
    if verification.verification_status != FastqVerificationStatus.verified:
        raise ChecksumMismatchError(
            f"{path.name}: stored object MD5 {verification.computed_md5} does not match "
            f"{local_md5} (FASTQ {registration.id} marked {verification.verification_status})"
        )
