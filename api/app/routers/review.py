from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select

from ..checks.engine import run_checks
from ..deps import CurrentUser, DbSession, ManagerUser, audit, problem
from ..extract.pipeline import normalise
from ..models import (
    Approval,
    Check,
    CheckResolution,
    Correction,
    Decision,
    Document,
    Field,
    FieldStatus,
    LineItem,
    Page,
    Severity,
    Shipment,
    ShipmentStatus,
)
from ..schemas import (
    ApprovalIn,
    CheckAcknowledgeIn,
    CheckOut,
    ConfirmAllOut,
    DocumentReviewOut,
    FieldMutationOut,
    FieldOut,
    FieldPatchIn,
    GateOut,
    LineItemOut,
    LineItemPatchIn,
    LineMutationOut,
    PageOut,
    ReviewOut,
    ShipmentOut,
    SubmitOut,
)
from ..services.gate import evaluate
from ..services.storage import get_storage

router = APIRouter(prefix="/api", tags=["review"])


def _shipment(db, shipment_id: str, org_id: str) -> Shipment:
    shipment = db.get(Shipment, shipment_id)
    if not shipment or shipment.org_id != org_id:
        raise problem(404, "shipment_not_found", "Shipment not found.")
    return shipment


def _field(db, field_id: str, org_id: str) -> Field:
    field = db.get(Field, field_id)
    if not field:
        raise problem(404, "field_not_found", "Field not found.")
    shipment = db.get(Shipment, field.shipment_id)
    if not shipment or shipment.org_id != org_id:
        raise problem(404, "field_not_found", "Field not found.")
    return field


def _check(db, check_id: str, org_id: str) -> Check:
    check = db.get(Check, check_id)
    if not check:
        raise problem(404, "check_not_found", "Check not found.")
    shipment = db.get(Shipment, check.shipment_id)
    if not shipment or shipment.org_id != org_id:
        raise problem(404, "check_not_found", "Check not found.")
    return check


def _resolutions(db, shipment_id: str) -> dict[tuple[str, str, str], CheckResolution]:
    rows = db.scalars(
        select(CheckResolution).where(CheckResolution.shipment_id == shipment_id)
    ).all()
    return {(r.code, r.subject_key, r.input_hash): r for r in rows}


def _field_out(field: Field) -> FieldOut:
    return FieldOut(
        id=field.id,
        document_id=field.document_id,
        key=field.key,
        line_no=field.line_no,
        value_raw=field.value_raw,
        value_norm=field.value_norm,
        model_conf=field.model_conf,
        effective_conf=field.effective_conf,
        verification_level=field.verification_level,
        page_idx=field.page_idx,
        bbox=field.bbox,
        quote=field.quote,
        status=field.status,
    )


def _line_out(line: LineItem) -> LineItemOut:
    return LineItemOut(
        id=line.id,
        document_id=line.document_id,
        line_no=line.line_no,
        description_raw=line.description_raw,
        hsn_code=line.hsn_code,
        qty=float(line.qty),
        uom=line.uom,
        unit_price=float(line.unit_price) if line.unit_price is not None else None,
        amount=float(line.amount) if line.amount is not None else None,
        gross_weight_kg=float(line.gross_weight_kg) if line.gross_weight_kg is not None else None,
        net_weight_kg=float(line.net_weight_kg) if line.net_weight_kg is not None else None,
        matched_line_id=line.matched_line_id,
        match_score=line.match_score,
        status=line.status,
        verification_level=line.verification_level,
        effective_conf=line.effective_conf,
        page_idx=line.page_idx,
        bbox=line.bbox,
        quote=line.quote,
    )


def _check_out(check: Check, resolutions) -> CheckOut:
    resolution = resolutions.get((check.code, check.subject_key, check.input_hash))
    return CheckOut(
        id=check.id,
        code=check.code,
        subject_key=check.subject_key,
        severity=check.severity,
        message=check.message,
        field_keys=list(check.field_keys or []),
        params=dict(check.params or {}),
        input_hash=check.input_hash,
        resolved=resolution is not None,
        resolved_reason=resolution.reason if resolution else None,
    )


