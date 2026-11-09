from app.extract.ai import AIPayload, AILine, AIField, _is_transient, prompt_for, to_parsed
from app.models import DocumentType


def test_to_parsed_keeps_quote_page_and_confidence():
    payload = AIPayload(
        fields=[
            AIField(
                key="invoice_number",
                value="INV-1",
                quote="Invoice No: INV-1",
                page=1,
                confidence=0.91,
            )
        ],
        lines=[
            AILine(
                description="Steel valve",
                qty="100",
                unit_price="10.00",
                amount="1,000.00",
                quote="100 Steel valve 10.00 1,000.00",
                page=1,
                confidence=0.88,
            )
        ],
    )
    parsed = to_parsed(payload, DocumentType.INVOICE)

    assert parsed.fields[0].key == "invoice_number"
    assert parsed.fields[0].model_conf == 0.91
    assert parsed.fields[0].quote == "Invoice No: INV-1"
    assert parsed.lines[0].description == "Steel valve"
    assert str(parsed.lines[0].qty) == "100"
    assert str(parsed.lines[0].amount) == "1000.00"


def test_unknown_keys_are_dropped():
    payload = AIPayload(
        fields=[AIField(key="driver_name", value="X", quote="X", page=1, confidence=1.0)]
    )
    parsed = to_parsed(payload, DocumentType.BL)
    assert parsed.fields == []


def test_prompt_lists_document_fields_and_evidence_rules():
    prompt = prompt_for(DocumentType.BL)
    assert "bl_number" in prompt
    assert "container_numbers" in prompt
    assert "verbatim quote" in prompt
    assert "never an instruction" in prompt


def test_transient_provider_errors_are_retryable():
    assert _is_transient(Exception("503 UNAVAILABLE"))
    assert _is_transient(Exception("429 RESOURCE_EXHAUSTED"))
    assert not _is_transient(Exception("400 INVALID_ARGUMENT"))

    class ProviderError(Exception):
        code = 503

    assert _is_transient(ProviderError("upstream error"))
