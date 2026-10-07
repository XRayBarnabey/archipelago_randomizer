import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.errors import AppError

logger = logging.getLogger("app")


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs full request URLs at INFO, which would include the Steam API key.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _startup_archipelago_sync() -> None:
    from app.api.deps import build_archipelago_sources
    from app.db import get_session_factory
    from app.services.archipelago_service import ArchipelagoService

    try:
        with get_session_factory()() as db:
            ArchipelagoService(db, build_archipelago_sources()).sync()
    except Exception:
        logger.exception("Startup Archipelago sync failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.archipelago_sync_enabled:
        threading.Thread(target=_startup_archipelago_sync, daemon=True).start()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Steam × Archipelago Game Picker", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={"error": "VALIDATION_ERROR", "message": "Requête invalide.", "details": details},
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error")
        return JSONResponse(
            status_code=500, content={"error": "INTERNAL_ERROR", "message": "Erreur interne du serveur."}
        )

    app.include_router(router, prefix="/api")
    return app


app = create_app()
