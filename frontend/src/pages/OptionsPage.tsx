import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, OptionsProposal, StrategyTemplate } from "../api";

export function OptionsPage() {
  const navigate = useNavigate();
  const [ticker, setTicker] = useState("");
  const [thesis, setThesis] = useState<"" | "bullish" | "bearish" | "neutral">("");
  const [strategy, setStrategy] = useState("");
  const [dte, setDte] = useState(35);
  const [delta, setDelta] = useState<number | "">("");
  const [width, setWidth] = useState<number | "">("");
  const [ivRank, setIvRank] = useState<number | "">("");
  const [qty, setQty] = useState(1);
  const [ownShares, setOwnShares] = useState(false);

  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OptionsProposal | null>(null);

  useEffect(() => {
    api.strategies().then((r) => setTemplates(r.strategies)).catch(() => {});
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const r = await api.proposeOptions(ticker.trim().toUpperCase(), {
        thesis_direction: thesis || undefined,
        strategy: strategy || undefined,
        target_dte: dte,
        target_delta: delta === "" ? undefined : delta,
        width: width === "" ? undefined : width,
        iv_rank: ivRank === "" ? undefined : ivRank,
        qty,
        own_shares: ownShares,
      });
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="bg-white border border-slate-200 rounded-lg p-6">
        <h1 className="text-2xl font-bold mb-1">Propose options strategy</h1>
        <p className="text-sm text-slate-600 mb-4">
          Picks a strategy based on your thesis × IV regime, builds the legs from the option
          chain, computes Greeks / PoP / breakevens, and stores a multi-leg ticket. Phase 1.
        </p>
        <form onSubmit={onSubmit} className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
          <Field label="Ticker">
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="AAPL"
              className="w-full border border-slate-300 rounded-md px-3 py-2 uppercase"
            />
          </Field>
          <Field label="Thesis (override)">
            <select
              value={thesis}
              onChange={(e) => setThesis(e.target.value as typeof thesis)}
              className="w-full border border-slate-300 rounded-md px-3 py-2"
            >
              <option value="">use latest research</option>
              <option value="bullish">bullish</option>
              <option value="bearish">bearish</option>
              <option value="neutral">neutral</option>
            </select>
          </Field>
          <Field label="Strategy (auto if blank)">
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full border border-slate-300 rounded-md px-3 py-2"
            >
              <option value="">auto (selector)</option>
              {templates.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.key}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Target DTE">
            <input
              type="number"
              min={1}
              max={365}
              value={dte}
              onChange={(e) => setDte(Number(e.target.value))}
              className="w-full border border-slate-300 rounded-md px-3 py-2"
            />
          </Field>
          <Field label="Target |delta|">
            <input
              type="number"
              step={0.05}
              value={delta}
              onChange={(e) => setDelta(e.target.value === "" ? "" : Number(e.target.value))}
              className="w-full border border-slate-300 rounded-md px-3 py-2"
              placeholder="(template default)"
            />
          </Field>
          <Field label="Width ($)">
            <input
              type="number"
              step={1}
              value={width}
              onChange={(e) => setWidth(e.target.value === "" ? "" : Number(e.target.value))}
              className="w-full border border-slate-300 rounded-md px-3 py-2"
              placeholder="(template default)"
            />
          </Field>
          <Field label="IV rank (override 0..100)">
            <input
              type="number"
              min={0}
              max={100}
              value={ivRank}
              onChange={(e) => setIvRank(e.target.value === "" ? "" : Number(e.target.value))}
              className="w-full border border-slate-300 rounded-md px-3 py-2"
              placeholder="(computed if blank)"
            />
          </Field>
          <Field label="Qty (contract sets)">
            <input
              type="number"
              min={1}
              value={qty}
              onChange={(e) => setQty(Number(e.target.value))}
              className="w-full border border-slate-300 rounded-md px-3 py-2"
            />
          </Field>
          <label className="col-span-2 md:col-span-1 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={ownShares}
              onChange={(e) => setOwnShares(e.target.checked)}
            />
            I already own 100+ shares
          </label>
          <button
            type="submit"
            disabled={loading || !ticker.trim()}
            className="col-span-2 md:col-span-1 bg-emerald-700 text-white px-4 py-2 rounded-md font-medium disabled:opacity-50"
          >
            {loading ? "Building..." : "Propose"}
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      {result && (
        <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
          <div>
            <div className="text-xs text-slate-500">Ticket {result.ticket_id}</div>
            <h2 className="text-xl font-bold">
              {result.strategy} on {result.ticker} × {result.qty}
            </h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <Metric label="Net price" value={`$${result.estimated_price.toFixed(2)}`} />
            <Metric label="Net notional" value={`$${result.estimated_notional.toFixed(2)}`} />
            <Metric label="Max loss" value={fmt(result.analysis.max_loss)} negative />
            <Metric label="Max gain" value={fmt(result.analysis.max_gain)} />
            <Metric label="PoP %" value={result.analysis.pop_pct ?? "n/a"} />
            <Metric
              label="Breakevens"
              value={result.analysis.breakevens.map((b) => `$${b}`).join(", ") || "n/a"}
            />
          </div>
          <div>
            <h3 className="font-semibold text-sm mb-1">Legs</h3>
            <table className="w-full text-xs">
              <thead className="text-left text-slate-500">
                <tr>
                  <th>action</th>
                  <th>type</th>
                  <th>strike</th>
                  <th>expiry</th>
                  <th>delta</th>
                  <th>iv</th>
                  <th>mid</th>
                  <th>symbol</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {result.legs.map((leg, i) => (
                  <tr key={i}>
                    <td className={leg.action === "sell" ? "text-red-700" : "text-emerald-700"}>
                      {leg.action}
                    </td>
                    <td>{leg.option_type}</td>
                    <td>${leg.strike}</td>
                    <td>{leg.expiry}</td>
                    <td>{leg.delta?.toFixed(2) ?? "—"}</td>
                    <td>{leg.iv?.toFixed(3) ?? "—"}</td>
                    <td>${leg.mid?.toFixed(2) ?? "—"}</td>
                    <td className="font-mono">{leg.symbol}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm text-slate-700 whitespace-pre-wrap">{result.rationale}</p>
          <button
            onClick={() => navigate(`/tickets/${result.ticket_id}`)}
            className="bg-slate-900 text-white px-4 py-2 rounded-md font-medium"
          >
            Review & approve →
          </button>
        </section>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-slate-600 mb-1">{label}</span>
      {children}
    </label>
  );
}

function Metric({
  label,
  value,
  negative,
}: {
  label: string;
  value: string | number | null;
  negative?: boolean;
}) {
  return (
    <div className="bg-slate-50 border border-slate-200 rounded p-2">
      <div className="text-[10px] uppercase text-slate-500">{label}</div>
      <div className={`font-semibold ${negative ? "text-red-700" : "text-slate-900"}`}>
        {value === null || value === undefined ? "n/a" : value}
      </div>
    </div>
  );
}

function fmt(v: number | null | undefined) {
  if (v === null || v === undefined) return "n/a";
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toFixed(2)}`;
}
