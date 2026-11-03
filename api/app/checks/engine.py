from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    Check,
    CheckResolution,
    Document,
    DocumentStatus,
    DocumentType,
    Field,
    LineItem,
    Severity,
    Shipment,
    ShipmentStatus,
    Supplier,
)
from ..config import settings

RULE_VERSION = "1"
INCOTERMS_2020 = {
    "EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP",
}


@dataclass
class Result:
    code: str
    severity: Severity
    message: str
    subject_key: str = "shipment"
    field_keys: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    input_hash: str = ""


def _hash(code: str, values: list, tolerance: object = "") -> str:
    payload = json.dumps(
        {"code": code, "values": values, "tol": str(tolerance), "v": RULE_VERSION},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _dec(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", value)
    return int(match.group()) if match else None


def _container_valid(value: str) -> bool:
    code = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if not re.fullmatch(r"[A-Z]{4}\d{7}", code):
        return False
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total = 0
    for index, char in enumerate(code[:10]):
        number = int(char) if char.isdigit() else letters.index(char) + 10
        if number >= 11:
            number += 1
        total += number * (2**index)
    check = total % 11
    if check == 10:
        check = 0
    return str(check) == code[-1]


def _match_lines(invoice: list[LineItem], packing: list[LineItem]):
    pairs: list[tuple[LineItem, LineItem | None, float]] = []
    used: set[str] = set()
    for item in invoice:
        best = None
        best_score = 0.0
        for candidate in packing:
            if candidate.id in used:
                continue
            score = fuzz.token_set_ratio(item.description_raw or "", candidate.description_raw or "") / 100
            if score > best_score:
                best, best_score = candidate, score
        if best is not None and best_score >= 0.70:
            used.add(best.id)
            pairs.append((item, best, best_score))
        else:
            pairs.append((item, None, best_score))
    leftovers = [candidate for candidate in packing if candidate.id not in used]
    return pairs, leftovers


def run_checks(db: Session, shipment_id: str) -> list[Check]:
    shipment = db.get(Shipment, shipment_id)
    if not shipment:
        return []

    documents = db.scalars(select(Document).where(Document.shipment_id == shipment_id)).all()
    doc_by_id = {d.id: d for d in documents}
    fields = db.scalars(select(Field).where(Field.shipment_id == shipment_id)).all()
    by_type: dict[str, dict[str, Field]] = {}
    for item in fields:
        document = doc_by_id.get(item.document_id)
        if not document:
            continue
        by_type.setdefault(str(document.type), {})[item.key] = item

    invoice_lines = db.scalars(
        select(LineItem).where(
            LineItem.shipment_id == shipment_id,
            LineItem.document_id.in_(
                [d.id for d in documents if d.type == DocumentType.INVOICE]
            ),
        ).order_by(LineItem.line_no)
    ).all()
    packing_lines = db.scalars(
        select(LineItem).where(
            LineItem.shipment_id == shipment_id,
            LineItem.document_id.in_(
                [d.id for d in documents if d.type == DocumentType.PACKING]
            ),
        ).order_by(LineItem.line_no)
    ).all()

    tolerance = float(shipment.org.weight_tol_pct)
    results: list[Result] = []
    pairs, unmatched_packing = _match_lines(invoice_lines, packing_lines)

    # 1. line arithmetic
    for item in invoice_lines:
        if item.unit_price is None or item.amount is None:
            continue
        expected = (item.qty * item.unit_price).quantize(Decimal("0.01"))
        diff = abs(expected - item.amount)
        values = [str(item.qty), str(item.unit_price), str(item.amount), str(expected)]
        results.append(
            Result(
                code="LINE_AMOUNT",
                severity=Severity.PASS if diff <= Decimal("0.01") else Severity.BLOCK,
                message=(
                    f"Line {item.line_no}: {item.qty} × {item.unit_price} = {expected}"
                    if diff <= Decimal("0.01")
                    else f"Line {item.line_no}: {item.qty} × {item.unit_price} = {expected}, "
                    f"but the document states {item.amount}"
                ),
                subject_key=f"line-{item.line_no}",
                params={"expected": str(expected), "actual": str(item.amount)},
                input_hash=_hash("LINE_AMOUNT", values, "0.01"),
            )
        )

    # 2. invoice total
    invoice = by_type.get(str(DocumentType.INVOICE), {})
    total = _dec(invoice.get("invoice_total").value_norm) if invoice.get("invoice_total") else None
    if total is not None:
        line_sum = sum((item.amount or Decimal("0")) for item in invoice_lines)
        freight = _dec(invoice.get("freight").value_norm) if invoice.get("freight") else Decimal("0")
        insurance = _dec(invoice.get("insurance").value_norm) if invoice.get("insurance") else Decimal("0")
        discount = _dec(invoice.get("discount").value_norm) if invoice.get("discount") else Decimal("0")
        expected = line_sum + (freight or 0) + (insurance or 0) - (discount or 0)
        diff = abs(expected - total)
        values = [str(line_sum), str(freight), str(insurance), str(discount), str(total)]
        results.append(
            Result(
                code="INVOICE_TOTAL",
                severity=Severity.PASS if diff <= Decimal("0.01") else Severity.BLOCK,
                message=(
                    f"Lines {line_sum} + freight {freight} + insurance {insurance} "
                    f"− discount {discount} = {expected}"
                    if diff <= Decimal("0.01")
                    else f"Calculated total {expected} does not match invoice total {total} "
                    f"(difference {diff})"
                ),
                field_keys=["invoice_total"],
                params={"expected": str(expected), "actual": str(total), "difference": str(diff)},
                input_hash=_hash("INVOICE_TOTAL", values, "0.01"),
            )
        )

    # 3. declared line count
    declared = _int(invoice.get("declared_item_count").value_norm) if invoice.get("declared_item_count") else None
    if declared is not None:
        results.append(
            Result(
                code="LINE_COUNT",
                severity=Severity.PASS if declared == len(invoice_lines) else Severity.BLOCK,
                message=(
                    f"{declared} item{'s' if declared != 1 else ''} declared and extracted"
                    if declared == len(invoice_lines)
                    else f"Document declares {declared} items but {len(invoice_lines)} were extracted"
                ),
                params={"declared": declared, "extracted": len(invoice_lines)},
                input_hash=_hash("LINE_COUNT", [declared, len(invoice_lines)]),
            )
        )

    # 4. quantity match
    for invoice_line, packing_line, score in pairs:
        if packing_line is None:
            results.append(
                Result(
                    code="QTY_MATCH",
                    severity=Severity.BLOCK,
                    message=f"Line {invoice_line.line_no} “{invoice_line.description_raw}” is not on the packing list",
                    subject_key=f"line-{invoice_line.line_no}",
                    params={"invoice_qty": str(invoice_line.qty), "packing_qty": None},
                    input_hash=_hash("QTY_MATCH", [invoice_line.line_no, str(invoice_line.qty), None]),
                )
            )
            continue
        same = invoice_line.qty == packing_line.qty
        results.append(
            Result(
                code="QTY_MATCH",
                severity=Severity.PASS if same else Severity.BLOCK,
                message=(
                    f"Line {invoice_line.line_no}: {invoice_line.qty} on invoice and packing list"
                    if same
                    else f"Line {invoice_line.line_no}: invoice {invoice_line.qty} vs packing list "
                    f"{packing_line.qty}"
                ),
                subject_key=f"line-{invoice_line.line_no}",
                params={
                    "invoice_qty": str(invoice_line.qty),
                    "packing_qty": str(packing_line.qty),
                    "match": round(score, 2),
                },
                input_hash=_hash(
                    "QTY_MATCH",
                    [invoice_line.line_no, str(invoice_line.qty), str(packing_line.qty)],
                ),
            )
        )

    # 5. weights
    weights = {}
    for doc_type in (DocumentType.INVOICE, DocumentType.PACKING, DocumentType.BL):
        section = by_type.get(str(doc_type), {})
        if "gross_weight_kg" in section:
            value = _dec(section["gross_weight_kg"].value_norm)
            if value is not None:
                weights[str(doc_type)] = value
    if len(weights) >= 2:
        values = list(weights.values())
        base = min(values)
        delta = max(values) - base
        pct = (delta / base * 100) if base else Decimal("0")
        passed = pct <= Decimal(str(tolerance))
        results.append(
            Result(
                code="WEIGHT_MATCH",
                severity=Severity.PASS if passed else Severity.WARN,
                message=(
                    f"Gross weight agrees across {len(weights)} documents"
                    if passed
                    else " · ".join(f"{k.lower()} {v:,.0f} kg" for k, v in weights.items())
                    + f" — difference {delta:,.0f} kg ({pct:.2f}%)"
                ),
                field_keys=["gross_weight_kg"],
                params={
                    "weights": {k: str(v) for k, v in weights.items()},
                    "delta_kg": str(delta),
                    "pct": str(pct.quantize(Decimal("0.01"))),
                    "tolerance_pct": tolerance,
                },
                input_hash=_hash("WEIGHT_MATCH", [str(v) for v in values], tolerance),
            )
        )
    elif len(weights) == 1:
        results.append(
            Result(
                code="WEIGHT_MATCH",
                severity=Severity.PASS,
                message="Only one weight available; missing-document check covers the gap",
                params={},
                input_hash=_hash("WEIGHT_MATCH", list(weights.values()), tolerance),
            )
        )

    # 6. packages
    packages = {}
    for doc_type in (DocumentType.INVOICE, DocumentType.PACKING, DocumentType.BL):
        section = by_type.get(str(doc_type), {})
        if "packages" in section:
            value = _int(section["packages"].value_norm)
            if value is not None:
                packages[str(doc_type)] = value
    if len(packages) >= 2:
        distinct = set(packages.values())
        results.append(
            Result(
                code="PACKAGES_MATCH",
                severity=Severity.PASS if len(distinct) == 1 else Severity.BLOCK,
                message=(
                    f"{list(distinct)[0]} packages across {len(packages)} documents"
                    if len(distinct) == 1
                    else " · ".join(f"{k.lower()} {v}" for k, v in packages.items())
                ),
                field_keys=["packages"],
                params={"packages": packages},
                input_hash=_hash("PACKAGES_MATCH", [str(v) for v in packages.values()]),
            )
        )

    # 7. containers
    section = by_type.get(str(DocumentType.BL), {})
    if "container_numbers" in section:
        raw = section["container_numbers"].value_norm or ""
        containers = [c.strip() for c in re.split(r"[,;]", raw) if c.strip()]
        distinct = {c.upper() for c in containers}
        invalid = [c for c in containers if not _container_valid(c)]
        duplicate = len(distinct) != len(containers)
        results.append(
            Result(
                code="CONTAINER_CHECK",
                severity=Severity.BLOCK if invalid or duplicate else Severity.PASS,
                message=(
                    f"{len(containers)} containers, ISO 6346 valid"
                    if not invalid and not duplicate
                    else f"Invalid container number(s): {', '.join(invalid)}"
                    if invalid
                    else "Duplicate container numbers on the bill of lading"
                ),
                field_keys=["container_numbers"],
                params={"containers": containers, "invalid": invalid},
                input_hash=_hash("CONTAINER_CHECK", containers),
            )
        )

    # 8. parties
    supplier_names = {}
    for doc_type in (DocumentType.INVOICE, DocumentType.PACKING, DocumentType.BL):
        section = by_type.get(str(doc_type), {})
        if "supplier_name" in section:
            supplier_names[str(doc_type)] = section["supplier_name"].value_norm or ""
    if len(supplier_names) >= 2:
        values = list(supplier_names.values())
        base = values[0]
        worst = min(fuzz.token_set_ratio(base, value) for value in values[1:]) / 100
        results.append(
            Result(
                code="PARTY_MATCH",
                severity=Severity.PASS if worst >= 0.90 else Severity.WARN,
                message=(
                    "Supplier name consistent across documents"
                    if worst >= 0.90
                    else f"Supplier name differs across documents (best match {worst:.0%}): "
                    + " · ".join(f"{k.lower()} “{v}”" for k, v in supplier_names.items())
                ),
                field_keys=["supplier_name"],
                params={"names": supplier_names, "score": round(worst, 2)},
                input_hash=_hash("PARTY_MATCH", values),
            )
        )
    buyer = by_type.get(str(DocumentType.INVOICE), {}).get("buyer_name")
    consignee = by_type.get(str(DocumentType.BL), {}).get("consignee")
    if buyer and consignee:
        score = fuzz.token_set_ratio(buyer.value_norm or "", consignee.value_norm or "") / 100
        results.append(
            Result(
                code="PARTY_MATCH",
                severity=Severity.PASS if score >= 0.90 else Severity.WARN,
                message=(
                    "Buyer and consignee consistent"
                    if score >= 0.90
                    else f"Buyer “{buyer.value_norm}” and consignee “{consignee.value_norm}” "
                    f"differ ({score:.0%} match)"
                ),
                subject_key="buyer-consignee",
                field_keys=["buyer_name", "consignee"],
                params={"score": round(score, 2)},
                input_hash=_hash("PARTY_MATCH", [buyer.value_norm, consignee.value_norm]),
            )
        )

    # 9. currency
    currency_field = invoice.get("currency")
    if currency_field:
        currency = (currency_field.value_norm or "").upper()
        results.append(
            Result(
                code="CURRENCY_MATCH",
                severity=Severity.PASS if currency == shipment.currency.upper() else Severity.BLOCK,
                message=(
                    f"Currency {currency} consistent"
                    if currency == shipment.currency.upper()
                    else f"Invoice is in {currency} but the shipment is recorded as {shipment.currency}"
                ),
                field_keys=["currency"],
                params={"invoice": currency, "shipment": shipment.currency},
                input_hash=_hash("CURRENCY_MATCH", [currency, shipment.currency]),
            )
        )

    # 10. incoterm
    incoterm_field = invoice.get("incoterm")
    if incoterm_field:
        incoterm = (incoterm_field.value_norm or "").upper()
        valid = incoterm in INCOTERMS_2020
        results.append(
            Result(
                code="INCOTERM_VALID",
                severity=Severity.PASS if valid else Severity.WARN,
                message=(
                    f"Incoterm {incoterm} is valid"
                    if valid
                    else f"“{incoterm}” is not a valid Incoterms 2020 code"
                ),
                field_keys=["incoterm"],
                params={"incoterm": incoterm},
                input_hash=_hash("INCOTERM_VALID", [incoterm]),
            )
        )

    # 11. dates
    date_field = invoice.get("invoice_date")
    if date_field and date_field.value_norm:
        try:
            invoice_date = date.fromisoformat(date_field.value_norm)
            today = date.today()
            problems = []
            if invoice_date > today:
                problems.append("invoice is dated in the future")
            if (today - invoice_date).days > 90:
                problems.append("invoice is more than 90 days old")
            bl_date_field = by_type.get(str(DocumentType.BL), {}).get("bl_date")
            if bl_date_field and bl_date_field.value_norm:
                bl_date = date.fromisoformat(bl_date_field.value_norm)
                if invoice_date > bl_date:
                    problems.append("invoice is dated after the bill of lading")
            results.append(
                Result(
                    code="DATE_SANITY",
                    severity=Severity.PASS if not problems else Severity.WARN,
                    message="Invoice date is plausible" if not problems else "; ".join(problems).capitalize(),
                    field_keys=["invoice_date"],
                    params={"invoice_date": invoice_date.isoformat()},
                    input_hash=_hash("DATE_SANITY", [invoice_date.isoformat()]),
                )
            )
        except ValueError:
            results.append(
                Result(
                    code="DATE_SANITY",
                    severity=Severity.WARN,
                    message="Invoice date could not be parsed",
                    field_keys=["invoice_date"],
                    input_hash=_hash("DATE_SANITY", ["unparseable"]),
                )
            )

    # 12. uom consistency
    uom_problems = [
        pair for pair in pairs if pair[1] is not None and pair[0].uom and pair[1].uom
        and pair[0].uom.upper() != pair[1].uom.upper()
    ]
    if pairs:
        results.append(
            Result(
                code="UOM_CONSISTENCY",
                severity=Severity.PASS if not uom_problems else Severity.WARN,
                message=(
                    "Units consistent between invoice and packing list"
                    if not uom_problems
                    else f"{len(uom_problems)} line(s) use different units"
                ),
                params={"mismatches": len(uom_problems)},
                input_hash=_hash("UOM_CONSISTENCY", [p[0].uom for p in pairs if p[1]]),
            )
        )

    # 13. documents complete
    present = {str(d.type) for d in documents if d.status == DocumentStatus.EXTRACTED}
    required = {"INVOICE", "PACKING", "BL"}
    missing = sorted(required - present)
    results.append(
        Result(
            code="DOCS_COMPLETE",
            severity=Severity.BLOCK if missing else Severity.PASS,
            message=(
                "All three documents extracted"
                if not missing
                else "Missing or unreadable: " + ", ".join(m.replace("BL", "bill of lading").title() for m in missing)
            ),
            params={"missing": missing},
            input_hash=_hash("DOCS_COMPLETE", sorted(present)),
        )
    )

    # unmatched packing lines
    for item in unmatched_packing:
        results.append(
            Result(
                code="QTY_MATCH",
                severity=Severity.WARN,
                message=f"Packing line {item.line_no} “{item.description_raw}” is not on the invoice",
                subject_key=f"packing-{item.line_no}",
                params={"packing_qty": str(item.qty)},
                input_hash=_hash("QTY_MATCH", ["packing-only", item.line_no, str(item.qty)]),
            )
        )

    db.execute(delete(Check).where(Check.shipment_id == shipment_id))
    rows: list[Check] = []
    for result in results:
        row = Check(
            shipment_id=shipment_id,
            code=result.code,
            subject_key=result.subject_key,
            severity=result.severity,
            message=result.message,
            field_keys=result.field_keys,
            params=result.params,
            input_hash=result.input_hash,
            rule_version=RULE_VERSION,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


def resolved_map(db: Session, shipment_id: str) -> dict[tuple[str, str, str], CheckResolution]:
    rows = db.scalars(
        select(CheckResolution).where(CheckResolution.shipment_id == shipment_id)
    ).all()
    return {(r.code, r.subject_key, r.input_hash): r for r in rows}
