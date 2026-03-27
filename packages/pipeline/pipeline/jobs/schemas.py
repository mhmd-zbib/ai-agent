"""Pydantic schemas for pipeline job responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from shared.models.job import JobStatus


class JobResponse(BaseModel):
    """Serialized view of a PipelineJob returned by the API."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Unique job identifier")
    status: JobStatus = Field(description="Current job status")
    document_path: str = Field(description="Path or key of the document being processed")
    created_at: datetime = Field(description="UTC timestamp when the job was created")
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the job reached a terminal state",
    )
    error: str | None = Field(default=None, description="Error message if the job failed")


class JobListResponse(BaseModel):
    """Paginated list of pipeline jobs."""

    model_config = ConfigDict(extra="forbid")

    items: list[JobResponse] = Field(description="Job records for the current page")
    total: int = Field(ge=0, description="Total number of jobs across all pages")
    page: int = Field(ge=1, description="Current page number (1-based)")
    page_size: int = Field(ge=1, description="Number of items per page")
