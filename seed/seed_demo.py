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
from app.extract.pipeline import process_document  # noqa: E402
from app.models import (  # noqa: E402
    Check,
    Document,
    DocumentStatus,
    DocumentType,
    Field,
    FieldStatus,
    LineItem,
    Org,
    Shipment,
    ShipmentStatus,
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
        field.status = FieldStatus.CONFIRMED
        field.effective_conf = max(field.effective_conf, 0.99)


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

        # A clean shipment waiting for the manager.
        for ref, status in [("SHP-24818", ShipmentStatus.READY),
                            ("SHP-24819", ShipmentStatus.AWAITING_APPROVAL)]:
            shipment = db.scalar(
                select(Shipment).where(Shipment.org_id == org.id, Shipment.ref == ref)
            )
            if not shipment:
                continue
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
