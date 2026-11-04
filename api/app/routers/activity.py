from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..deps import CurrentUser, DbSession, problem
from ..models import Shipment
from ..services.activity import build_activity

router = APIRouter(prefix="/api", tags=["activity"])


class ActivityItem(BaseModel):
    id: str
    kind: str
    at: datetime
    actor: str
    title: str
    detail: str = ""
    reason: str | None = None


class ActivityOut(BaseModel):
    items: list[ActivityItem]


@router.get("/shipments/{shipment_id}/activity", response_model=ActivityOut)
def shipment_activity(
    shipment_id: str,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=80, ge=1, le=200),
) -> ActivityOut:
    shipment = db.get(Shipment, shipment_id)
    if not shipment or shipment.org_id != user.org_id:
        raise problem(404, "shipment_not_found", "Shipment not found.")
    return ActivityOut(items=build_activity(db, shipment, limit=limit))
