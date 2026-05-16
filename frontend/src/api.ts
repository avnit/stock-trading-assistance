export type Snapshot = {
  price: number | null;
  sma_50: number | null;
  sma_200: number | null;
  return_6mo_pct: number | null;
  filing_accession: string | null;
  filing_date: string | null;
};

export type ResearchResult = {
  research_id: number;
  ticker: string;
  recommendation: string;
  direction: string;
  thesis_markdown: string;
  snapshot: Snapshot;
  usage: Record<string, number>;
};

export type Ticket = {
  id: string;
  ticker: string;
  side: string;
  asset_type: string;
  qty: number;
  estimated_price: number | null;
  estimated_notional: number | null;
  rationale: string;
  status: string;
  created_at: string;
  research_id: number | null;
};

export type Position = {
  ticker: string;
  qty: number;
  avg_entry_price: number;
  market_value: number;
  unrealized_pl: number;
};

export type Proposal = {
  ticket_id: string;
  ticker: string;
  side: string;
  qty: number;
  estimated_price: number;
  estimated_notional: number;
  rationale: string;
  approve_with: string;
};

export type ExecuteResult = {
  ticket_id: string;
  broker_order_id: string | null;
  status: string;
  fill_price: number | null;
  fill_qty: number | null;
};

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = text;
  }
  if (!res.ok) {
    const detail =
      (parsed && typeof parsed === "object" && "detail" in parsed
        ? (parsed as { detail: string }).detail
        : null) ?? res.statusText;
    throw new Error(`${res.status}: ${detail}`);
  }
  return parsed as T;
}

export const api = {
  health: () => req<{ status: string; version: string }>("GET", "/healthz"),
  config: () => req<Record<string, unknown>>("GET", "/config"),
  research: (ticker: string) => req<ResearchResult>("POST", `/research/${ticker}`),
  propose: (ticker: string, body: { thesis_direction?: string; capital_usd: number }) =>
    req<Proposal>("POST", `/propose/${ticker}`, body),
  tickets: (status?: string) =>
    req<{ tickets: Ticket[] }>("GET", "/tickets" + (status ? `?status=${status}` : "")),
  ticket: (id: string) => req<Ticket>("GET", `/tickets/${id}`),
  execute: (id: string, confirmation: string) =>
    req<ExecuteResult>("POST", `/tickets/${id}/execute`, { confirmation }),
  positions: () => req<{ positions: Position[] }>("GET", "/positions"),
  halt: () =>
    req<{ cancelled_open_orders: number; blocked_pending_tickets: number }>("POST", "/halt"),
};
