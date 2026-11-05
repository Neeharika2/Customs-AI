from sqlalchemy import select

from app.extract import ai
from app.extract.ai import AIField, AILine, AIPayload
from app.extract.pipeline import process_document
from app.models import (
    DocumentType,
    EvidenceLevel,
    ExtractionRun,
    Field,
    Page,
    PageSource,
)
from app.services.storage import get_storage
from tests.conftest import make_document, make_shipment


def test_live_provider_is_wired_into_the_pipeline(db, world, monkeypatch):
    shipment = make_shipment(db, world, ref="SHP-LIVE")
    document = make_document(db, shipment, DocumentType.INVOICE)
    storage = get_storage()
    storage.put(document.storage_key, b"%PDF-1.4 dummy", "application/pdf")
    image_key = f"test-live/{document.id}.jpg"
    storage.put(image_key, b"\xff\xd8\xff\xe0fake", "image/jpeg")
    db.add(
        Page(
            document_id=document.id,
            idx=1,
            image_key=image_key,
            width_px=100,
            height_px=100,
            words_key=None,
            source=PageSource.NONE,
        )
    )
    db.commit()

    payload = AIPayload(
        fields=[
            AIField(
                key="invoice_number",
                value="INV-LIVE",
                quote="Invoice No: INV-LIVE",
                page=1,
                confidence=0.9,
            )
        ],
        lines=[AILine(description="Widget", qty="10", unit_price="5.00", amount="50.00")],
    )
    monkeypatch.setattr(ai, "configured", lambda: True)
    monkeypatch.setattr(
        ai,
        "extract",
        lambda document_type, images: (
            payload,
            {"model_id": "mock-model", "tokens_in": 10, "tokens_out": 5},
        ),
    )

    process_document(db, document.id)
    db.expire_all()

    refreshed = db.get(type(document), document.id)
    assert str(refreshed.status) == "EXTRACTED"

    field = db.scalar(
        select(Field).where(Field.document_id == document.id, Field.key == "invoice_number")
    )
    assert field is not None
    assert field.value_norm == "INV-LIVE"
    assert field.verification_level == EvidenceLevel.CLAIMED

    run = db.scalar(
        select(ExtractionRun).where(ExtractionRun.document_id == document.id)
    )
    assert run is not None
    assert run.model_id == "mock-model"
    assert run.tokens_in == 10
