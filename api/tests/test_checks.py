from sqlalchemy import select

from app.checks.engine import _container_valid, run_checks
from app.extract.pipeline import effective_confidence
from app.models import Check, DocumentType, EvidenceLevel
from tests.conftest import add_field, add_line, make_document, make_shipment


def three_documents(db, world, ref="SHP-CHK"):
    shipment = make_shipment(db, world, ref=ref)
    invoice = make_document(db, shipment, DocumentType.INVOICE)
    packing = make_document(db, shipment, DocumentType.PACKING)
    bl = make_document(db, shipment, DocumentType.BL)
    return shipment, invoice, packing, bl


def check_for(db, shipment, code, subject="shipment"):
    run_checks(db, shipment.id)
    return db.scalar(
        select(Check).where(
            Check.shipment_id == shipment.id,
            Check.code == code,
            Check.subject_key == subject,
        )
    )


def test_weight_difference_is_warn_not_block(db, world):
    shipment, invoice, packing, bl = three_documents(db, world)
    add_field(db, shipment, invoice, "gross_weight_kg", "3120.00")
    add_field(db, shipment, packing, "gross_weight_kg", "3165.00")
    add_field(db, shipment, bl, "gross_weight_kg", "3160.00")

    check = check_for(db, shipment, "WEIGHT_MATCH")
    assert check is not None
    assert str(check.severity) == "WARN"
    assert "1.44" in check.message or "45" in check.message


def test_weight_within_tolerance_passes(db, world):
    shipment, invoice, packing, bl = three_documents(db, world, ref="SHP-W2")
    add_field(db, shipment, invoice, "gross_weight_kg", "3120.00")
    add_field(db, shipment, packing, "gross_weight_kg", "3125.00")
    add_field(db, shipment, bl, "gross_weight_kg", "3122.00")

    check = check_for(db, shipment, "WEIGHT_MATCH")
    assert str(check.severity) == "PASS"


def test_net_weight_above_gross_blocks(db, world):
    shipment, invoice, packing, bl = three_documents(db, world, ref="SHP-NET")
    add_field(db, shipment, invoice, "gross_weight_kg", "760.00")
    add_field(db, shipment, invoice, "net_weight_kg", "3060.00")

    check = check_for(db, shipment, "NET_GROSS")
    assert check is not None
    assert str(check.severity) == "BLOCK"
    assert "net weight exceeds gross weight" in check.message.lower()


def test_net_weight_below_gross_passes(db, world):
    shipment, invoice, packing, bl = three_documents(db, world, ref="SHP-NET2")
    add_field(db, shipment, invoice, "gross_weight_kg", "760.00")
    add_field(db, shipment, invoice, "net_weight_kg", "740.00")

    check = check_for(db, shipment, "NET_GROSS")
    assert check is not None
    assert str(check.severity) == "PASS"


def test_package_mismatch_blocks(db, world):
    shipment, invoice, packing, bl = three_documents(db, world, ref="SHP-PKG")
    add_field(db, shipment, invoice, "packages", "120")
    add_field(db, shipment, packing, "packages", "118")
    add_field(db, shipment, bl, "packages", "120")

    check = check_for(db, shipment, "PACKAGES_MATCH")
    assert str(check.severity) == "BLOCK"
    assert "118" in check.message


def test_line_arithmetic_and_invoice_total(db, world):
    shipment, invoice, packing, bl = three_documents(db, world, ref="SHP-AMT")
    add_field(db, shipment, invoice, "invoice_total", "1000.00")
    add_field(db, shipment, invoice, "declared_item_count", "1")
    add_line(db, shipment, invoice, qty=100, unit_price="10.00", amount="1000.00")

    amount = check_for(db, shipment, "LINE_AMOUNT", subject="line-1")
    total = check_for(db, shipment, "INVOICE_TOTAL")
    assert str(amount.severity) == "PASS"
    assert str(total.severity) == "PASS"


def test_line_arithmetic_catches_wrong_amount(db, world):
    shipment, invoice, packing, bl = three_documents(db, world, ref="SHP-AMT2")
    add_field(db, shipment, invoice, "invoice_total", "1000.00")
    add_line(db, shipment, invoice, qty=100, unit_price="10.00", amount="1010.00")

    check = check_for(db, shipment, "LINE_AMOUNT", subject="line-1")
    assert str(check.severity) == "BLOCK"
    assert "1010" in check.message


def test_container_checksum(db):
    assert _container_valid("MSCU1234566")
    assert not _container_valid("MSCU1234567")
    assert not _container_valid("NOTACONTAINER")


def test_confidence_format_gate_beats_evidence():
    invalid_date = effective_confidence(
        EvidenceLevel.EXACT, "invoice_date", "31/02/2026", 1.0
    )
    assert invalid_date == 0.0


def test_confidence_cannot_exceed_evidence():
    claimed = effective_confidence(
        EvidenceLevel.CLAIMED, "invoice_number", "INV-1", 1.0
    )
    assert claimed == 0.5
    exact = effective_confidence(EvidenceLevel.EXACT, "invoice_number", "INV-1", 0.0)
    assert exact == 0.75


def test_missing_document_blocks(db, world):
    shipment = make_shipment(db, world, ref="SHP-MISS")
    make_document(db, shipment, DocumentType.INVOICE)
    make_document(db, shipment, DocumentType.PACKING)

    check = check_for(db, shipment, "DOCS_COMPLETE")
    assert str(check.severity) == "BLOCK"
    assert "bill of lading" in check.message.lower()


def test_checks_are_deterministic(db, world):
    shipment, invoice, packing, bl = three_documents(db, world, ref="SHP-DET")
    add_field(db, shipment, invoice, "gross_weight_kg", "3120.00")
    add_field(db, shipment, packing, "gross_weight_kg", "3165.00")

    run_checks(db, shipment.id)
    first = {
        (c.code, c.input_hash)
        for c in db.scalars(select(Check).where(Check.shipment_id == shipment.id)).all()
    }
    run_checks(db, shipment.id)
    second = {
        (c.code, c.input_hash)
        for c in db.scalars(select(Check).where(Check.shipment_id == shipment.id)).all()
    }
    assert first == second
