import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "../components/Icon";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

export function Settings() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [weight, setWeight] = useState("0.5");
  const [value, setValue] = useState("0.01");
  const [retention, setRetention] = useState("180");
  const [toast, setToast] = useState<string | null>(null);

  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: user?.role === "MANAGER" });

  useEffect(() => {
    if (query.data) {
      setWeight(String(query.data.weight_tol_pct));
      setValue(String(query.data.value_tol));
      setRetention(String(query.data.retention_days));
    }
  }, [query.data]);

  const save = useMutation({
    mutationFn: () =>
      api.saveSettings({
        weight_tol_pct: Number(weight),
        value_tol: Number(value),
        retention_days: Number(retention),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      setToast("Settings saved");
      window.setTimeout(() => setToast(null), 2500);
    },
    onError: (error) => {
      setToast(error instanceof ApiError ? error.detail : "Could not save settings");
      window.setTimeout(() => setToast(null), 3000);
    },
  });

  if (user?.role !== "MANAGER") {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-icon">
            <Icon name="settings" size={19} />
          </div>
          <h3>Settings are for managers</h3>
          <p>Tolerances, retention and the export template are managed by the documentation manager.</p>
        </div>
      </div>
    );
  }

  if (query.isLoading || !query.data) {
    return (
      <div className="page">
        <div className="skeleton" style={{ height: 26, width: 180, marginBottom: 18 }} />
        <div className="skeleton" style={{ height: 260, borderRadius: 10, marginBottom: 14 }} />
        <div className="skeleton" style={{ height: 200, borderRadius: 10 }} />
      </div>
    );
  }

  const data = query.data;

  return (
    <div className="page page-enter" style={{ maxWidth: 980 }}>
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <p className="sub">{data.org_name} · documentation workspace</p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <h2>Verification tolerances</h2>
          <span style={{ fontSize: 11.5, color: "var(--muted)" }}>applies to every shipment</span>
        </div>
        <div style={{ padding: 16, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
          <div className="field">
            <label className="label" htmlFor="weight">
              Weight tolerance (%)
            </label>
            <input
              id="weight"
              className="input num"
              type="number"
              step="0.1"
              min="0"
              max="10"
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
            />
            <span style={{ fontSize: 10.5, color: "var(--faint)" }}>
              Differences above this raise a WARN, never a silent pass.
            </span>
          </div>
          <div className="field">
            <label className="label" htmlFor="value">
              Amount tolerance
            </label>
            <input
              id="value"
              className="input num"
              type="number"
              step="0.01"
              min="0"
              max="100"
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
            <span style={{ fontSize: 10.5, color: "var(--faint)" }}>
              Absolute difference allowed on invoice arithmetic.
            </span>
          </div>
          <div className="field">
            <label className="label" htmlFor="retention">
              Retention (days)
            </label>
            <input
              id="retention"
              className="input num"
              type="number"
              step="1"
              min="30"
              max="3650"
              value={retention}
              onChange={(event) => setRetention(event.target.value)}
            />
            <span style={{ fontSize: 10.5, color: "var(--faint)" }}>
              Documents are deleted after export; the audit record remains.
            </span>
          </div>
        </div>
        <div
          style={{
            padding: "10px 16px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            justifyContent: "flex-end",
          }}
        >
          <button
            className="btn btn-primary btn-sm"
            type="button"
            disabled={save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? (
              <Icon name="refresh" size={13} className="spin" />
            ) : (
              <Icon name="check" size={13} />
            )}
            Save settings
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <h2>Export template</h2>
          <span style={{ fontSize: 11.5, color: "var(--muted)" }}>
            {data.template ? `${data.template.name} · v${data.template.version}` : "No template"}
          </span>
        </div>
        {data.template ? (
          <div style={{ padding: 14, display: "flex", flexWrap: "wrap", gap: 5 }}>
            {data.template.columns.map((column) => (
              <span
                key={column.header}
                style={{
                  fontSize: 11,
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                  padding: "3px 7px",
                  color: "var(--ink-2)",
                  background: "#fcfcfa",
                }}
              >
                {column.header}
                {column.required ? <span style={{ color: "var(--block-fg)" }}> *</span> : null}
              </span>
            ))}
          </div>
        ) : null}
        <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--muted)" }}>
          The mapping is data, not code. Replacing it with the filing software's real template does
          not require a release.
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>Users</h2>
          <span style={{ fontSize: 11.5, color: "var(--muted)" }}>{data.users.length} accounts</span>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Role</th>
              <th className="right">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.users.map((row) => (
              <tr key={row.email}>
                <td>{row.email}</td>
                <td>{row.role === "MANAGER" ? "Documentation manager" : "Documentation executive"}</td>
                <td className="right" style={{ color: row.active ? "var(--ok-fg)" : "var(--muted)" }}>
                  {row.active ? "Active" : "Disabled"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
