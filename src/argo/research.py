from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

MAX_SECTION_CHARS = 12_000


@dataclass
class CompanySnapshot:
    ticker: str
    name: str | None
    description: str | None
    price: float | None
    sma_50: float | None
    sma_200: float | None
    return_6mo_pct: float | None
    last_close_date: str | None
    fundamentals_rows: list[dict[str, Any]] = field(default_factory=list)
    sections_10k: dict[str, str] = field(default_factory=dict)
    filing_accession: str | None = None
    filing_date: str | None = None

    def to_context(self) -> str:
        parts = [f"## Snapshot for {self.ticker}", f"Name: {self.name or 'unknown'}"]
        if self.description:
            parts.append(f"Description: {self.description}")
        parts.append("")
        parts.append("## Price")
        parts.append(f"- Last close: {self.price} (as of {self.last_close_date})")
        parts.append(f"- 50-day SMA: {self.sma_50}")
        parts.append(f"- 200-day SMA: {self.sma_200}")
        parts.append(f"- 6-month return: {self.return_6mo_pct}%")
        parts.append("")
        if self.fundamentals_rows:
            parts.append("## Fundamentals (last 8 reported quarters/fiscal periods)")
            for row in self.fundamentals_rows:
                line = ", ".join(f"{k}={v}" for k, v in row.items())
                parts.append(f"- {line}")
            parts.append("")
        if self.sections_10k:
            parts.append(
                f"## 10-K excerpts (accession {self.filing_accession}, filed {self.filing_date})"
            )
            for title, body in self.sections_10k.items():
                parts.append(f"### {title}")
                parts.append(body[:MAX_SECTION_CHARS])
                parts.append("")
        return "\n".join(parts)


def fetch_price_snapshot(ticker: str) -> dict[str, Any]:
    import yfinance as yf  # imported lazily to keep CLI startup snappy

    t = yf.Ticker(ticker)
    hist = t.history(period="1y", auto_adjust=False)
    if hist.empty:
        return {
            "price": None,
            "sma_50": None,
            "sma_200": None,
            "return_6mo_pct": None,
            "last_close_date": None,
        }
    closes = hist["Close"]
    price = float(closes.iloc[-1])
    sma_50 = float(closes.tail(50).mean()) if len(closes) >= 50 else None
    sma_200 = float(closes.tail(200).mean()) if len(closes) >= 200 else None
    six_mo_idx = max(0, len(closes) - 126)
    ret_6mo = (price / float(closes.iloc[six_mo_idx]) - 1) * 100 if six_mo_idx < len(closes) else None
    return {
        "price": round(price, 2),
        "sma_50": round(sma_50, 2) if sma_50 else None,
        "sma_200": round(sma_200, 2) if sma_200 else None,
        "return_6mo_pct": round(ret_6mo, 2) if ret_6mo is not None else None,
        "last_close_date": hist.index[-1].date().isoformat(),
    }


def fetch_edgar_snapshot(ticker: str, user_agent: str) -> dict[str, Any]:
    """Pull the latest 10-K sections and last 8 quarters of revenue + net income via edgartools."""
    from edgar import Company, set_identity

    if not user_agent:
        raise ValueError("SEC_USER_AGENT is required (set in .env, format: 'Name email@example.com').")
    set_identity(user_agent)

    company = Company(ticker.upper())
    name = getattr(company, "name", None)
    description = getattr(company, "description", None) or getattr(company, "business_description", None)

    sections: dict[str, str] = {}
    filing_accession = None
    filing_date = None

    filings = company.get_filings(form="10-K").latest(1)
    filing = filings[0] if hasattr(filings, "__getitem__") else filings
    if filing is not None:
        filing_accession = str(getattr(filing, "accession_number", "") or "")
        filing_date = str(getattr(filing, "filing_date", "") or "")
        try:
            tenk = filing.obj()
            for label, attr in [
                ("Item 1 — Business", "business"),
                ("Item 1A — Risk Factors", "risk_factors"),
                ("Item 7 — Management's Discussion & Analysis", "mda"),
            ]:
                body = getattr(tenk, attr, None)
                if body:
                    sections[label] = str(body)[:MAX_SECTION_CHARS]
        except Exception as exc:
            sections["Item parser error"] = f"edgartools could not parse this 10-K: {exc}"

    fundamentals_rows: list[dict[str, Any]] = []
    try:
        facts = company.get_facts() if hasattr(company, "get_facts") else None
        if facts is not None:
            df = facts.to_pandas() if hasattr(facts, "to_pandas") else None
            if df is not None and not df.empty:
                wanted_concepts = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss"]
                sub = df[df.get("concept", df.get("fact", "")).isin(wanted_concepts)] if "concept" in df.columns or "fact" in df.columns else df.head(0)
                if not sub.empty:
                    cols = [c for c in ["end_date", "concept", "fact", "value", "unit", "fiscal_year", "fiscal_period"] if c in sub.columns]
                    sub = sub[cols].sort_values(by=cols[0]).tail(24)
                    fundamentals_rows = sub.to_dict(orient="records")
    except Exception:
        pass

    return {
        "name": name,
        "description": description,
        "sections_10k": sections,
        "filing_accession": filing_accession,
        "filing_date": filing_date,
        "fundamentals_rows": fundamentals_rows,
    }


def build_snapshot(ticker: str, user_agent: str) -> CompanySnapshot:
    edgar = fetch_edgar_snapshot(ticker, user_agent)
    price = fetch_price_snapshot(ticker)
    return CompanySnapshot(
        ticker=ticker.upper(),
        name=edgar.get("name"),
        description=edgar.get("description"),
        price=price.get("price"),
        sma_50=price.get("sma_50"),
        sma_200=price.get("sma_200"),
        return_6mo_pct=price.get("return_6mo_pct"),
        last_close_date=price.get("last_close_date"),
        fundamentals_rows=edgar.get("fundamentals_rows", []),
        sections_10k=edgar.get("sections_10k", {}),
        filing_accession=edgar.get("filing_accession"),
        filing_date=edgar.get("filing_date"),
    )


def today_iso() -> str:
    return date.today().isoformat()


def six_months_ago_iso() -> str:
    return (date.today() - timedelta(days=180)).isoformat()
