import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { api, ApiError, type ShipmentStatus } from "../lib/api";
import { relativeTime, STATUS_LABEL } from "../lib/format";

const FILTERS: { key: string; label: string }[] = [
  { key: "", label: "All" },
  { key: "NEEDS_REVIEW", label: "Needs review" },
  { key: "AWAITING_APPROVAL", label: "Awaiting approval" },
  { key: "READY", label: "Ready" },
  { key: "EXPORTED", label: "Exported" },
];

const PILL: Record<ShipmentStatus, string> = {
  DRAFT: "pill-draft",
  EXTRACTING: "pill-extracting",
  NEEDS_REVIEW: "pill-review",
  AWAITING_APPROVAL: "pill-awaiting",
  READY: "pill-ready",
  EXPORTED: "pill-exported",
};

function StatusPill({ status }: { status: ShipmentStatus }) {
  return (
    <span className={`pill ${PILL[status]}`}>
      <i className="dot" />
      {STATUS_LABEL[status]}
    </span>
  );
}

function DocMeter({ count, total }: { count: number; total: number }) {
  return (
    <div className="doc-meter">
      <div className="meter" aria-hidden="true">
        {Array.from({ length: total }).map((_, index) => (
          <i key={index} className={index < count ? "on" : ""} />
        ))}
      </div>
      <span className="doc-count">
        {count}/{total}
      </span>
    </div>
  );
}

export function Shipments() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const qParam = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);
  const limit = 50;
  const [search, setSearch] = useState(qParam);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams(params);
      if (search.trim()) next.set("q", search.trim());
      else next.delete("q");
      next.delete("page");
      if (next.toString() !== params.toString()) setParams(next, { replace: true });
    }, 250);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    setSearch(qParam);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qParam]);

  const query = useQuery({
    queryKey: ["shipments", status, qParam, page],
    queryFn: () =>
      api.shipments({
        status: status || undefined,
        q: qParam || undefined,
        page,
        limit,
      }),
    placeholderData: (previous) => previous,
    refetchInterval: (query) => {
      const data = query.state.data;
      const extracting =
        (data?.counts.EXTRACTING ?? 0) > 0 ||
        data?.items.some((item) => item.status === "EXTRACTING");
      return extracting ? 2000 : false;
    },
  });

  const data = query.data;
  const counts = data?.counts ?? {};
  const needsReview =
    (counts.NEEDS_REVIEW ?? 0) + (counts.EXTRACTING ?? 0) + (counts.DRAFT ?? 0);

  function setStatus(next: string) {
    const p = new URLSearchParams(params);
    if (next) p.set("status", next);
    else p.delete("status");
    p.delete("page");
    setParams(p, { replace: true });
  }

  function setPage(next: number) {
    const p = new URLSearchParams(params);
    if (next <= 1) p.delete("page");
    else p.set("page", String(next));
    setParams(p, { replace: true });
  }

  return (
    <div className="page page-enter">
      <div className="page-head">
        <div>
          <h1>Shipments</h1>
          <p className="sub">
            {data ? `${data.total} in this view` : "Loading"} ·{" "}
            {needsReview === 1 ? "1 needs attention" : `${needsReview} need attention`}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn"
            type="button"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <Icon name="refresh" size={15} className={query.isFetching ? "spin" : ""} />
            Refresh
          </button>
          <button
            className="btn btn-primary"
            type="button"
            onClick={() => navigate("/shipments/new")}
          >
            <Icon name="plus" size={15} />
            New shipment
          </button>
        </div>
      </div>

      <div className="toolbar">
        <div className="chip-row">
          {FILTERS.map((filter) => {
            const count = filter.key ? counts[filter.key] ?? 0 : data?.total ?? 0;
            return (
              <button
                key={filter.key}
                type="button"
                className={`chip${status === filter.key ? " active" : ""}`}
                onClick={() => setStatus(filter.key)}
              >
                {filter.label}
                <span className="count num">{count}</span>
              </button>
            );
          })}
        </div>
        <div className="search" style={{ marginLeft: "auto" }}>
          <Icon name="search" size={15} />
          <input
            className="input"
            placeholder="Search reference or supplier"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Search shipments"
          />
        </div>
      </div>

      {query.isError && (
        <div className="banner banner-error" role="alert">
          <Icon name="alert" size={16} />
          <span>
            {query.error instanceof ApiError
              ? query.error.detail
              : "Could not load shipments."}{" "}
            <button
              type="button"
              className="btn btn-sm"
              style={{ marginLeft: 8 }}
              onClick={() => void query.refetch()}
            >
              Retry
            </button>
          </span>
        </div>
      )}

      <div className="card">
        {query.isLoading ? (
          <div style={{ padding: 18, display: "grid", gap: 12 }}>
            {Array.from({ length: 7 }).map((_, index) => (
              <div key={index} style={{ display: "flex", gap: 24, alignItems: "center" }}>
                <div className="skeleton" style={{ height: 14, width: 110 }} />
                <div className="skeleton" style={{ height: 14, width: 150 }} />
                <div className="skeleton" style={{ height: 14, width: 70 }} />
                <div className="skeleton" style={{ height: 14, width: 90, marginLeft: "auto" }} />
                <div className="skeleton" style={{ height: 20, width: 100 }} />
              </div>
            ))}
          </div>
        ) : data && data.items.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">
              <Icon name="box" size={19} />
            </div>
            <h3>{qParam || status ? "No shipments match" : "No shipments yet"}</h3>
            <p>
              {qParam || status
                ? "Try a different reference, supplier or status filter."
                : "Create a shipment, upload its three documents, and the data lands here for review."}
            </p>
            {qParam || status ? (
              <button
                className="btn btn-sm"
                type="button"
                onClick={() => {
                  setSearch("");
                  setParams({}, { replace: true });
                }}
              >
                Clear filters
              </button>
            ) : (
              <button
                className="btn btn-primary"
                type="button"
                onClick={() => navigate("/shipments/new")}
              >
                <Icon name="plus" size={15} />
                New shipment
              </button>
            )}
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Shipment</th>
                <th className="hide-mobile">Documents</th>
                <th className="hide-mobile">Issues</th>
                <th>Status</th>
                <th className="right hide-mobile">Updated</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((item) => (
                <tr
                  key={item.id}
                  className="row"
                  onClick={() => navigate(`/shipments/${item.id}`)}
                >
                  <td>
                    <div className="ref">{item.ref}</div>
                    <div className="supplier">
                      {item.supplier_name ?? "No supplier"} · {item.currency}
                      {item.incoterm ? ` · ${item.incoterm}` : ""}
                    </div>
                  </td>
                  <td className="hide-mobile">
                    <DocMeter count={item.document_count} total={item.document_total} />
                  </td>
                  <td className="hide-mobile">
                    {item.open_issues > 0 ? (
                      <span className="issues open">
                        <Icon name="alert" size={13} />
                        {item.open_issues} open
                      </span>
                    ) : (
                      <span className="issues clear">—</span>
                    )}
                  </td>
                  <td>
                    <StatusPill status={item.status} />
                  </td>
                  <td className="right time hide-mobile">{relativeTime(item.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {data && data.total > limit && (
        <div className="pager">
          <span>
            Showing {(page - 1) * limit + 1}–{Math.min(page * limit, data.total)} of {data.total}
          </span>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              className="btn btn-sm"
              type="button"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              <Icon name="arrow-left" size={13} />
              Previous
            </button>
            <button
              className="btn btn-sm"
              type="button"
              disabled={page * limit >= data.total}
              onClick={() => setPage(page + 1)}
            >
              Next
              <Icon name="arrow-right" size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
