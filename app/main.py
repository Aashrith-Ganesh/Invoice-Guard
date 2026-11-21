from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api.v1 import approvals, documents, invoices, payments, webhooks
from app.core.config import Settings
from app.core.masking import install_account_masking
from app.database.engine import make_engine
from app.integrations.sarvam.extractor import DemoExtractor
from app.integrations.sarvam.prism import HeuristicPrism
from app.integrations.sarvam.translate import SarvamTranslator

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def create_app() -> FastAPI:
    install_account_masking()
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        application.state.engine.dispose()

    application = FastAPI(title="Accounts Payable Check Service", lifespan=lifespan)
    application.state.settings = Settings.from_env()
    application.state.engine = make_engine(application.state.settings.database_url)
    application.state.extractor = DemoExtractor()
    application.state.rater = HeuristicPrism()
    key = application.state.settings.sarvam_api_key
    application.state.translator = SarvamTranslator(key) if key else None
    for routes in (invoices, approvals, payments, webhooks, documents):
        application.include_router(routes.router, prefix="/api/v1")

    @application.exception_handler(RequestValidationError)
    async def invalid_input(_: Request, error: RequestValidationError) -> JSONResponse:
        fields = [{"location": item["loc"], "type": item["type"]} for item in error.errors()]
        return JSONResponse(status_code=422, content={"error": {
            "code": "INVALID_INPUT", "message": "Request does not match the schema.", "fields": fields,
        }})

    @application.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail
        if not isinstance(detail, dict):
            detail = {"code": "HTTP_ERROR", "message": str(detail)}
        return JSONResponse(status_code=error.status_code, content={"error": detail}, headers=error.headers)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if FRONTEND.is_dir():
        application.mount("/app", StaticFiles(directory=FRONTEND, html=True), name="frontend")

        @application.get("/", include_in_schema=False)
        def home() -> RedirectResponse:
            return RedirectResponse("/app/")

    return application


app = create_app()
