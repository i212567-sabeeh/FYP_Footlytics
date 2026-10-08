from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.calibration import FRAME_HEADERS
from app.api.errors import register_error_handlers
from app.api.review import REVIEW_HEADERS
from app.api.router import api_router
from app.auth.passwords import dummy_password_hash
from app.core.config import Settings, get_settings
from app.database.session import create_database_engine, create_session_factory
from app.workers.queue import RQJobQueue


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        config.require_jwt_secret()
        dummy_password_hash()
        engine = create_database_engine(config.database_url)
        application.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            queue = getattr(application.state, "job_queue", None)
            if isinstance(queue, RQJobQueue):
                queue.close()
            engine.dispose()

    application = FastAPI(title=config.app_name, version="0.4.0", lifespan=lifespan)
    application.state.settings = config
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=[*FRAME_HEADERS, *REVIEW_HEADERS],
    )
    application.include_router(api_router, prefix=config.api_prefix)
    register_error_handlers(application)
    return application


app = create_app()
