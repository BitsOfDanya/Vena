from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.models import Base
from app.db.seed import seed_demo
from app.db.session import SessionLocal, engine
from app.domain.email import build_email_provider
from app.domain.ingest import refresh_predictions
from app.domain.predictions import get_prediction_source
from app.domain.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Manage application resources."""
    settings = get_settings()
    if settings.auth_enabled and len(settings.jwt_secret.encode()) < 32:
        raise RuntimeError("Set VENA_JWT_SECRET to at least 32 random bytes")
    Base.metadata.create_all(engine)
    if settings.seed_demo:
        session = SessionLocal()
        try:
            seed_demo(session)
            session.commit()
        finally:
            session.close()
    else:
        # Spatial demo layer is required for map mode on the stand even without action seed.
        from app.domain.spatial import ensure_demo_spatial

        session = SessionLocal()
        try:
            ensure_demo_spatial(session)
            session.commit()
        finally:
            session.close()
    if settings.ingest_on_startup:
        session = SessionLocal()
        try:
            refresh_predictions(
                session, settings, get_prediction_source(settings), build_email_provider(settings)
            )
            session.commit()
        finally:
            session.close()
    scheduler = build_scheduler(settings)
    if scheduler is not None:
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    return application


app = create_app()
