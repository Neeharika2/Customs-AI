from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Check,
    CheckResolution,
    Document,
    DocumentStatus,
    Field,
    FieldStatus,
    LineItem,
    Shipment,
    ShipmentStatus,
)
from ..schemas import GateBlocker, GateOut

REQUIRED_KEYS = {
    "invoice_number",
    "invoice_date",
    "currency",
    "incoterm",
    "supplier_name",
    "invoice_total",
    "gross_weight_kg",
    "packages",
}

LABELS = {
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "currency": "Currency",
    "incoterm": "Incoterm",
    "supplier_name": "Supplier",
    "invoice_total": "Invoice total",
    "gross_weight_kg": "Gross weight",
    "packages": "Packages",
    "bl_number": "B/L number",
    "container_numbers": "Container numbers",
}


def evaluate(db: Session, shipment: Shipment, for_export: bool = False) -> GateOut:
    blockers: list[GateBlocker] = []

    documents = db.scalars(select(Document).where(Document.shipment_id == shipment.id)).all()
    present = {str(d.type) for d in documents if d.status == DocumentStatus.EXTRACTED}
    missing = sorted({"INVOICE", "PACKING", "BL"} - present)
    if missing:
        blockers.append(
            GateBlocker(
                code="DOCS_INCOMPLETE",
                message="Missing or unreadable: "
                + ", ".join(
                    "invoice" if m == "INVOICE" else "packing list" if m == "PACKING" else "bill of lading"
                    for m in missing
                ),
            )
        )

    fields = db.scalars(select(Field).where(Field.shipment_id == shipment.id)).all()
    unconfirmed = [
        f for f in fields if f.key in REQUIRED_KEYS and f.status == FieldStatus.SUGGESTED
    ]
    # Group by key: "supplier" appearing on three documents is one decision, not three.
    grouped: dict[str, list[Field]] = {}
    for field in unconfirmed:
        grouped.setdefault(field.key, []).append(field)
    for index, (key, group) in enumerate(grouped.items()):
        if index >= 8:
            blockers.append(
                GateBlocker(
                    code="FIELDS_REMAINING",
                    message=f"{len(grouped) - 8} more field groups need confirmation",
                )
            )
            break
        suffix = f" ({len(group)} documents)" if len(group) > 1 else ""
        blockers.append(
            GateBlocker(
                code="FIELD_UNCONFIRMED",
                message=f"{LABELS.get(key, key)} needs confirmation{suffix}",
                field_id=group[0].id,
            )
        )

    invoice_lines = db.scalar(
        select(LineItem)
        .where(
            LineItem.shipment_id == shipment.id,
            LineItem.document_id.in_(
                [d.id for d in documents if str(d.type) == "INVOICE"]
            ),
        )
        .limit(1)
    )
    if not invoice_lines and "INVOICE" in present:
        blockers.append(
            GateBlocker(code="LINES_MISSING", message="No invoice line items were extracted")
        )

    resolutions = {
        (r.code, r.subject_key, r.input_hash)
        for r in db.scalars(
            select(CheckResolution).where(CheckResolution.shipment_id == shipment.id)
        ).all()
    }
    checks = db.scalars(select(Check).where(Check.shipment_id == shipment.id)).all()
    for check in checks:
        if str(check.severity) == "PASS":
            continue
        if (check.code, check.subject_key, check.input_hash) in resolutions:
            continue
        if str(check.severity) == "BLOCK":
            blockers.append(
                GateBlocker(
                    code=f"CHECK_{check.code}",
                    message=check.message,
                )
            )
        else:
            blockers.append(
                GateBlocker(
                    code=f"ACK_{check.code}",
                    message=check.message,
                )
            )

    if for_export:
        if shipment.status not in {ShipmentStatus.READY, ShipmentStatus.EXPORTED}:
            blockers.append(
                GateBlocker(code="NOT_APPROVED", message="Shipment has not been approved")
            )
        latest_field = db.scalar(
            select(Field.updated_at)
            .where(Field.shipment_id == shipment.id)
            .order_by(Field.updated_at.desc())
            .limit(1)
        )
        if shipment.approved_at and latest_field and latest_field > shipment.approved_at:
            blockers.append(
                GateBlocker(
                    code="STALE_APPROVAL",
                    message="A field changed after approval — approval must be repeated",
                )
            )

    return GateOut(ok=not blockers, blockers=blockers)
