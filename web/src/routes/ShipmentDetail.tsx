import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import {
  api,
  ApiError,
  uploadDocument,
  type DocumentOut,
  type DocumentStatus,
  type DocumentType,
  type ShipmentStatus,
} from "../lib/api";
import { formatDate, relativeTime, STATUS_LABEL } from "../lib/format";

const DOC_LABEL: Record<DocumentType, string> = {
  INVOICE: "Commercial invoice",
  PACKING: "Packing list",
  BL: "Bill of lading",
};

const DOC_HINT: Record<DocumentType, string> = {
  INVOICE: "Prices, currency, Incoterm, line items",
  PACKING: "Packages, quantities, gross and net weight",
  BL: "Shipper, containers, ports, declared weight",
};

const PILL: Record<ShipmentStatus, string> = {
  DRAFT: "pill-draft",
  EXTRACTING: "pill-extracting",
  NEEDS_REVIEW: "pill-review",
  AWAITING_APPROVAL: "pill-awaiting",
  READY: "pill-ready",
  EXPORTED: "pill-exported",
};

const DOC_PILL: Record<DocumentStatus, string> = {
  UPLOADED: "pill-draft",
  QUEUED: "pill-extracting",
  PROCESSING: "pill-extracting",
  EXTRACTED: "pill-ready",
  FAILED: "pill-review",
  NEEDS_MANUAL_ENTRY: "pill-review",
};

function docStatusLabel(status: DocumentStatus): string {
  if (status === "NEEDS_MANUAL_ENTRY") return "Manual entry";
  if (status === "PROCESSING") return "Reading";
  return status.charAt(0) + status.slice(1).toLowerCase();
}

function DocSlot({
  type,
  document,
  uploading,
  progress,
  onPick,
  onOpenReview,
}: {
  type: DocumentType;
  document?: DocumentOut;
  uploading: boolean;
  progress: number;
  onPick: (file: File) => void;
  onOpenReview: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div className="doc-slot">
      <div className="doc-slot-head">
        <Icon name="file" size={15} />
        {DOC_LABEL[type]}
        {document && (
          <span className={`pill ${DOC_PILL[document.status]} right`}>
            <i className="dot" />
            {docStatusLabel(document.status)}
          </span>
        )}
      </div>

      {uploading ? (
        <div className="doc-file">
          <div className="name">Uploading…</div>
          <div className="progress">
            <i style={{ width: `${Math.max(6, progress)}%` }} />
          </div>
          <div className="meta">{progress}% · validating on the server</div>
        </div>
      ) : document ? (
        <div className="doc-file">
          <div className="name" title={document.file_name}>
            {document.file_name}
          </div>
          <div className="meta">
            {document.page_count || "—"} page{document.page_count === 1 ? "" : "s"} · uploaded{" "}
            {relativeTime(document.created_at)}
          </div>
          {document.status === "NEEDS_MANUAL_ENTRY" ? (
            <div className="doc-note">
              <Icon name="alert" size={13} />
              <span>No usable text layer. Type the values in review.</span>
            </div>
          ) : document.status === "FAILED" ? (
            <div className="doc-note">
              <Icon name="alert" size={13} />
              <span>{document.error_detail ?? "Extraction failed."}</span>
            </div>
          ) : null}
          <div style={{ marginTop: "auto", display: "flex", gap: 6 }}>
            <button className="btn btn-sm" type="button" onClick={onOpenReview}>
              <Icon name="eye" size={13} />
              {document.status === "NEEDS_MANUAL_ENTRY" ? "Enter manually" : "View fields"}
            </button>
          </div>
        </div>
      ) : (
        <div
          className={`dropzone${over ? " over" : ""}`}
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setOver(false);
            const file = event.dataTransfer.files?.[0];
            if (file) onPick(file);
          }}
        >
          <Icon name="upload" size={18} style={{ color: "var(--muted)" }} />
          <strong>Drop a file or click to browse</strong>
          <span>PDF, JPG or PNG · max 25 MB</span>
          <span style={{ marginTop: 2 }}>{DOC_HINT[type]}</span>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,image/jpeg,image/png"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onPick(file);
              event.target.value = "";
            }}
          />
        </div>
      )}
    </div>
  );
}

