import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Ticket } from "../api";

const statusColor: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  executed: "bg-emerald-100 text-emerald-800",
  blocked: "bg-red-100 text-red-800",
};

export function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [halting, setHalting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const r = await api.tickets();
      setTickets(r.tickets);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onHalt() {
    if (!confirm("Cancel all open orders and block pending tickets?")) return;
    setHalting(true);
    try {
      const r = await api.halt();
      alert(
        `Cancelled ${r.cancelled_open_orders} open order(s); blocked ${r.blocked_pending_tickets} pending ticket(s).`,
      );
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setHalting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Tickets</h1>
        <button
          onClick={onHalt}
          disabled={halting}
          className="bg-red-600 text-white px-4 py-2 rounded-md font-medium disabled:opacity-50"
        >
          {halting ? "Halting..." : "HALT"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">Loading...</p>
        ) : tickets.length === 0 ? (
          <p className="p-6 text-sm text-slate-500">
            No tickets yet. <Link to="/" className="text-emerald-700 underline">Run research</Link>{" "}
            to generate one.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">id</th>
                <th className="px-4 py-2 font-medium">ticker</th>
                <th className="px-4 py-2 font-medium">side</th>
                <th className="px-4 py-2 font-medium">qty</th>
                <th className="px-4 py-2 font-medium">notional</th>
                <th className="px-4 py-2 font-medium">status</th>
                <th className="px-4 py-2 font-medium">created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {tickets.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono">
                    <Link to={`/tickets/${t.id}`} className="text-emerald-700 hover:underline">
                      {t.id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 font-medium">{t.ticker}</td>
                  <td className="px-4 py-2">{t.side}</td>
                  <td className="px-4 py-2">{t.qty}</td>
                  <td className="px-4 py-2">${(t.estimated_notional ?? 0).toFixed(2)}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        statusColor[t.status] ?? "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {t.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-slate-500 text-xs">{t.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
