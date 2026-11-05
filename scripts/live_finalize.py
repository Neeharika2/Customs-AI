"""After a live extraction run, restore the clean demo state and sample corrections.

Run from api/:  uv run python ../scripts/live_finalize.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.cwd()))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "api"))

from decimal import Decimal  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.checks.engine import run_checks  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.extract.pipeline import normalise  # noqa: E402
from app.models import (  # noqa: E402
    Correction,
    DocumentType,
    Field,
    FieldStatus,
    Org,
    Shipment,
    ShipmentStatus,
    User,
)
from app.services.gate import evaluate  # noqa: E402


def confirm_all(db, shipment: Shipment) -> None:
    for field in db.scalars(select(Field).where(Field.shipment_id == shipment.id)).all():
        if field.status != FieldStatus.CORRECTED:
            field.status = FieldStatus.CONFIRMED


def add_correction(db, shipment, doc_type, key, new_value, actor, reason) -> None:
    document_ids = [d.id for d in shipment.documents if d.type == doc_type]
    if not document_ids:
        return
    field = db.scalar(
        select(Field).where(
            Field.shipment_id == shipment.id,
            Field.key == key,
            Field.document_id.in_(document_ids),
        )
    )
    if not field or field.value_raw == new_value:
        return
    exists = db.scalar(
        select(Correction).where(
            Correction.field_id == field.id,
            Correction.new_value == new_value,
        )
    )
    if exists:
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
    with SessionLocal() as db:
        org = db.scalar(select(Org).where(Org.name == "Demo Freight"))
        exec_user = db.scalar(select(User).where(User.email == "exec@demo.local"))
        manager = db.scalar(select(User).where(User.email == "manager@demo.local"))

        for ref, status in [
            ("SHP-24818", ShipmentStatus.READY),
            ("SHP-24819", ShipmentStatus.AWAITING_APPROVAL),
        ]:
            shipment = db.scalar(
                select(Shipment).where(Shipment.org_id == org.id, Shipment.ref == ref)
            )
            if not shipment:
                continue
            if ref == "SHP-24818":
                add_correction(
                    db, shipment, DocumentType.BL, "vessel_name", "MSC ARIA",
                    exec_user, "Aligned with the carrier's B/L wording",
                )
                add_correction(
                    db, shipment, DocumentType.INVOICE, "package_type", "Cartons",
                    exec_user, "Packing description clarified with the supplier",
                )
            if ref == "SHP-24819":
                add_correction(
                    db, shipment, DocumentType.BL, "port_of_loading", "Ningbo, China",
                    manager, "Added country for the filing description",
                )
            confirm_all(db, shipment)
            db.commit()
            run_checks(db, shipment.id)
            shipment.status = status
            db.commit()
            gate = evaluate(db, shipment, for_export=False)
            print(
                f"{ref}: {status} · "
                f"{'gate clear' if gate.ok else str(len(gate.blockers)) + ' blockers'}"
            )
            for blocker in gate.blockers[:4]:
                print("  ", blocker.code, "|", blocker.message[:90])


if __name__ == "__main__":
    main()
