# Phase 6 — Export, shipment list and reports

> **Day 6** · **Estimate:** 10.5 h · **Depends on:** Phase 5
> **Exit:** an approved shipment downloads a CSV that opens correctly in Excel, the filing layout is configurable, the list is usable with real volume, and reports show where corrections come from.

## 1. Objective

Deliver the output the client actually asked for, and the operational surfaces around it: a list that survives 1,100 shipments a month, and reports that turn corrections into supplier and field intelligence.

The export is where the product meets the client's constraint — *do not change our filing software*. It is also the least forgiving surface: a CSV that looks right and imports wrong is worse than no CSV.

## 2. Tasks

| # | Task | Est. | Output |
|---|---|---|---|
| 6.1 | Export template model, seed, mapping engine | 1.0 h | Configurable column map |
| 6.2 | CSV renderer with correct encoding and quoting | 1.5 h | Byte-correct file |
| 6.3 | Preview endpoint and export screen | 1.5 h | First 20 rows + gate |
| 6.4 | Gate checklist UI and refusal handling | 1.0 h | Every blocker actionable |
| 6.5 | Export audit, idempotency, re-download | 1.0 h | Reproducible files |
| 6.6 | Shipment list: filters, search, counts, states | 2.0 h | Home screen at volume |
| 6.7 | Reports API and UI | 2.0 h | Field and supplier accuracy |
| 6.8 | Retention job | 0.5 h | 180-day deletion runs |

## 3. Export mapping

Extraction knows nothing about the filing software. A template is data:

```json
{
  "name": "Bill of Entry — default",
  "version": 1,
  "columns": [
    {"header": "Invoice No",    "source": "invoice_number",  "required": true},
    {"header": "Invoice Date",  "source": "invoice_date",    "format": "%d/%m/%Y"},
    {"header": "Supplier",      "source": "supplier_name"},
    {"header": "Buyer",         "source": "buyer_name"},
    {"header": "Currency",      "source": "currency"},
    {"header": "Incoterm",      "source": "incoterm"},
    {"header": "Description",   "source": "item.description"},
    {"header": "HSN",           "source": "item.hsn_code"},
    {"header": "Quantity",      "source": "item.qty",        "format": "0.###"},
    {"header": "Unit Price",    "source": "item.unit_price", "format": "0.0000"},
    {"header": "Amount",        "source": "item.amount",     "format": "0.00"},
    {"header": "Packages",      "source": "packages"},
    {"header": "Gross Weight",  "source": "gross_weight_kg", "format": "0.000"},
    {"header": "Container No",  "source": "container_numbers", "join": ";"}
  ]
}
```

Two levels of source: shipment-level fields repeat on every row; `item.*` fields iterate line items. This is what filing imports expect and avoids a separate line-item file.

**A1 is visible here.** Without the client's real template, this is a plausible Bill of Entry layout. The architecture guarantees the template can change without touching extraction; it cannot guarantee column compatibility with software nobody has shown us. The TDD says this; the export screen should too, in one muted line: "Template v1 — configurable".

### 3.1 Rendering

```python
def render_csv(shipment, template) -> tuple[bytes, int]:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow([c["header"] for c in template.columns])
    rows = 0
    for item in shipment.items or [None]:
        writer.writerow([resolve(c, shipment, item) for c in template.columns])
        rows += 1
    return buf.getvalue().encode("utf-8-sig"), rows
```

| Detail | Value | Reason |
|---|---|---|
| Encoding | UTF-8 **with BOM** | Excel on Windows needs it for ₹ and Chinese descriptions |
| Line endings | CRLF | RFC 4180 and Windows importers |
| Quoting | Minimal, quotes doubled | Standard; only quote when required |
| Headers | Exact template order and case | Filing imports are positional in practice |
| Numbers | Template format, not locale | Avoid `1.234,56` surprises |
| Empty values | Empty field, never `"null"` | Importers treat text "null" as data |
| Row count | Response metadata, not a trailing row | A total row breaks imports |
| Formula injection | Prefix `=`, `+`, `-`, `@` values with `'` | A description beginning `=` must not execute in Excel |

