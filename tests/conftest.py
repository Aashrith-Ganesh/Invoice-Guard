import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from scripts.seed import seed


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECK_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("CHECK_BEARER_KEYS", json.dumps({
        "test-owner": {"business_id": 1, "role": "owner"},
        "test-service": {"business_id": 1, "role": "service"},
        "other-owner": {"business_id": 2, "role": "owner"},
    }))
    monkeypatch.setenv("CHECK_SIMULATOR_SECRET", "test-webhook")
    monkeypatch.setenv("SARVAM_API_KEY", "")  # tests never reach Sarvam
    app = create_app()
    from app.database.base import Base

    Base.metadata.create_all(app.state.engine)
    seed(app.state.engine)
    with TestClient(app, headers={"Authorization": "Bearer test-owner"}) as client:
        yield client, app.state.engine


@pytest.fixture
def invoice():
    return {
        "invoice_number": "DEMO-100",
        "invoice_date": "2026-11-01",
        "acceptance_date": "2026-11-02",
        "written_agreement": False,
        "currency": "INR",
        "gstin": "99ZZZZZ0000Z0Z0",
        "legal_name": "Fictional Vendor 1",
        "bank_reference": "demo:vendor-1:current",
        "lines": [{"quantity": "2", "unit_price": "50.00"}],
        "subtotal": "100.00",
        "cgst_rate": "9",
        "sgst_rate": "9",
        "igst_rate": "0",
        "cgst": "9.00",
        "sgst": "9.00",
        "igst": "0.00",
        "tax_total": "18.00",
        "grand_total": "118.00",
    }
