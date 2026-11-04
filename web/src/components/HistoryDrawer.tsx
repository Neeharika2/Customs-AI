import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { relativeTime } from "../lib/format";
import { Icon } from "./Icon";

const KIND_ICON = {
  correction: "edit",
  approval: "check",
  export: "download",
  status: "clock",
} as const;

export function HistoryDrawer({
  shipmentId,
  open,
  onClose,
}: {
  shipmentId: string;
  open: boolean;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: ["activity", shipmentId],
    queryFn: () => api.activity(shipmentId),
    enabled: open,
  });

  if (!open) return null;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(event) => event.stopPropagation()}>
        <header className="drawer-head">
          <div>
            <h2>History</h2>
            <p>Every upload, correction, check and decision.</p>
          </div>
          <button className="btn btn-ghost btn-sm" type="button" onClick={onClose} title="Close">
            <Icon name="x" size={15} />
          </button>
        </header>

        <div className="drawer-body">
          {query.isLoading && (
            <div style={{ display: "grid", gap: 14 }}>
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="skeleton" style={{ height: 52, borderRadius: 8 }} />
              ))}
            </div>
          )}

          {query.isError && (
            <div className="banner banner-error">
              <Icon name="alert" size={15} />
              <span>
                {query.error instanceof ApiError ? query.error.detail : "Could not load history."}
              </span>
            </div>
          )}

          {query.data && query.data.items.length === 0 && (
            <div className="empty" style={{ padding: "48px 12px" }}>
              <div className="empty-icon">
                <Icon name="clock" size={18} />
              </div>
              <h3>No activity yet</h3>
              <p>Uploads, corrections and approvals will appear here.</p>
            </div>
          )}

          {query.data && query.data.items.length > 0 && (
            <div className="timeline">
              {query.data.items.map((item) => (
                <div className="timeline-item" key={item.id}>
                  <div className="timeline-icon">
                    <Icon name={KIND_ICON[item.kind] ?? "clock"} size={13} />
                  </div>
                  <div>
                    <div className="timeline-title">{item.title}</div>
                    {item.detail && <div className="timeline-detail">{item.detail}</div>}
                    {item.reason && <div className="timeline-reason">“{item.reason}”</div>}
                    <div className="timeline-meta">
                      {item.actor} · {relativeTime(item.at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