The last row is easy to forget and genuinely dangerous. Any free-text cell starting with `=`, `+`, `-` or `@` is escaped as text.

### 3.2 Preview

`GET /api/shipments/{id}/export/preview` returns:

```json
{
  "template": {"id": "...", "name": "Bill of Entry — default", "version": 1},
  "headers": ["Invoice No", "Invoice Date", "..."],
  "rows": [["INV-24811", "20/10/2026", "..."]],
  "total_rows": 3,
  "gate": {"ok": true, "blockers": []}
}
```

The preview and the file are rendered by the same function. A separate preview implementation is a bug factory — it will agree on day one and diverge by week three.

### 3.3 Gate and refusal

`POST /api/shipments/{id}/export` re-evaluates the gate server-side and returns `409` with the typed blocker list if it fails. The UI renders the same list as a checklist:

```
Before you can export:
  ⛔ 2 fields still need confirmation      [Review]
  ⚠  Weight difference not acknowledged    [Acknowledge]
  ⛔  Approval is older than the latest edit [Request approval]
```

Each item is a link to the precise field, check or action. No modal that says "cannot export" without saying why.

### 3.4 Audit and idempotency

Each export stores shipment, template version, row count, content hash, actor and timestamp, plus the file key.

- Requesting the same export again with no data change returns the stored file and a `200`, not a new row.
- Regenerating after a change creates a new export row; old rows are never deleted.
- "What did we file on 14 October" is answerable for the life of the shipment.

## 4. Shipment list

The home screen must survive 1,100 shipments a month, roughly 50 a day, with 14 users filtering constantly.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shipments                                    [+ New shipment]        │
│ [All 42] [Needs review 8] [Awaiting approval 3] [Ready 2] [Exported] │
│ Search ref or supplier…        Supplier ▾     Date ▾                  │
├──────────────────────────────────────────────────────────────────────┤
│ SHP-24811  Company B   3/3 docs   ⚠ 2 issues      Needs review  2h   │
│ SHP-24812  Company C   3/3 docs   ✓ clear         Awaiting appr 1d   │
│ SHP-24815  Company C   2/3 docs   ⛔ BL missing    Needs review  3h   │
└──────────────────────────────────────────────────────────────────────┘
```

| Decision | Value |
|---|---|
| Row height | 44 px; secondary line only when there is an issue |
| Status counts | Server-computed, not derived from the current page |
| Search | `ref`, supplier name, invoice number |
| Filters | Status, supplier, date range; encoded in the URL |
| Pagination | 50 per page, server-side |
| Default sort | Needs attention first, then updated desc |
| Empty | "No shipments match" with a clear-filters action |
| Loading | Skeleton rows, not a spinner |
| Error | Inline banner with retry, table headers retained |

"Needs attention first" is a product decision: an executive opening the list should see work, not a chronological log. Exported shipments remain reachable through the filter.

## 5. Reports

Manager-only. Two tables and four numbers, no charts in this iteration.

### 5.1 Field accuracy

```sql
SELECT f.key,
       count(*)                                        AS extracted,
       count(*) FILTER (WHERE f.status = 'CORRECTED')   AS corrected,
       round(100.0 * count(*) FILTER (WHERE f.status = 'CORRECTED') / count(*), 1)
                                                        AS correction_rate,
       round(avg(f.effective_conf), 3)                  AS avg_confidence
