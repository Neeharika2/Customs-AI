from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from ..deps import DbSession, ManagerUser
from ..models import (
    Correction,
    Document,
    DocumentStatus,
    EvidenceLevel,
    Field,
    FieldStatus,
    Shipment,
    Supplier,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])

SMALL_SAMPLE = 20


class FieldRow(BaseModel):
    key: str
    extracted: int
    corrected: int
    correction_rate: float
    avg_confidence: float
    sufficient: bool


class SupplierRow(BaseModel):
    supplier: str
    shipments: int
    fields: int
    corrected: int
    correction_rate: float
    manual_documents: int
    sufficient: bool


class Totals(BaseModel):
    shipments: int
    documents: int
    fields: int
    corrections: int
    manual_documents: int
    manual_rate: float
    first_pass: float
    evidence_coverage: float


class Overview(BaseModel):
    totals: Totals
    fields: list[FieldRow]
    suppliers: list[SupplierRow]
    small_sample: int


@router.get("/overview", response_model=Overview)
def overview(user: ManagerUser, db: DbSession) -> Overview:
    org_id = user.org_id

    shipments = db.scalar(select(func.count()).select_from(Shipment).where(Shipment.org_id == org_id)) or 0
    documents = (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .join(Shipment, Shipment.id == Document.shipment_id)
            .where(Shipment.org_id == org_id)
        )
        or 0
    )
    fields = (
        db.scalar(
            select(func.count())
            .select_from(Field)
            .join(Shipment, Shipment.id == Field.shipment_id)
            .where(Shipment.org_id == org_id)
        )
        or 0
    )
    corrections = (
        db.scalar(
            select(func.count())
            .select_from(Correction)
            .join(Field, Field.id == Correction.field_id)
            .join(Shipment, Shipment.id == Field.shipment_id)
            .where(Shipment.org_id == org_id)
        )
        or 0
    )
    manual = (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .join(Shipment, Shipment.id == Document.shipment_id)
            .where(
                Shipment.org_id == org_id,
                Document.status == DocumentStatus.NEEDS_MANUAL_ENTRY,
            )
        )
        or 0
    )
    confirmed = (
        db.scalar(
            select(func.count())
            .select_from(Field)
            .join(Shipment, Shipment.id == Field.shipment_id)
            .where(Shipment.org_id == org_id, Field.status == FieldStatus.CONFIRMED)
        )
        or 0
    )
    reviewed = confirmed + corrections
    evidenced = (
        db.scalar(
            select(func.count())
            .select_from(Field)
            .join(Shipment, Shipment.id == Field.shipment_id)
            .where(
                Shipment.org_id == org_id,
                Field.verification_level.in_(
                    [EvidenceLevel.EXACT, EvidenceLevel.CONTAINED]
                ),
            )
        )
        or 0
    )

    field_rows = db.execute(
        select(
            Field.key,
            func.count(Field.id),
            func.count(Field.id).filter(Field.status == FieldStatus.CORRECTED),
            func.avg(Field.effective_conf),
        )
        .join(Shipment, Shipment.id == Field.shipment_id)
        .where(Shipment.org_id == org_id)
        .group_by(Field.key)
    ).all()

    # Two aggregates, merged in Python. Joining fields and documents in one query
    # multiplies rows by the number of documents per shipment.
    supplier_field_rows = db.execute(
        select(
            Supplier.name,
            func.count(func.distinct(Shipment.id)),
            func.count(Field.id),
            func.count(Field.id).filter(Field.status == FieldStatus.CORRECTED),
        )
        .select_from(Supplier)
        .join(Shipment, Shipment.supplier_id == Supplier.id)
        .join(Field, Field.shipment_id == Shipment.id)
        .where(Supplier.org_id == org_id)
        .group_by(Supplier.name)
    ).all()
    manual_by_supplier = dict(
        db.execute(
            select(Supplier.name, func.count(func.distinct(Document.id)))
            .select_from(Supplier)
            .join(Shipment, Shipment.supplier_id == Supplier.id)
            .join(Document, Document.shipment_id == Shipment.id)
            .where(
                Supplier.org_id == org_id,
                Document.status == DocumentStatus.NEEDS_MANUAL_ENTRY,
            )
            .group_by(Supplier.name)
        ).all()
    )
    supplier_rows = [
        (name, ships, total, corrected, manual_by_supplier.get(name, 0))
        for name, ships, total, corrected in supplier_field_rows
    ]

    field_list = [
        FieldRow(
            key=key,
            extracted=total,
            corrected=corrected,
            correction_rate=round((corrected / total) * 100, 1) if total else 0.0,
            avg_confidence=round(float(avg or 0), 2),
            sufficient=total >= SMALL_SAMPLE,
        )
        for key, total, corrected, avg in field_rows
    ]
    field_list.sort(key=lambda row: (-row.correction_rate, -row.extracted))

    supplier_list = [
        SupplierRow(
            supplier=name,
            shipments=ships,
            fields=total,
            corrected=corrected,
            correction_rate=round((corrected / total) * 100, 1) if total else 0.0,
            manual_documents=manual_docs,
            sufficient=total >= SMALL_SAMPLE,
        )
        for name, ships, total, corrected, manual_docs in supplier_rows
    ]
    supplier_list.sort(key=lambda row: -row.correction_rate)

    return Overview(
        totals=Totals(
            shipments=shipments,
            documents=documents,
            fields=fields,
            corrections=corrections,
            manual_documents=manual,
            manual_rate=round((manual / documents) * 100, 1) if documents else 0.0,
            first_pass=round((confirmed / reviewed) * 100, 1) if reviewed else 0.0,
            evidence_coverage=round((evidenced / fields) * 100, 1) if fields else 0.0,
        ),
        fields=field_list,
        suppliers=supplier_list,
        small_sample=SMALL_SAMPLE,
    )
