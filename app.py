from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from studio.api import router
from studio.auth import ApplicationAuth
from studio.config import Settings
from studio.logging import configure_logging
from studio.services.generator import ImageGenerator
from studio.services.history import HistoryStore
from studio.services.jobs import GenerationQueue
from studio.services.profiles import CharacterProfileStore
from studio.services.references import ReferenceImageStore
from studio.services.registry import ModelRegistry


def create_app() -> FastAPI:
    configure_logging()
    settings = Settings.from_environment()
    auth = ApplicationAuth(
        settings.auth_token,
        settings.auth_session_ttl_seconds,
        settings.auth_enabled,
    )
    history_store = HistoryStore(settings)
    registry = ModelRegistry(settings)
    character_profiles = CharacterProfileStore(settings)
    reference_images = ReferenceImageStore(settings)
    generator = ImageGenerator(settings, history_store, reference_images)
    job_queue = GenerationQueue(
        generator,
        registry,
        settings.max_queue_size,
        job_retention_seconds=settings.job_retention_seconds,
        max_completed_jobs=settings.max_completed_jobs,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.require_cuda and settings.device != "cuda":
            raise RuntimeError("CUDA is required for this deployment but is not available")
        if settings.demo_warmup:
            generator.prepare(
                registry.get(None),
                include_ip_adapter=settings.demo_preload_ip_adapter,
            )
        job_queue.start()
        try:
            yield
        finally:
            job_queue.stop()

    application = FastAPI(title="Shikishi Studio", lifespan=lifespan)
    application.state.settings = settings
    application.state.auth = auth
    application.state.history_store = history_store
    application.state.model_registry = registry
    application.state.character_profiles = character_profiles
    application.state.reference_images = reference_images
    application.state.image_generator = generator
    application.state.job_queue = job_queue
    application.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

    @application.middleware("http")
    async def authentication(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if auth.is_public_path(request.url.path) or auth.is_authenticated(request):
            return await call_next(request)
        return auth.unauthorized_response(request)

    @application.get("/", response_class=HTMLResponse)
    def home(request: Request) -> Response:
        if not auth.is_authenticated(request):
            return RedirectResponse("/login", status_code=307)
        return HTMLResponse((settings.static_dir / "index.html").read_text(encoding="utf-8"))

    @application.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page() -> HTMLResponse:
        return auth.login_page()

    @application.post("/auth/login", include_in_schema=False)
    async def login(request: Request) -> Response:
        return await auth.login(request)

    application.include_router(router)
    return application


app = create_app()
