import { Link, NavLink } from "react-router-dom";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded-md text-sm font-medium ${
    isActive ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-200"
  }`;

export function Nav() {
  return (
    <nav className="bg-white border-b border-slate-200">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-2">
        <Link to="/" className="text-lg font-bold text-slate-900 mr-4">
          argo
        </Link>
        <NavLink to="/" end className={linkClass}>
          Research
        </NavLink>
        <NavLink to="/tickets" className={linkClass}>
          Tickets
        </NavLink>
        <NavLink to="/positions" className={linkClass}>
          Positions
        </NavLink>
        <div className="ml-auto text-xs text-slate-500">
          Phase 0 — Alpaca paper
        </div>
      </div>
    </nav>
  );
}
