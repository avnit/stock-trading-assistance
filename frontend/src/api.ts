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

export type OptionLeg = {
  symbol: string;
  underlying: string;
  expiry: string;
  strike: number;
  option_type: "call" | "put";
  action: "buy" | "sell";
  ratio: number;
  mid: number | null;
  iv: number | null;
  delta: number | null;
  bid: number | null;
  ask: number | null;
};

export type StrategyAnalysisDict = {
  template: string;
  max_loss: number | null;
  max_gain: number | null;
  breakevens: number[];
  pop_pct: number | null;
  expected_profit: number | null;
  net_debit_credit: number | null;
  notes: string;
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
  strategy_template?: string | null;
  legs_json?: string | null;
  analysis_json?: string | null;
};

export type Position = {
  ticker: string;
  qty: number;
  avg_entry_price: number;
  market_value: number;
  unrealized_pl: number;
};

export type StockProposal = {
  ticket_id: string;
  ticker: string;
  side: string;
  qty: number;
  estimated_price: number;
  estimated_notional: number;
  rationale: string;
  approve_with: string;
};

export type OptionsProposal = {
  ticket_id: string;
  ticker: string;
  strategy: string;
  qty: number;
  estimated_price: number;
  estimated_notional: number;
  legs: OptionLeg[];
  analysis: StrategyAnalysisDict;
  rationale: string;
  approve_with: string;
};

export type StrategyTemplate = {
  key: string;
  description: string;
  directions: string[];
  iv_fit: string[];
  default_delta: number;
  default_width: number | null;
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

export type ProposeOptionsBody = {
  thesis_direction?: string;
  strategy?: string | null;
  target_dte?: number;
  target_delta?: number | null;
  width?: number | null;
  iv_rank?: number | null;
  own_shares?: boolean;
  qty?: number;
};

export const api = {
  health: () => req<{ status: string; version: string }>("GET", "/healthz"),
  config: () => req<Record<string, unknown>>("GET", "/config"),
  research: (ticker: string) => req<ResearchResult>("POST", `/research/${ticker}`),
  propose: (ticker: string, body: { thesis_direction?: string; capital_usd: number }) =>
    req<StockProposal>("POST", `/propose/${ticker}`, body),
  proposeOptions: (ticker: string, body: ProposeOptionsBody) =>
    req<OptionsProposal>("POST", `/propose-options/${ticker}`, body),
  strategies: () => req<{ strategies: StrategyTemplate[] }>("GET", "/strategies"),
  expiries: (ticker: string) => req<{ expiries: string[] }>("GET", `/expiries/${ticker}`),
  tickets: (status?: string) =>
    req<{ tickets: Ticket[] }>("GET", "/tickets" + (status ? `?status=${status}` : "")),
  ticket: (id: string) => req<Ticket>("GET", `/tickets/${id}`),
  execute: (id: string, confirmation: string) =>
    req<ExecuteResult>("POST", `/tickets/${id}/execute`, { confirmation }),
  positions: () => req<{ positions: Position[] }>("GET", "/positions"),
  halt: () =>
    req<{ cancelled_open_orders: number; blocked_pending_tickets: number }>("POST", "/halt"),
};
