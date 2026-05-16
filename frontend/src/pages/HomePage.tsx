import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { api, ResearchResult } from "../api";

export function HomePage() {
  const navigate = useNavigate();
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);

  const [capital, setCapital] = useState(500);
  const [proposing, setProposing] = useState(false);

  async function runResearch(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const r = await api.research(ticker.trim().toUpperCase());
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function proposeTrade() {
    if (!result) return;
    setError(null);
    setProposing(true);
    try {
      const p = await api.propose(result.ticker, { capital_usd: capital });
      navigate(`/tickets/${p.ticket_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProposing(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="bg-white border border-slate-200 rounded-lg p-6">
        <h1 className="text-2xl font-bold mb-1">Run research</h1>
        <p className="text-sm text-slate-600 mb-4">
          Pulls the latest 10-K (Item 1, 1A, 7), fundamentals, and price action. Claude
          synthesises a one-page thesis.
        </p>
        <form onSubmit={runResearch} className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="block text-xs font-medium text-slate-600 mb-1">Ticker</label>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="NVDA"
              className="w-full border border-slate-300 rounded-md px-3 py-2 uppercase"
              autoFocus
            />
          </div>
          <button
            type="submit"
            disabled={loading || !ticker.trim()}
            className="bg-slate-900 text-white px-4 py-2 rounded-md font-medium disabled:opacity-50"
          >
            {loading ? "Researching..." : "Research"}
          </button>
        </form>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        {loading && (
          <p className="mt-3 text-sm text-slate-500">
            This calls SEC EDGAR + yfinance + Claude Opus 4.7. Usually 30–60s.
          </p>
        )}
      </section>

      {result && (
        <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
          <div className="flex items-start gap-4 flex-wrap">
            <div>
              <div className="text-xs text-slate-500">{result.ticker}</div>
              <div className="text-lg font-bold">
                {result.recommendation} ({result.direction})
              </div>
            </div>
            <div className="text-sm text-slate-600 flex gap-4 flex-wrap">
              <div>price ${result.snapshot.price ?? "?"}</div>
              <div>50d SMA ${result.snapshot.sma_50 ?? "?"}</div>
              <div>200d SMA ${result.snapshot.sma_200 ?? "?"}</div>
              <div>6mo {result.snapshot.return_6mo_pct ?? "?"}%</div>
              <div>filing {result.snapshot.filing_accession ?? "?"}</div>
            </div>
          </div>

          <div className="prose max-w-none">
            <ReactMarkdown>{result.thesis_markdown}</ReactMarkdown>
          </div>

          <div className="border-t border-slate-200 pt-4">
            <h2 className="font-semibold mb-2">Propose a trade</h2>
            <p className="text-sm text-slate-600 mb-3">
              Phase 0 proposes long stock only, on bullish theses. Direction here is{" "}
              <span className="font-medium">{result.direction}</span>.
            </p>
            <div className="flex gap-2 items-end">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Capital (USD)
                </label>
                <input
                  type="number"
                  min={1}
                  value={capital}
                  onChange={(e) => setCapital(Number(e.target.value))}
                  className="border border-slate-300 rounded-md px-3 py-2 w-32"
                />
              </div>
              <button
                onClick={proposeTrade}
                disabled={proposing}
                className="bg-emerald-700 text-white px-4 py-2 rounded-md font-medium disabled:opacity-50"
              >
                {proposing ? "Generating..." : "Propose"}
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
