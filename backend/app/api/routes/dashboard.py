"""Dashboard summary route derived from current master-device and reading data."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.schemas.readings import DashboardSummaryResponse
from app.services.dashboard import get_dashboard_summary


router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse, summary="Get current dashboard summary")
def read_dashboard_summary(database: Session = Depends(get_db)) -> DashboardSummaryResponse:
    """Return inventory, per-device current status, and latest data."""
    return get_dashboard_summary(database)
