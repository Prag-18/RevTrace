import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import ModelMetrics from "./pages/ModelMetrics";
import EventsList from "./pages/EventsList";
import EventDetail from "./pages/EventDetail";
import "./index.css";

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <nav className="sidebar">
          <div className="brand">RevTrace</div>
          <NavLink to="/" end className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            Dashboard
          </NavLink>
          <NavLink to="/events" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            Events
          </NavLink>
          <NavLink to="/model" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            Model
          </NavLink>
        </nav>
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/events" element={<EventsList />} />
            <Route path="/events/:eventId" element={<EventDetail />} />
            <Route path="/model" element={<ModelMetrics />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;