FROM field f
JOIN shipment s ON s.id = f.shipment_id
WHERE s.org_id = :org AND s.created_at >= :from
GROUP BY f.key
ORDER BY correction_rate DESC;
```

### 5.2 Supplier accuracy

Same shape, grouped by `supplier.name`, plus:

- documents requiring manual entry,
- average `effective_conf`,
- most common failing check code.

### 5.3 Headline numbers

| Metric | Formula |
|---|---|
| Field accuracy proxy | `1 − corrected / extracted` |
| First-pass acceptance | `confirmed_without_edit / extracted` |
| Manual-entry rate | `documents manual / documents processed` |
| Open-issue rate | `shipments with ≥1 open BLOCK / active shipments` |

### 5.4 Honesty rules

- Show raw counts next to every percentage. A supplier with 3 documents and one correction is not "33% error".
- Suppress percentages below n = 20 and show "insufficient data".
- Label the section "correction rate", not "accuracy". The system knows what humans changed; it does not know ground truth in production. True accuracy comes from the golden set in `eval/`, not from this table.

This distinction belongs on screen, not only in the TDD. A report that calls corrections "accuracy" will eventually be quoted as one.

## 6. Retention job

A Procrastinate periodic task runs daily at 02:00 IST:

1. Find shipments exported more than `org.retention_days` ago.
2. Delete document objects, page images, `words.json` and raw model responses from S3.
3. Keep rows, fields, checks, corrections, approvals, exports and audit.
4. Write `retention.purged` to the audit log with counts.
5. Respect a legal hold flag if one exists (not exposed in the UI this iteration).

Deleting objects while keeping metadata means "what did we file" remains answerable without retaining the source documents indefinitely.

## 7. API surface added

| Method | Route | Role | Notes |
|---|---|---|---|
| GET | `/api/shipments` | both | Filters, search, counts, pagination |
| GET | `/api/shipments/{id}/export/preview` | both | Headers, 20 rows, total, gate |
| POST | `/api/shipments/{id}/export` | both | 409 with blockers if gate fails |
| GET | `/api/exports/{id}/download` | both | 5-minute presigned URL |
| GET | `/api/reports/fields` | MANAGER | Date range |
| GET | `/api/reports/suppliers` | MANAGER | Date range |
| GET/PUT | `/api/settings` | MANAGER | Tolerances, retention |
| GET/POST/PUT | `/api/export-templates` | MANAGER | Column maps, versioned |

## 8. Tests

| Test | Assertion |
|---|---|
| `test_csv_bom` | File starts with `EF BB BF` |
| `test_csv_crlf` | Rows end with `\r\n`, no bare `\n` |
| `test_csv_quotes` | Value containing a comma, quote and newline round-trips |
| `test_formula_escaped` | Description `=SUM(A1)` is written as text |
| `test_header_order` | Matches the template exactly |
| `test_row_expansion` | 3 line items produce 3 rows with shipment fields repeated |
| `test_preview_matches_download` | First 20 preview rows equal the first 20 file rows |
| `test_gate_blocks_export` | 409 with typed blockers; no file created |
| `test_export_idempotent` | Same data twice → one export row |
| `test_list_counts` | Counts are server-side and match filters |
| `test_list_empty_state` | Filter with no matches renders empty state, not error |
| `test_reports_suppress_small_n` | n < 20 shows insufficient data |
| `test_retention_deletes_objects` | S3 objects gone, rows retained |
| `test_retention_respects_window` | Shipment inside window untouched |

## 9. Exit checklist

- [ ] A CSV opens in Excel with correct headers, ₹/Chinese text and no mojibake.
- [ ] LibreOffice and a second spreadsheet tool both import it cleanly.
- [ ] Template editable in settings; export reflects the change without a redeploy.
- [ ] Export blocked with a typed, clickable checklist when the gate is red.
- [ ] Re-export with no change returns the same file, not a duplicate row.
- [ ] Shipment list handles 200 seeded rows with filters in under 400 ms.
- [ ] Status counts match the filtered totals.
- [ ] Reports show correction rate by field and supplier, with raw counts.
- [ ] Small samples are suppressed, not rounded into a misleading percentage.
- [ ] Retention job runs on schedule and logs counts.

## 10. Risks and gotchas

| Risk | Mitigation |
|---|---|
| Excel mangles UTF-8 without BOM | Test with a Chinese description and a ₹ amount before sign-off |
| Template mismatch with real software | A1 disclosure; mapping is configurable; obtain the real file in week 3 |
| Formula injection in descriptions | Escape leading `= + - @` |
| Preview drifts from download | One renderer, two callers |
| Reports quote correlation as accuracy | Label "correction rate"; document the difference on screen |
| List counts slow at scale | Index `(org_id, status, updated_at)`; counts via one aggregate query |
| Retention deletes evidence too early | Default 180 days, configurable; legal hold column reserved |

## 11. Handoff

Phase 7 can assume: the full workflow exists on the live URL, the export is correct, and the list and reports are usable. Phase 7 is testing, security, documentation and demo — not new features.
