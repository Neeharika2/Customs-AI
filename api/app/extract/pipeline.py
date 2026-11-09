from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import audit
from ..models import (
    Document,
    DocumentStatus,
    DocumentType,
    EvidenceLevel,
    ExtractionRun,
    Field,
    FieldStatus,
    LineItem,
    Page,
    PageSource,
    RunStatus,
    Shipment,
    ShipmentStatus,
)
from ..services.render import bbox_for, page_lines, render_pdf
from ..services.storage import get_storage
from . import ai
from .parser import ParsedDocument, parse_bl, parse_invoice, parse_packing

PROMPT_VERSION = "fixture-v1"
SCHEMA_VERSION = "1"

EVIDENCE = {
    EvidenceLevel.EXACT: 1.0,
    EvidenceLevel.CONTAINED: 0.7,
    EvidenceLevel.CLAIMED: 0.5,
    EvidenceLevel.NONE: 0.0,
}


def format_score(key: str, value: str | None) -> float:
    if value is None or value == "":
        return 0.0
    if key in {"invoice_date", "bl_date"}:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                datetime.strptime(value.strip(), fmt)
                return 1.0
            except ValueError:
                continue
        return 0.0
    if key == "currency":
        return 1.0 if re.fullmatch(r"[A-Z]{3}", value.strip().upper()) else 0.0
    if key in {"hsn_code", "hsn"}:
        digits = re.sub(r"\D", "", value)
        return 1.0 if len(digits) in (6, 8) else 0.5 if len(digits) == 4 else 0.0
    if key in {
        "invoice_total", "freight", "insurance", "discount", "gross_weight_kg",
        "net_weight_kg", "unit_price", "amount",
    }:
        try:
            Decimal(value.replace(",", "").strip())
            return 1.0
        except (InvalidOperation, ValueError):
            return 0.0
    if key == "packages":
        return 1.0 if value.strip().isdigit() else 0.0
    if key == "container_numbers":
        parts = [p.strip() for p in re.split(r"[,;]", value) if p.strip()]
        if not parts:
            return 0.0
        return 1.0 if all(container_valid(p) for p in parts) else 0.5
    return 1.0


def container_valid(value: str) -> bool:
    code = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if not re.fullmatch(r"[A-Z]{4}\d{7}", code):
        return False
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for index, char in enumerate(code[:10]):
        if char.isdigit():
            number = int(char)
        else:
            number = letters.index(char) + 10
            if number >= 11:
                number += 1
        total += number * (2**index)
    check = total % 11
    if check == 10:
        check = 0
    return str(check) == code[-1]


def effective_confidence(level: EvidenceLevel, key: str, value: str | None, model_conf: float) -> float:
    evidence = EVIDENCE[level]
    form = format_score(key, value)
    if evidence == 0 or form == 0:
        return 0.0
    return round(min(evidence, form) * (0.75 + 0.25 * model_conf), 3)


def normalise(key: str, value: str | None) -> str | None:
    if value is None:
        return None
    if key in {"invoice_date", "bl_date"}:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date().isoformat()
            except ValueError:
                continue
        return value.strip()
    if key in {"currency", "incoterm"}:
        return value.strip().upper()
    if key in {
        "invoice_total", "freight", "insurance", "discount", "gross_weight_kg",
        "net_weight_kg", "unit_price", "amount",
    }:
        try:
            return str(Decimal(value.replace(",", "").strip()))
        except (InvalidOperation, ValueError):
            return value.strip()
    return value.strip()


def _parse(document_type: DocumentType, lines: list[dict]) -> ParsedDocument:
    if document_type == DocumentType.INVOICE:
        return parse_invoice(lines)
    if document_type == DocumentType.PACKING:
        return parse_packing(lines)
    return parse_bl(lines)


