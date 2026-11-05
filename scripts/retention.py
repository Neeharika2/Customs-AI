"""Retention purge: delete document objects for old exported shipments.

Default is a dry run:
    cd api && uv run python ../scripts/retention.py

Delete objects:
    cd api && uv run python ../scripts/retention.py --apply

Database rows (fields, checks, corrections, exports and audit) are retained so the
filing history and accuracy record survive. Only the source files and page images go.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db import SessionLocal
from app.deps import audit
from app.models import Document, Export, Org, Page, Shipment, ShipmentStatus
from app.services.storage import get_storage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="delete objects; default is dry-run")
    parser.add_argument("--org", default="Demo Freight", help="organisation name")
    args = parser.parse_args()

    storage = get_storage()
    now = datetime.now(UTC)
    total_objects = 0
    total_shipments = 0

    with SessionLocal() as db:
        org = db.scalar(select(Org).where(Org.name == args.org))
        if not org:
            raise SystemExit(f"Organisation not found: {args.org}")
        cutoff = now - timedelta(days=org.retention_days)

        rows = db.execute(
            select(Shipment, func.max(Export.created_at))
            .join(Export, Export.shipment_id == Shipment.id)
            .where(Shipment.org_id == org.id, Shipment.status == ShipmentStatus.EXPORTED)
            .group_by(Shipment.id)
        ).all()

        for shipment, last_export in rows:
            if not last_export:
                continue
            if last_export.tzinfo is None:
                last_export = last_export.replace(tzinfo=UTC)
            if last_export >= cutoff:
                continue

            documents = db.scalars(
                select(Document).where(Document.shipment_id == shipment.id)
            ).all()
            keys: list[str] = []
            for document in documents:
                keys.append(document.storage_key)
                for run_key in [
                    run.raw_response_key
                    for run in document.runs
                    if run.raw_response_key
                ]:
                    keys.append(run_key)
                for page in db.scalars(
                    select(Page).where(Page.document_id == document.id)
                ).all():
                    keys.append(page.image_key)
                    if page.words_key:
                        keys.append(page.words_key)

            total_shipments += 1
            total_objects += len(keys)
            print(
                f"{shipment.ref}: {len(documents)} documents, {len(keys)} objects, "
                f"last export {last_export.date()}"
            )

            if args.apply:
                for key in keys:
                    storage.delete(key)
                audit(
                    db,
                    org_id=org.id,
                    actor_id=None,
                    action="retention.purged",
                    entity="shipment",
                    entity_id=shipment.id,
                    meta={"objects": len(keys), "documents": len(documents)},
                )

        if args.apply:
            db.commit()

    mode = "APPLIED" if args.apply else "DRY RUN"
    print(
        f"{mode}: {total_shipments} shipments, {total_objects} objects "
        f"(retention {org.retention_days} days for {org.name})"
    )
    if not args.apply:
        print("Run again with --apply to delete.")


if __name__ == "__main__":
    main()
