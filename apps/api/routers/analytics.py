"""FastAPI router exposing server-side QA dashboard aggregates."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_current_principal
from packages.contracts.analytics import DashboardResponse
from packages.contracts.security import Principal
from packages.infrastructure.database.repositories.analytics_repository import (
    SqlAlchemyAnalyticsRepository,
)
from packages.infrastructure.database.session import get_db_session
from packages.observability.logging import get_logger

logger = get_logger("api.analytics")

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

MAX_WINDOW_DAYS = 400


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Agent, campaign and team-lead QA dashboard for a date window",
)
async def get_dashboard(
    granularity: Annotated[
        Literal["daily", "weekly", "monthly"], Query(description="Time bucket size")
    ] = "daily",
    days: Annotated[int, Query(ge=1, le=MAX_WINDOW_DAYS)] = 30,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    repeat_offence_window_days: Annotated[int, Query(ge=1, le=90)] = 7,
    repeat_offence_threshold: Annotated[int, Query(ge=2, le=50)] = 3,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> DashboardResponse:
    """Aggregate gate decisions for the caller's tenant.

    Aggregation happens in the database layer rather than the browser, so figures are correct over
    the whole window instead of over whatever page the UI last fetched.
    """
    window_to = date_to or datetime.now(UTC)
    window_from = date_from or (window_to - timedelta(days=days))

    if window_from > window_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from must not be after date_to.",
        )
    if (window_to - window_from).days > MAX_WINDOW_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Requested window exceeds the {MAX_WINDOW_DAYS} day maximum.",
        )

    repository = SqlAlchemyAnalyticsRepository(session)
    dashboard = await repository.get_dashboard(
        tenant_id=principal.tenant_id,
        date_from=window_from,
        date_to=window_to,
        granularity=granularity,
        repeat_offence_window_days=repeat_offence_window_days,
        repeat_offence_threshold=repeat_offence_threshold,
    )
    return DashboardResponse(**dashboard)
