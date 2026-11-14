"""Health-check endpoint."""

from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Report that the API service is available."""
    return {"status": "success", "message": "Smart Campus API is healthy"}