function Stepper({ shipment }: { shipment: { status: ShipmentStatus; documents: DocumentOut[] } }) {
  const extracted = shipment.documents.filter((doc) => doc.status === "EXTRACTED").length;
  const manual = shipment.documents.some((doc) =>
    ["NEEDS_MANUAL_ENTRY", "FAILED"].includes(doc.status),
  );
  const processing = shipment.documents.some((doc) =>
    ["UPLOADED", "QUEUED", "PROCESSING"].includes(doc.status),
  );

  const steps = [
    {
      label: "Documents",
      state: shipment.documents.length === 3 && !processing ? "done" : shipment.documents.length > 0 ? "active" : "",
    },
    {
      label: "Extraction",
      state:
        extracted === 3 && !manual ? "done" : manual || processing || extracted > 0 ? "active" : "",
    },
    {
      label: "Review",
      state:
        shipment.status === "NEEDS_REVIEW"
          ? "active"
          : ["AWAITING_APPROVAL", "READY", "EXPORTED"].includes(shipment.status)
            ? "done"
            : "",
    },
    {
      label: "Approval",
      state:
        shipment.status === "AWAITING_APPROVAL"
          ? "active"
          : ["READY", "EXPORTED"].includes(shipment.status)
            ? "done"
            : "",
    },
    {
      label: "Export",
      state: shipment.status === "EXPORTED" ? "done" : shipment.status === "READY" ? "active" : "",
    },
  ];

  return (
    <div className="stepper" aria-label="Shipment progress">
      {steps.map((step) => (
        <div key={step.label} className={`step ${step.state}`}>
          <div className="bar" />
          <div className="label">{step.label}</div>
        </div>
      ))}
    </div>
  );
}

