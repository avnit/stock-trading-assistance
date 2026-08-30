import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    created_at TEXT NOT NULL,
    thesis_summary TEXT NOT NULL,
    thesis_direction TEXT,
    full_report_path TEXT NOT NULL,
    inputs_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_ticker ON research(ticker);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    side TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    qty REAL NOT NULL,
    estimated_price REAL,
    estimated_notional REAL,
    rationale TEXT NOT NULL,
    research_id INTEGER,
    order_payload_json TEXT NOT NULL,
    strategy_template TEXT,
    legs_json TEXT,
    analysis_json TEXT,
    FOREIGN KEY (research_id) REFERENCES research(id)
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);

CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    broker TEXT NOT NULL,
    broker_order_id TEXT,
    fill_price REAL,
    fill_qty REAL,
    status TEXT NOT NULL,
    raw_response_json TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
CREATE INDEX IF NOT EXISTS idx_executions_ticket ON executions(ticket_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DB:
    def __init__(self, path: Path):
        self.path = path
        self._init()

    def _init(self) -> None:
        with self.conn() as c:
            c.executescript(SCHEMA)
            existing_cols = {r["name"] for r in c.execute("PRAGMA table_info(tickets)").fetchall()}
            for col in ("strategy_template", "legs_json", "analysis_json"):
                if col not in existing_cols:
                    c.execute(f"ALTER TABLE tickets ADD COLUMN {col} TEXT")

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def save_research(
        self,
        ticker: str,
        thesis_summary: str,
        thesis_direction: str | None,
        full_report_path: Path,
        inputs: dict[str, Any],
    ) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO research (ticker, created_at, thesis_summary, thesis_direction, "
                "full_report_path, inputs_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ticker.upper(),
                    utc_now(),
                    thesis_summary,
                    thesis_direction,
                    str(full_report_path),
                    json.dumps(inputs, default=str),
                ),
            )
            return int(cur.lastrowid)

    def latest_research(self, ticker: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM research WHERE ticker = ? ORDER BY id DESC LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
            return dict(row) if row else None

    def next_ticket_id(self) -> str:
        with self.conn() as c:
            row = c.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()
            return f"TKT-{int(row['n']) + 1:03d}"

    def save_ticket(
        self,
        ticket_id: str,
        ticker: str,
        side: str,
        asset_type: str,
        qty: float,
        estimated_price: float | None,
        estimated_notional: float | None,
        rationale: str,
        research_id: int | None,
        order_payload: dict[str, Any],
        strategy_template: str | None = None,
        legs: list[dict[str, Any]] | None = None,
        analysis: dict[str, Any] | None = None,
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO tickets (id, ticker, created_at, status, side, asset_type, qty, "
                "estimated_price, estimated_notional, rationale, research_id, order_payload_json, "
                "strategy_template, legs_json, analysis_json) "
                "VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket_id,
                    ticker.upper(),
                    utc_now(),
                    side,
                    asset_type,
                    qty,
                    estimated_price,
                    estimated_notional,
                    rationale,
                    research_id,
                    json.dumps(order_payload),
                    strategy_template,
                    json.dumps(legs) if legs is not None else None,
                    json.dumps(analysis, default=str) if analysis is not None else None,
                ),
            )

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            return dict(row) if row else None

    def list_tickets(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.conn() as c:
            if status:
                rows = c.execute(
                    "SELECT * FROM tickets WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM tickets ORDER BY created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def update_ticket_status(self, ticket_id: str, status: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))

    def block_pending_tickets(self) -> int:
        with self.conn() as c:
            cur = c.execute(
                "UPDATE tickets SET status = 'blocked' WHERE status = 'pending'"
            )
            return cur.rowcount

    def save_execution(
        self,
        ticket_id: str,
        broker: str,
        broker_order_id: str | None,
        fill_price: float | None,
        fill_qty: float | None,
        status: str,
        raw_response: dict[str, Any],
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO executions (ticket_id, executed_at, broker, broker_order_id, "
                "fill_price, fill_qty, status, raw_response_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket_id,
                    utc_now(),
                    broker,
                    broker_order_id,
                    fill_price,
                    fill_qty,
                    status,
                    json.dumps(raw_response, default=str),
                ),
            )
