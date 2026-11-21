from uuid import uuid4

from app.api import document_routes
from app.agent_framework import orchestrator


def test_vendor_chat_uses_business_scope(api, monkeypatch):
    client, _ = api
    async def chat(payload):
        if payload["messages"][-1]["role"] == "tool":
            return {"content": "Lookup complete"}
        return {"tool_calls": [{"id": "v1", "function": {
            "name": "get_vendor", "arguments": '{"vendor_id":1}'}}]}
    monkeypatch.setattr(orchestrator, "complete_chat", chat)
    body = {"agent_id": "vendor_agent", "input": {"content": "Find vendor 1"}}
    run = client.post("/api/v1/agent-runs", json=body)
    assert run.json()["outputs"][0]["data"]["vendor"]["id"] == 1
    assert client.get("/api/v1/agent-runs", headers={"Authorization": ""}).status_code == 401


def test_document_job_requires_ownership(api, monkeypatch):
    client, engine = api
    from app.models import Business
    from sqlalchemy.orm import Session
    job_id = uuid4()
    calls = []
    async def provider(method, path, **kwargs):
        calls.append(path)
        return {"job_id": str(job_id), "status": "pending"}
    monkeypatch.setattr(document_routes, "sarvam_request", provider)
    path = "/api/agents/sarvam/invoices"
    response = client.post(path, files={"file": ("test.pdf", b"%PDF-synthetic")})
    assert response.status_code == 202
    assert client.get(f"{path}/{job_id}").json()["status"] == "pending"
    with Session(engine) as session:
        session.add(Business(id=2, name="Second synthetic tenant", cash_minor=0))
        session.commit()
    assert client.get(f"{path}/{job_id}", headers={"Authorization": "Bearer other-owner"}).status_code == 404
    assert len(calls) == 2
