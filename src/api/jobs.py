"""Asynchronous job manager for background training, evaluation, and batch forecasting."""

import asyncio
import json
import traceback
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.logging import get_logger

logger = get_logger("job_manager")


@dataclass
class JobRecord:
    """State record for a tracked background execution."""
    job_id: str
    job_type: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED
    progress_pct: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def update_progress(self, progress: float) -> None:
        """Update progress percentage between 0 and 100."""
        self.progress_pct = max(0.0, min(100.0, float(progress)))

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary for API serialization."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "progress_pct": round(self.progress_pct, 2),
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    """Async job queue and lifecycle coordinator with persistent disk storage (FL-02)."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()
        self._store_dir = Path("./data/jobs")
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _persist_job(self, record: JobRecord) -> None:
        """Atomically persist job state to disk for multi-worker durability (FL-02)."""
        try:
            file_path = self._store_dir / f"{record.job_id}.json"
            data = record.to_dict()
            temp_path = self._store_dir / f"{record.job_id}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(file_path)
        except Exception as exc:
            logger.warning(f"Failed to persist job [{record.job_id}] state: {exc}")

    def _load_persisted_job(self, job_id: str) -> JobRecord | None:
        """Load job state from persistent disk store."""
        try:
            file_path = self._store_dir / f"{job_id}.json"
            if not file_path.exists():
                return None
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return JobRecord(
                job_id=data["job_id"],
                job_type=data["job_type"],
                status=data.get("status", "PENDING"),
                progress_pct=data.get("progress_pct", 0.0),
                created_at=datetime.fromisoformat(data["created_at"]),
                completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
                result=data.get("result"),
                error=data.get("error"),
            )
        except Exception as exc:
            logger.warning(f"Failed to read persisted job [{job_id}]: {exc}")
            return None

    async def submit_job(
        self,
        job_type: str,
        task_func: Callable[[JobRecord, Any], Coroutine[Any, Any, dict[str, Any]]],
        *args: Any,
        **kwargs: Any,
    ) -> JobRecord:
        """Register and dispatch a background coroutine."""
        job_id = f"JOB_{uuid.uuid4().hex[:12].upper()}"
        record = JobRecord(job_id=job_id, job_type=job_type)

        async with self._lock:
            self._jobs[job_id] = record
            self._persist_job(record)

        # Run in background event loop
        asyncio.create_task(self._run_job_wrapper(record, task_func, *args, **kwargs))
        logger.info(f"Dispatched background job [{job_id}] type={job_type}")
        return record

    async def _run_job_wrapper(
        self,
        record: JobRecord,
        task_func: Callable[[JobRecord, Any], Coroutine[Any, Any, dict[str, Any]]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Internal execution wrapper capturing timing, outputs, and unhandled exceptions."""
        record.status = "RUNNING"
        record.update_progress(5.0)
        self._persist_job(record)

        try:
            result = await task_func(record, *args, **kwargs)
            record.status = "COMPLETED"
            record.progress_pct = 100.0
            record.result = result
            record.completed_at = datetime.now(UTC)
            self._persist_job(record)
            logger.info(f"Background job [{record.job_id}] COMPLETED successfully.")
        except Exception as exc:
            record.status = "FAILED"
            record.error = str(exc)
            record.completed_at = datetime.now(UTC)
            self._persist_job(record)
            logger.error(
                f"Background job [{record.job_id}] FAILED: {exc}\n{traceback.format_exc()}"
            )

    async def get_job(self, job_id: str) -> JobRecord | None:
        """Retrieve job record by ID (checking memory and persistent disk store)."""
        async with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]

        # Multi-worker fallback: check persistent store (FL-02)
        persisted = self._load_persisted_job(job_id)
        if persisted:
            async with self._lock:
                self._jobs[job_id] = persisted
        return persisted

    async def list_jobs(self, limit: int = 50) -> list[JobRecord]:
        """List recent jobs combining in-memory records and persisted multi-worker files."""
        async with self._lock:
            # Check disk for any jobs created by parallel worker processes
            for path in self._store_dir.glob("JOB_*.json"):
                jid = path.stem
                if jid not in self._jobs:
                    job = self._load_persisted_job(jid)
                    if job:
                        self._jobs[jid] = job

            items = list(self._jobs.values())

        items.sort(key=lambda j: j.created_at, reverse=True)
        return items[:limit]


# Global job manager singleton
job_manager = JobManager()
