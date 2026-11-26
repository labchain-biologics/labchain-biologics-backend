"""
Typed models of the Titerlane Biologics API.

They mirror the server's public OpenAPI contract (``openapi.json``), not its code: the SDK never
imports the server. Python attributes are snake_case; the JSON sent and received is camelCase.
Response models ignore fields they do not know, so a newer server does not break older SDKs.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# --- Enums ---------------------------------------------------------------------------------


class Role(enum.StrEnum):
    bioinformatics_lead = "bioinformatics_lead"
    lab_technician = "lab_technician"


class OmicsModality(enum.StrEnum):
    genomics = "genomics"
    transcriptomics = "transcriptomics"
    epigenomics = "epigenomics"
    proteomics = "proteomics"
    metabolomics = "metabolomics"
    multiomics = "multiomics"


class SampleAssay(enum.StrEnum):
    wgs = "wgs"
    exome = "exome"
    targeted_panel = "targeted_panel"
    bulk_rna = "bulk_rna"
    single_cell_rna = "single_cell_rna"
    atac_seq = "atac_seq"
    methylation = "methylation"
    amplicon_16s = "amplicon_16s"
    metagenomics = "metagenomics"


class SampleType(enum.StrEnum):
    tumor = "tumor"
    normal = "normal"
    control = "control"
    environmental = "environmental"
    cell_line = "cell_line"


class SampleStatus(enum.StrEnum):
    registered = "registered"
    fastq_received = "fastq_received"
    processing = "processing"
    completed = "completed"


class QcStatus(enum.StrEnum):
    pending = "pending"
    pass_ = "pass"
    fail = "fail"
    warn = "warn"


class JobStatus(enum.StrEnum):
    pending = "pending"
    submitted = "submitted"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled)


class OutputFileType(enum.StrEnum):
    vcf = "vcf"
    bam = "bam"
    multiqc = "multiqc"
    other = "other"


class FastqVerificationStatus(enum.StrEnum):
    pending = "pending"
    verified = "verified"
    mismatch = "mismatch"


# --- Base classes --------------------------------------------------------------------------


class ApiModel(BaseModel):
    """A response from the API."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class RequestModel(BaseModel):
    """A request body. Unknown fields are rejected so typos fail before reaching the server."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    def to_json(self, *, exclude_unset: bool = False) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True, exclude_unset=exclude_unset)


# --- Auth and users ------------------------------------------------------------------------


class Token(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MembershipSummary(ApiModel):
    workspace_id: uuid.UUID
    slug: str
    name: str
    role: Role


class User(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime
    memberships: list[MembershipSummary] = Field(default_factory=list)


class ApiToken(ApiModel):
    id: uuid.UUID
    name: str
    token_prefix: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiTokenCreated(ApiToken):
    token: str = Field(repr=False)


class ApiTokenCreate(RequestModel):
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int | None = Field(default=None, ge=1)


# --- Workspaces ----------------------------------------------------------------------------


class Workspace(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    role: Role
    created_at: datetime


SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"


class WorkspaceCreate(RequestModel):
    slug: str = Field(min_length=1, max_length=64, pattern=SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=255)


class Member(ApiModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    joined_at: datetime


class MemberCreate(RequestModel):
    email: str
    role: Role = Role.lab_technician


class MemberUpdate(RequestModel):
    role: Role


# --- Samples -------------------------------------------------------------------------------


class _SampleFields(BaseModel):
    """Optional LIMS fields shared by sample creation, update and reads."""

    assay: SampleAssay | None = None
    sample_type: SampleType | None = None
    organism: str | None = None
    tissue_type: str | None = None
    collection_date: str | None = None
    patient_id: str | None = None
    biobank_id: str | None = None
    project_code: str | None = None
    paired_group: str | None = None
    platform: str | None = None
    library_prep_kit: str | None = None
    index_id: str | None = None
    target_panel: str | None = None
    rin_din: float | None = None
    concentration_ng_ul: float | None = None
    a260280: float | None = None
    volume_ul: float | None = None
    qc_notes: str | None = None
    notes: str | None = None


class SampleCreate(RequestModel, _SampleFields):
    sample_code: str = Field(min_length=1, max_length=128)
    modality: OmicsModality
    qc_status: QcStatus = QcStatus.pending
    metadata: dict[str, Any] = Field(default_factory=dict)


class SampleUpdate(RequestModel, _SampleFields):
    """Partial update: only the fields you set are sent."""

    sample_code: str | None = None
    modality: OmicsModality | None = None
    qc_status: QcStatus | None = None
    metadata: dict[str, Any] | None = None


class Sample(ApiModel, _SampleFields):
    id: uuid.UUID
    workspace: str
    sample_code: str
    modality: OmicsModality
    status: SampleStatus
    qc_status: QcStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class SampleImportResult(ApiModel):
    created: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
    samples: list[Sample] = Field(default_factory=list)


# --- Sequencing runs and FASTQ -------------------------------------------------------------


class SequencingRunCreate(RequestModel):
    run_name: str = Field(min_length=1, max_length=255)
    instrument: str | None = None
    flowcell_id: str | None = None
    read_length: str | None = None


class SequencingRun(ApiModel):
    id: uuid.UUID
    workspace: str
    run_name: str
    instrument: str | None = None
    flowcell_id: str | None = None
    read_length: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime


class FastqRegisterRequest(RequestModel):
    filename: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(default=0, ge=0)
    expected_md5: str | None = None
    sample_id: uuid.UUID | None = None
    sequencing_run_id: uuid.UUID | None = None
    read_pair: str | None = None
    s3_key: str | None = None


class FastqRegistration(ApiModel):
    id: uuid.UUID
    workspace: str
    filename: str
    s3_key: str
    size_bytes: int
    expected_md5: str | None = None
    verification_status: FastqVerificationStatus
    upload_url: str = Field(repr=False)
    created_at: datetime


class FastqVerification(ApiModel):
    id: uuid.UUID
    expected_md5: str | None = None
    computed_md5: str
    verification_status: FastqVerificationStatus


class FastqFile(ApiModel):
    id: uuid.UUID
    workspace: str
    filename: str
    s3_key: str
    size_bytes: int
    expected_md5: str | None = None
    computed_md5: str | None = None
    verification_status: FastqVerificationStatus
    sample_id: uuid.UUID | None = None
    sequencing_run_id: uuid.UUID | None = None
    read_pair: str | None = None
    created_at: datetime


# --- Pipelines, runs and results -----------------------------------------------------------


class Pipeline(ApiModel):
    id: str
    name: str
    description: str
    version: str
    versions: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    assays: list[SampleAssay] = Field(default_factory=list)
    default_params: dict[str, Any] = Field(default_factory=dict)
    nf_core: bool = True


class RunCreate(RequestModel):
    pipeline_id: str = Field(min_length=1)
    pipeline_version: str = "latest"
    sample_ids: list[uuid.UUID] = Field(default_factory=list)
    sequencing_run_id: uuid.UUID | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ResultFile(ApiModel):
    id: uuid.UUID
    file_type: OutputFileType
    filename: str
    s3_key: str
    size_bytes: int
    md5: str | None = None
    sample_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    download_url: str | None = Field(default=None, repr=False)
    created_at: datetime


class Run(ApiModel):
    id: uuid.UUID
    workspace: str
    pipeline_id: str
    pipeline_name: str
    pipeline_version: str
    status: JobStatus
    execution_submitted: bool = Field(
        description="False when pipeline execution is disabled on the server: the run never runs"
    )
    sequencing_run_id: uuid.UUID | None = None
    sample_ids: list[uuid.UUID] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    aws_batch_job_id: str | None = None
    nextflow_run_name: str | None = None
    work_dir: str | None = None
    output_dir: str | None = None
    samplesheet_uri: str | None = None
    progress: dict[str, Any] = Field(default_factory=dict)
    launched_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_files: list[ResultFile] = Field(default_factory=list)


class RunLogLine(ApiModel):
    index: int
    timestamp: datetime | None = None
    message: str


class ResultDownload(ApiModel):
    id: uuid.UUID
    file_type: OutputFileType
    filename: str
    download_url: str = Field(repr=False)
    expires_in: int
    md5: str | None = None
