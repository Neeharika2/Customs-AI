"""Idempotent development seed. Run with: cd api && ../.venv/bin/python -m app.seed"""
from decimal import Decimal

from sqlalchemy import func, select

from .config import settings
from .db import Base, SessionLocal, engine
from .models import (
    ExportTemplate,
    Org,
    Role,
    Shipment,
    ShipmentStatus,
    Supplier,
    User,
)
from .security import hash_password

DEMO_SHIPMENTS = [
    ("SHP-24811", "Company B", "USD", "FOB", ShipmentStatus.NEEDS_REVIEW),
    ("SHP-24812", "Company C", "EUR", "CIF", ShipmentStatus.NEEDS_REVIEW),
    ("SHP-24813", "Company B", "USD", "FOB", ShipmentStatus.NEEDS_REVIEW),
    ("SHP-24814", "Company D", "USD", "FOB", ShipmentStatus.NEEDS_REVIEW),
    ("SHP-24815", "Company C", "EUR", "CFR", ShipmentStatus.NEEDS_REVIEW),
    ("SHP-24816", "Company E", "USD", "FOB", ShipmentStatus.NEEDS_REVIEW),
    ("SHP-24817", "Company B", "USD", "FOB", ShipmentStatus.NEEDS_REVIEW),
    ("SHP-24818", "Company C", "EUR", "FOB", ShipmentStatus.EXPORTED),
    ("SHP-24819", "Company D", "USD", "CIF", ShipmentStatus.AWAITING_APPROVAL),
]

SUPPLIERS = [
    ("Company B", "CN"),
    ("Company C", "SE"),
    ("Company D", "CN"),
    ("Company E", "IN"),
]

TEMPLATE = [
    {"header": "Invoice No", "source": "invoice_number", "required": True},
    {"header": "Invoice Date", "source": "invoice_date", "format": "%d/%m/%Y"},
    {"header": "Supplier", "source": "supplier_name"},
    {"header": "Buyer", "source": "buyer_name"},
    {"header": "Currency", "source": "currency", "required": True},
    {"header": "Incoterm", "source": "incoterm"},
    {"header": "Description", "source": "item.description"},
    {"header": "HSN", "source": "item.hsn_code"},
    {"header": "Quantity", "source": "item.qty", "format": "0.###"},
    {"header": "Unit Price", "source": "item.unit_price", "format": "0.0000"},
    {"header": "Amount", "source": "item.amount", "format": "0.00"},
    {"header": "Packages", "source": "packages"},
    {"header": "Gross Weight", "source": "gross_weight_kg", "format": "0.000"},
    {"header": "Container No", "source": "container_numbers", "join": ";"},
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        org = db.scalar(select(Org).where(Org.name == "Demo Freight"))
        if not org:
            org = Org(name="Demo Freight", weight_tol_pct=Decimal("0.5"),
                      value_tol=Decimal("0.01"), monthly_ai_cap_paise=500_000,
                      retention_days=180)
            db.add(org)
            db.flush()

        users = [
            ("exec@demo.local", settings.demo_exec_password, Role.EXEC, "Asha Sharma"),
            ("manager@demo.local", settings.demo_manager_password, Role.MANAGER, "Ravi Iyer"),
        ]
        for email, password, role, _name in users:
            found = db.scalar(
                select(User).where(User.org_id == org.id, func.lower(User.email) == email)
            )
            if not found:
                db.add(User(org_id=org.id, email=email, password_hash=hash_password(password),
                            role=role))
        db.flush()

        for name, country in SUPPLIERS:
            found = db.scalar(
                select(Supplier).where(Supplier.org_id == org.id, Supplier.name == name)
            )
            if not found:
                db.add(Supplier(org_id=org.id, name=name, country_code=country))
        db.flush()

        template = db.scalar(
            select(ExportTemplate).where(ExportTemplate.org_id == org.id,
                                         ExportTemplate.is_active.is_(True))
        )
        if not template:
            db.add(ExportTemplate(org_id=org.id, name="Bill of Entry — default",
                                  column_map=TEMPLATE, version=1, is_active=True))
        db.flush()

        supplier_by_name = {
            s.name: s for s in db.scalars(
                select(Supplier).where(Supplier.org_id == org.id)
            ).all()
        }
        for ref, supplier_name, currency, incoterm, status in DEMO_SHIPMENTS:
            found = db.scalar(
                select(Shipment).where(Shipment.org_id == org.id, Shipment.ref == ref)
            )
            if not found:
                db.add(Shipment(org_id=org.id, ref=ref,
                                supplier_id=supplier_by_name[supplier_name].id,
                                currency=currency, incoterm=incoterm, status=status))
        db.commit()

    print("Seeded:")
    print("  org        Demo Freight")
    print("  executive  exec@demo.local")
    print("  manager    manager@demo.local")
    print(f"  suppliers  {len(SUPPLIERS)}")
    print(f"  shipments  {len(DEMO_SHIPMENTS)}")


if __name__ == "__main__":
    main()
