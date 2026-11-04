from sqlalchemy import select

from app.checks.engine import run_checks
from app.models import Check, CheckResolution, DocumentType, Field, FieldStatus
from app.services.gate import evaluate
from tests.conftest import add_field, add_line, make_document, make_shipment


def build_clean_shipment(db, world, ref="SHP-GATE", weight="3121.00"):
    shipment = make_shipment(db, world, ref=ref)
    invoice = make_document(db, shipment, DocumentType.INVOICE)
    packing = make_document(db, shipment, DocumentType.PACKING)
    bl = make_document(db, shipment, DocumentType.BL)

    values = [
        (invoice, "invoice_number", "INV-1"),
        (invoice, "invoice_date", "2026-10-20"),
        (invoice, "currency", "USD"),
        (invoice, "incoterm", "FOB"),
        (invoice, "supplier_name", "Company B"),
        (invoice, "invoice_total", "1000.00"),
        (invoice, "gross_weight_kg", "3120.00"),
        (invoice, "packages", "120"),
        (packing, "gross_weight_kg", weight),
        (packing, "packages", "120"),
        (bl, "gross_weight_kg", "3122.00"),
        (bl, "packages", "120"),
    ]
    for document, key, value in values:
        add_field(db, shipment, document, key, value, status="CONFIRMED")
    add_line(db, shipment, invoice, qty=100, unit_price="10.00", amount="1000.00")
    add_line(db, shipment, packing, qty=100, unit_price=None, amount=None,
             description="Widget")
    return shipment, invoice, packing, bl


def test_clean_shipment_has_no_blockers(db, world):
    shipment, *_ = build_clean_shipment(db, world)
    run_checks(db, shipment.id)
    gate = evaluate(db, shipment)
    assert gate.ok, [blocker.message for blocker in gate.blockers]


def test_open_weight_warning_blocks_submit(db, world):
    shipment, *_ = build_clean_shipment(db, world, ref="SHP-GATE2", weight="3165.00")
    run_checks(db, shipment.id)
    gate = evaluate(db, shipment)
    assert not gate.ok
    assert any("weight" in blocker.message.lower() for blocker in gate.blockers)


def test_acknowledgement_clears_warning(db, world):
    shipment, *_ = build_clean_shipment(db, world, ref="SHP-GATE3", weight="3165.00")
    run_checks(db, shipment.id)
    check = db.scalar(
        select(Check).where(Check.shipment_id == shipment.id, Check.code == "WEIGHT_MATCH")
    )
    db.add(
        CheckResolution(
            shipment_id=shipment.id,
            code=check.code,
            subject_key=check.subject_key,
            input_hash=check.input_hash,
            resolved_by=world["manager"].id,
            reason="Pallet weight included in the packing list",
        )
    )
    db.commit()
    gate = evaluate(db, shipment)
    assert gate.ok, [blocker.message for blocker in gate.blockers]


def test_changed_value_invalidates_acknowledgement(db, world):
    shipment, invoice, packing, bl = build_clean_shipment(
        db, world, ref="SHP-GATE4", weight="3165.00"
    )
    run_checks(db, shipment.id)
    check = db.scalar(
        select(Check).where(Check.shipment_id == shipment.id, Check.code == "WEIGHT_MATCH")
    )
    db.add(
        CheckResolution(
            shipment_id=shipment.id,
            code=check.code,
            subject_key=check.subject_key,
            input_hash=check.input_hash,
            resolved_by=world["manager"].id,
            reason="Pallet weight included",
        )
    )
    db.commit()

    field = db.scalar(
        select(Field).where(
            Field.document_id == invoice.id, Field.key == "gross_weight_kg"
        )
    )
    field.value_raw = "3150.00"
    field.value_norm = "3150.00"
    field.status = FieldStatus.CORRECTED
    db.commit()
    run_checks(db, shipment.id)

    gate = evaluate(db, shipment)
    assert not gate.ok
    assert any("weight" in blocker.message.lower() for blocker in gate.blockers)
