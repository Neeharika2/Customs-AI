from fastapi import APIRouter, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import joinedload

from ..deps import CurrentUser, DbSession, audit, problem
from ..models import (
    Check,
    CheckResolution,
    Document,
    DocumentStatus,
    Shipment,
    ShipmentStatus,
    Supplier,
)
from ..schemas import (
    DocumentOut,
    ShipmentCreateIn,
    ShipmentListItem,
    ShipmentListOut,
    ShipmentOut,
    SupplierOut,
)

router = APIRouter(prefix="/api", tags=["shipments"])

ALL_STATUSES = [s.value for s in ShipmentStatus]
DOCS_REQUIRED = 3


def _open_issue_counts(db, org_id: str) -> dict[str, int]:
    rows = db.execute(
        select(Check.shipment_id, func.count())
        .join(Shipment, Shipment.id == Check.shipment_id)
        .where(Shipment.org_id == org_id, Check.severity != "PASS")
        .group_by(Check.shipment_id)
    ).all()
    return {shipment_id: count for shipment_id, count in rows}


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(user: CurrentUser, db: DbSession) -> list[SupplierOut]:
    rows = db.scalars(
        select(Supplier).where(Supplier.org_id == user.org_id).order_by(Supplier.name)
    ).all()
    return [SupplierOut(id=s.id, name=s.name, country_code=s.country_code) for s in rows]


@router.get("/shipments", response_model=ShipmentListOut)
def list_shipments(
    user: CurrentUser,
    db: DbSession,
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=80),
    supplier_id: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> ShipmentListOut:
    base = select(Shipment).options(joinedload(Shipment.supplier)).where(
        Shipment.org_id == user.org_id
    )
    if status and status in ALL_STATUSES:
        base = base.where(Shipment.status == status)
    if supplier_id:
        base = base.where(Shipment.supplier_id == supplier_id)
    if q:
        term = f"%{q.strip()}%"
        base = base.join(Supplier, Supplier.id == Shipment.supplier_id, isouter=True).where(
            or_(Shipment.ref.ilike(term), Supplier.name.ilike(term))
        )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    attention = case(
        (Shipment.status == ShipmentStatus.NEEDS_REVIEW, 0),
        (Shipment.status == ShipmentStatus.AWAITING_APPROVAL, 1),
        (Shipment.status == ShipmentStatus.READY, 2),
        (Shipment.status == ShipmentStatus.EXTRACTING, 3),
        (Shipment.status == ShipmentStatus.DRAFT, 4),
        else_=5,
    )
    rows = db.scalars(
        base.order_by(attention, Shipment.updated_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()

    issues = _open_issue_counts(db, user.org_id)
    counts = {s: 0 for s in ALL_STATUSES}
    for value, count in db.execute(
        select(Shipment.status, func.count())
        .where(Shipment.org_id == user.org_id)
        .group_by(Shipment.status)
    ).all():
        counts[str(value)] = count

    items = []
    for s in rows:
        doc_count = db.scalar(
            select(func.count()).select_from(Document).where(Document.shipment_id == s.id)
        ) or 0
        items.append(
            ShipmentListItem(
                id=s.id,
                ref=s.ref,
                supplier_name=s.supplier.name if s.supplier else None,
                currency=s.currency,
                incoterm=s.incoterm,
                status=s.status,
                document_count=doc_count,
                document_total=DOCS_REQUIRED,
                open_issues=issues.get(s.id, 0),
                updated_at=s.updated_at,
            )
        )
    return ShipmentListOut(items=items, total=total, counts=counts)


@router.post("/shipments", response_model=ShipmentOut, status_code=201)
def create_shipment(body: ShipmentCreateIn, user: CurrentUser, db: DbSession) -> ShipmentOut:
    existing = db.scalar(
        select(Shipment).where(Shipment.org_id == user.org_id, Shipment.ref == body.ref)
    )
    if existing:
        raise problem(409, "duplicate_ref", f"Shipment {body.ref} already exists.")
    supplier = None
    if body.supplier_id:
        supplier = db.get(Supplier, body.supplier_id)
        if not supplier or supplier.org_id != user.org_id:
            raise problem(404, "supplier_not_found", "Supplier not found.")

    shipment = Shipment(
        org_id=user.org_id,
        ref=body.ref,
        supplier_id=supplier.id if supplier else None,
        incoterm=body.incoterm.upper() if body.incoterm else None,
        currency=body.currency,
        created_by=user.id,
        status=ShipmentStatus.DRAFT,
    )
    db.add(shipment)
    db.flush()
    audit(db, org_id=user.org_id, actor_id=user.id, action="shipment.created",
          entity="shipment", entity_id=shipment.id, meta={"ref": shipment.ref})
    db.commit()
    db.refresh(shipment)
    return _shipment_out(db, shipment)


def _shipment_out(db, shipment: Shipment) -> ShipmentOut:
    docs = db.scalars(
        select(Document).where(Document.shipment_id == shipment.id).order_by(Document.created_at)
    ).all()
    return ShipmentOut(
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
        documents=[
            DocumentOut(
                id=d.id,
                type=d.type,
                file_name=d.file_name,
                page_count=d.page_count,
                status=d.status,
                error_code=d.error_code,
                error_detail=d.error_detail,
                created_at=d.created_at,
            )
            for d in docs
        ],
    )


@router.get("/shipments/{shipment_id}", response_model=ShipmentOut)
def get_shipment(shipment_id: str, user: CurrentUser, db: DbSession) -> ShipmentOut:
    shipment = db.get(Shipment, shipment_id)
    if not shipment or shipment.org_id != user.org_id:
        raise problem(404, "shipment_not_found", "Shipment not found.")
    return _shipment_out(db, shipment)
