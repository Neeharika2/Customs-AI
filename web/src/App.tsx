import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { useAuth } from "./lib/auth";
import { ExportScreen } from "./routes/Export";
import { Login } from "./routes/Login";
import { NewShipment } from "./routes/NewShipment";
import { Placeholder } from "./routes/Placeholder";
import { Reports } from "./routes/Reports";
import { Settings } from "./routes/Settings";
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
          <Route path="/shipments/:id/export" element={<ExportScreen />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
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
