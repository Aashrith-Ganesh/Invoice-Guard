import asyncio
import json
import os
import re
import selectors
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Business, Invoice, InvoiceValidation
from test_invoices import validate
from test_payments import approve, event, initiate


@pytest.fixture
def mcp_access(api):
    from app.core.config import Principal

    client, engine = api
    keys = client.app.state.settings.bearer_keys
    keys["audit-mcp"] = Principal(business_id=1, role="mcp")
    keys["other-mcp"] = Principal(business_id=2, role="mcp")
    with Session(engine) as session, session.begin():
        session.add(Business(id=2, name="Other tenant", cash_minor=10000))
    return client, engine


@pytest.mark.parametrize(("key", "status"), [
    ("", 401), ("invalid", 401), ("test-owner", 403), ("test-service", 403), ("audit-mcp", 200),
])
def test_mcp_authentication(mcp_access, key, status):
    client, _ = mcp_access
    assert client.get("/api/v1/mcp/access", headers={"Authorization": f"Bearer {key}"}).status_code == status


def test_read_only_credential_is_tenant_scoped_and_cannot_write(mcp_access, invoice):
    client, _ = mcp_access
    invoice_id = validate(mcp_access, invoice)["invoice_id"]
    url = f"/api/v1/invoices/{invoice_id}"
    tenant = {"Authorization": "Bearer audit-mcp"}
    other = {"Authorization": "Bearer other-mcp"}
    assert client.get(url, headers=tenant).status_code == 200
    assert client.get(url, headers=other).status_code == 404
    for path, data in (
        ("/api/v1/approvals", {"invoice_id": invoice_id}),
        ("/api/v1/approvals/confirm", {"token": "x" * 43}),
        ("/api/v1/payments/initiate", {"invoice_id": invoice_id, "approval_id": 1, "idempotency_key": "demo"}),
        ("/api/v1/invoices/validate", invoice),
        (f"{url}/revalidate", {}),
    ):
        assert client.post(path, headers=tenant, json=data).status_code == 403


def test_preview_runs_rules_without_persisting_or_accepting_trusted_facts(mcp_access, invoice):
    client, engine = mcp_access
    headers = {"Authorization": "Bearer audit-mcp"}
    url = "/api/v1/mcp/invoice-preview"
    clean = {key: value for key, value in invoice.items()
             if key not in {"bank_reference", "acceptance_date", "written_agreement"}}
    assert client.post(url, headers=headers, json=invoice).status_code == 422
    result = client.post(url, headers=headers, json=clean).json()
    assert result["overall_status"] == "HOLD"
    assert "invoice_id" not in result and "payout_permitted" not in result
    bad = client.post(url, headers=headers, json=clean | {"grand_total": "150.00"}).json()
    assert bad["overall_status"] == "BLOCK"
    assert "ARITHMETIC_GRAND_TOTAL" in bad["risk_indicators"]
    with Session(engine) as session:
        for record_type in (Invoice, InvoiceValidation, AuditLog):
            assert session.scalar(select(func.count()).select_from(record_type)) == 0
    assert validate(mcp_access, invoice)["overall_status"] == "PASS"


def test_tools_project_only_safe_response_fields():
    from app.mcp_server.server import build_server

    private = "demo-private-123456789012"

    def backend(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/payments/1"
        return httpx.Response(200, json={"payment_id": 1, "invoice_id": 4, "amount": "44.00",
                                        "currency": "INR", "status": "SUCCESS",
                                        "external_reference": private, "token": private})

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(backend)) as client:
        server = build_server(client)
        result = asyncio.run(server.call_tool("get_payment_status", {"payment_id": 1}))
    assert private not in str(result)
    assert "SUCCESS" in str(result)


def test_stdio_startup_discovery_and_calls(mcp_access, invoice):
    client, _ = mcp_access
    invoice_id = validate(mcp_access, invoice)["invoice_id"]
    payment = initiate(client, invoice_id, approve(client, invoice_id)).json()
    assert event(client, payment, "SUCCESS").status_code == 200
    environment = os.environ | {
        "CHECK_DATABASE_URL": client.app.state.settings.database_url,
        "CHECK_BEARER_KEYS": json.dumps({
            "audit-mcp": {"business_id": 1, "role": "mcp"},
            "other-mcp": {"business_id": 2, "role": "mcp"},
        }),
    }
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "app.mcp_server.server"]
    with subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "0"],
        cwd=root, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    ) as process:
        try:
            # Uvicorn reports the ephemeral port once its socket is ready.
            logs = b""
            with selectors.DefaultSelector() as select_output:
                select_output.register(process.stderr, selectors.EVENT_READ)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and process.poll() is None:
                    if not select_output.select(timeout=0.2):
                        continue
                    logs += os.read(process.stderr.fileno(), 4096)
                    match = re.search(rb"http://127\.0\.0\.1:\d+", logs)
                    if match:
                        origin = match.group().decode()
                        break
                else:
                    pytest.fail("Test backend did not start")

            failed = subprocess.run(command, cwd=root, timeout=10, capture_output=True,
                                    env=environment | {"CHECK_MCP_BASE_URL": origin,
                                                       "CHECK_MCP_SERVICE_TOKEN": "invalid-for-demo"})
            assert failed.returncode != 0 and not failed.stdout
            assert b"invalid-for-demo" not in failed.stderr

            async def exercise() -> None:
                for key in ("audit-mcp", "other-mcp"):
                    params = StdioServerParameters(
                        command=command[0], args=command[1:], cwd=root,
                        env={"CHECK_MCP_BASE_URL": origin, "CHECK_MCP_SERVICE_TOKEN": key},
                    )
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            lookup = await session.call_tool("get_invoice", {"invoice_id": invoice_id})
                            if key == "other-mcp":
                                assert lookup.isError
                                assert (await session.call_tool("get_payment_status",
                                                               {"payment_id": payment["payment_id"]})).isError
                                continue
                            assert lookup.structuredContent["invoice_id"] == invoice_id
                            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                            assert set(tools) == {"get_invoice", "get_validation_reasons", "get_invoice_priorities",
                                                  "get_payment_status", "validate_invoice"}
                            assert all(tool.annotations.readOnlyHint for tool in tools.values())
                            assert "invoice" in tools["validate_invoice"].inputSchema["properties"]
                            assert (await session.call_tool("get_payment_status", {"payment_id": 0})).isError
                            assert (await session.call_tool("initiate_payout", {})).isError
                            assert (await session.call_tool("confirm_approval", {})).isError
                            assert not (await session.call_tool("get_invoice_priorities", {})).isError
                            status = await session.call_tool("get_payment_status", {"payment_id": payment["payment_id"]})
                            assert status.structuredContent["status"] == "SUCCESS"
                            assert "external_reference" not in status.structuredContent

                            malformed = await session.call_tool("validate_invoice", {
                                "invoice": {"bank_reference": "synthetic-private-123456789012"},
                            })
                            assert malformed.isError
                            assert "synthetic-private-123456789012" not in str(malformed)
                            preview = await session.call_tool("validate_invoice", {"invoice": {}})
                            assert preview.structuredContent["overall_status"] == "HOLD"

            asyncio.run(asyncio.wait_for(exercise(), timeout=20))
        finally:
            process.terminate()
            process.wait(timeout=10)
