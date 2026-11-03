from pydantic import BaseModel

from ..deps import CurrentUser, DbSession, audit, problem
from ..extract.pipeline import normalise
from ..models import (
    Document,
    DocumentStatus,
    DocumentType,
    EvidenceLevel,
    Field,
    FieldStatus,
    Shipment,
    ShipmentStatus,
)
from ..schemas import DocumentOut
from fastapi import APIRouter
from sqlalchemy import select

from ..checks.engine import run_checks

router = APIRouter(prefix="/api", tags=["manual"])

ALLOWED = {
    DocumentType.INVOICE: {
        "invoice_number", "invoice_date", "currency", "incoterm", "supplier_name",
        "buyer_name", "invoice_total", "freight", "insurance", "discount",
        "gross_weight_kg", "net_weight_kg", "packages", "package_type",
    },
    DocumentType.PACKING: {
        "supplier_name", "buyer_name", "invoice_reference", "packages",
        "package_type", "gross_weight_kg", "net_weight_kg",
    },
    DocumentType.BL: {
        "bl_number", "bl_date", "supplier_name", "consignee", "notify_party",
        "container_numbers", "packages", "gross_weight_kg", "port_of_loading",
        "port_of_discharge", "vessel_name",
    },
}


class ManualEntryIn(BaseModel):
    values: dict[str, str] = {}


@router.post("/documents/{document_id}/manual", response_model=DocumentOut)
def manual_entry(
    document_id: str, body: ManualEntryIn, user: CurrentUser, db: DbSession
) -> DocumentOut:
    document = db.get(Document, document_id)
    if not document:
        raise problem(404, "document_not_found", "Document not found.")
    shipment = db.get(Shipment, document.shipment_id)
    if not shipment or shipment.org_id != user.org_id:
        raise problem(404, "document_not_found", "Document not found.")
    if shipment.status in {ShipmentStatus.READY, ShipmentStatus.EXPORTED}:
        raise problem(409, "locked", "Reopen the shipment before editing.")

    allowed = ALLOWED.get(document.type, set())
    clean = {
        key: value.strip()
        for key, value in body.values.items()
        if key in allowed and value and value.strip()
    }
    if not clean:
        raise problem(422, "no_values", "Enter at least one field.")

    for key, value in clean.items():
        field = db.scalar(
            select(Field).where(
                Field.document_id == document.id, Field.key == key, Field.line_no.is_(None)
            )
        )
        if field:
            field.value_raw = value
            field.value_norm = normalise(key, value)
            field.status = FieldStatus.CORRECTED
            field.effective_conf = 1.0
            field.updated_by = user.id
        else:
            db.add(
                Field(
                    shipment_id=shipment.id,
                    document_id=document.id,
                    extraction_run_id=None,
                    key=key,
                    value_raw=value,
                    value_norm=normalise(key, value),
                    model_conf=0.0,
                    effective_conf=1.0,
                    verification_level=EvidenceLevel.NONE,
                    page_idx=1,
                    bbox=None,
                    quote=None,
                    status=FieldStatus.CORRECTED,
                    updated_by=user.id,
                )
            )
    document.status = DocumentStatus.EXTRACTED
    document.error_code = None
    document.error_detail = None
    if shipment.status in {ShipmentStatus.AWAITING_APPROVAL}:
        shipment.status = ShipmentStatus.NEEDS_REVIEW
        shipment.approved_at = None
        shipment.approved_by = None
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="document.manual_entry",
        entity="document",
        entity_id=document.id,
        meta={"fields": sorted(clean)},
    )
    db.commit()
    run_checks(db, shipment.id)
    return DocumentOut(
        id=document.id,
        type=document.type,
        file_name=document.file_name,
        page_count=document.page_count,
        status=document.status,
        error_code=None,
        error_detail=None,
        created_at=document.created_at,
    )
