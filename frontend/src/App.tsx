import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ModelMetrics from "./pages/ModelMetrics";
import EventsList from "./pages/EventsList";
import EventDetail from "./pages/EventDetail";
import Simulate from "./pages/Simulate";
import "./index.css";

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <nav className="sidebar">
          <div className="brand-wrapper">
            <div className="brand-logo-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            </div>
            <div className="brand">RevTrace</div>
            <span className="brand-badge">AI 2.0</span>
          </div>

          <div className="nav-section">
            <NavLink to="/" end className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
              </svg>
              <span>Dashboard</span>
            </NavLink>

            <NavLink to="/events" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="8" y1="6" x2="21" y2="6" />
                <line x1="8" y1="12" x2="21" y2="12" />
                <line x1="8" y1="18" x2="21" y2="18" />
                <line x1="3" y1="6" x2="3.01" y2="6" />
                <line x1="3" y1="12" x2="3.01" y2="12" />
                <line x1="3" y1="18" x2="3.01" y2="18" />
              </svg>
              <span>Events Trail</span>
            </NavLink>

            <NavLink to="/simulate" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              <span>Simulate</span>
            </NavLink>

            <NavLink to="/model" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
              <span>Model Metrics</span>
            </NavLink>
          </div>

          <div className="sidebar-footer">
            <div className="system-status">
              <span className="status-dot"></span>
              <span>Autonomous Engine Active</span>
            </div>
          </div>
        </nav>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/events" element={<EventsList />} />
            <Route path="/events/:eventId" element={<EventDetail />} />
            <Route path="/simulate" element={<Simulate />} />
            <Route path="/model" element={<ModelMetrics />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
