"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.data_management import router as data_management_router
from app.api.routes.devices import router as devices_router
from app.api.routes.health import router as health_router
from app.api.routes.monitoring import router as monitoring_router
from app.api.routes.readings import router as readings_router
from app.api.routes.simulation import router as simulation_router
from app.core.config import settings
from app.services.simulation import simulation_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize scheduler infrastructure without starting simulation jobs."""
    simulation_service.initialize()
    try:
        yield
    finally:
        simulation_service.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The Stored Data export uses this header to distinguish an empty CSV
    # result from a successful download.  Browsers hide non-safelisted
    # response headers unless they are explicitly exposed to CORS clients.
    expose_headers=["X-Export-Record-Count", "Content-Disposition"],
)

app.include_router(health_router, prefix="/api")
app.include_router(devices_router, prefix="/api")
app.include_router(readings_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(data_management_router, prefix="/api")
app.include_router(simulation_router, prefix="/api")
app.include_router(monitoring_router)
