from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import (
    Approval,
    AuditEvent,
    Check,
    Correction,
    Document,
    DocumentType,
    Export,
    ExportTemplate,
    Field,
    LineItem,
    Shipment,
    User,
)

DOC_LABEL = {
    DocumentType.INVOICE: "Invoice",
    DocumentType.PACKING: "Packing list",
    DocumentType.BL: "Bill of lading",
}

SKIP_AUDIT = {
    "auth.login",
    "field.corrected",
    "line_item.corrected",
    "shipment.approved",
    "shipment.rejected",
    "shipment.exported",
    "shipment.approval",
}


def _json(value: str | None) -> dict | str | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _line_detail(old: dict, new: dict) -> str:
    parts = []
    for key in new:
        before = old.get(key)
        after = new.get(key)
        if before != after:
            parts.append(f"{key.replace('_', ' ')}: {before} → {after}")
    return "; ".join(parts) or "Line item corrected"


def build_activity(db: Session, shipment: Shipment, limit: int = 80) -> list[dict]:
    documents = db.scalars(select(Document).where(Document.shipment_id == shipment.id)).all()
    doc_by_id = {d.id: d for d in documents}
    doc_ids = list(doc_by_id)

    fields = db.scalars(select(Field).where(Field.shipment_id == shipment.id)).all()
    field_by_id = {f.id: f for f in fields}
    lines = db.scalars(select(LineItem).where(LineItem.shipment_id == shipment.id)).all()
    line_by_id = {line.id: line for line in lines}
    checks = db.scalars(select(Check).where(Check.shipment_id == shipment.id)).all()
    check_ids = [c.id for c in checks]

    items: list[dict] = []
    actor_ids: set[str] = set()

    corrections = db.execute(
        select(Correction)
        .outerjoin(Field, Field.id == Correction.field_id)
        .outerjoin(LineItem, LineItem.id == Correction.line_item_id)
        .where(
            or_(
                Field.shipment_id == shipment.id,
                LineItem.shipment_id == shipment.id,
            )
        )
        .order_by(Correction.created_at.desc())
        .limit(limit)
    ).scalars().all()
    for correction in corrections:
        if correction.actor_id:
            actor_ids.add(correction.actor_id)
        at = correction.created_at
        if correction.field_id and correction.field_id in field_by_id:
            field = field_by_id[correction.field_id]
            document = doc_by_id.get(field.document_id)
            label = DOC_LABEL.get(document.type, "Document") if document else "Document"
            items.append(
                {
                    "id": f"corr-{correction.id}",
                    "kind": "correction",
                    "at": at,
                    "actor_id": correction.actor_id,
                    "title": f"{label}: {field.key.replace('_', ' ')} corrected",
                    "detail": f"{correction.old_value or '—'} → {correction.new_value or '—'}",
                    "reason": correction.reason,
                }
            )
        elif correction.line_item_id and correction.line_item_id in line_by_id:
            line = line_by_id[correction.line_item_id]
            document = doc_by_id.get(line.document_id) if line.document_id else None
            label = DOC_LABEL.get(document.type, "Document") if document else "Document"
            old = _json(correction.old_value)
            new = _json(correction.new_value)
            detail = (
                _line_detail(old, new)
                if isinstance(old, dict) and isinstance(new, dict)
                else "Line item corrected"
            )
            items.append(
                {
                    "id": f"corr-{correction.id}",
                    "kind": "correction",
                    "at": at,
                    "actor_id": correction.actor_id,
                    "title": f"{label}: line {line.line_no} corrected",
                    "detail": detail,
                    "reason": correction.reason,
                }
            )

    approvals = db.scalars(
        select(Approval).where(Approval.shipment_id == shipment.id)
    ).all()
    for approval in approvals:
        actor_ids.add(approval.actor_id)
        items.append(
            {
                "id": f"approval-{approval.id}",
                "kind": "approval",
                "at": approval.created_at,
                "actor_id": approval.actor_id,
                "title": "Approved" if str(approval.decision) == "APPROVE" else "Sent back for correction",
                "detail": approval.note or "",
                "reason": None,
            }
        )

    exports = db.scalars(select(Export).where(Export.shipment_id == shipment.id)).all()
    for export in exports:
        template = db.get(ExportTemplate, export.template_id)
        if export.created_by:
            actor_ids.add(export.created_by)
        items.append(
            {
                "id": f"export-{export.id}",
                "kind": "export",
                "at": export.created_at,
                "actor_id": export.created_by,
                "title": "Exported filing CSV",
                "detail": f"{export.row_count} row{'s' if export.row_count != 1 else ''}"
                + (f" · {template.name} v{template.version}" if template else ""),
                "reason": None,
            }
        )

    conditions = [
        (AuditEvent.entity == "shipment") & (AuditEvent.entity_id == shipment.id),
        (AuditEvent.entity == "document") & (AuditEvent.entity_id.in_(doc_ids)),
        (AuditEvent.entity == "field") & (AuditEvent.entity_id.in_(list(field_by_id))),
        (AuditEvent.entity == "line_item") & (AuditEvent.entity_id.in_(list(line_by_id))),
        (AuditEvent.entity == "check") & (AuditEvent.entity_id.in_(check_ids)),
    ]
    audit_rows = db.scalars(
        select(AuditEvent)
        .where(or_(*conditions))
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
    for event in audit_rows:
        if event.action in SKIP_AUDIT:
            continue
        if event.actor_id:
            actor_ids.add(event.actor_id)
        meta = event.meta or {}
        detail = ""
        title = event.action.replace(".", " ").replace("_", " ").capitalize()
        document = doc_by_id.get(event.entity_id)
        doc_label = DOC_LABEL.get(document.type, "Document") if document else "Document"
        if event.action == "document.uploaded":
            title = f"{doc_label} uploaded"
        elif event.action == "document.extracted":
            title = f"{doc_label} extracted"
        elif event.action == "document.manual_entry":
            title = f"{doc_label} entered manually"
        elif event.action == "document.ai_error":
            title = f"{doc_label} AI extraction failed"
            detail = str(meta.get("error", ""))[:160]
        elif event.action == "document.deleted":
            title = f"{doc_label} removed"
        elif event.action == "shipment.created":
            title = "Shipment created"
        elif event.action == "shipment.submitted":
            title = "Submitted for approval"
        elif event.action == "shipment.reopened":
            title = "Reopened by manager"
        elif event.action == "approval.voided":
            title = "Approval voided"
            detail = str(meta.get("reason", ""))
        elif event.action == "check.acknowledged":
            title = f"Check acknowledged: {str(meta.get('code', '')).replace('_', ' ')}"
            detail = str(meta.get("reason", ""))
        elif event.action == "check.overridden":
            title = f"Check overridden: {str(meta.get('code', '')).replace('_', ' ')}"
            detail = str(meta.get("reason", ""))
        elif event.action == "fields.confirmed_bulk":
            title = f"{meta.get('count', 0)} fields confirmed"
        elif event.action == "field.confirmed":
            title = f"Field confirmed: {str(meta.get('key', '')).replace('_', ' ')}"
        items.append(
            {
                "id": f"audit-{event.id}",
                "kind": "status",
                "at": event.created_at,
                "actor_id": event.actor_id,
                "title": title,
                "detail": detail,
                "reason": meta.get("reason"),
            }
        )

    actor_ids = {a for a in actor_ids if a}
    users = {
        user.id: user.email
        for user in db.scalars(select(User).where(User.id.in_(actor_ids))).all()
    } if actor_ids else {}
    for item in items:
        item["actor"] = users.get(item.get("actor_id") or "", "System")
        item.pop("actor_id", None)

    items.sort(key=lambda item: item["at"], reverse=True)
    return [
        {
            **item,
            "at": item["at"].isoformat() if isinstance(item["at"], datetime) else item["at"],
        }
        for item in items[:limit]
    ]
