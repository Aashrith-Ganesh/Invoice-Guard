"""Stdio MCP process with a dedicated tenant-scoped Check Service credential."""

import os
import re
from ipaddress import ip_address
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from app.schemas.invoice import InvoicePreviewInput
from app.schemas.mcp import InvoiceSummary, PaymentSummary, PriorityList, ValidationPreview, ValidationSummary

RecordId = Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
PriorityLimit = Annotated[int, Field(strict=True, ge=1, le=100)]
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


class CheckServiceMCP(FastMCP):
    async def call_tool(self, name: str, arguments: dict):
        try:
            return await super().call_tool(name, arguments)
        except ToolError:
            # The SDK's tool errors can include rejected values or upstream diagnostics.
            raise ToolError("Request could not be completed. Check the tool schema and tenant access.") from None


def build_server(client: httpx.Client) -> FastMCP:
    server = CheckServiceMCP("PS3 Check Service")

    def exchange(method: str, path: str, **body):
        response = client.request(method, f"/api/v1{path}", **body)
        response.raise_for_status()
        return response.json()

    @server.tool(annotations=READ_ONLY)
    def get_invoice(invoice_id: RecordId) -> InvoiceSummary:
        """Read the stored invoice decision and approval eligibility."""
        return InvoiceSummary.model_validate(exchange("GET", f"/invoices/{invoice_id}"))

    @server.tool(annotations=READ_ONLY)
    def get_validation_reasons(invoice_id: RecordId) -> ValidationSummary:
        """Read stable validation codes and field names for an existing invoice."""
        return ValidationSummary.model_validate(exchange("GET", f"/invoices/{invoice_id}"))

    @server.tool(annotations=READ_ONLY)
    def get_invoice_priorities(limit: PriorityLimit = 20) -> PriorityList:
        """Read the leading entries in the current tenant's priority list."""
        return PriorityList.model_validate({"invoices": exchange("GET", "/invoices/priorities")[:limit]})

    @server.tool(annotations=READ_ONLY)
    def get_payment_status(payment_id: RecordId) -> PaymentSummary:
        """Read a recorded simulated payment status."""
        return PaymentSummary.model_validate(exchange("GET", f"/payments/{payment_id}"))

    @server.tool(annotations=READ_ONLY)
    def validate_invoice(invoice: InvoicePreviewInput) -> ValidationPreview:
        """Run a non-persisting validation preview on untrusted invoice fields."""
        fields = invoice.model_dump(mode="json", exclude_none=True)
        return ValidationPreview.model_validate(exchange("POST", "/mcp/invoice-preview", json=fields))

    return server


def backend_url(value: str) -> str:
    url = urlsplit(value)
    if (not url.hostname or url.username is not None or url.password is not None
            or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError("Set CHECK_MCP_BASE_URL to a Check Service origin.")
    if url.scheme == "https":
        return value.rstrip("/")
    try:
        loopback = ip_address(url.hostname).is_loopback
    except ValueError:
        loopback = url.hostname == "localhost"
    if url.scheme == "http" and loopback:
        return value.rstrip("/")
    raise ValueError("CHECK_MCP_BASE_URL requires HTTPS outside loopback.")


def main() -> None:
    token = os.getenv("CHECK_MCP_SERVICE_TOKEN", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._~+/-]{1,1024}={0,2}", token):
        raise SystemExit("Set CHECK_MCP_SERVICE_TOKEN to a dedicated MCP bearer credential.")
    try:
        url = backend_url(os.getenv("CHECK_MCP_BASE_URL", "http://127.0.0.1:8000"))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    with httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"},
                      timeout=10, follow_redirects=False, trust_env=False) as client:
        try:
            client.get("/api/v1/mcp/access").raise_for_status()
        except httpx.HTTPError:
            raise SystemExit("Check Service rejected MCP access or is unreachable.") from None
        build_server(client).run(transport="stdio")


if __name__ == "__main__":
    main()
