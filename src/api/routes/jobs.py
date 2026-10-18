"""Background Job Tracking Endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth import AuthenticatedUser, require_viewer
from src.api.jobs import job_manager
from src.api.schemas import JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Check Asynchronous Job Status",
)
async def get_job_status(
    job_id: str,
    current_user: AuthenticatedUser = Depends(require_viewer),
) -> JobStatusResponse:
    """Poll execution state, progress, and results of background training or forecasting jobs."""
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Background job '{job_id}' not found.",
        )

    return JobStatusResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        progress_pct=job.progress_pct,
        created_at=job.created_at,
        completed_at=job.completed_at,
        result=job.result,
        error=job.error,
    )
