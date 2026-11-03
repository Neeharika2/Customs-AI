from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def enum(values: type[StrEnum], length: int = 32) -> Enum:
    return Enum(values, native_enum=False, validate_strings=True, length=length)


class Role(StrEnum):
    EXEC = "EXEC"
    MANAGER = "MANAGER"


class ShipmentStatus(StrEnum):
    DRAFT = "DRAFT"
    EXTRACTING = "EXTRACTING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    READY = "READY"
    EXPORTED = "EXPORTED"


class DocumentType(StrEnum):
    INVOICE = "INVOICE"
    PACKING = "PACKING"
    BL = "BL"


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    FAILED = "FAILED"
    NEEDS_MANUAL_ENTRY = "NEEDS_MANUAL_ENTRY"


class PageSource(StrEnum):
    TEXT = "TEXT"
    NONE = "NONE"


class RunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REPAIRED = "REPAIRED"


class EvidenceLevel(StrEnum):
    EXACT = "EXACT"
    CONTAINED = "CONTAINED"
    CLAIMED = "CLAIMED"
    NONE = "NONE"


class FieldStatus(StrEnum):
    SUGGESTED = "SUGGESTED"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"


class Severity(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


class Decision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Org(Base, TimestampMixin):
    __tablename__ = "org"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    weight_tol_pct: Mapped[float] = mapped_column(Numeric(5, 3), default=0.5, nullable=False)
    value_tol: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.01"), nullable=False
    )
    monthly_ai_cap_paise: Mapped[int] = mapped_column(BigInteger, default=500_000, nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=180, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="org")
    suppliers: Mapped[list[Supplier]] = relationship(back_populates="org")


class User(Base, TimestampMixin):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_user_org_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(enum(Role), default=Role.EXEC, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    org: Mapped[Org] = relationship(back_populates="users")


class UserSession(Base):
    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Supplier(Base, TimestampMixin):
    __tablename__ = "supplier"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_supplier_org_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    aliases: Mapped[list | None] = mapped_column(JSON, default=list)

    org: Mapped[Org] = relationship(back_populates="suppliers")


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipment"
    __table_args__ = (
        UniqueConstraint("org_id", "ref", name="uq_shipment_org_ref"),
        Index("ix_shipment_org_status", "org_id", "status"),
        CheckConstraint("char_length(currency) = 3", name="ck_shipment_currency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), index=True)
    ref: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("supplier.id"))
    status: Mapped[ShipmentStatus] = mapped_column(
        enum(ShipmentStatus), default=ShipmentStatus.DRAFT, nullable=False
    )
    incoterm: Mapped[str | None] = mapped_column(String(8))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    org: Mapped[Org] = relationship()
    supplier: Mapped[Supplier | None] = relationship()
    documents: Mapped[list[Document]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    fields: Mapped[list[Field]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    checks: Mapped[list[Check]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )


class Document(Base, TimestampMixin):
    __tablename__ = "document"
    __table_args__ = (UniqueConstraint("shipment_id", "sha256", name="uq_document_shipment_sha"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipment.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[DocumentType] = mapped_column(enum(DocumentType), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        enum(DocumentStatus), default=DocumentStatus.UPLOADED, nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_detail: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"))

    shipment: Mapped[Shipment] = relationship(back_populates="documents")
    pages: Mapped[list[Page]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Page.idx"
    )
    runs: Mapped[list[ExtractionRun]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "page"
    __table_args__ = (UniqueConstraint("document_id", "idx", name="uq_page_document_idx"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    image_key: Mapped[str] = mapped_column(String(500), nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    words_key: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[PageSource] = mapped_column(
        enum(PageSource), default=PageSource.NONE, nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="pages")


class ExtractionRun(Base, TimestampMixin):
    __tablename__ = "extraction_run"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "content_sha256",
            "prompt_version",
            "schema_version",
            name="uq_run_document_content_versions",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[RunStatus] = mapped_column(enum(RunStatus), default=RunStatus.SUCCESS)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_paise: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    raw_response_key: Mapped[str | None] = mapped_column(String(500))
    error_code: Mapped[str | None] = mapped_column(String(60))

    document: Mapped[Document] = relationship(back_populates="runs")


class Field(Base):
    __tablename__ = "field"
    __table_args__ = (
        UniqueConstraint("document_id", "key", "line_no", name="uq_field_document_key_line"),
        CheckConstraint(
            "effective_conf >= 0 AND effective_conf <= 1", name="ck_field_confidence"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipment.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    extraction_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("extraction_run.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    line_no: Mapped[int | None] = mapped_column(Integer)
    value_raw: Mapped[str | None] = mapped_column(Text)
    value_norm: Mapped[str | None] = mapped_column(Text)
    model_conf: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    effective_conf: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    verification_level: Mapped[EvidenceLevel] = mapped_column(
        enum(EvidenceLevel), default=EvidenceLevel.NONE, nullable=False
    )
    page_idx: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    bbox: Mapped[dict | None] = mapped_column(JSON)
    quote: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FieldStatus] = mapped_column(
        enum(FieldStatus), default=FieldStatus.SUGGESTED, nullable=False
    )
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    shipment: Mapped[Shipment] = relationship(back_populates="fields")
    document: Mapped[Document] = relationship()


class LineItem(Base):
    __tablename__ = "line_item"
    __table_args__ = (CheckConstraint("qty > 0", name="ck_line_item_qty"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipment.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(ForeignKey("document.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description_raw: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    hsn_code: Mapped[str | None] = mapped_column(String(12))
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    uom: Mapped[str | None] = mapped_column(String(16))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    gross_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    net_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    matched_line_id: Mapped[str | None] = mapped_column(ForeignKey("line_item.id"))
    match_score: Mapped[float | None] = mapped_column(Float)


class Check(Base):
    __tablename__ = "check"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipment.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    severity: Mapped[Severity] = mapped_column(enum(Severity), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    field_keys: Mapped[list | None] = mapped_column(JSON, default=list)
    params: Mapped[dict | None] = mapped_column(JSON, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    rule_version: Mapped[str] = mapped_column(String(20), default="1", nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    shipment: Mapped[Shipment] = relationship(back_populates="checks")


class CheckResolution(Base):
    __tablename__ = "check_resolution"
    __table_args__ = (
        UniqueConstraint(
            "shipment_id", "code", "subject_key", "input_hash", name="uq_resolution_scope"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipment.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_by: Mapped[str] = mapped_column(ForeignKey("user.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Correction(Base):
    __tablename__ = "correction"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    field_id: Mapped[str] = mapped_column(
        ForeignKey("field.id", ondelete="CASCADE"), index=True
    )
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("user.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Approval(Base):
    __tablename__ = "approval"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipment.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str] = mapped_column(ForeignKey("user.id"), nullable=False)
    decision: Mapped[Decision] = mapped_column(enum(Decision), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExportTemplate(Base, TimestampMixin):
    __tablename__ = "export_template"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    column_map: Mapped[list] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Export(Base):
    __tablename__ = "export"
    __table_args__ = (
        UniqueConstraint("shipment_id", "template_id", "content_hash", name="uq_export_content"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shipment_id: Mapped[str] = mapped_column(
        ForeignKey("shipment.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[str] = mapped_column(ForeignKey("export_template.id"), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    meta: Mapped[dict | None] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
