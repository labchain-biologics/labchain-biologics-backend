"""Pipeline, FastQ, run, and result Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.models.pipeline import (
    FastqVerificationStatus,
    JobStatus,
    OutputFileType,
)

# Prefer ORM column `metadata_json` over SQLAlchemy's reserved `.metadata` (MetaData).
_METADATA_ALIASES = AliasChoices("metadata_json", "metadata")


class PipelineCatalogItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str
    version: str
    nf_core: bool = Field(alias="nfCore", default=True)
    categories: list[str] = Field(default_factory=list)
    default_params: dict[str, Any] = Field(default_factory=dict, alias="defaultParams")


class FastqRegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filename: str = Field(min_length=1, max_length=512)
    s3_key: str | None = Field(default=None, alias="s3Key", max_length=1024)
    size_bytes: int = Field(default=0, alias="sizeBytes", ge=0)
    expected_md5: str | None = Field(default=None, alias="expectedMd5", max_length=32)
    sample_id: uuid.UUID | None = Field(default=None, alias="sampleId")
    sequencing_run_id: uuid.UUID | None = Field(default=None, alias="sequencingRunId")
    read_pair: str | None = Field(default=None, alias="readPair", max_length=8)


class FastqRegisterResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    filename: str
    s3_key: str = Field(alias="s3Key")
    size_bytes: int = Field(alias="sizeBytes")
    expected_md5: str | None = Field(default=None, alias="expectedMd5")
    verification_status: FastqVerificationStatus = Field(alias="verificationStatus")
    upload_url: str = Field(alias="uploadUrl")
    workspace: str
    created_at: datetime = Field(alias="createdAt")


class FastqVerifyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    expected_md5: str | None = Field(default=None, alias="expectedMd5")
    computed_md5: str = Field(alias="computedMd5")
    verification_status: FastqVerificationStatus = Field(alias="verificationStatus")


class FastqRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    filename: str
    s3_key: str = Field(alias="s3Key")
    size_bytes: int = Field(alias="sizeBytes")
    expected_md5: str | None = Field(default=None, alias="expectedMd5")
    computed_md5: str | None = Field(default=None, alias="computedMd5")
    verification_status: FastqVerificationStatus = Field(alias="verificationStatus")
    sample_id: uuid.UUID | None = Field(default=None, alias="sampleId")
    sequencing_run_id: uuid.UUID | None = Field(default=None, alias="sequencingRunId")
    read_pair: str | None = Field(default=None, alias="readPair")
    workspace: str
    created_at: datetime = Field(alias="createdAt")


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pipeline_id: str = Field(alias="pipelineId", min_length=1)
    pipeline_version: str = Field(default="latest", alias="pipelineVersion")
    sample_ids: list[uuid.UUID] = Field(default_factory=list, alias="sampleIds")
    sequencing_run_id: uuid.UUID | None = Field(default=None, alias="sequencingRunId")
    parameters: dict[str, Any] = Field(default_factory=dict)
    run_name: str | None = Field(default=None, alias="runName", max_length=255)


class RunOutputFileRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    file_type: OutputFileType = Field(alias="fileType")
    filename: str
    s3_key: str = Field(alias="s3Key")
    size_bytes: int = Field(alias="sizeBytes")
    md5: str | None = None
    sample_id: uuid.UUID | None = Field(default=None, alias="sampleId")
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=_METADATA_ALIASES,
        serialization_alias="metadata",
    )
    download_url: str | None = Field(default=None, alias="downloadUrl")
    created_at: datetime = Field(alias="createdAt")


class PipelineJobRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    workspace: str
    pipeline_id: str = Field(alias="pipelineId")
    pipeline_name: str = Field(alias="pipelineName")
    pipeline_version: str = Field(alias="pipelineVersion")
    status: JobStatus
    sequencing_run_id: uuid.UUID | None = Field(default=None, alias="sequencingRunId")
    sample_ids: list[Any] = Field(default_factory=list, alias="sampleIds")
    parameters: dict[str, Any] = Field(default_factory=dict)
    aws_batch_job_id: str | None = Field(default=None, alias="awsBatchJobId")
    nextflow_run_name: str | None = Field(default=None, alias="nextflowRunName")
    work_dir: str | None = Field(default=None, alias="workDir")
    launched_by: uuid.UUID | None = Field(default=None, alias="launchedBy")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    output_files: list[RunOutputFileRead] = Field(default_factory=list, alias="outputFiles")


class ResultDownloadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    file_type: OutputFileType = Field(alias="fileType")
    filename: str
    download_url: str = Field(alias="downloadUrl")
    expires_in: int = Field(alias="expiresIn")
    md5: str | None = None
