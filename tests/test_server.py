from fastapi.testclient import TestClient

from argo.server import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_config_endpoint_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGO_DATA_DIR", str(tmp_path))
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert "alpaca_paper" in body
    assert "max_notional_usd" in body


def test_execute_requires_exact_confirmation_string(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")

    from argo.config import get_settings
    from argo.db import DB

    db = DB(get_settings().db_path)
    db.save_ticket(
        ticket_id="TKT-001",
        ticker="AAPL",
        side="buy",
        asset_type="stock",
        qty=1,
        estimated_price=100,
        estimated_notional=100,
        rationale="x",
        research_id=None,
        order_payload={},
    )

    r = client.post("/tickets/TKT-001/execute", json={"confirmation": "wrong"})
    assert r.status_code == 400
    assert "APPROVE AAPL TKT-001" in r.json()["detail"]
