from __future__ import annotations

import os
import pathlib
import sys
import uuid

TEST_DB = "postgresql+psycopg://postgres@/customs_test?host=/tmp/opencode/pgdata"
os.environ["DATABASE_URL"] = TEST_DB
os.environ["APP_ENV"] = "test"
os.environ["AI_BACKEND"] = "fixture"
os.environ["DEMO_EXEC_PASSWORD"] = "test-exec"
os.environ["DEMO_MANAGER_PASSWORD"] = "test-manager"

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

with psycopg.connect(
    "postgresql://postgres@/postgres?host=/tmp/opencode/pgdata", autocommit=True
) as connection:
    exists = connection.execute(
        "select 1 from pg_database where datname = 'customs_test'"
    ).fetchone()
    if not exists:
        connection.execute("create database customs_test")

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Document,
    DocumentStatus,
    DocumentType,
    EvidenceLevel,
    Field,
    FieldStatus,
    LineItem,
    Org,
    Role,
    Shipment,
    ShipmentStatus,
    Supplier,
    User,
)
from app.security import hash_password  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def world(db):
    org = Org(name="Test Freight")
    other = Org(name="Other Freight")
    db.add_all([org, other])
    db.flush()

    supplier = Supplier(org_id=org.id, name="Company B", country_code="CN")
    db.add(supplier)
    db.flush()

    exec_user = User(
        org_id=org.id,
        email="exec@test.local",
        password_hash=hash_password("test-exec"),
        role=Role.EXEC,
    )
    manager = User(
        org_id=org.id,
        email="manager@test.local",
        password_hash=hash_password("test-manager"),
        role=Role.MANAGER,
    )
    other_user = User(
        org_id=other.id,
        email="other@test.local",
        password_hash=hash_password("test-exec"),
        role=Role.EXEC,
    )
    db.add_all([exec_user, manager, other_user])
    db.commit()

    return {
        "org": org,
        "other_org": other,
        "supplier": supplier,
        "exec": exec_user,
        "manager": manager,
        "other_user": other_user,
    }


def new_id() -> str:
    return str(uuid.uuid4())


def make_shipment(db, world, ref="SHP-1", status=ShipmentStatus.NEEDS_REVIEW):
    shipment = Shipment(
        org_id=world["org"].id,
        ref=ref,
        supplier_id=world["supplier"].id,
        status=status,
        currency="USD",
        incoterm="FOB",
        created_by=world["exec"].id,
    )
    db.add(shipment)
    db.commit()
    db.refresh(shipment)
    return shipment


def make_document(db, shipment, doc_type: DocumentType):
    document = Document(
        shipment_id=shipment.id,
        type=doc_type,
        storage_key=f"test/{shipment.id}/{doc_type}.pdf",
        file_name=f"{str(doc_type).lower()}.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        sha256=uuid.uuid4().hex,
        page_count=1,
        status=DocumentStatus.EXTRACTED,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def add_field(
    db,
    shipment,
    document,
    key,
    value,
    level="EXACT",
    confidence=0.99,
    status="SUGGESTED",
):
    field = Field(
        shipment_id=shipment.id,
        document_id=document.id,
        key=key,
        value_raw=str(value),
        value_norm=str(value),
        model_conf=0.95,
        effective_conf=confidence,
        verification_level=EvidenceLevel(level) if isinstance(level, str) else level,
        page_idx=1,
        status=FieldStatus(status) if isinstance(status, str) else status,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


def add_line(db, shipment, document, line_no=1, description="Widget", qty=100,
             unit_price="10.00", amount="1000.00", hsn="8481.80"):
    line = LineItem(
        shipment_id=shipment.id,
        document_id=document.id,
        line_no=line_no,
        description_raw=description,
        hsn_code=hsn,
        qty=qty,
        uom="PCS",
        unit_price=unit_price,
        amount=amount,
        gross_weight_kg=None,
        net_weight_kg=None,
    )
    db.add(line)
    db.commit()
    db.refresh(line)
    return line


def login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = token
    return token