def _checks(db, shipment_id: str) -> list[CheckOut]:
    resolutions = _resolutions(db, shipment_id)
    rows = db.scalars(
        select(Check)
        .where(Check.shipment_id == shipment_id)
        .order_by(Check.severity.desc(), Check.code)
    ).all()
    order = {Severity.BLOCK: 0, Severity.WARN: 1, Severity.PASS: 2}
    return [_check_out(c, resolutions) for c in sorted(rows, key=lambda c: (order[c.severity], c.code))]


def _documents(db, shipment: Shipment) -> list[DocumentReviewOut]:
    documents = db.scalars(
        select(Document).where(Document.shipment_id == shipment.id).order_by(Document.created_at)
    ).all()
    storage = get_storage()
    result = []
    for document in documents:
        pages = db.scalars(
            select(Page).where(Page.document_id == document.id).order_by(Page.idx)
        ).all()
        page_out = []
        for page in pages:
            direct = storage.presigned_get(page.image_key)
            page_out.append(
                PageOut(
                    idx=page.idx,
                    url=direct or f"/api/files/{page.image_key}",
                    width=page.width_px,
                    height=page.height_px,
                    source=str(page.source),
                )
            )
        result.append(
            DocumentReviewOut(
                id=document.id,
                type=document.type,
                file_name=document.file_name,
                page_count=document.page_count,
                status=document.status,
                error_code=document.error_code,
                error_detail=document.error_detail,
                created_at=document.created_at,
                pages=page_out,
            )
        )
    return result


def _review(db, shipment: Shipment) -> ReviewOut:
    documents = _documents(db, shipment)
    fields = db.scalars(
        select(Field).where(Field.shipment_id == shipment.id).order_by(Field.line_no, Field.key)
    ).all()
    lines = db.scalars(
        select(LineItem)
        .where(LineItem.shipment_id == shipment.id)
        .order_by(LineItem.line_no)
    ).all()
    return ReviewOut(
        shipment=ShipmentOut(
            id=shipment.id,
            ref=shipment.ref,
            supplier_id=shipment.supplier_id,
            supplier_name=shipment.supplier.name if shipment.supplier else None,
            currency=shipment.currency,
            incoterm=shipment.incoterm,
            status=shipment.status,
            created_at=shipment.created_at,
            updated_at=shipment.updated_at,
            approved_at=shipment.approved_at,
            documents=[],
            document_total=3,
        ),
        documents=documents,
        fields=[_field_out(f) for f in fields],
        lines=[_line_out(line) for line in lines],
        checks=_checks(db, shipment.id),
        gate=evaluate(db, shipment, for_export=False),
    )


def _void_approval(db, shipment: Shipment, actor_id: str, reason: str) -> None:
    if shipment.status in {ShipmentStatus.READY, ShipmentStatus.AWAITING_APPROVAL}:
        shipment.status = ShipmentStatus.NEEDS_REVIEW
        shipment.approved_by = None
        shipment.approved_at = None
        audit(
            db,
            org_id=shipment.org_id,
            actor_id=actor_id,
            action="approval.voided",
            entity="shipment",
            entity_id=shipment.id,
            meta={"reason": reason},
        )


@router.get("/shipments/{shipment_id}/review", response_model=ReviewOut)
def review(shipment_id: str, user: CurrentUser, db: DbSession) -> ReviewOut:
    shipment = _shipment(db, shipment_id, user.org_id)
    return _review(db, shipment)


@router.get("/shipments/{shipment_id}/gate", response_model=GateOut)
def gate(shipment_id: str, user: CurrentUser, db: DbSession) -> GateOut:
    shipment = _shipment(db, shipment_id, user.org_id)
    return evaluate(db, shipment, for_export=False)


