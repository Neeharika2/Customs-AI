from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models import (
    Decision,
    DocumentStatus,
    DocumentType,
    EvidenceLevel,
    FieldStatus,
    Role,
    Severity,
    ShipmentStatus,
)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def lower(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    id: str
    email: str
    role: Role
    org_id: str
    org_name: str


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str


class SupplierOut(BaseModel):
    id: str
    name: str
    country_code: str | None


class ShipmentCreateIn(BaseModel):
    ref: str = Field(min_length=3, max_length=40)
    supplier_id: str | None = None
    incoterm: str | None = Field(default=None, max_length=8)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("ref")
    @classmethod
    def upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("currency")
    @classmethod
    def currency_upper(cls, value: str) -> str:
        return value.strip().upper()


class DocumentOut(BaseModel):
    id: str
    type: DocumentType
    file_name: str
    page_count: int
    status: DocumentStatus
    error_code: str | None = None
    error_detail: str | None = None
    created_at: datetime


class ShipmentListItem(BaseModel):
    id: str
    ref: str
    supplier_name: str | None
    currency: str
    incoterm: str | None
    status: ShipmentStatus
    document_count: int
    document_total: int
    open_issues: int
    updated_at: datetime


class ShipmentListOut(BaseModel):
    items: list[ShipmentListItem]
    total: int
    counts: dict[str, int]


class ShipmentOut(BaseModel):
    id: str
    ref: str
    supplier_id: str | None
    supplier_name: str | None
    currency: str
    incoterm: str | None
    status: ShipmentStatus
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    documents: list[DocumentOut]
    document_total: int = 3


class DocumentPresignIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime: str = Field(min_length=3, max_length=100)
    size: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    type: DocumentType


class DocumentPresignOut(BaseModel):
    document_id: str
    upload_url: str
    key: str


class DocumentConfirmIn(BaseModel):
    document_id: str


class FieldOut(BaseModel):
    id: str
    document_id: str
    key: str
    line_no: int | None
    value_raw: str | None
    value_norm: str | None
    model_conf: float
    effective_conf: float
    verification_level: EvidenceLevel
    page_idx: int
    bbox: dict | None
    quote: str | None
    status: FieldStatus


class FieldPatchIn(BaseModel):
    value: str | None = None
    reason: str | None = Field(default=None, max_length=400)


class CheckOut(BaseModel):
    id: str
    code: str
    subject_key: str
    severity: Severity
    message: str
    field_keys: list[str] = []
    params: dict = {}
    input_hash: str
    resolved: bool = False
    resolved_reason: str | None = None


class GateBlocker(BaseModel):
    code: str
    message: str
    field_id: str | None = None
    document_id: str | None = None


class GateOut(BaseModel):
    ok: bool
    blockers: list[GateBlocker]


class LineItemOut(BaseModel):
    id: str
    document_id: str | None
    line_no: int
    description_raw: str | None
    hsn_code: str | None
    qty: float
    uom: str | None
    unit_price: float | None
    amount: float | None
    gross_weight_kg: float | None
    net_weight_kg: float | None
    matched_line_id: str | None
    match_score: float | None


class PageOut(BaseModel):
    idx: int
    url: str
    width: int
    height: int
    source: str


class DocumentReviewOut(DocumentOut):
    pages: list[PageOut] = []


class ReviewOut(BaseModel):
    shipment: ShipmentOut
    documents: list[DocumentReviewOut]
    fields: list[FieldOut]
    lines: list[LineItemOut]
    checks: list[CheckOut]
    gate: GateOut


class FieldMutationOut(BaseModel):
    field: FieldOut
    gate: GateOut
    check: list[CheckOut] = []


class ConfirmAllOut(BaseModel):
    confirmed: int
    gate: GateOut


class SubmitOut(BaseModel):
    status: ShipmentStatus
    gate: GateOut


class CheckAcknowledgeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=400)


class ApprovalIn(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str | None = Field(default=None, max_length=600)


class ExportColumn(BaseModel):
    header: str
    source: str
    required: bool = False
    format: str | None = None
    join: str | None = None
