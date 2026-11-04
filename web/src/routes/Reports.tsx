import { useQuery } from "@tanstack/react-query";
import { Icon } from "../components/Icon";
import { api, ApiError, type ReportField, type ReportSupplier } from "../lib/api";
import { useAuth } from "../lib/auth";

const FIELD_LABEL: Record<string, string> = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  currency: "Currency",
  incoterm: "Incoterm",
  supplier_name: "Supplier",
  buyer_name: "Buyer",
  invoice_total: "Invoice total",
  gross_weight_kg: "Gross weight",
  net_weight_kg: "Net weight",
  packages: "Packages",
  container_numbers: "Containers",
  bl_number: "B/L number",
  bl_date: "B/L date",
  consignee: "Consignee",
};

function label(key: string): string {
  return FIELD_LABEL[key] ?? key.replaceAll("_", " ");
}

function Rate({ value, sufficient }: { value: number; sufficient: boolean }) {
  if (!sufficient) {
    return <span className="small-n">n &lt; 20</span>;
  }
  return (
    <div className="rate">
      <div className="rate-track">
        <i
          className={value >= 10 ? "warn" : ""}
          style={{ width: `${Math.min(100, Math.max(2, value))}%` }}
        />
      </div>
      <span>{value.toFixed(1)}%</span>
    </div>
  );
}

export function Reports() {
  const { user } = useAuth();
  const query = useQuery({ queryKey: ["reports"], queryFn: api.reports });

  if (user?.role !== "MANAGER") {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-icon">
            <Icon name="chart" size={19} />
          </div>
          <h3>Reports are for managers</h3>
          <p>Sign in with a manager account to see correction rates by field and supplier.</p>
        </div>
      </div>
    );
  }

  if (query.isLoading) {
    return (
      <div className="page">
        <div className="skeleton" style={{ height: 26, width: 180, marginBottom: 12 }} />
        <div className="stats-grid">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="skeleton" style={{ height: 88, borderRadius: 9 }} />
          ))}
        </div>
        <div className="skeleton" style={{ height: 320, borderRadius: 10 }} />
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-icon">
            <Icon name="alert" size={19} />
          </div>
          <h3>Could not load reports</h3>
          <p>{query.error instanceof ApiError ? query.error.detail : "Unexpected error."}</p>
          <button className="btn" type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  const data = query.data;
  const t = data.totals;

  return (
    <div className="page page-enter">
      <div className="page-head">
        <div>
          <h1>Accuracy</h1>
          <p className="sub">
            {t.shipments} shipments · {t.documents} documents · {t.fields} extracted fields
          </p>
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat">
          <div className="k">Evidence coverage</div>
          <div className="v">{t.evidence_coverage.toFixed(1)}%</div>
          <div className="s">fields anchored to a verified source</div>
        </div>
        <div className="stat">
          <div className="k">First-pass acceptance</div>
          <div className="v">{t.first_pass.toFixed(1)}%</div>
          <div className="s">fields confirmed without an edit</div>
        </div>
        <div className="stat">
          <div className="k">Manual entry rate</div>
          <div className="v">{t.manual_rate.toFixed(1)}%</div>
          <div className="s">
            {t.manual_documents} of {t.documents} documents
          </div>
        </div>
        <div className="stat">
          <div className="k">Corrections logged</div>
          <div className="v">{t.corrections}</div>
          <div className="s">attributed to a person and a field</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-head">
          <h2>Correction rate by field</h2>
          <span style={{ fontSize: 11.5, color: "var(--muted)" }}>all time</span>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Field</th>
              <th className="right">Extracted</th>
              <th className="right">Corrected</th>
              <th>Correction rate</th>
              <th className="right hide-mobile">Avg confidence</th>
            </tr>
          </thead>
          <tbody>
            {data.fields.map((row: ReportField) => (
              <tr key={row.key}>
                <td>
                  <div className="ref" style={{ fontWeight: 500 }}>
                    {label(row.key)}
                  </div>
                </td>
                <td className="right num">{row.extracted}</td>
                <td className="right num">{row.corrected}</td>
                <td>
                  <Rate value={row.correction_rate} sufficient={row.sufficient} />
                </td>
                <td className="right num hide-mobile">
                  {row.sufficient ? `${(row.avg_confidence * 100).toFixed(0)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>By supplier</h2>
          <span style={{ fontSize: 11.5, color: "var(--muted)" }}>
            where corrections and manual entry concentrate
          </span>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Supplier</th>
              <th className="right hide-mobile">Shipments</th>
              <th className="right">Fields</th>
              <th className="right">Corrected</th>
              <th>Correction rate</th>
              <th className="right hide-mobile">Manual docs</th>
            </tr>
          </thead>
          <tbody>
            {data.suppliers.map((row: ReportSupplier) => (
              <tr key={row.supplier}>
                <td>
                  <div className="ref" style={{ fontWeight: 500 }}>
                    {row.supplier}
                  </div>
                </td>
                <td className="right num hide-mobile">{row.shipments}</td>
                <td className="right num">{row.fields}</td>
                <td className="right num">{row.corrected}</td>
                <td>
                  <Rate value={row.correction_rate} sufficient={row.sufficient} />
                </td>
                <td className="right num hide-mobile">{row.manual_documents}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="report-note">
        <Icon name="alert" size={14} style={{ marginTop: 1, flex: "none" }} />
        <span>
          Correction rate measures what people changed, not what was wrong. It is a proxy, and it
          is suppressed below {data.small_sample} extracted fields. True accuracy is measured by
          the hand-verified golden set in <span className="mono">eval/</span>, not by this table.
        </span>
      </div>
    </div>
  );
}
