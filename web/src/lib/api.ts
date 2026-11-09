export type Role = "EXEC" | "MANAGER";

export type ShipmentStatus =
  | "DRAFT"
  | "EXTRACTING"
  | "NEEDS_REVIEW"
  | "AWAITING_APPROVAL"
  | "READY"
  | "EXPORTED";

export type DocumentType = "INVOICE" | "PACKING" | "BL";
export type DocumentStatus =
  | "UPLOADED"
  | "QUEUED"
  | "PROCESSING"
  | "EXTRACTED"
  | "FAILED"
  | "NEEDS_MANUAL_ENTRY";
export type EvidenceLevel = "EXACT" | "CONTAINED" | "CLAIMED" | "NONE";
export type FieldStatus = "SUGGESTED" | "CONFIRMED" | "CORRECTED";
export type Severity = "PASS" | "WARN" | "BLOCK";

export interface User {
  id: string;
  email: string;
  role: Role;
  org_id: string;
  org_name: string;
}

export interface Me {
  user: User;
  csrf_token: string;
}

export interface Supplier {
  id: string;
  name: string;
  country_code: string | null;
}

export interface ShipmentListItem {
  id: string;
  ref: string;
  supplier_name: string | null;
  currency: string;
  incoterm: string | null;
  status: ShipmentStatus;
  document_count: number;
  document_total: number;
  open_issues: number;
  updated_at: string;
}

export interface ShipmentList {
  items: ShipmentListItem[];
  total: number;
  counts: Record<string, number>;
}

export interface DocumentOut {
  id: string;
  type: DocumentType;
  file_name: string;
  page_count: number;
  status: DocumentStatus;
  error_code: string | null;
  error_detail: string | null;
  created_at: string;
}

export interface Shipment {
  id: string;
  ref: string;
  supplier_id: string | null;
  supplier_name: string | null;
  currency: string;
  incoterm: string | null;
  status: ShipmentStatus;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  documents: DocumentOut[];
  document_total: number;
}

export interface FieldOut {
  id: string;
  document_id: string;
  key: string;
  line_no: number | null;
  value_raw: string | null;
  value_norm: string | null;
  model_conf: number;
  effective_conf: number;
  verification_level: EvidenceLevel;
  page_idx: number;
  bbox: { x0: number; y0: number; x1: number; y1: number } | null;
  quote: string | null;
  status: FieldStatus;
}

export interface CheckOut {
  id: string;
  code: string;
  subject_key: string;
  severity: Severity;
  message: string;
  field_keys: string[];
  params: Record<string, unknown>;
  input_hash: string;
  resolved: boolean;
  resolved_reason: string | null;
}

export interface GateBlocker {
  code: string;
  message: string;
  field_id?: string | null;
  document_id?: string | null;
}

export interface Gate {
  ok: boolean;
  blockers: GateBlocker[];
}

export interface LineItemOut {
  id: string;
  document_id: string | null;
  line_no: number;
  description_raw: string | null;
  hsn_code: string | null;
  qty: number;
  uom: string | null;
  unit_price: number | null;
  amount: number | null;
  gross_weight_kg: number | null;
  net_weight_kg: number | null;
  matched_line_id: string | null;
  match_score: number | null;
  status: FieldStatus;
  verification_level: EvidenceLevel;
  effective_conf: number;
  page_idx: number;
  bbox: { x0: number; y0: number; x1: number; y1: number } | null;
  quote: string | null;
}

export interface LineMutation {
  line: LineItemOut;
  gate: Gate;
  check: CheckOut[];
}

export interface ActivityItem {
  id: string;
  kind: "correction" | "approval" | "export" | "status";
  at: string;
  actor: string;
  title: string;
  detail: string;
  reason: string | null;
}

export interface ActivityOut {
  items: ActivityItem[];
}

export interface PageOut {
  idx: number;
  url: string;
  width: number;
  height: number;
  source: string;
}

export interface DocumentReview extends DocumentOut {
  pages: PageOut[];
}

export interface Review {
  shipment: Shipment;
  documents: DocumentReview[];
  fields: FieldOut[];
  lines: LineItemOut[];
  checks: CheckOut[];
  gate: Gate;
}

export interface Meta {
  app: string;
  version: string;
  env: string;
  extractor: "vertex" | "developer" | "fixture";
  model: string;
  region: string;
  storage: "local" | "s3";
  storage_region: string;
}

export interface FieldMutation {
  field: FieldOut;
  gate: Gate;
  check: CheckOut[];
}

export interface ExportPreview {
  template: { id: string; name: string; version: number };
  headers: string[];
  rows: string[][];
  total_rows: number;
  gate: Gate;
  shipment_status: ShipmentStatus;
  shipment_ref: string;
  existing_export: {
    id: string;
    created_at: string;
    row_count: number;
    url: string;
  } | null;
}

export interface ExportResult {
  export_id: string;
  url: string;
  row_count: number;
  content_hash: string;
}

export interface ReportField {
  key: string;
  extracted: number;
  corrected: number;
  correction_rate: number;
  avg_confidence: number;
  sufficient: boolean;
}

export interface ReportSupplier {
  supplier: string;
  shipments: number;
  fields: number;
  corrected: number;
  correction_rate: number;
  manual_documents: number;
  sufficient: boolean;
}

export interface SettingsData {
  org_name: string;
  weight_tol_pct: number;
  value_tol: number;
  retention_days: number;
  template: {
    id: string;
    name: string;
    version: number;
    columns: {
      header: string;
      source: string;
      required?: boolean;
      format?: string | null;
      join?: string | null;
    }[];
  } | null;
  users: { email: string; role: string; active: boolean }[];
}

