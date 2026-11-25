"""Pipeline, FastQ, run, and result Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field

from app.models.pipeline import (
    FastqVerificationStatus,
    JobStatus,
    OutputFileType,
)
from app.models.sample import SampleAssay

# Prefer ORM column `metadata_json` over SQLAlchemy's reserved `.metadata` (MetaData).
_METADATA_ALIASES = AliasChoices("metadata_json", "metadata")


class PipelineCatalogItem(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    id: str
    name: str
    description: str
    version: str = Field(description="Default revision used when 'latest' is requested")
    versions: list[str] = Field(default_factory=list, description="Revisions allowed at launch")
    nf_core: bool = Field(alias="nfCore", default=True)
    categories: list[str] = Field(default_factory=list)
    assays: list[SampleAssay] = Field(
        default_factory=list, description="Sample assays this pipeline is suggested for"
    )
    default_params: dict[str, Any] = Field(default_factory=dict, alias="defaultParams")


class FastqRegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    filename: str = Field(min_length=1, max_length=512)
    s3_key: str | None = Field(default=None, alias="s3Key", max_length=1024)
    size_bytes: int = Field(default=0, alias="sizeBytes", ge=0)
    expected_md5: str | None = Field(default=None, alias="expectedMd5", max_length=32)
    sample_id: uuid.UUID | None = Field(default=None, alias="sampleId")
    sequencing_run_id: uuid.UUID | None = Field(default=None, alias="sequencingRunId")
    read_pair: str | None = Field(default=None, alias="readPair", max_length=8)


class FastqRegisterResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

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
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

    id: uuid.UUID
    expected_md5: str | None = Field(default=None, alias="expectedMd5")
    computed_md5: str = Field(alias="computedMd5")
    verification_status: FastqVerificationStatus = Field(alias="verificationStatus")


class FastqRead(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

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
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    pipeline_id: str = Field(alias="pipelineId", min_length=1)
    pipeline_version: str = Field(default="latest", alias="pipelineVersion")
    sample_ids: list[uuid.UUID] = Field(default_factory=list, alias="sampleIds")
    sequencing_run_id: uuid.UUID | None = Field(default=None, alias="sequencingRunId")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="nf-core parameters (string, number or boolean). input/outdir are reserved.",
    )


class RunOutputFileRead(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

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
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

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
    output_dir: str | None = Field(default=None, alias="outputDir")
    samplesheet_uri: str | None = Field(default=None, alias="samplesheetUri")
    progress: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Execution progress from Nextflow weblog events: processesSubmitted, "
            "processesCompleted, processesFailed, currentProcess, lastEvent, errorMessage"
        ),
    )
    launched_by: uuid.UUID | None = Field(default=None, alias="launchedBy")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")
    output_files: list[RunOutputFileRead] = Field(default_factory=list, alias="outputFiles")

    @computed_field(  # type: ignore[prop-decorator]  # mypy does not support decorated properties
        alias="executionSubmitted",
        description=(
            "True when the run was submitted to an executor (AWS Batch). False when pipeline "
            "execution is disabled on this instance: the run is recorded but never executed "
            "and stays pending"
        ),
    )
    @property
    def execution_submitted(self) -> bool:
        return self.aws_batch_job_id is not None


class ResultDownloadResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    id: uuid.UUID
    file_type: OutputFileType = Field(alias="fileType")
    filename: str
    download_url: str = Field(alias="downloadUrl")
    expires_in: int = Field(alias="expiresIn")
    md5: str | None = None


class SequencingRunCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    run_name: str = Field(alias="runName", min_length=1, max_length=255)
    instrument: str | None = Field(default=None, max_length=128)
    flowcell_id: str | None = Field(default=None, alias="flowcellId", max_length=128)
    read_length: str | None = Field(
        default=None, alias="readLength", max_length=32, description="e.g. '2x150'"
    )


class SequencingRunRead(SequencingRunCreate):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True,
        populate_by_name=True,
        from_attributes=True,
    )

    id: uuid.UUID
    workspace: str
    created_by: uuid.UUID | None = Field(default=None, alias="createdBy")
    created_at: datetime = Field(alias="createdAt")


class RunLogLine(BaseModel):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    index: int = Field(description="0-based position in the run log; use it as a cursor")
    timestamp: datetime | None = None
    message: str


class WeblogEvent(BaseModel):
    """Payload Nextflow posts with ``-with-weblog`` (only the fields the API uses)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    event: str = Field(max_length=64)
    run_name: str | None = Field(default=None, alias="runName")
    run_id: str | None = Field(default=None, alias="runId")
    utc_time: datetime | None = Field(default=None, alias="utcTime")
    trace: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