export function ShipmentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState<Partial<Record<DocumentType, number>>>({});
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["shipment", id],
    queryFn: () => api.shipment(id as string),
    enabled: Boolean(id),
    refetchInterval: (instance) => {
      const data = instance.state.data;
      return data?.documents.some((doc) =>
        ["UPLOADED", "QUEUED", "PROCESSING"].includes(doc.status),
      )
        ? 1200
        : false;
    },
  });

  async function startUpload(type: DocumentType, file: File) {
    if (!id) return;
    setError(null);
    if (file.size > 25 * 1024 * 1024) {
      setError(`${file.name} is larger than 25 MB.`);
      return;
    }
    setUploading((current) => ({ ...current, [type]: 1 }));
    try {
      await uploadDocument(id, type, file, (progress) =>
        setUploading((current) => ({ ...current, [type]: progress })),
      );
      await queryClient.invalidateQueries({ queryKey: ["shipment", id] });
      await queryClient.invalidateQueries({ queryKey: ["shipments"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "The file could not be uploaded.");
    } finally {
      setUploading((current) => {
        const next = { ...current };
        delete next[type];
        return next;
      });
    }
  }

  if (query.isLoading) {
    return (
      <div className="page">
        <div className="skeleton" style={{ height: 16, width: 110, marginBottom: 18 }} />
        <div className="skeleton" style={{ height: 26, width: 240, marginBottom: 10 }} />
        <div className="skeleton" style={{ height: 14, width: 320 }} />
        <div className="skeleton" style={{ height: 170, marginTop: 30, borderRadius: 10 }} />
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
          <h3>Could not open this shipment</h3>
          <p>{query.error instanceof ApiError ? query.error.detail : "Shipment not found."}</p>
          <button className="btn" type="button" onClick={() => navigate("/shipments")}>
            Back to shipments
          </button>
        </div>
      </div>
    );
  }

  const shipment = query.data;
  const byType = new Map(shipment.documents.map((document) => [document.type, document]));
  const extracted = shipment.documents.filter((doc) => doc.status === "EXTRACTED").length;
  const hasReviewable = shipment.documents.length > 0;

  return (
    <div className="page page-enter">
      <button className="btn btn-ghost btn-sm" type="button" onClick={() => navigate("/shipments")}>
        <Icon name="arrow-left" size={14} />
        Shipments
      </button>

      <div className="page-head" style={{ marginTop: 12, marginBottom: 8 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <h1 className="num">{shipment.ref}</h1>
            <span className={`pill ${PILL[shipment.status]}`}>
              <i className="dot" />
              {STATUS_LABEL[shipment.status]}
            </span>
          </div>
          <p className="sub">
            {shipment.supplier_name ?? "No supplier"} · {shipment.currency}
            {shipment.incoterm ? ` · ${shipment.incoterm}` : ""}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn btn-primary"
            type="button"
            onClick={() => navigate(`/shipments/${shipment.id}/review`)}
            disabled={!hasReviewable}
            title={hasReviewable ? "Open the review screen" : "Upload a document first"}
          >
            <Icon name="eye" size={15} />
            {shipment.status === "NEEDS_REVIEW" ? "Review shipment" : "Open review"}
          </button>
          {(shipment.status === "READY" || shipment.status === "EXPORTED") && (
            <button
              className="btn"
              type="button"
              onClick={() => navigate(`/shipments/${shipment.id}/export`)}
            >
              <Icon name="download" size={15} />
              Export
            </button>
          )}
        </div>
      </div>

      <Stepper shipment={shipment} />

      <div className="meta-grid">
        <div className="meta-cell">
          <div className="k">Supplier</div>
          <div className="v">{shipment.supplier_name ?? "—"}</div>
        </div>
        <div className="meta-cell">
          <div className="k">Commercial terms</div>
          <div className="v">
            {shipment.currency}
            {shipment.incoterm ? ` · ${shipment.incoterm}` : ""}
          </div>
        </div>
        <div className="meta-cell">
          <div className="k">Documents</div>
          <div className="v num">
            {shipment.documents.length}/3 uploaded · {extracted} extracted
          </div>
        </div>
        <div className="meta-cell">
          <div className="k">Created</div>
          <div className="v">{formatDate(shipment.created_at)}</div>
        </div>
      </div>

      {error && (
        <div className="banner banner-error" role="alert">
          <Icon name="alert" size={15} />
          <span>{error}</span>
          <button
            className="btn btn-sm btn-ghost"
            style={{ marginLeft: "auto" }}
            type="button"
            onClick={() => setError(null)}
          >
            <Icon name="x" size={13} />
          </button>
        </div>
      )}

      <div className="doc-grid">
        {(["INVOICE", "PACKING", "BL"] as DocumentType[]).map((type) => (
          <DocSlot
            key={type}
            type={type}
            document={byType.get(type)}
            uploading={type in uploading}
            progress={uploading[type] ?? 0}
            onPick={(file) => void startUpload(type, file)}
            onOpenReview={() => navigate(`/shipments/${shipment.id}/review`)}
          />
        ))}
      </div>

      <div className="privacy-note">
        <Icon name="check" size={13} style={{ color: "var(--accent)" }} />
        Files are stored privately in Mumbai and accessed through short-lived links. Only your
        organisation can open them.
      </div>

      {shipment.status === "AWAITING_APPROVAL" && (
        <div className="banner banner-warn" style={{ marginTop: 18 }}>
          <Icon name="clock" size={15} />
          <span>
            Submitted for approval. A documentation manager needs to review and approve before
            export.
          </span>
        </div>
      )}

      {shipment.status === "READY" && (
        <div className="banner" style={{ marginTop: 18, background: "#f2faf6", color: "var(--ok-fg)" }}>
          <Icon name="check" size={15} />
          <span>Approved. The shipment is ready to export in the filing layout.</span>
        </div>
      )}
    </div>
  );
}
