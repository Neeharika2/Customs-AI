import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Icon } from "../components/Icon";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

type TemplateColumn = {
  header: string;
  source: string;
  required?: boolean;
  format?: string | null;
  join?: string | null;
};

const SOURCE_OPTIONS = [
  ["invoice_number", "Invoice number"],
  ["invoice_date", "Invoice date"],
  ["supplier_name", "Supplier"],
  ["buyer_name", "Buyer"],
  ["currency", "Currency"],
  ["incoterm", "Incoterm"],
  ["invoice_total", "Invoice total"],
  ["freight", "Freight"],
  ["insurance", "Insurance"],
  ["discount", "Discount"],
  ["gross_weight_kg", "Gross weight"],
  ["net_weight_kg", "Net weight"],
  ["packages", "Packages"],
  ["package_type", "Package type"],
  ["container_numbers", "Container numbers"],
  ["bl_number", "B/L number"],
  ["bl_date", "B/L date"],
  ["consignee", "Consignee"],
  ["notify_party", "Notify party"],
  ["vessel_name", "Vessel"],
  ["port_of_loading", "Port of loading"],
  ["port_of_discharge", "Port of discharge"],
  ["item.description", "Line description"],
  ["item.hsn_code", "Line HSN"],
  ["item.qty", "Line quantity"],
  ["item.unit_price", "Line unit price"],
  ["item.amount", "Line amount"],
] as const;

export function Settings() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [weight, setWeight] = useState("0.5");
  const [value, setValue] = useState("0.01");
  const [retention, setRetention] = useState("180");
  const [toast, setToast] = useState<string | null>(null);
  const [templateName, setTemplateName] = useState("");
  const [columns, setColumns] = useState<TemplateColumn[]>([]);

  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: user?.role === "MANAGER" });

  useEffect(() => {
    if (query.data) {
      setWeight(String(query.data.weight_tol_pct));
      setValue(String(query.data.value_tol));
      setRetention(String(query.data.retention_days));
      if (query.data.template) {
        setTemplateName(query.data.template.name);
        setColumns(
          query.data.template.columns.map((column) => ({
            header: column.header,
            source: column.source,
            required: column.required ?? false,
            format: column.format ?? "",
            join: (column as { join?: string }).join ?? "",
          })),
        );
      }
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

  const saveTemplate = useMutation({
    mutationFn: () => {
      const template = query.data?.template;
      if (!template) throw new Error("No template");
      return api.saveTemplate(template.id, templateName.trim(), columns);
    },
    onSuccess: () => {
      setToast("Template saved as a new version");
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
      window.setTimeout(() => setToast(null), 2500);
    },
    onError: (error) => {
      setToast(error instanceof ApiError ? error.detail : "Could not save the template");
      window.setTimeout(() => setToast(null), 3500);
    },
  });

  const headers = columns.map((column) => column.header.trim().toLowerCase()).filter(Boolean);
  const hasRequiredSources =
    columns.some((column) => column.source === "invoice_number") &&
    columns.some((column) => column.source === "item.description");
  const templateValid =
    columns.length > 0 &&
    headers.length === columns.length &&
    new Set(headers).size === headers.length &&
    columns.every((column) => column.header.trim() && column.source) &&
    hasRequiredSources;

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
            {data.template ? `v${data.template.version} · saving creates a new version` : "No template"}
          </span>
        </div>
        <div style={{ padding: 14 }}>
          <div className="field" style={{ maxWidth: 360, marginBottom: 12 }}>
            <label className="label">Template name</label>
            <input
              className="input"
              value={templateName}
              onChange={(event) => setTemplateName(event.target.value)}
            />
          </div>

          <div className="template-table">
            <div className="template-row template-head">
              <span>Column header</span>
              <span>Source</span>
              <span>Format</span>
              <span>Req.</span>
              <span />
            </div>
            {columns.map((column, index) => (
              <div className="template-row" key={index}>
                <input
                  className="input"
                  value={column.header}
                  onChange={(event) =>
                    setColumns((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, header: event.target.value } : item,
                      ),
                    )
                  }
                />
                <select
                  className="select"
                  value={column.source}
                  onChange={(event) =>
                    setColumns((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, source: event.target.value } : item,
                      ),
                    )
                  }
                >
                  {SOURCE_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <input
                  className="input num"
                  placeholder="—"
                  value={column.format ?? ""}
                  onChange={(event) =>
                    setColumns((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, format: event.target.value } : item,
                      ),
                    )
                  }
                />
                <input
                  type="checkbox"
                  checked={Boolean(column.required)}
                  onChange={(event) =>
                    setColumns((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, required: event.target.checked } : item,
                      ),
                    )
                  }
                />
                <button
                  className="btn btn-ghost btn-sm"
                  type="button"
                  title="Remove column"
                  onClick={() =>
                    setColumns((current) => current.filter((_, itemIndex) => itemIndex !== index))
                  }
                >
                  <Icon name="x" size={13} />
                </button>
              </div>
            ))}
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 10,
              marginTop: 12,
            }}
          >
            <button
              className="btn btn-sm"
              type="button"
              onClick={() =>
                setColumns((current) => [
                  ...current,
                  { header: "", source: "item.description", required: false, format: "" },
                ])
              }
            >
              <Icon name="plus" size={13} />
              Add column
            </button>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {!templateValid && (
                <span style={{ fontSize: 11, color: "var(--block-fg)" }}>
                  Headers must be unique; invoice number and line description are required.
                </span>
              )}
              <button
                className="btn btn-primary btn-sm"
                type="button"
                disabled={!templateValid || saveTemplate.isPending || !data.template}
                onClick={() => saveTemplate.mutate()}
              >
                {saveTemplate.isPending ? (
                  <Icon name="refresh" size={13} className="spin" />
                ) : (
                  <Icon name="check" size={13} />
                )}
                Save template
              </button>
            </div>
          </div>
        </div>
        <div
          style={{
            padding: "10px 14px",
            borderTop: "1px solid var(--border)",
            fontSize: 11,
            color: "var(--muted)",
          }}
        >
          The mapping is data, not code. Existing exports keep the template version they used.
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
