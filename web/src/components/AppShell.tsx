import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "./Icon";
import { useAuth } from "../lib/auth";
import { initials } from "../lib/format";

const TITLES: Record<string, string> = {
  "/shipments": "Shipments",
  "/reports": "Reports",
  "/settings": "Settings",
};

function pageTitle(pathname: string): string {
  if (pathname.startsWith("/shipments/new")) return "New shipment";
  if (pathname.endsWith("/review")) return "Review";
  if (pathname.includes("/export")) return "Export";
  if (pathname.startsWith("/shipments/")) return "Shipment";
  return TITLES[pathname] ?? "Customs-AI";
}

export function AppShell() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (!user) return null;

  const title = pageTitle(location.pathname);

  // The review screen is a focused workspace: no nav, no top bar, full width.
  if (location.pathname.endsWith("/review")) {
    return <Outlet />;
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="box" size={16} />
          </div>
          <div className="brand-name">
            Customs<span>-AI</span>
          </div>
        </div>

        <div className="nav-label">Operations</div>
        <NavLink
          to="/shipments"
          className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
        >
          <Icon name="box" size={17} />
          <span>Shipments</span>
        </NavLink>

        <NavLink
          to="/reports"
          className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
        >
          <Icon name="chart" size={17} />
          <span>Reports</span>
        </NavLink>

        <div className="nav-label">Workspace</div>
        <NavLink
          to="/settings"
          className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
        >
          <Icon name="settings" size={17} />
          <span>Settings</span>
        </NavLink>

        <div className="sidebar-foot">
          <button
            type="button"
            className="user-chip"
            onClick={() => navigate("/settings")}
            title={`${user.email} · ${user.role === "MANAGER" ? "Manager" : "Executive"}`}
          >
            <div className="avatar">{initials(user.email.split("@")[0].replace(".", " "))}</div>
            <div className="user-meta">
              <strong>{user.email.split("@")[0]}</strong>
              <span>{user.role === "MANAGER" ? "Documentation manager" : "Documentation executive"}</span>
            </div>
          </button>
          <button
            type="button"
            className="nav-item"
            onClick={() => void signOut()}
            style={{ width: "100%" }}
          >
            <Icon name="logout" size={16} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="crumbs">
            <span>Operations</span>
            <Icon name="chevron-right" size={13} />
            <strong>{title}</strong>
          </div>
          <div className="topbar-right">
            <span className="env-tag">Demo</span>
            <div className="avatar" title={user.email}>
              {initials(user.email.split("@")[0].replace(".", " "))}
            </div>
          </div>
        </header>
        <Outlet />
      </div>
    </div>
  );
}
