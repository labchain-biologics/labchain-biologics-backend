"""Pipeline outputs (VCF, BAM, MultiQC...)."""

from __future__ import annotations

import builtins
import hashlib
import os
import tempfile
import uuid
from pathlib import Path

from labchain.errors import ChecksumMismatchError
from labchain.models import OutputFileType, ResultDownload, ResultFile
from labchain.resources._base import Resource, parse, parse_list


class Results(Resource):
    def list(
        self,
        *,
        run_id: uuid.UUID | str | None = None,
        file_type: OutputFileType | str | None = None,
    ) -> builtins.list[ResultFile]:
        params = {"runId": run_id, "fileType": file_type}
        return parse_list(ResultFile, self._http.request("GET", "/results", params=params))

    def for_run(self, run_id: uuid.UUID | str) -> builtins.list[ResultFile]:
        """Outputs of one run, read from its output directory."""
        return parse_list(ResultFile, self._http.request("GET", f"/results/runs/{run_id}"))

    def download_url(self, output_id: uuid.UUID | str) -> ResultDownload:
        """A short-lived signed URL. Treat it as a secret until it expires."""
        data = self._http.request("GET", f"/results/{output_id}/download")
        return parse(ResultDownload, data)

    def download(self, output_id: uuid.UUID | str, dest: str | Path) -> Path:
        """
        Download a result file. ``dest`` is a file path, or an existing directory to save it
        under its own name. The MD5 is checked when the server knows it, and the file only
        appears at ``dest`` once complete.

        Raises:
            ChecksumMismatchError: the downloaded bytes do not match the recorded MD5; nothing
                is left at ``dest``.
        """
        link = self.download_url(output_id)
        target = download_target(dest, link)
        digest = hashlib.md5(usedforsecurity=False)
        fd, tmp_name = tempfile.mkstemp(prefix=".labchain-", dir=target.parent)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle, self._http.storage_get(link.download_url) as resp:
                for chunk in resp.iter_bytes():
                    digest.update(chunk)
                    handle.write(chunk)
            check_download(link, digest.hexdigest())
            tmp_path.replace(target)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return target


# --- Shared with the async client ------------------------------------------------------------


def download_target(dest: str | Path, link: ResultDownload) -> Path:
    """``dest`` itself, or the file's own name inside ``dest`` when it is a directory."""
    target = Path(dest)
    return target / Path(link.filename).name if target.is_dir() else target


def check_download(link: ResultDownload, md5: str) -> None:
    if link.md5 is not None and md5 != link.md5.lower():
        raise ChecksumMismatchError(
            f"{link.filename}: downloaded MD5 {md5} does not match recorded {link.md5}"
        )
