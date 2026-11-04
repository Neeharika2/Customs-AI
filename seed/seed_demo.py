"""Attach the generated documents to the seeded shipments and run the pipeline.

Run after `seed/generate.py`:
    cd api && ../.venv/bin/python ../seed/seed_demo.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))

from sqlalchemy import delete, select  # noqa: E402

from app.checks.engine import run_checks  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.extract.pipeline import normalise, process_document  # noqa: E402
from app.models import (  # noqa: E402
    Approval,
    Check,
    CheckResolution,
    Correction,
    Document,
    DocumentStatus,
    DocumentType,
    Export,
    Field,
    FieldStatus,
    LineItem,
    Org,
    Shipment,
    ShipmentStatus,
    User,
)
from app.seed import main as seed_base  # noqa: E402
from app.services.gate import evaluate  # noqa: E402
from app.services.storage import get_storage  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
MANIFEST = ROOT / "output" / "manifest.json"


def attach(db, shipment: Shipment, doc_type: str, path: pathlib.Path) -> Document:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Document).where(Document.shipment_id == shipment.id, Document.sha256 == digest)
    )
    if existing:
        return existing
    key = (
        f"org/{shipment.org_id}/shipment/{shipment.id}/"
        f"doc-{uuid.uuid4()}.{path.suffix.lstrip('.')}"
    )
    get_storage().put(key, data, "application/pdf")
    document = Document(
        shipment_id=shipment.id,
        type=DocumentType(doc_type),
        storage_key=key,
        file_name=path.name,
        mime_type="application/pdf",
        size_bytes=len(data),
        sha256=digest,
        status=DocumentStatus.UPLOADED,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def confirm_all(db, shipment: Shipment) -> None:
    fields = db.scalars(select(Field).where(Field.shipment_id == shipment.id)).all()
    for field in fields:
        if field.status == FieldStatus.CORRECTED:
            continue
        field.status = FieldStatus.CONFIRMED
        field.effective_conf = max(field.effective_conf, 0.99)


def seed_correction(
    db,
    shipment: Shipment,
    doc_type: DocumentType,
    key: str,
    new_value: str,
    actor: User,
    reason: str,
) -> None:
    document_ids = [
        d.id for d in shipment.documents if d.type == doc_type
    ]
    if not document_ids:
        return
    field = db.scalar(
        select(Field).where(
            Field.shipment_id == shipment.id,
            Field.key == key,
            Field.document_id.in_(document_ids),
        )
    )
    if not field:
        return
    old = field.value_raw
    field.value_raw = new_value
    field.value_norm = normalise(key, new_value)
    field.status = FieldStatus.CORRECTED
    field.effective_conf = 1.0
    field.updated_by = actor.id
    db.add(
        Correction(
            field_id=field.id,
            old_value=old,
            new_value=new_value,
            actor_id=actor.id,
            reason=reason,
        )
    )


def main() -> None:
    seed_base()
    manifest = json.loads(MANIFEST.read_text())
    with SessionLocal() as db:
        org = db.scalar(select(Org).where(Org.name == "Demo Freight"))
        assert org is not None

        for ref, documents in manifest.items():
            shipment = db.scalar(
                select(Shipment).where(Shipment.org_id == org.id, Shipment.ref == ref)
            )
            if not shipment:
                continue

            # Re-seeding: remove previous derived rows in FK-safe order.
            db.execute(delete(Export).where(Export.shipment_id == shipment.id))
            db.execute(delete(Approval).where(Approval.shipment_id == shipment.id))
            db.execute(delete(CheckResolution).where(CheckResolution.shipment_id == shipment.id))
            db.execute(delete(Field).where(Field.shipment_id == shipment.id))
            db.execute(delete(LineItem).where(LineItem.shipment_id == shipment.id))
            db.execute(delete(Check).where(Check.shipment_id == shipment.id))
            for existing in db.scalars(
                select(Document).where(Document.shipment_id == shipment.id)
            ).all():
                db.delete(existing)
            db.commit()
            shipment.status = ShipmentStatus.NEEDS_REVIEW
            shipment.approved_at = None
            shipment.approved_by = None
            db.commit()

            for doc_type, path in documents.items():
                document = attach(db, shipment, doc_type, pathlib.Path(path))
                process_document(db, document.id)
            print(f"{ref}: {len(documents)} documents processed")

        exec_user = db.scalar(select(User).where(User.email == "exec@demo.local"))
        manager = db.scalar(select(User).where(User.email == "manager@demo.local"))

        # A clean shipment waiting for the manager, with a little correction history
        # so the accuracy report is not empty on first load.
        for ref, status in [("SHP-24818", ShipmentStatus.READY),
                            ("SHP-24819", ShipmentStatus.AWAITING_APPROVAL)]:
            shipment = db.scalar(
                select(Shipment).where(Shipment.org_id == org.id, Shipment.ref == ref)
            )
            if not shipment or not exec_user or not manager:
                continue
            if ref == "SHP-24818":
                seed_correction(
                    db, shipment, DocumentType.BL, "vessel_name", "MSC ARIA", exec_user,
                    "Aligned with the carrier's B/L wording",
                )
                seed_correction(
                    db, shipment, DocumentType.INVOICE, "package_type", "Cartons", exec_user,
                    "Packing description clarified with the supplier",
                )
            if ref == "SHP-24819":
                seed_correction(
                    db, shipment, DocumentType.BL, "port_of_loading", "Ningbo, China",
                    manager, "Added country for the filing description",
                )
            confirm_all(db, shipment)
            db.commit()
            run_checks(db, shipment.id)
            shipment.status = status
            db.commit()
            gate = evaluate(db, shipment, for_export=False)
            print(f"{ref}: {status} · gate {'clear' if gate.ok else f'{len(gate.blockers)} blockers'}")

    print("Demo data ready.")


if __name__ == "__main__":
    main()
