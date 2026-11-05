"""Golden-set evaluation for the extraction and evidence pipeline.

Run after seeding:
    cd api && ../.venv/bin/python ../eval/run.py

The local demo uses a deterministic fixture extractor. This harness measures the
extraction, evidence and persistence pipeline on synthetic documents. It is not a
measurement of Gemini; the Vertex adapter is exercised separately when credentials exist.
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Correction,
    Document,
    DocumentStatus,
    DocumentType,
    ExtractionRun,
    Field,
    Org,
    Shipment,
)
from seed.generate import build_specs  # noqa: E402

NUMERIC = {
    "invoice_total", "freight", "insurance", "discount", "gross_weight_kg",
    "net_weight_kg", "packages", "declared_item_count",
}


def iso_date(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%Y").date().isoformat()


def expected_for(spec) -> dict[str, dict[str, object]]:
    return {
        DocumentType.INVOICE: {
            "supplier_name": spec.supplier,
            "buyer_name": spec.buyer,
            "invoice_number": spec.invoice_no,
            "invoice_date": iso_date(spec.invoice_date),
            "currency": spec.currency,
            "incoterm": spec.incoterm,
            "invoice_total": spec.total,
            "freight": spec.freight,
            "insurance": spec.insurance,
            "discount": spec.discount,
            "gross_weight_kg": spec.gross_invoice,
            "net_weight_kg": spec.net_invoice,
            "packages": spec.packages_invoice,
            "declared_item_count": len(spec.items),
        },
        DocumentType.PACKING: {
            "supplier_name": spec.supplier,
            "buyer_name": spec.buyer,
            "invoice_reference": spec.invoice_no,
            "packages": spec.packages_packing,
            "package_type": "CTN",
            "gross_weight_kg": spec.gross_packing,
            "net_weight_kg": spec.net_packing,
            "declared_item_count": len(spec.items),
        },
        DocumentType.BL: {
            "supplier_name": spec.supplier,
            "consignee": spec.buyer,
            "bl_number": spec.bl_no,
            "bl_date": iso_date(spec.bl_date),
            "packages": spec.packages_bl,
            "gross_weight_kg": spec.gross_bl,
            "container_numbers": ",".join(spec.containers),
            "port_of_loading": "Ningbo",
            "port_of_discharge": "Nhava Sheva",
            "vessel_name": "MSC Aria",
        },
    }


def matches(key: str, expected, actual) -> bool:
    if actual is None:
        return False
    if key == "container_numbers":
        return {x.strip().upper() for x in str(actual).split(",")} == {
            x.strip().upper() for x in str(expected).split(",")
        }
    if key in NUMERIC:
        try:
            return Decimal(str(actual)) == Decimal(str(expected))
        except (InvalidOperation, ValueError):
            return False
    return str(actual).strip().casefold() == str(expected).strip().casefold()


def main() -> None:
    specs = build_specs()
    results = []
    evidence = Counter()
    misses = []
    manual = []
    missing = []

    with SessionLocal() as db:
        org = db.scalar(select(Org).where(Org.name == "Demo Freight"))
        if not org:
            raise SystemExit("Seed the demo first: cd api && ../.venv/bin/python ../seed/seed_demo.py")

        for spec in specs:
            shipment = db.scalar(
                select(Shipment).where(Shipment.org_id == org.id, Shipment.ref == spec.ref)
            )
            if not shipment:
                continue
            doc_list = db.scalars(
                select(Document).where(Document.shipment_id == shipment.id)
            ).all()
            documents = {d.type: d for d in doc_list}
            by_id = {d.id: d for d in doc_list}
            field_rows = db.scalars(
                select(Field).where(Field.shipment_id == shipment.id)
            ).all()
            # Evaluate the original extraction, not the post-correction value.
            original: dict[str, str | None] = {}
            for correction in db.scalars(
                select(Correction)
                .join(Field, Field.id == Correction.field_id)
                .where(Field.shipment_id == shipment.id)
                .order_by(Correction.created_at)
            ).all():
                original.setdefault(correction.field_id, correction.old_value)
            fields = {
                (by_id[f.document_id].type, f.key): f
                for f in field_rows
                if f.document_id in by_id
            }

            for doc_type, expected_fields in expected_for(spec).items():
                document = documents.get(doc_type)
                label = f"{spec.ref} {str(doc_type).lower()}"
                if not document:
                    missing.append(label)
                    continue
                if document.status in {DocumentStatus.NEEDS_MANUAL_ENTRY, DocumentStatus.FAILED}:
                    manual.append(label)
                    continue
                for key, expected in expected_fields.items():
                    field = fields.get((doc_type, key))
                    actual = (
                        original.get(field.id, field.value_norm) if field else None
                    )
                    ok = matches(key, expected, actual)
                    results.append({"document": label, "key": key, "ok": ok})
                    if field:
                        evidence[str(field.verification_level)] += 1
                    if not ok:
                        misses.append((label, key, expected, actual))

        model_counts = Counter(
            run.model_id for run in db.scalars(select(ExtractionRun)).all()
        )

    total = len(results)
    correct = sum(1 for r in results if r["ok"])
    accuracy = (correct / total * 100) if total else 0.0
    live = any(not str(model).startswith("fixture") for model in model_counts)

    by_key: dict[str, list[bool]] = defaultdict(list)
    for row in results:
        by_key[row["key"]].append(row["ok"])

    print()
    print("Synthetic golden set — extraction and evidence evaluation")
    print("=" * 78)
    print(f"documents compared {total and len({r['document'] for r in results}) or 0}"
          f" · fields compared {total} · exact match {correct}/{total} ({accuracy:.1f}%)")
    if live:
        print("Models:", " · ".join(f"{m} ({c})" for m, c in sorted(model_counts.items())))
    print()
    print(f"{'FIELD':28} {'N':>4} {'OK':>4} {'ACCURACY':>9}")
    print("-" * 78)
    for key in sorted(by_key, key=lambda k: (-len(by_key[k]), k)):
        rows = by_key[key]
        ok = sum(rows)
        print(f"{key:28} {len(rows):>4} {ok:>4} {ok / len(rows) * 100:>8.1f}%")

    print()
    print("Evidence distribution:", " · ".join(f"{k} {v}" for k, v in sorted(evidence.items())))
    print(f"Manual entry documents: {len(manual)}" + (f" ({', '.join(manual)})" if manual else ""))
    print(f"Missing documents: {len(missing)}" + (f" ({', '.join(missing)})" if missing else ""))

    if misses:
        print()
        print("Mismatches")
        print("-" * 78)
        for label, key, expected, actual in misses:
            print(f"{label:24} {key:22} expected={expected!r:22} actual={actual!r}")
    else:
        print()
        print("No field mismatches on extractable documents.")

    output = {
        "documents_compared": len({r["document"] for r in results}),
        "fields_compared": total,
        "correct": correct,
        "accuracy": round(accuracy, 2),
        "evidence": dict(evidence),
        "manual_documents": manual,
        "missing_documents": missing,
        "misses": [
            {"document": label, "field": key, "expected": str(expected), "actual": str(actual)}
            for label, key, expected, actual in misses
        ],
        "extractor": "live" if live else "fixture",
        "models": dict(model_counts),
    }
    (ROOT / "eval" / "results.json").write_text(json.dumps(output, indent=2))
    print()
    print("Wrote eval/results.json")
    if live:
        print("Note: live model(s) on synthetic documents — not client data.")
    else:
        print("Note: fixture extractor, synthetic documents. Not a Gemini accuracy measurement.")


if __name__ == "__main__":
    main()
