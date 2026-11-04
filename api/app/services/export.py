from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Document,
    DocumentType,
    Export,
    ExportTemplate,
    Field,
    LineItem,
    Shipment,
)

PRIORITY = {DocumentType.INVOICE: 0, DocumentType.BL: 1, DocumentType.PACKING: 2}


def active_template(db: Session, org_id: str) -> ExportTemplate:
    template = db.scalar(
        select(ExportTemplate).where(
            ExportTemplate.org_id == org_id, ExportTemplate.is_active.is_(True)
        )
    )
    if not template:
        raise ValueError("no_export_template")
    return template


def field_values(db: Session, shipment_id: str) -> dict[str, str]:
    documents = {
        d.id: d for d in db.scalars(select(Document).where(Document.shipment_id == shipment_id)).all()
    }
    fields = db.scalars(select(Field).where(Field.shipment_id == shipment_id)).all()
    chosen: dict[str, tuple[int, str]] = {}
    for field in fields:
        if field.value_norm is None:
            continue
        document = documents.get(field.document_id)
        rank = PRIORITY.get(document.type, 9) if document else 9
        if field.key not in chosen or rank < chosen[field.key][0]:
            chosen[field.key] = (rank, field.value_norm)
    return {key: value for key, (_, value) in chosen.items()}


def _csv_safe(value: str) -> str:
    if not value:
        return value
    if value[0] in "=+@":
        return "'" + value
    if value[0] == "-" and not value[1:2].isdigit():
        return "'" + value
    return value


def _format(value: str | None, spec: dict) -> str:
    if value is None or value == "":
        return ""
    fmt = spec.get("format")
    if fmt == "%d/%m/%Y":
        try:
            return datetime.fromisoformat(value).strftime("%d/%m/%Y")
        except ValueError:
            return value
    if fmt and fmt.startswith("0."):
        # "0.0000" is width/precision in Python's format mini-language, which makes
        # Decimal fall back to scientific notation. Translate to an explicit fixed format.
        decimals = len(fmt) - 2
        try:
            text = f"{Decimal(value):.{decimals}f}"
        except (InvalidOperation, ValueError):
            return value
        if "#" in fmt:
            text = text.rstrip("0").rstrip(".")
        return text
    join = spec.get("join")
    if join:
        parts = [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
        return join.join(parts)
    return value


def render_shipment(db: Session, shipment: Shipment, template: ExportTemplate) -> tuple[list[str], list[list[str]], bytes]:
    columns = template.column_map or []
    headers = [column["header"] for column in columns]
    values = field_values(db, shipment.id)

    invoice_docs = [
        d.id
        for d in db.scalars(select(Document).where(Document.shipment_id == shipment.id)).all()
        if d.type == DocumentType.INVOICE
    ]
    lines = db.scalars(
        select(LineItem)
        .where(LineItem.shipment_id == shipment.id, LineItem.document_id.in_(invoice_docs))
        .order_by(LineItem.line_no)
    ).all()
    if not lines:
        lines = [None]

    rows: list[list[str]] = []
    for line in lines:
        row: list[str] = []
        for column in columns:
            source = column["source"]
            if source.startswith("item."):
                key = source.split(".", 1)[1]
                if line is None:
                    raw = None
                elif key == "description":
                    raw = line.description_raw
                elif key == "hsn_code":
                    raw = line.hsn_code
                elif key == "qty":
                    raw = str(line.qty) if line.qty is not None else None
                elif key == "unit_price":
                    raw = str(line.unit_price) if line.unit_price is not None else None
                elif key == "amount":
                    raw = str(line.amount) if line.amount is not None else None
                else:
                    raw = None
            else:
                raw = values.get(source)
            row.append(_csv_safe(_format(raw, column)))
        rows.append(row)

    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    content = buffer.getvalue().encode("utf-8-sig")
    return headers, rows, content


def preview(db: Session, shipment: Shipment, template: ExportTemplate) -> dict:
    headers, rows, _ = render_shipment(db, shipment, template)
    return {
        "template": {"id": template.id, "name": template.name, "version": template.version},
        "headers": headers,
        "rows": rows[:20],
        "total_rows": len(rows),
    }


def build_export(db: Session, shipment: Shipment, template: ExportTemplate, actor_id: str) -> tuple[Export, bytes]:
    _, rows, content = render_shipment(db, shipment, template)
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(
        select(Export).where(
            Export.shipment_id == shipment.id,
            Export.template_id == template.id,
            Export.content_hash == digest,
        )
    )
    if existing:
        return existing, content

    from .storage import get_storage

    key = f"org/{shipment.org_id}/shipment/{shipment.id}/export-{digest[:12]}.csv"
    get_storage().put(key, content, "text/csv")
    export = Export(
        shipment_id=shipment.id,
        template_id=template.id,
        row_count=len(rows),
        content_hash=digest,
        storage_key=key,
        created_by=actor_id,
    )
    db.add(export)
    db.commit()
    db.refresh(export)
    return export, content
