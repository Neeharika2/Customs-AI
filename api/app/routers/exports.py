from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import CurrentUser, DbSession, audit, problem
from ..models import Export, Shipment, ShipmentStatus
from ..schemas import GateOut
from ..services.export import active_template, build_export, preview
from ..services.gate import evaluate
from ..services.storage import get_storage

router = APIRouter(prefix="/api", tags=["export"])


class ExportPreviewOut(BaseModel):
    template: dict
    headers: list[str]
    rows: list[list[str]]
    total_rows: int
    gate: GateOut
    shipment_status: str
    shipment_ref: str
    existing_export: dict | None = None


class ExportOut(BaseModel):
    export_id: str
    url: str
    row_count: int
    content_hash: str


def _shipment(db, shipment_id: str, org_id: str) -> Shipment:
    shipment = db.get(Shipment, shipment_id)
    if not shipment or shipment.org_id != org_id:
        raise problem(404, "shipment_not_found", "Shipment not found.")
    return shipment


def _existing(db, shipment_id: str) -> Export | None:
    return db.scalar(
        select(Export)
        .where(Export.shipment_id == shipment_id)
        .order_by(Export.created_at.desc())
        .limit(1)
    )


def _url(key: str) -> str:
    direct = get_storage().presigned_get(key)
    return direct or f"/api/files/{key}"


@router.get("/shipments/{shipment_id}/export/preview", response_model=ExportPreviewOut)
def export_preview(shipment_id: str, user: CurrentUser, db: DbSession) -> ExportPreviewOut:
    shipment = _shipment(db, shipment_id, user.org_id)
    template = active_template(db, user.org_id)
    data = preview(db, shipment, template)
    existing = _existing(db, shipment.id)
    return ExportPreviewOut(
        template=data["template"],
        headers=data["headers"],
        rows=data["rows"],
        total_rows=data["total_rows"],
        gate=evaluate(db, shipment, for_export=True),
        shipment_status=str(shipment.status),
        shipment_ref=shipment.ref,
        existing_export=(
            {
                "id": existing.id,
                "created_at": existing.created_at.isoformat(),
                "row_count": existing.row_count,
                "url": _url(existing.storage_key),
            }
            if existing
            else None
        ),
    )


@router.post("/shipments/{shipment_id}/export", response_model=ExportOut)
def create_export(shipment_id: str, user: CurrentUser, db: DbSession) -> ExportOut:
    shipment = _shipment(db, shipment_id, user.org_id)
    gate = evaluate(db, shipment, for_export=True)
    if not gate.ok:
        raise problem(
            409,
            "gate_blocked",
            gate.blockers[0].message if gate.blockers else "Resolve the open issues before exporting.",
        )
    template = active_template(db, user.org_id)
    export, _ = build_export(db, shipment, template, user.id)
    shipment.status = ShipmentStatus.EXPORTED
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="shipment.exported",
        entity="shipment",
        entity_id=shipment.id,
        meta={"export_id": export.id, "rows": export.row_count, "template": template.version},
    )
    db.commit()
    return ExportOut(
        export_id=export.id,
        url=_url(export.storage_key),
        row_count=export.row_count,
        content_hash=export.content_hash,
    )


@router.get("/exports/{export_id}/download")
def download_export(export_id: str, user: CurrentUser, db: DbSession) -> dict:
    export = db.get(Export, export_id)
    if not export:
        raise problem(404, "export_not_found", "Export not found.")
    shipment = db.get(Shipment, export.shipment_id)
    if not shipment or shipment.org_id != user.org_id:
        raise problem(404, "export_not_found", "Export not found.")
    return {"url": _url(export.storage_key), "row_count": export.row_count}
