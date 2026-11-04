from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..deps import DbSession, ManagerUser, audit
from ..models import ExportTemplate, Org, User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class TemplateOut(BaseModel):
    id: str
    name: str
    version: int
    columns: list[dict]


class UserRow(BaseModel):
    email: str
    role: str
    active: bool


class SettingsOut(BaseModel):
    org_name: str
    weight_tol_pct: float
    value_tol: float
    retention_days: int
    template: TemplateOut | None
    users: list[UserRow]


class SettingsIn(BaseModel):
    weight_tol_pct: float = Field(ge=0, le=10)
    value_tol: float = Field(ge=0, le=100)
    retention_days: int = Field(ge=30, le=3650)


def _out(db, org: Org) -> SettingsOut:
    template = db.scalar(
        select(ExportTemplate).where(
            ExportTemplate.org_id == org.id, ExportTemplate.is_active.is_(True)
        )
    )
    users = db.scalars(select(User).where(User.org_id == org.id).order_by(User.email)).all()
    return SettingsOut(
        org_name=org.name,
        weight_tol_pct=float(org.weight_tol_pct),
        value_tol=float(org.value_tol),
        retention_days=org.retention_days,
        template=(
            TemplateOut(
                id=template.id,
                name=template.name,
                version=template.version,
                columns=list(template.column_map),
            )
            if template
            else None
        ),
        users=[UserRow(email=u.email, role=str(u.role), active=u.is_active) for u in users],
    )


@router.get("", response_model=SettingsOut)
def get_settings(user: ManagerUser, db: DbSession) -> SettingsOut:
    org = db.get(Org, user.org_id)
    return _out(db, org)


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsIn, user: ManagerUser, db: DbSession) -> SettingsOut:
    org = db.get(Org, user.org_id)
    org.weight_tol_pct = Decimal(str(body.weight_tol_pct))
    org.value_tol = Decimal(str(body.value_tol))
    org.retention_days = body.retention_days
    audit(
        db,
        org_id=user.org_id,
        actor_id=user.id,
        action="settings.updated",
        entity="org",
        entity_id=org.id,
        meta=body.model_dump(),
    )
    db.commit()
    return _out(db, org)
