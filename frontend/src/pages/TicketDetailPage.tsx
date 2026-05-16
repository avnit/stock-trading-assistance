import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ExecuteResult, Ticket } from "../api";

export function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<ExecuteResult | null>(null);

  async function load() {
    if (!id) return;
    try {
      setTicket(await api.ticket(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  const expected = ticket ? `APPROVE ${ticket.ticker} ${ticket.id}` : "";

  async function onExecute() {
    if (!id) return;
    setExecuting(true);
    setError(null);
    try {
      const r = await api.execute(id, confirmation);
      setResult(r);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setExecuting(false);
    }
  }

  if (error && !ticket) return <p className="text-sm text-red-600">{error}</p>;
  if (!ticket) return <p className="text-sm text-slate-500">Loading...</p>;

  return (
    <div className="space-y-4">
      <Link to="/tickets" className="text-sm text-emerald-700 hover:underline">
        ← Back to tickets
      </Link>
      <div className="bg-white border border-slate-200 rounded-lg p-6 space-y-3">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="text-xs text-slate-500">{ticket.id}</div>
            <div className="text-2xl font-bold">
              {ticket.side.toUpperCase()} {ticket.qty} {ticket.ticker}
            </div>
            <div className="text-sm text-slate-600">
              est. ${(ticket.estimated_notional ?? 0).toFixed(2)} @ $
              {(ticket.estimated_price ?? 0).toFixed(2)}
            </div>
          </div>
          <span
            className={`px-3 py-1 rounded text-sm font-medium ${
              ticket.status === "pending"
                ? "bg-amber-100 text-amber-800"
                : ticket.status === "executed"
                ? "bg-emerald-100 text-emerald-800"
                : "bg-red-100 text-red-800"
            }`}
          >
            {ticket.status}
          </span>
        </div>
        <div className="border-t border-slate-200 pt-3">
          <h2 className="font-semibold text-sm text-slate-700 mb-1">Rationale</h2>
          <p className="text-sm text-slate-600 whitespace-pre-wrap">{ticket.rationale}</p>
        </div>
      </div>

      {ticket.status === "pending" && (
        <div className="bg-white border border-slate-200 rounded-lg p-6 space-y-3">
          <h2 className="font-bold text-lg">Execute</h2>
          <p className="text-sm text-slate-600">
            Type the exact confirmation string below. This places a paper order via Alpaca and is
            re-validated against a fresh quote at execution time.
          </p>
          <code className="block bg-slate-100 text-slate-800 px-3 py-2 rounded text-sm font-mono">
            {expected}
          </code>
          <input
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            placeholder="paste the line above exactly"
            className="w-full border border-slate-300 rounded-md px-3 py-2 font-mono text-sm"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            onClick={onExecute}
            disabled={executing || confirmation.trim() !== expected}
            className="bg-emerald-700 text-white px-4 py-2 rounded-md font-medium disabled:opacity-50"
          >
            {executing ? "Executing..." : "Execute paper order"}
          </button>
        </div>
      )}

      {result && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-sm">
          <div className="font-semibold text-emerald-800 mb-1">Order placed</div>
          <div>
            broker order id: <span className="font-mono">{result.broker_order_id}</span>
          </div>
          <div>status: {result.status}</div>
          {result.fill_qty != null && (
            <div>
              fill: {result.fill_qty} @ ${result.fill_price}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