def process_document(
    db: Session, document_id: str, actor_id: str | None = None, force: bool = False
) -> None:
    document = db.get(Document, document_id)
    if not document:
        return
    storage = get_storage()
    try:
        document.status = DocumentStatus.PROCESSING
        db.commit()

        data = storage.get(document.storage_key)

        if not document.pages:
            rendered = render_pdf(data, f"org/{document.shipment.org_id}/shipment/{document.shipment_id}/doc-{document.id}", storage)
            for page in rendered:
                db.add(
                    Page(
                        document_id=document.id,
                        idx=page.idx,
                        image_key=page.image_key,
                        width_px=page.width,
                        height_px=page.height,
                        words_key=page.words_key,
                        source=PageSource(page.source),
                    )
                )
            document.page_count = len(rendered)
            db.commit()

        pages = db.scalars(
            select(Page).where(Page.document_id == document.id).order_by(Page.idx)
        ).all()

        payloads = []
        for page in pages:
            if page.words_key:
                payloads.append(json.loads(storage.get(page.words_key)))
            else:
                payloads.append({"page": page.idx, "words": [], "text": ""})

        use_live = ai.configured()
        model_meta: dict = {}
        prompt_version = PROMPT_VERSION
        schema_version = SCHEMA_VERSION
        if use_live:
            try:
                images = [storage.get(page.image_key) for page in pages]
                payload, model_meta = ai.extract(document.type, images)
                parsed = ai.to_parsed(payload, document.type)
                prompt_version = "ai-v1"
            except Exception as exc:  # provider/transport/schema failure
                document.status = DocumentStatus.NEEDS_MANUAL_ENTRY
                document.error_code = "ai_error"
                document.error_detail = f"AI extraction failed after retries: {exc}"[:400]
                audit(
                    db,
                    org_id=document.shipment.org_id,
                    actor_id=actor_id,
                    action="document.ai_error",
                    entity="document",
                    entity_id=document.id,
                    meta={"type": str(document.type), "reason": "ai_error", "error": str(exc)[:200]},
                )
                db.commit()
                _derive_shipment_status(db, document.shipment_id)
                return
        else:
            lines = page_lines(payloads)
            parsed = _parse(document.type, lines)

        if not parsed.lines and not any(f.value for f in parsed.fields):
            document.status = DocumentStatus.NEEDS_MANUAL_ENTRY
            document.error_code = "no_text"
            document.error_detail = "No readable text layer. Enter this document manually."
            audit(
                db,
                org_id=document.shipment.org_id,
                actor_id=actor_id,
                action="document.manual_entry",
                entity="document",
                entity_id=document.id,
                meta={"type": str(document.type)},
            )
            db.commit()
            _derive_shipment_status(db, document.shipment_id)
            return

        # Idempotent write: clear derived rows for this document first.
        db.execute(delete(Field).where(Field.document_id == document.id))
        db.execute(delete(LineItem).where(LineItem.document_id == document.id))

        run = ExtractionRun(
            document_id=document.id,
            model_id=model_meta.get("model_id", "fixture-text-v1"),
            prompt_version=prompt_version,
            schema_version=schema_version,
            content_sha256=document.sha256,
            status=RunStatus.SUCCESS,
            tokens_in=int(model_meta.get("tokens_in", 0)),
            tokens_out=int(model_meta.get("tokens_out", 0)),
            cost_paise=0,
            latency_ms=0,
        )
        db.add(run)
        db.flush()

        page_source = {p.idx: p.source for p in pages}
        for parsed_field in parsed.fields:
            if parsed_field.value is None:
                continue
            level = EvidenceLevel.NONE
            bbox = None
            source = page_source.get(parsed_field.page_idx, PageSource.NONE)
            if source == PageSource.TEXT:
                bbox = bbox_for(data, parsed_field.page_idx, parsed_field.value)
                if bbox:
                    level = EvidenceLevel.EXACT
                elif parsed_field.quote:
                    level = EvidenceLevel.CONTAINED
            else:
                level = EvidenceLevel.CLAIMED if parsed_field.quote else EvidenceLevel.NONE

            db.add(
                Field(
                    shipment_id=document.shipment_id,
                    document_id=document.id,
                    extraction_run_id=run.id,
                    key=parsed_field.key,
                    value_raw=parsed_field.value,
                    value_norm=normalise(parsed_field.key, parsed_field.value),
                    model_conf=parsed_field.model_conf,
                    effective_conf=effective_confidence(
                        level, parsed_field.key, parsed_field.value, parsed_field.model_conf
                    ),
                    verification_level=level,
                    page_idx=parsed_field.page_idx,
                    bbox=bbox,
                    quote=parsed_field.quote,
                    status=FieldStatus.SUGGESTED,
                )
            )

        for line in parsed.lines:
            line_bbox = bbox_for(data, line.page_idx, line.description or "")
            source = page_source.get(line.page_idx, PageSource.NONE)
            if source == PageSource.TEXT:
                level = EvidenceLevel.EXACT if line_bbox else EvidenceLevel.CONTAINED
            else:
                level = EvidenceLevel.CLAIMED
            confidence = round(min(EVIDENCE[level], 1.0) * (0.75 + 0.25 * 0.93), 3)
            db.add(
                LineItem(
                    shipment_id=document.shipment_id,
                    document_id=document.id,
                    line_no=line.line_no,
                    description_raw=line.description,
                    hsn_code=line.hsn,
                    qty=line.qty,
                    uom=line.uom,
                    unit_price=line.unit_price,
                    amount=line.amount,
                    gross_weight_kg=line.gross_weight,
                    net_weight_kg=line.net_weight,
                    status=FieldStatus.SUGGESTED,
                    verification_level=level,
                    effective_conf=confidence,
                    page_idx=line.page_idx,
                    bbox=line_bbox,
                    quote=line.quote,
                )
            )

        document.status = DocumentStatus.EXTRACTED
        document.error_code = None
        document.error_detail = None
        audit(
            db,
            org_id=document.shipment.org_id,
            actor_id=actor_id,
            action="document.extracted",
            entity="document",
            entity_id=document.id,
            meta={"type": str(document.type), "fields": len(parsed.fields), "lines": len(parsed.lines)},
        )
        db.commit()
        _derive_shipment_status(db, document.shipment_id)

        from ..checks.engine import run_checks

        run_checks(db, document.shipment_id)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        document = db.get(Document, document_id)
        if document:
            document.status = DocumentStatus.FAILED
            document.error_code = "extraction_failed"
            document.error_detail = str(exc)[:400]
            db.commit()
            _derive_shipment_status(db, document.shipment_id)


def _derive_shipment_status(db: Session, shipment_id: str) -> None:
    shipment = db.get(Shipment, shipment_id)
    if not shipment:
        return
    if shipment.status in {ShipmentStatus.AWAITING_APPROVAL, ShipmentStatus.READY, ShipmentStatus.EXPORTED}:
        return
    documents = db.scalars(select(Document).where(Document.shipment_id == shipment_id)).all()
    if not documents:
        shipment.status = ShipmentStatus.DRAFT
    elif any(
        d.status in {DocumentStatus.UPLOADED, DocumentStatus.QUEUED, DocumentStatus.PROCESSING}
        for d in documents
    ):
        shipment.status = ShipmentStatus.EXTRACTING
    else:
        shipment.status = ShipmentStatus.NEEDS_REVIEW
    db.commit()
