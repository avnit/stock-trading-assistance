import { useEffect, useState } from "react";
import { api, Position } from "../api";

export function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .positions()
      .then((r) => setPositions(r.positions))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Positions (Alpaca paper)</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">Loading...</p>
        ) : positions.length === 0 ? (
          <p className="p-6 text-sm text-slate-500">No open positions.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-4 py-2 font-medium">ticker</th>
                <th className="px-4 py-2 font-medium">qty</th>
                <th className="px-4 py-2 font-medium">avg entry</th>
                <th className="px-4 py-2 font-medium">market value</th>
                <th className="px-4 py-2 font-medium">unrealized P/L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {positions.map((p) => (
                <tr key={p.ticker}>
                  <td className="px-4 py-2 font-medium">{p.ticker}</td>
                  <td className="px-4 py-2">{p.qty}</td>
                  <td className="px-4 py-2">${p.avg_entry_price.toFixed(2)}</td>
                  <td className="px-4 py-2">${p.market_value.toFixed(2)}</td>
                  <td
                    className={`px-4 py-2 ${
                      p.unrealized_pl >= 0 ? "text-emerald-700" : "text-red-700"
                    }`}
                  >
                    ${p.unrealized_pl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
