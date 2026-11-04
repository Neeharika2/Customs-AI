from app.db import SessionLocal
from app.main import app
from app.models import DocumentType, Shipment, ShipmentStatus
from fastapi.testclient import TestClient
from tests.conftest import add_field, add_line, login, make_document, make_shipment


def test_login_and_me(world):
    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "EXEC"


def test_exec_cannot_approve(world):
    with SessionLocal() as db:
        shipment = make_shipment(
            db, world, ref="SHP-AUTH", status=ShipmentStatus.AWAITING_APPROVAL
        )
        shipment_id = shipment.id

    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        response = client.post(
            f"/api/shipments/{shipment_id}/approve", json={"decision": "APPROVE"}
        )
        assert response.status_code == 403
        assert response.json()["code"] == "role_required"


def test_cross_org_shipment_returns_404(world):
    with SessionLocal() as db:
        other = Shipment(
            org_id=world["other_org"].id,
            ref="SHP-OTHER",
            currency="USD",
            status=ShipmentStatus.NEEDS_REVIEW,
        )
        db.add(other)
        db.commit()
        other_id = other.id

    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        response = client.get(f"/api/shipments/{other_id}")
        assert response.status_code == 404


def test_mutation_requires_csrf(world):
    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        token = client.headers.pop("X-CSRF-Token")
        response = client.post("/api/shipments", json={"ref": "SHP-CSRF", "currency": "USD"})
        assert response.status_code == 403
        assert response.json()["code"] == "csrf_failed"
        client.headers["X-CSRF-Token"] = token


def test_submit_blocked_when_fields_unconfirmed(world):
    with SessionLocal() as db:
        shipment = make_shipment(db, world, ref="SHP-SUB")
        invoice = make_document(db, shipment, DocumentType.INVOICE)
        make_document(db, shipment, DocumentType.PACKING)
        make_document(db, shipment, DocumentType.BL)
        add_field(db, shipment, invoice, "invoice_number", "INV-1")
        add_field(db, shipment, invoice, "currency", "USD")
        add_field(db, shipment, invoice, "invoice_total", "1000.00")
        add_line(db, shipment, invoice)
        shipment_id = shipment.id

    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        response = client.post(f"/api/shipments/{shipment_id}/submit")
        assert response.status_code == 409
        assert response.json()["code"] == "gate_blocked"
