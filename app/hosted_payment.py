"""Local listener for the hosted simulator page and its public API."""

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.main import app as merchant_app


def hosted_only(backend: ASGIApp) -> ASGIApp:
    async def serve(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path, method = scope["path"], scope["method"]
            is_page = method in {"GET", "HEAD"} and (
                path in {"/app/pay.html", "/health"} or path.startswith("/app/assets/")
            )
            is_simulation = method == "POST" and path in {
                "/api/v1/simulated-payment/status", "/api/v1/simulated-payment/simulate",
            }
            if not (is_page or is_simulation):
                await PlainTextResponse("Not found", status_code=404)(scope, receive, send)
                return
        await backend(scope, receive, send)
    return serve


app = hosted_only(merchant_app)
