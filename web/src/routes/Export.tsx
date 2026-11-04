import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { api, ApiError } from "../lib/api";
import { relativeTime, STATUS_LABEL } from "../lib/format";

function triggerDownload(url: string, filename: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function ExportScreen() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const preview = useQuery({
    queryKey: ["export-preview", id],
    queryFn: () => api.exportPreview(id as string),
    enabled: Boolean(id),
  });

  const create = useMutation({
    mutationFn: () => api.createExport(id as string),
    onSuccess: (result) => {
      triggerDownload(
        result.url,
        `${preview.data?.shipment_ref ?? "shipment"}-filing.csv`,
      );
      void queryClient.invalidateQueries({ queryKey: ["export-preview", id] });
      void queryClient.invalidateQueries({ queryKey: ["shipment", id] });
    },
  });

  if (preview.isLoading) {
    return (
      <div className="page">
        <div className="skeleton" style={{ height: 18, width: 120, marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 28, width: 260, marginBottom: 20 }} />
        <div className="export-grid">
          <div className="skeleton" style={{ height: 340, borderRadius: 10 }} />
          <div className="skeleton" style={{ height: 220, borderRadius: 10 }} />
        </div>
      </div>
    );
  }

  if (preview.isError || !preview.data) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-icon">
            <Icon name="alert" size={19} />
          </div>
          <h3>Export is not available</h3>
          <p>{preview.error instanceof ApiError ? preview.error.detail : "Could not load export."}</p>
          <button className="btn" type="button" onClick={() => navigate(`/shipments/${id}`)}>
            Back to shipment
          </button>
        </div>
      </div>
    );
  }

  const data = preview.data;
  const blockers = data.gate.blockers;
  const existing = data.existing_export;

  function download() {
    if (existing) {
      triggerDownload(existing.url, `${data.shipment_ref}-filing.csv`);
      return;
    }
    create.mutate();
  }

  return (
    <div className="page page-enter">
      <button
        className="btn btn-ghost btn-sm"
        type="button"
        onClick={() => navigate(`/shipments/${id}`)}
      >
        <Icon name="arrow-left" size={14} />
        Back to shipment
      </button>

      <div className="page-head" style={{ marginTop: 12 }}>
        <div>
          <h1>Export</h1>
          <p className="sub">
            {data.total_rows} row{data.total_rows === 1 ? "" : "s"} in the filing layout ·{" "}
            {data.template.name} v{data.template.version}
          </p>
        </div>
        <span className="env-tag" style={{ height: 24 }}>
          {STATUS_LABEL[data.shipment_status] ?? data.shipment_status}
        </span>
      </div>

      {create.isError && (
        <div className="banner banner-error" role="alert">
          <Icon name="alert" size={15} />
          <span>{create.error instanceof ApiError ? create.error.detail : "Export failed."}</span>
        </div>
      )}

      <div className="export-grid">
        <div className="card">
          <div className="card-head">
            <h2>Preview</h2>
            <span style={{ fontSize: 11.5, color: "var(--muted)" }}>
              {data.total_rows > data.rows.length
                ? `first ${data.rows.length} of ${data.total_rows} rows`
                : `${data.total_rows} rows`}
              {` · ${data.headers.length} columns, scroll →`}
            </span>
          </div>

          {data.total_rows === 0 ? (
            <div className="empty" style={{ padding: 42 }}>
              <div className="empty-icon">
                <Icon name="file" size={18} />
              </div>
              <h3>No line items to export</h3>
              <p>The invoice needs at least one extracted line item before export.</p>
            </div>
          ) : (
            <div className="preview-table-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    {data.headers.map((header) => (
                      <th key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex}>{cell || "—"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="export-side">
          <div className="card">
            <div className="card-head">
              <h2>Export check</h2>
              {data.gate.ok ? (
                <span className="pill pill-ready">
                  <i className="dot" />
                  Ready
                </span>
              ) : (
                <span className="pill pill-review">
                  <i className="dot" />
                  {blockers.length} blocked
                </span>
              )}
            </div>
            <div style={{ padding: "12px 14px" }}>
              {data.gate.ok ? (
                <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                  <Icon name="check" size={15} style={{ color: "var(--ok-fg)", marginTop: 1 }} />
                  <div style={{ fontSize: 12, lineHeight: 1.5 }}>
                    Approved, all fields confirmed and every check cleared. This file is safe to
                    import into the filing software.
                  </div>
                </div>
              ) : (
                <div className="gate-list">
                  {blockers.map((blocker, index) => (
                    <div className="gate-item" key={`${blocker.code}-${index}`}>
                      <Icon
                        name={blocker.code.startsWith("ACK_") ? "alert" : "block"}
                        size={13}
                        style={{
                          color: blocker.code.startsWith("ACK_")
                            ? "var(--warn-fg)"
                            : "var(--block-fg)",
                          marginTop: 1,
                          flex: "none",
                        }}
                      />
                      <span>{blocker.message}</span>
                    </div>
                  ))}
                  <button
                    className="btn btn-sm"
                    type="button"
                    style={{ marginTop: 8, width: "100%" }}
                    onClick={() => navigate(`/shipments/${id}/review`)}
                  >
                    Open review
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <h2>File</h2>
            </div>
            <div style={{ padding: "12px 14px" }}>
              <div className="export-meta">
                <div className="row">
                  <span>Format</span>
                  <span>CSV · UTF-8</span>
                </div>
                <div className="row">
                  <span>Rows</span>
                  <span>{data.total_rows}</span>
                </div>
                <div className="row">
                  <span>Template</span>
                  <span>v{data.template.version}</span>
                </div>
                {existing && (
                  <div className="row">
                    <span>Last export</span>
                    <span>{relativeTime(existing.created_at)}</span>
                  </div>
                )}
              </div>

              <button
                className="btn btn-primary"
                type="button"
                style={{ width: "100%", marginTop: 12 }}
                disabled={!data.gate.ok || create.isPending}
                title={!data.gate.ok ? blockers[0]?.message : "Download CSV"}
                onClick={download}
              >
                {create.isPending ? (
                  <Icon name="refresh" size={14} className="spin" />
                ) : (
                  <Icon name="download" size={14} />
                )}
                {existing ? "Download CSV again" : "Generate CSV"}
              </button>

              <p style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 8, lineHeight: 1.5 }}>
                Template v{data.template.version} — configurable to the filing software's import
                layout. One row per invoice line, shipment fields repeated.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
