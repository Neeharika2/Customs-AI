from __future__ import annotations

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..deps import CurrentUser, DbSession, ManagerUser, audit, problem
from ..models import Export, ExportTemplate, Shipment, ShipmentStatus
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


class TemplateColumnIn(BaseModel):
    header: str = Field(min_length=1, max_length=60)
    source: str = Field(min_length=1, max_length=60)
    required: bool = False
    format: str | None = Field(default=None, max_length=20)
    join: str | None = Field(default=None, max_length=3)


class TemplateUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    columns: list[TemplateColumnIn] = Field(min_length=1, max_length=60)


class TemplateOut(BaseModel):
    id: str
    name: str
    version: int
    columns: list[dict]


SOURCES = {
    "invoice_number", "invoice_date", "supplier_name", "buyer_name", "currency",
    "incoterm", "invoice_total", "freight", "insurance", "discount", "gross_weight_kg",
    "net_weight_kg", "packages", "package_type", "container_numbers", "bl_number",
    "bl_date", "consignee", "notify_party", "vessel_name", "port_of_loading",
    "port_of_discharge", "item.description", "item.hsn_code", "item.qty",
    "item.unit_price", "item.amount",
}
REQUIRED_SOURCES = {"invoice_number", "item.description"}


def _validate(body: TemplateUpdateIn) -> None:
    headers = [column.header.strip() for column in body.columns]
    if len(set(headers)) != len(headers):
        raise problem(422, "duplicate_headers", "Column headers must be unique.")
    sources = {column.source for column in body.columns}
    unknown = sources - SOURCES
    if unknown:
        raise problem(422, "unknown_source", f"Unknown source: {', '.join(sorted(unknown))}.")
    missing = REQUIRED_SOURCES - sources
    if missing:
        raise problem(
            422,
            "missing_columns",
            f"Required columns missing: {', '.join(sorted(missing))}.",
        )
    for column in body.columns:
        if column.format and column.format != "%d/%m/%Y":
            if not re.fullmatch(r"0(\.[0#]+)?", column.format):
                raise problem(
                    422,
                    "invalid_format",
                    f"Unsupported format '{column.format}'. Use %d/%m/%Y or 0.00 style.",
                )


def _template_out(template: ExportTemplate) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        version=template.version,
        columns=list(template.column_map),
    )


@router.get("/export-templates", response_model=list[TemplateOut])
def list_templates(user: ManagerUser, db: DbSession) -> list[TemplateOut]:
    rows = db.scalars(
        select(ExportTemplate)
        .where(ExportTemplate.org_id == user.org_id)
        .order_by(ExportTemplate.version.desc())
    ).all()
    return [_template_out(template) for template in rows]


@router.put("/export-templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: str, body: TemplateUpdateIn, user: ManagerUser, db: DbSession
) -> TemplateOut:
    current = db.get(ExportTemplate, template_id)
    if not current or current.org_id != user.org_id:
        raise problem(404, "template_not_found", "Template not found.")
    _validate(body)

    current.is_active = False
    replacement = ExportTemplate(
        org_id=user.org_id,
        name=body.name.strip(),
        column_map=[column.model_dump() for column in body.columns],
        version=current.version + 1,
        is_active=True,
    )
    db.add(replacement)
    db.flush()
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="export_template.updated",
        entity="export_template",
        entity_id=replacement.id,
        meta={"version": replacement.version, "columns": len(body.columns)},
    )
    db.commit()
    db.refresh(replacement)
    return _template_out(replacement)


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