@router.patch("/fields/{field_id}", response_model=FieldMutationOut)
def patch_field(
    field_id: str, body: FieldPatchIn, user: CurrentUser, db: DbSession
) -> FieldMutationOut:
    field = _field(db, field_id, user.org_id)
    shipment = db.get(Shipment, field.shipment_id)
    old_value = field.value_raw
    value = body.value or ""
    field.value_raw = value
    field.value_norm = normalise(field.key, value)
    field.status = FieldStatus.CORRECTED
    field.effective_conf = 1.0
    field.updated_by = user.id
    db.add(
        Correction(
            field_id=field.id,
            old_value=old_value,
            new_value=value,
            actor_id=user.id,
            reason=body.reason,
        )
    )
    if shipment:
        _void_approval(db, shipment, user.id, f"field {field.key} edited")
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="field.corrected",
        entity="field",
        entity_id=field.id,
        meta={"key": field.key, "from": old_value, "to": value},
    )
    db.commit()
    if shipment:
        run_checks(db, shipment.id)
        db.refresh(shipment)
    return FieldMutationOut(
        field=_field_out(field),
        gate=evaluate(db, shipment, for_export=False) if shipment else GateOut(ok=False, blockers=[]),
        check=_checks(db, shipment.id) if shipment else [],
    )


@router.post("/fields/{field_id}/confirm", response_model=FieldMutationOut)
def confirm_field(field_id: str, user: CurrentUser, db: DbSession) -> FieldMutationOut:
    field = _field(db, field_id, user.org_id)
    shipment = db.get(Shipment, field.shipment_id)
    field.status = FieldStatus.CONFIRMED
    field.updated_by = user.id
    if shipment:
        _void_approval(db, shipment, user.id, f"field {field.key} confirmed")
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="field.confirmed",
        entity="field",
        entity_id=field.id,
        meta={"key": field.key},
    )
    db.commit()
    return FieldMutationOut(
        field=_field_out(field),
        gate=evaluate(db, shipment, for_export=False) if shipment else GateOut(ok=False, blockers=[]),
        check=_checks(db, shipment.id) if shipment else [],
    )


@router.patch("/line-items/{line_id}", response_model=LineMutationOut)
def patch_line(
    line_id: str, body: LineItemPatchIn, user: CurrentUser, db: DbSession
) -> LineMutationOut:
    line = db.get(LineItem, line_id)
    if not line:
        raise problem(404, "line_not_found", "Line item not found.")
    shipment = db.get(Shipment, line.shipment_id)
    if not shipment or shipment.org_id != user.org_id:
        raise problem(404, "line_not_found", "Line item not found.")

    changes = body.model_dump(exclude_unset=True)
    reason = changes.pop("reason", None)
    if not changes:
        raise problem(422, "no_changes", "Change at least one value.")

    # Numeric columns are Decimal in the model; convert at the boundary so the
    # checks engine never sees a float multiplying a Decimal.
    for key in {"qty", "unit_price", "amount", "gross_weight_kg", "net_weight_kg"}:
        if key in changes and changes[key] is not None:
            changes[key] = Decimal(str(changes[key]))

    # Drop exact no-ops (e.g. 42.5000 vs 42.5) so the history only shows real edits.
    actual: dict[str, object] = {}
    for key, value in changes.items():
        current = getattr(line, key)
        if isinstance(current, Decimal) and isinstance(value, Decimal):
            if current == value:
                continue
        elif current == value:
            continue
        actual[key] = value
    if not actual:
        raise problem(422, "no_changes", "Those values already match the document.")
    changes = actual

    old = {key: getattr(line, key) for key in changes}
    for key, value in changes.items():
        setattr(line, key, value)
    line.status = FieldStatus.CORRECTED
    line.effective_conf = 1.0
    line.updated_by = user.id
    new = {key: getattr(line, key) for key in changes}

    db.add(
        Correction(
            line_item_id=line.id,
            old_value=json.dumps(old, default=str),
            new_value=json.dumps(new, default=str),
            actor_id=user.id,
            reason=reason,
        )
    )
    _void_approval(db, shipment, user.id, f"line {line.line_no} edited")
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="line_item.corrected",
        entity="line_item",
        entity_id=line.id,
        meta={"line_no": line.line_no, "changed": sorted(changes)},
    )
    db.commit()
    run_checks(db, shipment.id)
    return LineMutationOut(
        line=_line_out(line),
        gate=evaluate(db, shipment, for_export=False),
        check=_checks(db, shipment.id),
    )


