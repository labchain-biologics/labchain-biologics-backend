"""Samples (LIMS records)."""

from __future__ import annotations

import builtins
import uuid
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from labchain.models import (
    OmicsModality,
    QcStatus,
    Sample,
    SampleAssay,
    SampleCreate,
    SampleImportResult,
    SampleStatus,
    SampleUpdate,
)
from labchain.resources._base import Resource, build, paginate, parse, parse_list

MAX_PAGE_SIZE = 1000


class Samples(Resource):
    def list(
        self,
        *,
        modality: OmicsModality | str | None = None,
        assay: SampleAssay | str | None = None,
        status: SampleStatus | str | None = None,
        qc_status: QcStatus | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> builtins.list[Sample]:
        """One page of samples, newest first. Use :meth:`iter` to walk all of them."""
        params = {
            "modality": modality,
            "assay": assay,
            "status": status,
            "qcStatus": qc_status,
            "limit": limit,
            "offset": offset,
        }
        return parse_list(Sample, self._http.request("GET", "/samples", params=params))

    def iter(
        self,
        *,
        modality: OmicsModality | str | None = None,
        assay: SampleAssay | str | None = None,
        status: SampleStatus | str | None = None,
        qc_status: QcStatus | str | None = None,
        page_size: int = MAX_PAGE_SIZE,
    ) -> Iterator[Sample]:
        """Every matching sample, fetched page by page."""
        return paginate(
            lambda limit, offset: self.list(
                modality=modality,
                assay=assay,
                status=status,
                qc_status=qc_status,
                limit=limit,
                offset=offset,
            ),
            page_size,
        )

    def get(self, sample_id: uuid.UUID | str) -> Sample:
        return parse(Sample, self._http.request("GET", f"/samples/{sample_id}"))

    def create(self, sample: SampleCreate | None = None, /, **fields: Any) -> Sample:
        """Register a sample: ``create(sample_code="S-001", modality="genomics")``."""
        body = build(SampleCreate, sample, fields).to_json()
        return parse(Sample, self._http.request("POST", "/samples", json=body))

    def update(
        self, sample_id: uuid.UUID | str, patch: SampleUpdate | None = None, /, **fields: Any
    ) -> Sample:
        """Change only the given fields: ``update(sample_id, qc_status="pass")``."""
        body = build(SampleUpdate, patch, fields).to_json(exclude_unset=True)
        return parse(Sample, self._http.request("PATCH", f"/samples/{sample_id}", json=body))

    def delete(self, sample_id: uuid.UUID | str) -> None:
        self._http.request("DELETE", f"/samples/{sample_id}")

    def bulk_update(
        self, patches: Mapping[uuid.UUID | str, SampleUpdate | Mapping[str, Any]]
    ) -> builtins.list[Sample]:
        """Update several samples in one request: ``{sample_id: {"qc_status": "pass"}}``."""
        data = self._http.request("PATCH", "/samples/bulk", json=bulk_patch_body(patches))
        return parse_list(Sample, data)

    def bulk_delete(self, sample_ids: Iterable[uuid.UUID | str]) -> int:
        """Delete several samples; returns how many were deleted."""
        body = {"ids": [str(sample_id) for sample_id in sample_ids]}
        data = self._http.request("DELETE", "/samples/bulk", json=body)
        return int(data["deleted"])

    def import_csv(self, path: str | Path) -> SampleImportResult:
        """
        Import samples from a UTF-8 CSV whose columns are sample fields (``sampleCode`` or
        ``sample_code``...). Existing or duplicated sample codes are skipped and reported.
        """
        csv_path = Path(path)
        with csv_path.open("rb") as handle:
            files = {"file": (csv_path.name, handle, "text/csv")}
            data = self._http.request("POST", "/samples/import", files=files)
        return parse(SampleImportResult, data)


# --- Shared with the async client ------------------------------------------------------------


def bulk_patch_body(
    patches: Mapping[uuid.UUID | str, SampleUpdate | Mapping[str, Any]],
) -> dict[str, Any]:
    items = []
    for sample_id, patch in patches.items():
        model = patch if isinstance(patch, SampleUpdate) else SampleUpdate(**patch)
        items.append({"id": str(sample_id), "patch": model.to_json(exclude_unset=True)})
    return {"items": items}
