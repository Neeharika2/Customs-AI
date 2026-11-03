import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { useAuth } from "./lib/auth";
import { Login } from "./routes/Login";
import { NewShipment } from "./routes/NewShipment";
import { Placeholder } from "./routes/Placeholder";
import { ShipmentDetail } from "./routes/ShipmentDetail";
import { ReviewScreen } from "./routes/Review";
import { Shipments } from "./routes/Shipments";

function Splash() {
  return <div className="splash">Loading workspace…</div>;
}

function Protected() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Splash />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/shipments" replace />} />
          <Route path="/shipments" element={<Shipments />} />
          <Route path="/shipments/new" element={<NewShipment />} />
          <Route path="/shipments/:id" element={<ShipmentDetail />} />
          <Route path="/shipments/:id/review" element={<ReviewScreen />} />
          <Route
            path="/shipments/:id/export"
            element={
              <Placeholder
                title="Export"
                description="Column-mapped CSV export with the gate checklist and a preview of exactly what will be downloaded."
                phase="Phase 6"
              />
            }
          />
          <Route
            path="/reports"
            element={
              <Placeholder
                title="Reports"
                description="Correction rate by field and supplier, first-pass acceptance, and the issues that block exports."
                phase="Phase 6"
              />
            }
          />
          <Route
            path="/settings"
            element={
              <Placeholder
                title="Settings"
                description="Tolerances, export templates, retention and users. Manager only."
                phase="Phase 6"
              />
            }
          />
          <Route
            path="*"
            element={
              <Placeholder
                title="Page not found"
                description="That route does not exist."
                phase=""
              />
            }
          />
        </Route>
      </Route>
    </Routes>
  );
}
