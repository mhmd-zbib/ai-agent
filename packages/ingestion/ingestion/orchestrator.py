"""Pipeline orchestrator — backward compatibility shim.

The orchestration logic has moved to :mod:`ingestion.main`.
This module re-exports ``ingest`` and ``job_events`` unchanged so that
existing imports (tests, CLI, old API wrapper) continue to work without
modification.
"""

from __future__ import annotations

from ingestion.main import _JOB_DONE, _JOB_STORE, ingest, job_events

__all__ = ["ingest", "job_events", "_JOB_STORE", "_JOB_DONE"]