@router.post("/shipments/{shipment_id}/confirm-high-confidence", response_model=ConfirmAllOut)
def confirm_high_confidence(
    shipment_id: str, user: CurrentUser, db: DbSession
) -> ConfirmAllOut:
    shipment = _shipment(db, shipment_id, user.org_id)
    open_checks = [
        c
        for c in db.scalars(select(Check).where(Check.shipment_id == shipment.id)).all()
        if c.severity != Severity.PASS
        and (c.code, c.subject_key, c.input_hash)
        not in _resolutions(db, shipment.id)
    ]
    blocked_keys = {key for check in open_checks for key in (check.field_keys or [])}
    fields = db.scalars(
        select(Field).where(
            Field.shipment_id == shipment.id,
            Field.status == FieldStatus.SUGGESTED,
            Field.effective_conf >= 0.85,
        )
    ).all()
    confirmed = 0
    for field in fields:
        if field.key in blocked_keys:
            continue
        field.status = FieldStatus.CONFIRMED
        field.updated_by = user.id
        confirmed += 1
    if confirmed:
        _void_approval(db, shipment, user.id, "bulk confirmation")
        audit(
            db,
            org_id=user.org_id,
            actor_id=user.id,
            action="fields.confirmed_bulk",
            entity="shipment",
            entity_id=shipment.id,
            meta={"count": confirmed},
        )
    db.commit()
    return ConfirmAllOut(confirmed=confirmed, gate=evaluate(db, shipment, for_export=False))


@router.post("/checks/{check_id}/acknowledge", response_model=GateOut)
def acknowledge_check(
    check_id: str, body: CheckAcknowledgeIn, user: CurrentUser, db: DbSession
) -> GateOut:
    check = _check(db, check_id, user.org_id)
    if check.severity == Severity.BLOCK:
        raise problem(403, "manager_required", "A blocking issue needs a manager override.")
    existing = db.scalar(
        select(CheckResolution).where(
            CheckResolution.shipment_id == check.shipment_id,
            CheckResolution.code == check.code,
            CheckResolution.subject_key == check.subject_key,
            CheckResolution.input_hash == check.input_hash,
        )
    )
    if not existing:
        db.add(
            CheckResolution(
                shipment_id=check.shipment_id,
                code=check.code,
                subject_key=check.subject_key,
                input_hash=check.input_hash,
                resolved_by=user.id,
                reason=body.reason,
            )
        )
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="check.acknowledged",
        entity="check",
        entity_id=check.id,
        meta={"code": check.code, "reason": body.reason},
    )
    db.commit()
    shipment = db.get(Shipment, check.shipment_id)
    return evaluate(db, shipment, for_export=False)


