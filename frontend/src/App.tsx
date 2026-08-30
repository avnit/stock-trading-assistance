import { Route, Routes } from "react-router-dom";
import { Nav } from "./components/Nav";
import { HomePage } from "./pages/HomePage";
import { OptionsPage } from "./pages/OptionsPage";
import { TicketsPage } from "./pages/TicketsPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { PositionsPage } from "./pages/PositionsPage";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <Nav />
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/options" element={<OptionsPage />} />
          <Route path="/tickets" element={<TicketsPage />} />
          <Route path="/tickets/:id" element={<TicketDetailPage />} />
          <Route path="/positions" element={<PositionsPage />} />
        </Routes>
      </main>
      <footer className="text-center text-xs text-slate-500 py-4 border-t border-slate-200 bg-white">
        Not investment advice. Paper trading only.
      </footer>
    </div>
  );
}
