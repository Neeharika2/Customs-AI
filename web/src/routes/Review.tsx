import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { HistoryDrawer } from "../components/HistoryDrawer";
import { Icon } from "../components/Icon";
import {
  api,
  ApiError,
  type CheckOut,
  type DocumentReview,
  type FieldOut,
  type LineItemOut,
  type Review,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatDate, num, STATUS_LABEL } from "../lib/format";

const DOC_TYPES = ["INVOICE", "PACKING", "BL"] as const;
const DOC_LABEL: Record<string, string> = {
  INVOICE: "Invoice",
  PACKING: "Packing list",
  BL: "Bill of lading",
};

const FIELD_ORDER: Record<string, string[]> = {
  INVOICE: [
    "invoice_number", "invoice_date", "currency", "incoterm", "supplier_name", "buyer_name",
    "invoice_total", "freight", "insurance", "discount", "gross_weight_kg", "net_weight_kg",
    "packages", "package_type", "declared_item_count",
  ],
  PACKING: [
    "invoice_reference", "supplier_name", "buyer_name", "packages", "package_type",
    "gross_weight_kg", "net_weight_kg", "declared_item_count",
  ],
  BL: [
    "bl_number", "bl_date", "supplier_name", "consignee", "notify_party", "vessel_name",
    "port_of_loading", "port_of_discharge", "container_numbers", "packages", "gross_weight_kg",
  ],
};

const FIELD_LABEL: Record<string, string> = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  currency: "Currency",
  incoterm: "Incoterm",
  supplier_name: "Supplier",
  buyer_name: "Buyer",
  invoice_total: "Invoice total",
  freight: "Freight",
  insurance: "Insurance",
  discount: "Discount",
  gross_weight_kg: "Gross weight",
  net_weight_kg: "Net weight",
  packages: "Packages",
  package_type: "Package type",
  declared_item_count: "Items declared",
  invoice_reference: "Invoice reference",
  bl_number: "B/L number",
  bl_date: "B/L date",
  consignee: "Consignee",
  notify_party: "Notify party",
  vessel_name: "Vessel",
  port_of_loading: "Port of loading",
  port_of_discharge: "Port of discharge",
  container_numbers: "Containers",
};

const MANUAL_FIELDS: Record<string, { key: string; label: string; placeholder?: string }[]> = {
  INVOICE: [
    { key: "invoice_number", label: "Invoice number", placeholder: "INV-24811" },
    { key: "invoice_date", label: "Invoice date", placeholder: "dd/mm/yyyy" },
    { key: "currency", label: "Currency", placeholder: "USD" },
    { key: "supplier_name", label: "Supplier" },
    { key: "invoice_total", label: "Invoice total", placeholder: "16890.00" },
    { key: "gross_weight_kg", label: "Gross weight kg", placeholder: "3120.00" },
    { key: "packages", label: "Packages", placeholder: "120" },
  ],
  PACKING: [
    { key: "packages", label: "Packages", placeholder: "120" },
    { key: "gross_weight_kg", label: "Gross weight kg", placeholder: "3165.00" },
    { key: "net_weight_kg", label: "Net weight kg", placeholder: "3100.00" },
    { key: "supplier_name", label: "Supplier" },
  ],
  BL: [
    { key: "bl_number", label: "B/L number", placeholder: "BL-24811" },
    { key: "bl_date", label: "B/L date", placeholder: "dd/mm/yyyy" },
    { key: "supplier_name", label: "Shipper" },
    { key: "consignee", label: "Consignee" },
    { key: "container_numbers", label: "Containers", placeholder: "MSCU1234566, MSCU7654329" },
    { key: "packages", label: "Packages", placeholder: "120" },
    { key: "gross_weight_kg", label: "Gross weight kg", placeholder: "3160.00" },
  ],
};

const PILL: Record<string, string> = {
  DRAFT: "pill-draft",
  EXTRACTING: "pill-extracting",
  NEEDS_REVIEW: "pill-review",
  AWAITING_APPROVAL: "pill-awaiting",
  READY: "pill-ready",
  EXPORTED: "pill-exported",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`pill ${PILL[status] ?? "pill-draft"}`}>
      <i className="dot" />
      {STATUS_LABEL[status as keyof typeof STATUS_LABEL] ?? status}
    </span>
  );
}

function confidenceState(field: FieldOut): "ok" | "warn" | "bad" | "confirmed" | "corrected" {
  if (field.status === "CORRECTED") return "corrected";
  if (field.status === "CONFIRMED") return "confirmed";
  if (field.effective_conf < 0.55 || field.verification_level === "NONE") return "bad";
  if (field.effective_conf < 0.85) return "warn";
  return "ok";
}

function displayValue(field: FieldOut, currency: string): string {
  const value = field.value_raw;
  if (!value) return "";
  if (["gross_weight_kg", "net_weight_kg"].includes(field.key)) {
    const n = Number(value.replace(/,/g, ""));
    return Number.isNaN(n) ? value : `${num(n, 0)} kg`;
  }
  if (["invoice_total", "freight", "insurance", "discount"].includes(field.key)) {
    const n = Number(value.replace(/,/g, ""));
    return Number.isNaN(n) ? value : `${currency} ${num(n, 2)}`;
  }
  if (field.key === "container_numbers") {
    return value.split(/[,;]/).map((part) => part.trim()).filter(Boolean).join(" · ");
  }
  return value;
}