export interface ReportOverview {
  totals: {
    shipments: number;
    documents: number;
    fields: number;
    corrections: number;
    manual_documents: number;
    manual_rate: number;
    first_pass: number;
    evidence_coverage: number;
  };
  fields: ReportField[];
  suppliers: ReportSupplier[];
  small_sample: number;
}

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  payload: unknown;

  constructor(status: number, code: string, detail: string, payload: unknown) {
    super(detail);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.payload = payload;
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-CSRF-Token", csrfToken());
  }
  const res = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    let payload: any = null;
    try {
      payload = await res.json();
    } catch {
      /* ignore */
    }
    const code = payload?.code ?? `http_${res.status}`;
    const detail = payload?.detail ?? res.statusText ?? "Request failed";
    throw new ApiError(res.status, code, detail, payload);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<Me>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => request<Me>("/auth/me"),
  shipments: (params: { status?: string; q?: string; page?: number; limit?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.status) search.set("status", params.status);
    if (params.q) search.set("q", params.q);
    if (params.page) search.set("page", String(params.page));
    if (params.limit) search.set("limit", String(params.limit));
    const qs = search.toString();
    return request<ShipmentList>(`/shipments${qs ? `?${qs}` : ""}`);
  },
  shipment: (id: string) => request<Shipment>(`/shipments/${id}`),
  createShipment: (body: {
    ref: string;
    supplier_id?: string | null;
    incoterm?: string | null;
    currency?: string;
  }) => request<Shipment>("/shipments", { method: "POST", body: JSON.stringify(body) }),
  suppliers: () => request<Supplier[]>("/suppliers"),
  meta: () => request<Meta>("/meta"),
  review: (id: string) => request<Review>(`/shipments/${id}/review`),
  exportPreview: (id: string) =>
    request<ExportPreview>(`/shipments/${id}/export/preview`),
  createExport: (id: string) =>
    request<ExportResult>(`/shipments/${id}/export`, { method: "POST" }),
  reports: () => request<ReportOverview>("/reports/overview"),
  settings: () => request<SettingsData>("/settings"),
  saveSettings: (body: {
    weight_tol_pct: number;
    value_tol: number;
    retention_days: number;
  }) => request<SettingsData>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  patchField: (fieldId: string, value: string, reason?: string) =>
    request<FieldMutation>(`/fields/${fieldId}`, {
      method: "PATCH",
      body: JSON.stringify({ value, reason }),
    }),
  confirmField: (fieldId: string) =>
    request<FieldMutation>(`/fields/${fieldId}/confirm`, { method: "POST" }),
  confirmHighConfidence: (shipmentId: string) =>
    request<{ confirmed: number; gate: Gate }>(
      `/shipments/${shipmentId}/confirm-high-confidence`,
      { method: "POST" },
    ),
  acknowledgeCheck: (checkId: string, reason: string) =>
    request<Gate>(`/checks/${checkId}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  overrideCheck: (checkId: string, reason: string) =>
    request<Gate>(`/checks/${checkId}/override`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  submit: (shipmentId: string) =>
    request<{ status: ShipmentStatus; gate: Gate }>(`/shipments/${shipmentId}/submit`, {
      method: "POST",
    }),
  approve: (shipmentId: string, decision: "APPROVE" | "REJECT", note?: string) =>
    request<{ status: ShipmentStatus; gate: Gate }>(`/shipments/${shipmentId}/approve`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    }),
  reopen: (shipmentId: string) =>
    request<{ status: ShipmentStatus; gate: Gate }>(`/shipments/${shipmentId}/reopen`, {
      method: "POST",
    }),
  manualEntry: (documentId: string, values: Record<string, string>) =>
    request<DocumentOut>(`/documents/${documentId}/manual`, {
      method: "POST",
      body: JSON.stringify({ values }),
    }),
  patchLine: (
    lineId: string,
    values: {
      description_raw?: string;
      hsn_code?: string;
      qty?: number;
      uom?: string;
      unit_price?: number | null;
      amount?: number | null;
      gross_weight_kg?: number | null;
      net_weight_kg?: number | null;
      reason?: string;
    },
  ) => request<LineMutation>(`/line-items/${lineId}`, { method: "PATCH", body: JSON.stringify(values) }),
  activity: (shipmentId: string) =>
    request<ActivityOut>(`/shipments/${shipmentId}/activity`),
  deleteDocument: (documentId: string) =>
    request<void>(`/documents/${documentId}`, { method: "DELETE" }),
  reprocessDocument: (documentId: string) =>
    request<DocumentOut>(`/documents/${documentId}/reprocess`, { method: "POST" }),
  saveTemplate: (
    templateId: string,
    name: string,
    columns: { header: string; source: string; required?: boolean; format?: string | null; join?: string | null }[],
  ) =>
    request<{ id: string; name: string; version: number; columns: unknown[] }>(
      `/export-templates/${templateId}`,
      { method: "PUT", body: JSON.stringify({ name, columns }) },
    ),
};

export function uploadDocument(
  shipmentId: string,
  type: DocumentType,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<DocumentOut> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/shipments/${shipmentId}/documents`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-CSRF-Token", csrfToken());
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      let payload: any = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as DocumentOut);
      } else {
        reject(
          new ApiError(
            xhr.status,
            payload?.code ?? `http_${xhr.status}`,
            payload?.detail ?? "Upload failed",
            payload,
          ),
        );
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "network", "Upload failed. Check your connection.", null));
    const form = new FormData();
    form.append("type", type);
    form.append("file", file);
    xhr.send(form);
  });
}
