from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api import agent_routes, document_routes
from app.api.v1 import approvals, invoices, mcp_access, payments, webhooks
from app.core.config import Settings
from app.core.masking import install_account_masking
from app.database.engine import make_engine


def create_app() -> FastAPI:
    install_account_masking()
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        application.state.engine.dispose()

    application = FastAPI(title="Accounts Payable Check Service", lifespan=lifespan)
    application.state.settings = Settings.from_env()
    application.state.engine = make_engine(application.state.settings.database_url)
    application.include_router(agent_routes.router)
    application.include_router(document_routes.router)
    for routes in (invoices, approvals, payments, webhooks, mcp_access):
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

    return application


app = create_app()
