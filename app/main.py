"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.internal import router as internal_router
from app.api.public import router as public_router
from app.api.v1.router import router as v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    yield


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title="Payment Service",
        description="Merchant commerce / payment layer for blockchain payment aggregator",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(v1_router)
    app.include_router(internal_router)
    app.include_router(public_router)
    return app


app = create_app()


@app.get("/health", tags=["health"])
async def health():
    """Liveness/readiness probe."""
    return {"status": "ok"}
