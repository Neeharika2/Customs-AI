import pytest

from app.models import AuditEvent


def test_audit_events_cannot_be_updated(db, world):
    event = AuditEvent(
        org_id=world["org"].id,
        actor_id=world["exec"].id,
        action="test.created",
        entity="shipment",
        entity_id="x",
        meta={},
    )
    db.add(event)
    db.commit()

    event.action = "test.changed"
    with pytest.raises(ValueError, match="append-only"):
        db.commit()
    db.rollback()


def test_audit_events_cannot_be_deleted(db, world):
    event = AuditEvent(
        org_id=world["org"].id,
        actor_id=world["exec"].id,
        action="test.created",
        entity="shipment",
        entity_id="x",
        meta={},
    )
    db.add(event)
    db.commit()

    db.delete(event)
    with pytest.raises(ValueError, match="append-only"):
        db.commit()
    db.rollback()