function FieldRow({
  field,
  active,
  blocked,
  currency,
  editing,
  onSelect,
  onEdit,
  onSave,
  onCancel,
  onConfirm,
}: {
  field: FieldOut;
  active: boolean;
  blocked: boolean;
  currency: string;
  editing: boolean;
  onSelect: () => void;
  onEdit: (value: string) => void;
  onSave: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [draft, setDraft] = useState(field.value_raw ?? "");
  const inputRef = useRef<HTMLInputElement>(null);
  const state = confidenceState(field);

  useEffect(() => {
    if (editing) {
      setDraft(field.value_raw ?? "");
      window.setTimeout(() => inputRef.current?.select(), 10);
    }
  }, [editing, field.value_raw]);

  const stateClass =
    state === "warn" ? "uncertain" : state === "bad" ? "blocked" : "";

  return (
    <div
      className={`field-row ${active ? "active" : ""} ${stateClass}`}
      onClick={() => {
        if (!editing) (active ? onEdit(draft) : onSelect());
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" && !editing) {
          event.preventDefault();
          active ? onEdit(draft) : onSelect();
        }
      }}
    >
      <div className="field-label">{FIELD_LABEL[field.key] ?? field.key}</div>
      <div className="field-value">
        {editing ? (
          <input
            ref={inputRef}
            className="field-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              event.stopPropagation();
              if (event.key === "Enter") onSave(draft);
              if (event.key === "Escape") onCancel();
            }}
            onBlur={() => {
              if (draft !== (field.value_raw ?? "")) onSave(draft);
              else onCancel();
            }}
          />
        ) : field.value_raw ? (
          displayValue(field, currency)
        ) : (
          <span className="empty">Not extracted</span>
        )}
      </div>
      <div className="field-meta" onClick={(event) => event.stopPropagation()}>
        {blocked && <span className="conf-dot bad" title="An open check references this field" />}
        {state === "confirmed" && <Icon name="check" size={13} style={{ color: "var(--ok-fg)" }} />}
        {state === "corrected" && <span className="conf-tag">edited</span>}
        {state === "warn" && (
          <>
            <span className="conf-dot warn" />
            <span className="conf-tag">check</span>
          </>
        )}
        {state === "bad" && (
          <>
            <span className="conf-dot bad" />
            <span className="conf-tag">verify</span>
          </>
        )}
        {state === "ok" && <span className="conf-dot ok" title="Evidence verified" />}
        {field.status !== "CONFIRMED" && (
          <button
            type="button"
            className="confirm-btn"
            title="Confirm this field"
            onClick={onConfirm}
          >
            <Icon name="check" size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

function ManualCard({
  document,
  onSave,
  busy,
}: {
  document: DocumentReview;
  onSave: (values: Record<string, string>) => void;
  busy: boolean;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const config = MANUAL_FIELDS[document.type] ?? [];
  return (
    <div className="group">
      <div className="group-head">
        <Icon name="file" size={14} />
        {DOC_LABEL[document.type]}
        <span className="muted">· needs manual entry</span>
        <span className="right">
          <span className="pill pill-review">
            <i className="dot" />
            Unreadable
          </span>
        </span>
      </div>
      <div className="manual-form">
        <div className="manual-note">
          <Icon name="alert" size={14} />
          <span>
            No usable text layer. Type the values from the page on the left. They enter the same
            checks and gate as extracted values.
          </span>
        </div>
        {config.map((item) => (
          <div className="field" key={item.key}>
            <label className="label" htmlFor={`${document.id}-${item.key}`}>
              {item.label}
            </label>
            <input
              id={`${document.id}-${item.key}`}
              className="input"
              placeholder={item.placeholder}
              value={values[item.key] ?? ""}
              onChange={(event) =>
                setValues((current) => ({ ...current, [item.key]: event.target.value }))
              }
            />
          </div>
        ))}
        <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end" }}>
          <button
            className="btn btn-primary btn-sm"
            type="button"
            disabled={busy || Object.values(values).every((value) => !value.trim())}
            onClick={() => onSave(values)}
          >
            {busy ? <Icon name="refresh" size={13} className="spin" /> : <Icon name="check" size={13} />}
            Save manual entry
          </button>
        </div>
      </div>
    </div>
  );
}

function LineEditor({
  line,
  docType,
  busy,
  onClose,
  onSave,
}: {
  line: LineItemOut;
  docType: string;
  busy: boolean;
  onClose: () => void;
  onSave: (values: Record<string, unknown>) => void;
}) {
  const [description, setDescription] = useState(line.description_raw ?? "");
  const [hsn, setHsn] = useState(line.hsn_code ?? "");
  const [qty, setQty] = useState(String(line.qty));
  const [uom, setUom] = useState(line.uom ?? "");
  const [unitPrice, setUnitPrice] = useState(line.unit_price != null ? String(line.unit_price) : "");
  const [amount, setAmount] = useState(line.amount != null ? String(line.amount) : "");
  const [gross, setGross] = useState(
    line.gross_weight_kg != null ? String(line.gross_weight_kg) : "",
  );
  const [net, setNet] = useState(line.net_weight_kg != null ? String(line.net_weight_kg) : "");
  const [reason, setReason] = useState("");

  const number = (value: string): number | null =>
    value.trim() === "" ? null : Number(value);

  const valid = description.trim().length > 0 && Number(qty) > 0;

  function save() {
    const values: Record<string, unknown> = {
      description_raw: description.trim(),
      qty: Number(qty),
      uom: uom.trim() || null,
      reason: reason.trim() || undefined,
    };
    if (docType === "INVOICE") {
      values.hsn_code = hsn.trim() || null;
      values.unit_price = number(unitPrice);
      values.amount = number(amount);
    } else {
      values.gross_weight_kg = number(gross);
      values.net_weight_kg = number(net);
    }
    onSave(values);
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        style={{ maxWidth: 540 }}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 style={{ fontSize: 16, fontWeight: 600 }}>Correct line {line.line_no}</h2>
        <p style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 4 }}>
          Saving reruns every cross-document check immediately.
        </p>

        <div className="line-editor-grid">
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label className="label" htmlFor="line-description">Description</label>
            <input
              id="line-description"
              className="input"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              autoFocus
            />
          </div>

          {docType === "INVOICE" && (
            <div className="field">
              <label className="label" htmlFor="line-hsn">HSN</label>
              <input id="line-hsn" className="input num" value={hsn} onChange={(event) => setHsn(event.target.value)} />
            </div>
          )}

          <div className="field">
            <label className="label" htmlFor="line-qty">Quantity</label>
            <input
              id="line-qty"
              className="input num"
              type="number"
              step="0.001"
              min="0"
              value={qty}
              onChange={(event) => setQty(event.target.value)}
            />
          </div>

          <div className="field">
            <label className="label" htmlFor="line-uom">Unit</label>
            <input id="line-uom" className="input" value={uom} onChange={(event) => setUom(event.target.value)} />
          </div>

          {docType === "INVOICE" ? (
            <>
              <div className="field">
                <label className="label" htmlFor="line-unit-price">Unit price</label>
                <input
                  id="line-unit-price"
                  className="input num"
                  type="number"
                  step="0.0001"
                  value={unitPrice}
                  onChange={(event) => setUnitPrice(event.target.value)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="line-amount">Amount</label>
                <input
                  id="line-amount"
                  className="input num"
                  type="number"
                  step="0.01"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                />
              </div>
            </>
          ) : (
            <>
              <div className="field">
                <label className="label" htmlFor="line-gross">Gross weight kg</label>
                <input
                  id="line-gross"
                  className="input num"
                  type="number"
                  step="0.001"
                  value={gross}
                  onChange={(event) => setGross(event.target.value)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="line-net">Net weight kg</label>
                <input
                  id="line-net"
                  className="input num"
                  type="number"
                  step="0.001"
                  value={net}
                  onChange={(event) => setNet(event.target.value)}
                />
              </div>
            </>
          )}

          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label className="label" htmlFor="line-reason">Reason (optional)</label>
            <input
              id="line-reason"
              className="input"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Why is this correction needed?"
            />
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
          <button className="btn" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" type="button" disabled={!valid || busy} onClick={save}>
            {busy ? <Icon name="refresh" size={14} className="spin" /> : <Icon name="check" size={14} />}
            Save correction
          </button>
        </div>
      </div>
    </div>
  );
}

export function ReviewScreen() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isManager = user?.role === "MANAGER";

  const [activeDoc, setActiveDoc] = useState<string>("INVOICE");
  const [activeFieldId, setActiveFieldId] = useState<string | null>(null);
  const [onlyUncertain, setOnlyUncertain] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [reasonFor, setReasonFor] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [decision, setDecision] = useState<null | "APPROVE" | "REJECT">(null);
  const [decisionNote, setDecisionNote] = useState("");
  const [reopenOpen, setReopenOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [editingLine, setEditingLine] = useState<LineItemOut | null>(null);
  const [zoom, setZoom] = useState(1);
  const viewerRef = useRef<HTMLDivElement>(null);

  const reviewQuery = useQuery({
    queryKey: ["review", id],
    queryFn: () => api.review(id as string),
    enabled: Boolean(id),
  });
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const review = reviewQuery.data;

  const openChecks = useMemo(
    () => (review?.checks ?? []).filter((check) => check.severity !== "PASS" && !check.resolved),
    [review],
  );
  const passedChecks = useMemo(
    () => (review?.checks ?? []).filter((check) => check.severity === "PASS"),
    [review],
  );
  const resolvedChecks = useMemo(
    () => (review?.checks ?? []).filter((check) => check.resolved),
    [review],
  );

  const fieldsByDoc = useMemo(() => {
    const map = new Map<string, FieldOut[]>();
    for (const field of review?.fields ?? []) {
      const list = map.get(field.document_id) ?? [];
      list.push(field);
      map.set(field.document_id, list);
    }
    return map;
  }, [review]);

  const docByType = useMemo(() => {
    const map = new Map<string, DocumentReview>();
    for (const doc of review?.documents ?? []) map.set(doc.type, doc);
    return map;
  }, [review]);

  const linesByDoc = useMemo(() => {
    const map = new Map<string, NonNullable<Review>["lines"]>();
    for (const line of review?.lines ?? []) {
      if (!line.document_id) continue;
      const list = map.get(line.document_id) ?? [];
      list.push(line);
      map.set(line.document_id, list);
    }
    return map;
  }, [review]);

  const activeField = review?.fields.find((field) => field.id === activeFieldId) ?? null;
  const activeDocument = docByType.get(activeDoc);
  const page = activeDocument?.pages.find((item) => item.idx === (activeField?.page_idx ?? 1))
    ?? activeDocument?.pages[0];

  const totalFields = review?.fields.length ?? 0;
  const confirmedFields = review?.fields.filter((field) => field.status !== "SUGGESTED").length ?? 0;
  const uncertainFields =
    review?.fields.filter(
      (field) =>
        field.status === "SUGGESTED" &&
        (field.effective_conf < 0.85 ||
          openChecks.some((check) => check.field_keys.includes(field.key))),
    ).length ?? 0;

  const highConfidence = review?.fields.filter(
    (field) =>
      field.status === "SUGGESTED" &&
      field.effective_conf >= 0.85 &&
      !openChecks.some((check) => check.field_keys.includes(field.key)),
  ).length ?? 0;

  function flash(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(null), 2600);
  }

  function applyFieldMutation(data: { field: FieldOut; gate: Review["gate"]; check: CheckOut[] }) {
    queryClient.setQueryData<Review>(["review", id], (old) =>
      old
        ? {
            ...old,
            fields: old.fields.map((field) => (field.id === data.field.id ? data.field : field)),
            gate: data.gate,
            checks: data.check,
          }
        : old,
    );
    setEditingId(null);
  }

  const patchField = useMutation({
    mutationFn: ({ fieldId, value }: { fieldId: string; value: string }) =>
      api.patchField(fieldId, value),
    onSuccess: (data) => {
      applyFieldMutation(data);
      flash("Correction saved");
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not save"),
  });

  const confirmField = useMutation({
    mutationFn: (fieldId: string) => api.confirmField(fieldId),
    onSuccess: (data) => {
      applyFieldMutation(data);
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not confirm"),
  });

  const confirmAll = useMutation({
    mutationFn: () => api.confirmHighConfidence(id as string),
    onSuccess: (data) => {
      flash(`${data.confirmed} fields confirmed`);
      void queryClient.invalidateQueries({ queryKey: ["review", id] });
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not confirm"),
  });

  const acknowledge = useMutation({
    mutationFn: ({ checkId, text }: { checkId: string; text: string }) =>
      api.acknowledgeCheck(checkId, text),
    onSuccess: () => {
      flash("Acknowledgement recorded");
      setReasonFor(null);
      setReason("");
      void queryClient.invalidateQueries({ queryKey: ["review", id] });
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not record"),
  });

  const override = useMutation({
    mutationFn: ({ checkId, text }: { checkId: string; text: string }) =>
      api.overrideCheck(checkId, text),
    onSuccess: () => {
      flash("Override recorded");
      setReasonFor(null);
      setReason("");
      void queryClient.invalidateQueries({ queryKey: ["review", id] });
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not override"),
  });

  const submit = useMutation({
    mutationFn: () => api.submit(id as string),
    onSuccess: () => {
      flash("Submitted for approval");
      void queryClient.invalidateQueries({ queryKey: ["review", id] });
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not submit"),
  });

  const decide = useMutation({
    mutationFn: (payload: { decision: "APPROVE" | "REJECT"; note?: string }) =>
      api.approve(id as string, payload.decision, payload.note),
    onSuccess: (_data, payload) => {
      flash(payload.decision === "APPROVE" ? "Shipment approved" : "Sent back for correction");
      setDecision(null);
      setDecisionNote("");
      void queryClient.invalidateQueries({ queryKey: ["review", id] });
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not complete"),
  });

  const manual = useMutation({
    mutationFn: ({ documentId, values }: { documentId: string; values: Record<string, string> }) =>
      api.manualEntry(documentId, values),
    onSuccess: () => {
      flash("Manual entry saved");
      void queryClient.invalidateQueries({ queryKey: ["review", id] });
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not save manual entry"),
  });

  const patchLine = useMutation({
    mutationFn: ({ lineId, values }: { lineId: string; values: Record<string, unknown> }) =>
      api.patchLine(lineId, values as never),
    onSuccess: (data) => {
      queryClient.setQueryData<Review>(["review", id], (old) =>
        old
          ? {
              ...old,
              lines: old.lines.map((line) => (line.id === data.line.id ? data.line : line)),
              gate: data.gate,
              checks: data.check,
            }
          : old,
      );
      setEditingLine(null);
      flash("Line corrected");
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not correct the line"),
  });

  const reopen = useMutation({
    mutationFn: () => api.reopen(id as string),
    onSuccess: () => {
      setReopenOpen(false);
      flash("Shipment reopened for review");
      void queryClient.invalidateQueries({ queryKey: ["review", id] });
      void queryClient.invalidateQueries({ queryKey: ["shipment", id] });
    },
    onError: (error) => flash(error instanceof ApiError ? error.detail : "Could not reopen"),
  });

  function selectField(field: FieldOut) {
    setActiveFieldId(field.id);
    const document = review?.documents.find((item) => item.id === field.document_id);
    if (document) setActiveDoc(document.type);
    viewerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }

  useEffect(() => {
    if (!review) return;
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.key === "j" || event.key === "k") {
        const index = DOC_TYPES.indexOf(activeDoc as (typeof DOC_TYPES)[number]);
        const next = event.key === "j" ? (index + 1) % 3 : (index + 2) % 3;
        if (docByType.has(DOC_TYPES[next])) setActiveDoc(DOC_TYPES[next]);
      }
      if (event.key === "1") setActiveDoc("INVOICE");
      if (event.key === "2") setActiveDoc("PACKING");
      if (event.key === "3") setActiveDoc("BL");
      if (event.key === "Escape") {
        setActiveFieldId(null);
        setEditingId(null);
      }
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        if (review.gate.ok && review.shipment.status === "NEEDS_REVIEW") submit.mutate();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });

  if (reviewQuery.isLoading) {
    return (
      <div className="review">
        <div className="review-head">
          <div className="skeleton" style={{ width: 28, height: 28 }} />
          <div className="skeleton" style={{ width: 160, height: 16 }} />
        </div>
        <div className="review-grid">
          <div className="doc-pane" style={{ padding: 16 }}>
            <div className="skeleton" style={{ flex: 1, borderRadius: 8 }} />
          </div>
          <div className="fields-pane" style={{ padding: 16, display: "grid", gap: 10 }}>
            {Array.from({ length: 8 }).map((_, index) => (
              <div key={index} className="skeleton" style={{ height: 34 }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (reviewQuery.isError || !review) {
    return (
      <div className="review">
        <div className="review-head">
          <button className="review-back" type="button" onClick={() => navigate("/shipments")}>
            <Icon name="arrow-left" size={15} />
          </button>
          <div className="review-title">
            <h1>Could not open review</h1>
          </div>
        </div>
        <div className="empty">
          <div className="empty-icon">
            <Icon name="alert" size={19} />
          </div>
          <h3>The review could not be loaded</h3>
          <p>
            {reviewQuery.error instanceof ApiError
              ? reviewQuery.error.detail
              : "An unexpected error occurred."}
          </p>
          <button className="btn" type="button" onClick={() => void reviewQuery.refetch()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  const shipment = review.shipment;
  const blockers = review.gate.blockers;
  const canSubmit = review.gate.ok && shipment.status === "NEEDS_REVIEW";

  return (
    <div className="review">
      <header className="review-head">
        <button
          className="review-back"
          type="button"
          onClick={() => navigate(`/shipments/${shipment.id}`)}
          title="Back to shipment"
        >
          <Icon name="arrow-left" size={15} />
        </button>
        <div className="review-title">
          <h1>{shipment.ref}</h1>
          <div className="review-sub">
            {shipment.supplier_name} · {shipment.currency}
            {shipment.incoterm ? ` · ${shipment.incoterm}` : ""} · {formatDate(shipment.created_at)}
          </div>
        </div>
        <StatusPill status={shipment.status} />
        <div className="review-head-right">
          <button
            className="btn btn-sm"
            type="button"
            onClick={() => setHistoryOpen(true)}
            title="Correction and approval history"
          >
            <Icon name="clock" size={14} />
            History
          </button>
          {metaQuery.data?.extractor === "fixture" && (
            <span
              className="extractor-tag"
              title="Rule-based fixture extractor. Vertex AI is used when GOOGLE_CLOUD_PROJECT and VERTEX_MODEL are configured."
            >
              <Icon name="spark" size={12} />
              Demo extractor
            </span>
          )}
          <button
            className="btn btn-sm"
            type="button"
            onClick={() => void reviewQuery.refetch()}
            title="Refresh"
          >
            <Icon name="refresh" size={14} className={reviewQuery.isFetching ? "spin" : ""} />
          </button>
        </div>
      </header>

      <div className="review-grid">
        <section className="doc-pane">
          <div className="doc-tabs">
            {DOC_TYPES.map((type) => {
              const document = docByType.get(type);
              const bad = document && ["NEEDS_MANUAL_ENTRY", "FAILED"].includes(document.status);
              const pending = document && ["QUEUED", "PROCESSING", "UPLOADED"].includes(document.status);
              return (
                <button
                  key={type}
                  type="button"
                  className={`doc-tab${activeDoc === type ? " active" : ""}`}
                  disabled={!document}
                  onClick={() => setActiveDoc(type)}
                  title={document ? document.file_name : "Not uploaded"}
                >
                  <span className={`status-dot${bad ? " bad" : pending ? " pending" : ""}`} />
                  {DOC_LABEL[type]}
                </button>
              );
            })}
            <div className="doc-tools">
              <button
                className="btn btn-ghost btn-sm"
                type="button"
                onClick={() => setZoom((value) => Math.max(0.6, +(value - 0.15).toFixed(2)))}
                title="Zoom out"
              >
                −
              </button>
              <span className="zoom-label">{Math.round(zoom * 100)}%</span>
              <button
                className="btn btn-ghost btn-sm"
                type="button"
                onClick={() => setZoom((value) => Math.min(2.5, +(value + 0.15).toFixed(2)))}
                title="Zoom in"
              >
                +
              </button>
            </div>
          </div>

          <div className="viewer-scroll" ref={viewerRef}>
            {activeDocument && page ? (
              <div className="viewer-inner" style={{ width: `${Math.round(zoom * 100)}%` }}>
                <img src={page.url} alt={`${DOC_LABEL[activeDoc]} page ${page.idx}`} />
                {activeField?.bbox &&
                  activeField.document_id === activeDocument.id &&
                  page.idx === activeField.page_idx && (
                    <div
                      className="bbox"
                      style={{
                        left: `${activeField.bbox.x0 * 100}%`,
                        top: `${activeField.bbox.y0 * 100}%`,
                        width: `${(activeField.bbox.x1 - activeField.bbox.x0) * 100}%`,
                        height: `${(activeField.bbox.y1 - activeField.bbox.y0) * 100}%`,
                      }}
                    />
                  )}
              </div>
            ) : (
              <div className="viewer-empty">
                <Icon name="file" size={22} />
                <span>
                  {activeDocument
                    ? "This document has no rendered pages. Manual entry is available on the right."
                    : `${DOC_LABEL[activeDoc]} has not been uploaded.`}
                </span>
                {!activeDocument && (
                  <button
                    className="btn btn-sm"
                    type="button"
                    onClick={() => navigate(`/shipments/${shipment.id}`)}
                  >
                    Open shipment
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="evidence">
            <div className="evidence-head">
              <Icon name="file" size={12} />
              {activeField
                ? `Source · page ${activeField.page_idx} · ${activeField.verification_level}`
                : "Source evidence"}
            </div>
            {activeField ? (
              <>
                <div className="evidence-quote">
                  {activeField.quote
                    ? `“${activeField.quote}”`
                    : "No quotation was returned for this field."}
                </div>
                <div className="evidence-note">
                  {activeField.verification_level === "EXACT"
                    ? "Located in the document's text layer. The highlight is derived from the quote, not from the model's coordinates."
                    : activeField.verification_level === "NONE"
                      ? "No source located. Enter this value manually and it will be marked as human-entered."
                      : "Quote present but not independently verifiable on this page. Confirm before export."}
                </div>
              </>
            ) : (
              <div className="evidence-note">
                Select a field to see the exact text it came from. Values with a verified quote are
                marked with a dot; amber means confirm.
              </div>
            )}
          </div>
        </section>

        <section className="fields-pane">
          <div className="fields-toolbar">
            <strong style={{ fontSize: 12.5 }}>Extracted data</strong>
            <span style={{ fontSize: 11.5, color: "var(--muted)" }}>
              {confirmedFields}/{totalFields} confirmed
            </span>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              <button
                type="button"
                className="toggle"
                aria-pressed={onlyUncertain}
                onClick={() => setOnlyUncertain((value) => !value)}
              >
                <Icon name="eye" size={13} />
                Only uncertain
              </button>
            </div>
          </div>

          <div className="fields-scroll">
            <div className={`issues-card${openChecks.length === 0 ? " clear" : ""}`} id="issues">
              {openChecks.length === 0 ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 12px", fontSize: 12 }}>
                  <Icon name="check" size={14} style={{ color: "var(--ok-fg)" }} />
                  All cross-document checks pass
                </div>
              ) : (
                openChecks.map((check) => {
                  const blocking = check.severity === "BLOCK";
                  return (
                    <div className="issue-row" key={check.id}>
                      <Icon
                        name={blocking ? "block" : "alert"}
                        size={15}
                        style={{ color: blocking ? "var(--block-fg)" : "var(--warn-fg)", marginTop: 1 }}
                      />
                      <div>
                        <div className="code">{check.code.replaceAll("_", " ")}</div>
                        <div className="msg">{check.message}</div>
                        {reasonFor === check.id && (
                          <div className="reason-box">
                            <input
                              className="input"
                              placeholder={
                                blocking
                                  ? "Reason for overriding this block (required)"
                                  : "Why is this difference acceptable?"
                              }
                              value={reason}
                              onChange={(event) => setReason(event.target.value)}
                              autoFocus
                            />
                            <button
                              className="btn btn-sm btn-primary"
                              type="button"
                              disabled={
                                reason.trim().length < (blocking ? 10 : 3) ||
                                acknowledge.isPending ||
                                override.isPending
                              }
                              onClick={() =>
                                blocking
                                  ? override.mutate({ checkId: check.id, text: reason })
                                  : acknowledge.mutate({ checkId: check.id, text: reason })
                              }
                            >
                              Record
                            </button>
                            <button
                              className="btn btn-sm"
                              type="button"
                              onClick={() => {
                                setReasonFor(null);
                                setReason("");
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                      <div className="issue-actions">
                        {check.field_keys.length > 0 && (
                          <button
                            className="btn btn-sm btn-ghost"
                            type="button"
                            onClick={() => {
                              const field = review.fields.find((item) =>
                                check.field_keys.includes(item.key),
                              );
                              if (field) selectField(field);
                            }}
                          >
                            View
                          </button>
                        )}
                        {blocking && !isManager ? (
                          <span style={{ fontSize: 10.5, color: "var(--faint)" }}>Manager</span>
                        ) : (
                          <button
                            className="btn btn-sm"
                            type="button"
                            onClick={() => {
                              setReasonFor(reasonFor === check.id ? null : check.id);
                              setReason("");
                            }}
                          >
                            {blocking ? "Override" : "Acknowledge"}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {DOC_TYPES.map((type) => {
              const document = docByType.get(type);
              if (!document) {
                return (
                  <div className="group" key={type}>
                    <div className="group-head">
                      <Icon name="file" size={14} />
                      {DOC_LABEL[type]}
                      <span className="muted">· not uploaded</span>
                      <span className="right">
                        <button
                          className="btn btn-sm"
                          type="button"
                          onClick={() => navigate(`/shipments/${shipment.id}`)}
                        >
                          Add document
                        </button>
                      </span>
                    </div>
                  </div>
                );
              }
              if (["NEEDS_MANUAL_ENTRY", "FAILED"].includes(document.status)) {
                return (
                  <ManualCard
                    key={type}
                    document={document}
                    busy={manual.isPending}
                    onSave={(values) =>
                      manual.mutate({ documentId: document.id, values })
                    }
                  />
                );
              }

              const order = FIELD_ORDER[type] ?? [];
              const all = fieldsByDoc.get(document.id) ?? [];
              const fields = all
                .filter((field) => order.includes(field.key) || field.line_no === null)
                .sort(
                  (a, b) =>
                    order.indexOf(a.key) - order.indexOf(b.key) || a.key.localeCompare(b.key),
                )
                .filter((field) => {
                  if (!onlyUncertain) return true;
                  return (
                    field.status === "SUGGESTED" &&
                    (field.effective_conf < 0.85 ||
                      openChecks.some((check) => check.field_keys.includes(field.key)))
                  );
                });

              const lines = document ? linesByDoc.get(document.id) ?? [] : [];

              return (
                <div className="group" key={type}>
                  <div className="group-head">
                    <Icon name="file" size={14} />
                    {DOC_LABEL[type]}
                    <span className="muted">
                      · {all.length} fields
                      {document.page_count ? ` · ${document.page_count} page` : ""}
                    </span>
                    <span className="right">
                      <span style={{ fontSize: 10.5, color: "var(--faint)" }}>
                        {document.file_name}
                      </span>
                    </span>
                  </div>

                  {fields.map((field) => (
                    <FieldRow
                      key={field.id}
                      field={field}
                      active={activeFieldId === field.id}
                      blocked={openChecks.some((check) => check.field_keys.includes(field.key))}
                      currency={shipment.currency}
                      editing={editingId === field.id}
                      onSelect={() => selectField(field)}
                      onEdit={() => {
                        setActiveFieldId(field.id);
                        setEditingId(field.id);
                      }}
                      onSave={(value) => {
                        patchField.mutate({ fieldId: field.id, value });
                      }}
                      onCancel={() => setEditingId(null)}
                      onConfirm={() => confirmField.mutate(field.id)}
                    />
                  ))}

                  {fields.length === 0 && (
                    <div style={{ padding: "10px 13px", fontSize: 12, color: "var(--muted)" }}>
                      {onlyUncertain ? "No uncertain fields here." : "No extracted fields."}
                    </div>
                  )}

                  {lines.length > 0 && (
                    <>
                      <div
                        style={{
                          padding: "8px 13px",
                          borderTop: "1px solid var(--border)",
                          background: "#fcfcfa",
                          fontSize: 11,
                          fontWeight: 600,
                          color: "var(--muted)",
                        }}
                      >
                        Line items
                      </div>
                      <table className="line-table">
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Description</th>
                            {type === "INVOICE" && <th>HSN</th>}
                            <th className="r">Qty</th>
                            {type === "INVOICE" ? (
                              <>
                                <th className="r">Unit price</th>
                                <th className="r">Amount</th>
                              </>
                            ) : (
                              <>
                                <th className="r">Gross kg</th>
                                <th className="r">Net kg</th>
                              </>
                            )}
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {lines.map((line) => (
                            <tr key={line.id}>
                              <td className="num">
                                <span
                                  className={`conf-dot ${
                                    line.status === "CORRECTED"
                                      ? "ok"
                                      : line.effective_conf < 0.55
                                        ? "bad"
                                        : line.effective_conf < 0.85
                                          ? "warn"
                                          : "ok"
                                  }`}
                                  title={`${line.verification_level} · confidence ${Math.round(
                                    line.effective_conf * 100,
                                  )}%`}
                                  style={{ marginRight: 6 }}
                                />
                                {line.line_no}
                              </td>
                              <td>
                                {line.description_raw}
                                {line.status === "CORRECTED" && (
                                  <span className="conf-tag" style={{ marginLeft: 6 }}>
                                    edited
                                  </span>
                                )}
                              </td>
                              {type === "INVOICE" && <td className="num">{line.hsn_code ?? "—"}</td>}
                              <td className="r num">
                                {num(line.qty)} {line.uom ?? ""}
                              </td>
                              {type === "INVOICE" ? (
                                <>
                                  <td className="r num">{line.unit_price != null ? num(line.unit_price, 2) : "—"}</td>
                                  <td className="r num">{line.amount != null ? num(line.amount, 2) : "—"}</td>
                                </>
                              ) : (
                                <>
                                  <td className="r num">
                                    {line.gross_weight_kg != null ? num(line.gross_weight_kg, 2) : "—"}
                                  </td>
                                  <td className="r num">
                                    {line.net_weight_kg != null ? num(line.net_weight_kg, 2) : "—"}
                                  </td>
                                </>
                              )}
                              <td className="r">
                                <button
                                  className="line-edit-btn"
                                  type="button"
                                  title="Correct this line"
                                  onClick={() => setEditingLine(line)}
                                >
                                  <Icon name="edit" size={13} />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  )}
                </div>
              );
            })}

            <details className="group checks-collapsed">
              <summary>
                {passedChecks.length} checks passed
                {resolvedChecks.length > 0 ? ` · ${resolvedChecks.length} resolved` : ""}
              </summary>
              {passedChecks.map((check) => (
                <div className="check-row pass" key={check.id}>
                  <Icon name="check" size={12} style={{ color: "var(--ok-fg)" }} />
                  {check.message}
                </div>
              ))}
              {resolvedChecks.map((check) => (
                <div className="check-row pass" key={check.id}>
                  <Icon name="check" size={12} style={{ color: "var(--ok-fg)" }} />
                  <span>
                    <strong style={{ color: "var(--ink-2)" }}>{check.code.replaceAll("_", " ")}</strong>
                    {" — "}
                    {check.resolved_reason}
                  </span>
                </div>
              ))}
            </details>
          </div>

          <div className="action-bar">
            <div className="action-meta">
              <strong className="num">
                {confirmedFields}/{totalFields}
              </strong>
              confirmed
              <span style={{ color: "var(--border-strong)" }}>·</span>
              {openChecks.length === 0 ? (
                <span style={{ color: "var(--ok-fg)" }}>All checks clear</span>
              ) : (
                <span style={{ color: "var(--warn-fg)" }}>
                  {openChecks.length} open {openChecks.length === 1 ? "issue" : "issues"}
                </span>
              )}
              {uncertainFields > 0 && (
                <>
                  <span style={{ color: "var(--border-strong)" }}>·</span>
                  <button
                    className="btn btn-sm btn-ghost"
                    type="button"
                    onClick={() => {
                      setOnlyUncertain(true);
                      document.getElementById("issues")?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    {uncertainFields} need you
                  </button>
                </>
              )}
            </div>

            <div className="action-buttons">
              {highConfidence > 0 && (
                <button
                  className="btn btn-sm"
                  type="button"
                  disabled={confirmAll.isPending}
                  onClick={() => confirmAll.mutate()}
                >
                  <Icon name="check" size={14} />
                  Confirm high-confidence ({highConfidence})
                </button>
              )}

              {shipment.status === "NEEDS_REVIEW" && (
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={!canSubmit || submit.isPending}
                  title={!review.gate.ok ? blockers[0]?.message : "Submit for manager approval"}
                  onClick={() => submit.mutate()}
                >
                  {submit.isPending ? (
                    <Icon name="refresh" size={14} className="spin" />
                  ) : (
                    <Icon name="arrow-right" size={14} />
                  )}
                  Submit for approval
                </button>
              )}

              {shipment.status === "AWAITING_APPROVAL" && (
                isManager ? (
                  <>
                    <button className="btn" type="button" onClick={() => setDecision("REJECT")}>
                      Reject
                    </button>
                    <button
                      className="btn btn-primary"
                      type="button"
                      disabled={decide.isPending}
                      onClick={() => setDecision("APPROVE")}
                    >
                      <Icon name="check" size={14} />
                      Approve shipment
                    </button>
                  </>
                ) : (
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>
                    Awaiting manager approval
                  </span>
                )
              )}

              {isManager &&
                (shipment.status === "READY" || shipment.status === "EXPORTED") && (
                  <button className="btn" type="button" onClick={() => setReopenOpen(true)}>
                    Reopen
                  </button>
                )}

              {shipment.status === "READY" && (
                <button
                  className="btn btn-primary"
                  type="button"
                  onClick={() => navigate(`/shipments/${shipment.id}/export`)}
                >
                  <Icon name="download" size={14} />
                  Export
                </button>
              )}

              {shipment.status === "EXPORTED" && (
                <button
                  className="btn"
                  type="button"
                  onClick={() => navigate(`/shipments/${shipment.id}/export`)}
                >
                  <Icon name="download" size={14} />
                  Download
                </button>
              )}
            </div>
          </div>
        </section>
      </div>

      <HistoryDrawer
        shipmentId={shipment.id}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />

      {toast && <div className="toast">{toast}</div>}

      {editingLine && (
        <LineEditor
          line={editingLine}
          docType={
            review.documents.find((document) => document.id === editingLine.document_id)?.type ??
            "INVOICE"
          }
          busy={patchLine.isPending}
          onClose={() => setEditingLine(null)}
          onSave={(values) => patchLine.mutate({ lineId: editingLine.id, values })}
        />
      )}

      {reopenOpen && (
        <div className="modal-backdrop" onClick={() => setReopenOpen(false)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h2 style={{ fontSize: 16, fontWeight: 600 }}>Reopen this shipment?</h2>
            <p style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
              The approval is voided and the shipment returns to review. Its export history is kept.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button className="btn" type="button" onClick={() => setReopenOpen(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                type="button"
                disabled={reopen.isPending}
                onClick={() => reopen.mutate()}
              >
                {reopen.isPending ? (
                  <Icon name="refresh" size={14} className="spin" />
                ) : (
                  <Icon name="refresh" size={14} />
                )}
                Reopen
              </button>
            </div>
          </div>
        </div>
      )}

      {decision && (
        <div className="modal-backdrop" onClick={() => setDecision(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h2 style={{ fontSize: 16, fontWeight: 600 }}>
              {decision === "APPROVE" ? "Approve this shipment?" : "Send back for correction"}
            </h2>
            <p style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 6 }}>
              {decision === "APPROVE"
                ? "Approval is invalidated if any field changes afterwards."
                : "The executive sees your note on the shipment."}
            </p>
            {decision === "REJECT" && (
              <textarea
                className="input"
                style={{ height: 84, padding: 9, marginTop: 12, resize: "vertical" }}
                placeholder="What needs correcting?"
                value={decisionNote}
                onChange={(event) => setDecisionNote(event.target.value)}
                autoFocus
              />
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button className="btn" type="button" onClick={() => setDecision(null)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                type="button"
                disabled={
                  decide.isPending || (decision === "REJECT" && decisionNote.trim().length < 3)
                }
                onClick={() =>
                  decide.mutate({
                    decision,
                    note: decision === "REJECT" ? decisionNote : undefined,
                  })
                }
              >
                {decide.isPending ? (
                  <Icon name="refresh" size={14} className="spin" />
                ) : (
                  <Icon name="check" size={14} />
                )}
                {decision === "APPROVE" ? "Approve" : "Send back"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
