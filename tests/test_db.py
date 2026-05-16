from pathlib import Path

from argo.db import DB


def test_research_roundtrip(db: DB, tmp_path: Path):
    report = tmp_path / "AAPL.md"
    report.write_text("# AAPL thesis")
    rid = db.save_research(
        ticker="AAPL",
        thesis_summary="bullish on services growth",
        thesis_direction="bullish",
        full_report_path=report,
        inputs={"price": 200.0},
    )
    assert rid >= 1
    latest = db.latest_research("aapl")
    assert latest is not None
    assert latest["ticker"] == "AAPL"
    assert latest["thesis_direction"] == "bullish"
    assert latest["full_report_path"] == str(report)


def test_ticket_id_increments(db: DB):
    assert db.next_ticket_id() == "TKT-001"
    db.save_ticket(
        ticket_id="TKT-001",
        ticker="NVDA",
        side="buy",
        asset_type="stock",
        qty=1,
        estimated_price=500.0,
        estimated_notional=500.0,
        rationale="test",
        research_id=None,
        order_payload={"ticker": "NVDA"},
    )
    assert db.next_ticket_id() == "TKT-002"


def test_ticket_status_lifecycle(db: DB):
    db.save_ticket(
        ticket_id="TKT-001",
        ticker="NVDA",
        side="buy",
        asset_type="stock",
        qty=1,
        estimated_price=500.0,
        estimated_notional=500.0,
        rationale="test",
        research_id=None,
        order_payload={},
    )
    assert db.get_ticket("TKT-001")["status"] == "pending"
    db.update_ticket_status("TKT-001", "executed")
    assert db.get_ticket("TKT-001")["status"] == "executed"


def test_halt_blocks_pending_only(db: DB):
    db.save_ticket("TKT-001", "AAPL", "buy", "stock", 1, 100, 100, "x", None, {})
    db.save_ticket("TKT-002", "MSFT", "buy", "stock", 1, 200, 200, "x", None, {})
    db.update_ticket_status("TKT-002", "executed")
    blocked = db.block_pending_tickets()
    assert blocked == 1
    assert db.get_ticket("TKT-001")["status"] == "blocked"
    assert db.get_ticket("TKT-002")["status"] == "executed"


def test_save_execution(db: DB):
    db.save_ticket("TKT-001", "AAPL", "buy", "stock", 1, 100, 100, "x", None, {})
    db.save_execution(
        ticket_id="TKT-001",
        broker="alpaca",
        broker_order_id="order-abc",
        fill_price=99.5,
        fill_qty=1.0,
        status="filled",
        raw_response={"id": "order-abc", "status": "filled"},
    )
