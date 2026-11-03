from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


@dataclass
class ParsedField:
    key: str
    value: str | None
    quote: str | None
    page_idx: int
    model_conf: float = 0.0


@dataclass
class ParsedLine:
    line_no: int
    description: str
    hsn: str | None
    qty: Decimal
    uom: str | None
    unit_price: Decimal | None
    amount: Decimal | None
    gross_weight: Decimal | None = None
    net_weight: Decimal | None = None
    quote: str | None = None
    page_idx: int = 1


@dataclass
class ParsedDocument:
    fields: list[ParsedField] = field(default_factory=list)
    lines: list[ParsedLine] = field(default_factory=list)
    declared_item_count: int | None = None


INVOICE_ROW = re.compile(
    r"^(\d{1,3})\s+(.+?)\s+(\d{4}\.\d{2}|\d{6,8})\s+([\d,]+)\s+"
    r"([A-Za-z]{1,5})\s+([\d,.]+)\s+([\d,.]+)$"
)
PACKING_ROW = re.compile(
    r"^(\d{1,3})\s+(.+?)\s+([\d,]+)\s+([A-Za-z]{1,5})\s+([\d,.]+)\s+([\d,.]+)$"
)


def dec(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = value.replace(",", "").replace(" ", "").strip()
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _find(lines: list[dict], pattern: str) -> tuple[str, str, int] | None:
    regex = re.compile(pattern, re.IGNORECASE)
    for line in lines:
        match = regex.search(line["text"])
        if match:
            return match.group(1).strip(), line["text"], line["page"]
    return None


def _field(
    lines: list[dict], key: str, patterns: list[str], conf: float = 0.97
) -> ParsedField:
    for pattern in patterns:
        found = _find(lines, pattern)
        if found:
            value, quote, page = found
            return ParsedField(key=key, value=value, quote=quote, page_idx=page, model_conf=conf)
    return ParsedField(key=key, value=None, quote=None, page_idx=1, model_conf=0.0)


def _lines_of_type(lines: list[dict], regex: re.Pattern) -> list[re.Match]:
    return [match for line in lines if (match := regex.match(line["text"]))]


def parse_invoice(lines: list[dict]) -> ParsedDocument:
    result = ParsedDocument()
    result.fields = [
        _field(lines, "supplier_name", [r"Supplier\s*:\s*(.+)"]),
        _field(lines, "buyer_name", [r"Buyer\s*:\s*(.+)"]),
        _field(lines, "invoice_number", [r"Invoice\s*No\.?\s*:\s*([A-Za-z0-9/-]+)"]),
        _field(lines, "invoice_date", [r"Invoice\s*Date\s*:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})"]),
        _field(lines, "currency", [r"Currency\s*:\s*([A-Za-z]{3})\s*$"], 0.99),
        _field(lines, "incoterm", [r"Incoterm\s*:\s*([A-Za-z]{3})\s*$"], 0.98),
        _field(lines, "invoice_total", [r"Invoice\s*Total\s*:?\s*([\d,]+\.\d{2})"]),
        _field(lines, "freight", [r"Freight\s*:?\s*([\d,]+\.\d{2})"]),
        _field(lines, "insurance", [r"Insurance\s*:?\s*([\d,]+\.\d{2})"]),
        _field(lines, "discount", [r"Discount\s*:?\s*([\d,]+\.\d{2})"]),
        _field(lines, "gross_weight_kg", [r"Gross\s*Weight\s*:?\s*([\d,]+\.\d{2})"]),
        _field(lines, "net_weight_kg", [r"Net\s*Weight\s*:?\s*([\d,]+\.\d{2})"]),
        _field(lines, "packages", [r"Packages\s*:\s*(\d+)"]),
        _field(lines, "package_type", [r"Packages\s*:\s*\d+\s*([A-Za-z]+)"]),
        _field(lines, "declared_item_count", [r"(?:Total\s*)?Items\s*:\s*(\d+)"]),
    ]

    page_by_line: dict[str, int] = {}
    for line in lines:
        page_by_line.setdefault(line["text"], line["page"])

    for index, match in enumerate(
        [
            match
            for line in lines
            if (match := INVOICE_ROW.match(line["text"]))
        ],
        start=1,
    ):
        line_text = match.group(0)
        result.lines.append(
            ParsedLine(
                line_no=index,
                description=match.group(2).strip(),
                hsn=match.group(3).strip(),
                qty=dec(match.group(4)) or Decimal("0"),
                uom=match.group(5).upper(),
                unit_price=dec(match.group(6)),
                amount=dec(match.group(7)),
                quote=line_text,
                page_idx=page_by_line.get(line_text, 1),
            )
        )
    if result.lines:
        result.declared_item_count = len(result.lines)
    return result


def parse_packing(lines: list[dict]) -> ParsedDocument:
    result = ParsedDocument()
    result.fields = [
        _field(lines, "supplier_name", [r"Supplier\s*:\s*(.+)"]),
        _field(lines, "buyer_name", [r"Buyer\s*:\s*(.+)"]),
        _field(lines, "invoice_reference", [r"Invoice\s*Ref(?:erence)?\.?\s*:\s*([A-Za-z0-9/-]+)"]),
        _field(lines, "packages", [r"Packages\s*:\s*(\d+)"]),
        _field(lines, "package_type", [r"Packages\s*:\s*\d+\s*([A-Za-z]+)"]),
        _field(lines, "gross_weight_kg", [r"Total\s*Gross\s*Weight\s*:?\s*([\d,]+\.\d{2})"]),
        _field(lines, "net_weight_kg", [r"Total\s*Net\s*Weight\s*:?\s*([\d,]+\.\d{2})"]),
        _field(lines, "declared_item_count", [r"(?:Total\s*)?Items\s*:\s*(\d+)"]),
    ]

    page_by_line = {line["text"]: line["page"] for line in lines}
    for index, match in enumerate(
        [match for line in lines if (match := PACKING_ROW.match(line["text"]))], start=1
    ):
        line_text = match.group(0)
        result.lines.append(
            ParsedLine(
                line_no=index,
                description=match.group(2).strip(),
                hsn=None,
                qty=dec(match.group(3)) or Decimal("0"),
                uom=match.group(4).upper(),
                unit_price=None,
                amount=None,
                gross_weight=dec(match.group(5)),
                net_weight=dec(match.group(6)),
                quote=line_text,
                page_idx=page_by_line.get(line_text, 1),
            )
        )
    if result.lines:
        result.declared_item_count = len(result.lines)
    return result


def parse_bl(lines: list[dict]) -> ParsedDocument:
    result = ParsedDocument()
    result.fields = [
        _field(lines, "supplier_name", [r"Shipper\s*:\s*(.+)"]),
        _field(lines, "consignee", [r"Consignee\s*:\s*(.+)"]),
        _field(lines, "notify_party", [r"Notify\s*Party\s*:\s*(.+)"]),
        _field(lines, "bl_number", [r"B/L\s*No\.?\s*:\s*([A-Za-z0-9/-]+)"]),
        _field(lines, "bl_date", [r"B/L\s*Date\s*:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})"]),
        _field(lines, "vessel_name", [r"Vessel\s*:\s*(.+)"]),
        _field(lines, "port_of_loading", [r"Port\s*of\s*Loading\s*:\s*(.+)"]),
        _field(lines, "port_of_discharge", [r"Port\s*of\s*Discharge\s*:\s*(.+)"]),
        _field(lines, "container_numbers", [r"Containers?\s*:\s*(.+)"]),
        _field(lines, "packages", [r"Packages\s*:\s*(\d+)"]),
        _field(lines, "gross_weight_kg", [r"Gross\s*Weight\s*:?\s*([\d,]+\.\d{2})"]),
    ]
    return result