@router.post("/checks/{check_id}/override", response_model=GateOut)
def override_check(
    check_id: str, body: CheckAcknowledgeIn, user: ManagerUser, db: DbSession
) -> GateOut:
    check = _check(db, check_id, user.org_id)
    if check.severity != Severity.BLOCK:
        raise problem(422, "not_blocking", "Only blocking checks can be overridden.")
    if len(body.reason.strip()) < 10:
        raise problem(422, "reason_required", "Give a written reason of at least 10 characters.")
    existing = db.scalar(
        select(CheckResolution).where(
            CheckResolution.shipment_id == check.shipment_id,
            CheckResolution.code == check.code,
            CheckResolution.subject_key == check.subject_key,
            CheckResolution.input_hash == check.input_hash,
        )
    )
    if not existing:
        db.add(
            CheckResolution(
                shipment_id=check.shipment_id,
                code=check.code,
                subject_key=check.subject_key,
                input_hash=check.input_hash,
                resolved_by=user.id,
                reason=body.reason,
            )
        )
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="check.overridden",
        entity="check",
        entity_id=check.id,
        meta={"code": check.code, "reason": body.reason},
    )
    db.commit()
    shipment = db.get(Shipment, check.shipment_id)
    return evaluate(db, shipment, for_export=False)


@router.post("/shipments/{shipment_id}/submit", response_model=SubmitOut)
def submit(shipment_id: str, user: CurrentUser, db: DbSession) -> SubmitOut:
    shipment = _shipment(db, shipment_id, user.org_id)
    result = evaluate(db, shipment, for_export=False)
    if not result.ok:
        raise problem(409, "gate_blocked", "Resolve the open issues before submitting.")
    if shipment.status not in {ShipmentStatus.NEEDS_REVIEW, ShipmentStatus.DRAFT}:
        raise problem(409, "invalid_state", "This shipment is not in review.")
    shipment.status = ShipmentStatus.AWAITING_APPROVAL
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="shipment.submitted",
        entity="shipment",
        entity_id=shipment.id,
    )
    db.commit()
    return SubmitOut(status=shipment.status, gate=result)


@router.post("/shipments/{shipment_id}/approve", response_model=SubmitOut)
def approve(
    shipment_id: str, body: ApprovalIn, user: ManagerUser, db: DbSession
) -> SubmitOut:
    shipment = _shipment(db, shipment_id, user.org_id)
    if shipment.status != ShipmentStatus.AWAITING_APPROVAL:
        raise problem(409, "invalid_state", "Shipment is not awaiting approval.")
    if body.decision == "REJECT" and not (body.note or "").strip():
        raise problem(422, "note_required", "Add a note explaining the rejection.")
    if body.decision == "APPROVE":
        result = evaluate(db, shipment, for_export=False)
        if not result.ok:
            raise problem(409, "gate_blocked", "Resolve the open issues before approving.")
        shipment.status = ShipmentStatus.READY
        shipment.approved_by = user.id
        shipment.approved_at = datetime.now(UTC)
    else:
        shipment.status = ShipmentStatus.NEEDS_REVIEW
        shipment.approved_by = None
        shipment.approved_at = None
    db.add(
        Approval(
            shipment_id=shipment.id,
            actor_id=user.id,
            decision=Decision(body.decision),
            note=body.note,
        )
    )
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action=f"shipment.{body.decision.lower()}d",
        entity="shipment",
        entity_id=shipment.id,
        meta={"note": body.note},
    )
    db.commit()
    return SubmitOut(status=shipment.status, gate=evaluate(db, shipment, for_export=False))


@router.post("/shipments/{shipment_id}/reopen", response_model=SubmitOut)
def reopen(shipment_id: str, user: ManagerUser, db: DbSession) -> SubmitOut:
    shipment = _shipment(db, shipment_id, user.org_id)
    if shipment.status not in {ShipmentStatus.READY, ShipmentStatus.AWAITING_APPROVAL}:
        raise problem(409, "invalid_state", "Shipment is not approved or awaiting approval.")
    shipment.status = ShipmentStatus.NEEDS_REVIEW
    shipment.approved_by = None
    shipment.approved_at = None
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="shipment.reopened",
        entity="shipment",
        entity_id=shipment.id,
    )
    db.commit()
    return SubmitOut(status=shipment.status, gate=evaluate(db, shipment, for_export=False))
