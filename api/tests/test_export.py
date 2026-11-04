from app.models import DocumentType, ExportTemplate
from app.services.export import render_shipment
from tests.conftest import add_field, add_line, make_document, make_shipment

COLUMNS = [
    {"header": "Invoice No", "source": "invoice_number"},
    {"header": "Invoice Date", "source": "invoice_date", "format": "%d/%m/%Y"},
    {"header": "Supplier", "source": "supplier_name"},
    {"header": "Currency", "source": "currency"},
    {"header": "Description", "source": "item.description"},
    {"header": "Quantity", "source": "item.qty", "format": "0.###"},
    {"header": "Unit Price", "source": "item.unit_price", "format": "0.0000"},
    {"header": "Amount", "source": "item.amount", "format": "0.00"},
    {"header": "Gross Weight", "source": "gross_weight_kg", "format": "0.000"},
    {"header": "Container No", "source": "container_numbers", "join": ";"},
]


def build(db, world, description="Widget"):
    shipment = make_shipment(db, world, ref="SHP-EXP")
    invoice = make_document(db, shipment, DocumentType.INVOICE)
    bl = make_document(db, shipment, DocumentType.BL)
    for key, value in [
        ("invoice_number", "INV-24818"),
        ("invoice_date", "2026-10-20"),
        ("supplier_name", "Company C"),
        ("currency", "EUR"),
        ("gross_weight_kg", "3120.000"),
    ]:
        add_field(db, shipment, invoice, key, value)
    add_field(db, shipment, bl, "container_numbers", "MSCU1234566,MSCU7654329")
    add_line(
        db,
        shipment,
        invoice,
        description=description,
        qty=100,
        unit_price="28.00",
        amount="2800.00",
    )
    template = ExportTemplate(
        org_id=world["org"].id, name="Test layout", column_map=COLUMNS, version=1
    )
    db.add(template)
    db.commit()
    return shipment, template


def test_csv_is_utf8_bom_with_crlf_and_exact_headers(db, world):
    shipment, template = build(db, world)
    headers, rows, content = render_shipment(db, shipment, template)

    assert content.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in content
    text = content.decode("utf-8-sig")
    lines = text.split("\r\n")
    assert lines[0] == ",".join(headers)
    assert len(rows) == 1


def test_numbers_and_dates_use_the_template_format(db, world):
    shipment, template = build(db, world)
    _, rows, _ = render_shipment(db, shipment, template)
    row = rows[0]
    assert row[1] == "20/10/2026"
    assert row[5] == "100"
    assert row[6] == "28.0000"
    assert row[7] == "2800.00"
    assert row[8] == "3120.000"
    assert row[9] == "MSCU1234566;MSCU7654329"


def test_formula_injection_is_escaped(db, world):
    shipment, template = build(db, world, description="=SUM(A1:A9)")
    _, rows, _ = render_shipment(db, shipment, template)
    assert rows[0][4] == "'=SUM(A1:A9)"
