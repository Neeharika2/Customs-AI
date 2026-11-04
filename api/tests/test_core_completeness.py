from __future__ import annotations

from sqlalchemy import select
from fastapi.testclient import TestClient

from app.checks.engine import run_checks
from app.db import SessionLocal
from app.main import app
from app.models import (
    Check,
    Document,
    DocumentType,
    ExportTemplate,
    FieldStatus,
    Shipment,
    ShipmentStatus,
)
from tests.conftest import add_field, add_line, login, make_document, make_shipment


def build_shipment(db, world, ref="SHP-CORE"):
    shipment = make_shipment(db, world, ref=ref)
    invoice = make_document(db, shipment, DocumentType.INVOICE)
    packing = make_document(db, shipment, DocumentType.PACKING)
    bl = make_document(db, shipment, DocumentType.BL)
    for document, key, value in [
        (invoice, "invoice_number", "INV-1"),
        (invoice, "invoice_date", "2026-10-20"),
        (invoice, "currency", "USD"),
        (invoice, "incoterm", "FOB"),
        (invoice, "supplier_name", "Company B"),
        (invoice, "invoice_total", "1000.00"),
        (invoice, "gross_weight_kg", "3120.00"),
        (invoice, "packages", "120"),
        (packing, "gross_weight_kg", "3121.00"),
        (packing, "packages", "120"),
        (bl, "gross_weight_kg", "3122.00"),
        (bl, "packages", "120"),
    ]:
        add_field(db, shipment, document, key, value, status="CONFIRMED")
    invoice_line = add_line(
        db, shipment, invoice, qty=100, unit_price="10.00", amount="1000.00"
    )
    add_line(db, shipment, packing, qty=100, unit_price=None, amount=None)
    run_checks(db, shipment.id)
    return shipment, invoice, packing, bl, invoice_line


def test_line_correction_reruns_checks(db, world):
    shipment, invoice, packing, bl, line = build_shipment(db, world)

    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        response = client.patch(
            f"/api/line-items/{line.id}",
            json={"qty": 110, "reason": "Supplier revised quantity"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["line"]["status"] == "CORRECTED"
        assert payload["line"]["effective_conf"] == 1.0
        assert any(
            check["code"] == "LINE_AMOUNT" and check["severity"] == "BLOCK"
            for check in payload["check"]
        )

        restored = client.patch(
            f"/api/line-items/{line.id}", json={"qty": 100, "reason": "Reverted"}
        )
        assert restored.status_code == 200
        assert any(
            check["code"] == "LINE_AMOUNT" and check["severity"] == "PASS"
            for check in restored.json()["check"]
        )


def test_activity_includes_the_line_correction(db, world):
    shipment, invoice, packing, bl, line = build_shipment(db, world, ref="SHP-ACT")

    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        client.patch(
            f"/api/line-items/{line.id}",
            json={"description_raw": "Steel valve", "reason": "Supplier wording"},
        )
        response = client.get(f"/api/shipments/{shipment.id}/activity")
        assert response.status_code == 200
        titles = [item["title"] for item in response.json()["items"]]
        assert any("line 1 corrected" in title for title in titles)
        assert any(item["actor"] == "exec@test.local" for item in response.json()["items"])


def test_document_removal_recomputes_the_gate(db, world):
    shipment, invoice, packing, bl, line = build_shipment(db, world, ref="SHP-DEL")

    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        response = client.delete(f"/api/documents/{packing.id}")
        assert response.status_code == 204

        with SessionLocal() as check_db:
            assert check_db.get(Document, packing.id) is None
            codes = {
                c.code
                for c in check_db.scalars(
                    select(Check).where(Check.shipment_id == shipment.id)
                ).all()
                if str(c.severity) == "BLOCK"
            }
            assert "DOCS_COMPLETE" in codes


def test_document_reprocess_queues_the_job(db, world):
    shipment, invoice, packing, bl, line = build_shipment(db, world, ref="SHP-RE")

    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        response = client.post(f"/api/documents/{invoice.id}/reprocess")
        assert response.status_code == 200
        assert response.json()["status"] in {"UPLOADED", "QUEUED", "PROCESSING", "EXTRACTED"}


def test_template_update_creates_a_new_version(db, world):
    template = ExportTemplate(
        org_id=world["org"].id,
        name="Filing",
        column_map=[
            {"header": "Invoice No", "source": "invoice_number"},
            {"header": "Description", "source": "item.description"},
        ],
        version=1,
    )
    db.add(template)
    db.commit()

    with TestClient(app) as client:
        login(client, "manager@test.local", "test-manager")
        response = client.put(
            f"/api/export-templates/{template.id}",
            json={
                "name": "Filing layout",
                "columns": [
                    {"header": "Invoice No", "source": "invoice_number", "required": True},
                    {"header": "Description", "source": "item.description"},
                    {"header": "Qty", "source": "item.qty", "format": "0.###"},
                ],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["version"] == 2

        duplicate = client.put(
            f"/api/export-templates/{template.id}",
            json={
                "name": "Bad",
                "columns": [
                    {"header": "Same", "source": "invoice_number"},
                    {"header": "Same", "source": "item.description"},
                ],
            },
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["code"] == "duplicate_headers"


def test_pagination_reports_total_and_pages(db, world):
    for index in range(3):
        make_shipment(db, world, ref=f"SHP-PAGE-{index}")

    with TestClient(app) as client:
        login(client, "exec@test.local", "test-exec")
        first = client.get("/api/shipments?page=1&limit=2")
        assert first.status_code == 200
        assert first.json()["total"] == 3
        assert len(first.json()["items"]) == 2
        second = client.get("/api/shipments?page=2&limit=2")
        assert len(second.json()["items"]) == 1


def test_manager_can_reopen_and_executive_cannot(db, world):
    ready = make_shipment(db, world, ref="SHP-REOPEN", status=ShipmentStatus.READY)

    with TestClient(app) as executive:
        login(executive, "exec@test.local", "test-exec")
        forbidden = executive.post(f"/api/shipments/{ready.id}/reopen")
        assert forbidden.status_code == 403

    with TestClient(app) as manager:
        login(manager, "manager@test.local", "test-manager")
        response = manager.post(f"/api/shipments/{ready.id}/reopen")
        assert response.status_code == 200
        assert response.json()["status"] == "NEEDS_REVIEW"
