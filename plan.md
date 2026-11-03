# Customs-AI — Build Plan

**Client:** Company A, Navi Mumbai — freight forwarder and customs broker
**Product:** AI document intake, cross-document verification and human approval for import shipments
**This document plans:** the 7-day assessment slice
**Production horizon:** 6 weeks (mapped in §13)
**Status:** planning complete, build not started
**Owner:** build candidate

> Working plan. Supersedes plan v1–v3. Every assumption is labelled **A1–A10** in §15 and must be repeated in the TDD.

---

## 0. The correction that changes the shape

The previous draft is written as a six-week greenfield build. The assessment gives **seven days**. Those are different products:

- **7 days** → a vertical slice that is genuinely usable end to end: upload → extract → evidence → cross-check → human clear → approve → CSV export, on seeded data, deployed.
- **6 weeks** → the same slice hardened, evaluated on 200 real shipments, tuned with the client, piloted with 14 executives.

Section 13 maps the remaining five weeks. Everything before it plans the seven days.

Two consequences:

1. The **200-shipment / 95% evaluation cannot happen in this window**. We ship the harness and a 10-document golden set; the 200-document run is week 1 of the pilot. Claiming otherwise would be dishonest.
2. **Deploy on day 2, not day 7.** A walking skeleton in Mumbai catches region, model-access and container problems while there is still time to react.

---

## 1. Problem and product thesis

An executive retypes data that already exists in a PDF, three times, then a senior resolves doubts over WhatsApp. 3% of shipments carry an error into filing.

**The product is not extraction.** Any vision model reads an invoice. The product is the **trust loop**:

> upload → extract with evidence → cross-check three documents → gate on uncertainty → human clears → manager approves → export → log the correction

- The **cross-check engine** is the moat.
- The **review screen** is where the value is realised.
- The **model is a swappable adapter**.

Design target: 45 minutes → under 15, and errors surfaced before filing rather than after.

---

## 2. Scope

### 2.1 In the 7-day slice

| Area | Included |
|---|---|
| Shipment list | Status chips, supplier/date filter, search, counts, empty/loading/error states |
| Create + upload | Invoice, packing list, B/L; drag-drop; type detection with override; late-document upload |
| Extraction | Gemini vision, per-document schema, per-field evidence, confidence |
| Review | Document beside fields, page navigation, evidence panel, inline edit, correction log |
| Cross-checks | 11 rules, line-item matching, WARN/BLOCK, acknowledgement with reason |
| Approval | Manager-only; rejection with note; BLOCK override with written reason |
| Export | CSV in configurable filing layout, preview before download, hard gate |
| Reports | Field accuracy, supplier accuracy, first-pass acceptance — basic |
| Auth | Two roles, org scoping, sessions, audit |
| Eval | 10-document golden set harness, per-field accuracy output |

### 2.2 Out

Customs portal filing · HSN classification · duty calculation · importer portal · WhatsApp · payments · notifications beyond a mocked email · multi-branch tenancy.

### 2.3 Deferred, with a trigger

| Item | Trigger to build |
|---|---|
| PaddleOCR fallback | Eval shows `NONE`-evidence rate on scans > 15% |
| OpenCV deskew | Pillow orientation fix proves insufficient on > 10% of samples |
| XLSX export | Client provides the actual import template |
| Many-to-one line aggregation | Pilot shows aggregated packing lists are common |
| Supplier trends, charts | After the review loop is measured |

---

## 3. Architecture

```
Browser (React SPA)
   │  same origin · httpOnly session · CSRF token
   ▼
FastAPI (uvicorn) ── /api + built SPA from /static
   │
   ├── PostgreSQL (Mumbai)   ← data + Procrastinate queue
   ├── S3 ap-south-1         ← originals, page PNGs, raw responses
   └── enqueue extraction
             │
             ▼
     Worker (same image, second CMD)
       validate → PyMuPDF → Pillow → Gemini → Pydantic
       → evidence → checks → persist
             │
             ▼
     Postgres → SPA polls status
```

**Modular monolith, one image, two entrypoints.** No microservices: six weeks, one organisation, 14 users. The split that matters is web vs worker, and that is a `CMD` difference.

### 3.1 Stack

| Component | Choice | Why |
|---|---|---|
| API | FastAPI + Pydantic v2 | Schema doubles as the model's output constraint and the validator |
| ORM | SQLAlchemy 2.0 async + Alembic | Migrations and transactions matter for audit data |
| DB | PostgreSQL | Genuinely relational; also hosts the job queue |
| Queue | Procrastinate | No Redis, retries, one image |
| AI | **Vertex AI Gemini, asia-south1** | Enterprise terms, no training, region-pinned |
| PDF | PyMuPDF | Render pages, native text, exact word boxes |
| Images | **Pillow only** | EXIF rotate, downscale, re-encode. No OpenCV in v1 |
| OCR | **None in v1** | Fallback only, gated by eval (A5) |
| Storage | S3 ap-south-1 (MinIO locally) | India residency; R2 only for synthetic public demo |
| Web | React + TypeScript + Vite + Tailwind + TanStack Query | The review screen is the product |
| Deploy | Docker → App Runner ap-south-1 (or Fly `bom`) | One image; no hand-built Nginx/TLS |
| Tests | pytest, httpx, Playwright | |

### 3.2 Why Vertex, not the Developer API

| | Developer API | Vertex AI |
|---|---|---|
| Free tier | **Trains on your data** | n/a |
| Paid tier | No training; abuse logging, possible human review | No training, enterprise terms |
| Region | Global | `asia-south1` (Mumbai) serves Gemini |
| Suitable for client documents | No | Yes, with DPA |

Hard requirement for real documents. The Developer API is acceptable **only** for the synthetic public demo, and the TDD must say so in one sentence.

Also: the Files API retains uploads for 48 hours. It is a transfer mechanism, never storage. Originals live in S3; small PDFs go inline.

**A3/A4:** Vertex needs a billing-enabled GCP project, and the exact model must be confirmed available in `asia-south1`. Both are day-1 checks. If the region fails, fall back to `asia-southeast1` and **disclose the change** — do not silently claim Mumbai.

---

## 4. Data model

```
org(id, name, weight_tol_pct, value_tol, monthly_ai_cap_paise)
user(id, org_id, email, password_hash, role EXEC|MANAGER, active)

supplier(id, org_id, name, country, aliases[])
shipment(id, org_id, ref, supplier_id, status, incoterm, currency,
         created_by, approved_by, approved_at)
document(id, shipment_id, type INVOICE|PACKING|BL, storage_key, sha256,
         page_count, status, error)
page(id, document_id, idx, image_key, width_px, height_px,
     words_key NULL, source TEXT|NONE)

extraction_run(id, document_id, model, prompt_version, schema_version,
               tokens_in, tokens_out, cost_paise, latency_ms,
               raw_response_key, status, error)

field(id, shipment_id, document_id, extraction_run_id, key,
      value_raw, value_norm, model_conf, effective_conf,
      verification_level, page_idx, bbox NULL, quote,
      status SUGGESTED|CONFIRMED|CORRECTED, updated_by, updated_at)
line_item(id, shipment_id, line_no, description_raw, description_en NULL,
          hsn, qty, uom, unit_price, amount, matched_line_id NULL)

check(id, shipment_id, code, severity PASS|WARN|BLOCK, message,
      field_keys[], params, rule_version,
      resolved_by, resolved_reason, resolved_at)
correction(id, field_id, old_value, new_value, actor_id, reason, at)
approval(id, shipment_id, actor_id, decision APPROVE|REJECT, note, at)
export(id, shipment_id, template_id, row_count, content_hash,
       csv_key, created_by, at)
audit_event(id, org_id, actor_id, action, entity, entity_id, meta, at)
export_template(id, org_id, name, column_map, version)
```

### 4.1 Status machines — kept separate

```
document:  UPLOADED → QUEUED → PROCESSING → EXTRACTED
                                     ├──→ FAILED
                                     └──→ NEEDS_MANUAL_ENTRY

shipment:  DRAFT → EXTRACTING → NEEDS_REVIEW → AWAITING_APPROVAL
                                             → READY → EXPORTED
```

A shipment with two good documents and one failure is `NEEDS_REVIEW`, never `EXTRACTED`. One shipment-level status cannot represent per-document truth; the list view reads shipment status, the review reads document status.

### 4.2 Idempotency

- `UNIQUE (document_id, content_sha256, prompt_version, schema_version)` on `extraction_run`.
- Worker writes delete-then-insert per document **inside one transaction** — a retry cannot duplicate fields.
- `UNIQUE (shipment_id, template_id, content_hash)` on `export` — double-click cannot produce two files.
- Upload dedupe on `(org_id, sha256)` — the same PDF emailed twice is one document, not two.

### 4.3 Why `extraction_run` exists

Without it you cannot answer: which model read this, with which prompt, at what cost, and what did it originally say before a human fixed it? It is the table that makes accuracy a measurement rather than a claim, and it is what the eval harness joins against.

---

## 5. Document pipeline

```
File validation        magic bytes, ≤25 MB, ≤40 pages, not encrypted, sha256
      ↓
Render                 PyMuPDF → 2000px-long-edge PNG per page (cached by hash)
      ↓
Text layer             text PDFs: PyMuPDF words (exact boxes)
                       scans: none — evidence capped at CLAIMED
      ↓
Image pass             Pillow: EXIF rotate, downscale, JPEG q85
      ↓
Extraction             Gemini, per-document-type response schema
      ↓
Pydantic               coerce, reject, repair once
      ↓
Evidence               locate quote / value → verification level
      ↓
Checks                 deterministic rules + line matching
      ↓
Persist                fields, checks, run, audit — one transaction
```

**Three schemas, not one:** invoice, packing list, bill of lading. A union schema is a pile of nullables and makes validation weaker. Full field lists in Appendix B.

### 5.1 Evidence model

```
verification_level
  EXACT      quote found verbatim in native PDF text          evidence 1.0
  CONTAINED  value appears inside the model's quote (scan)    evidence 0.7
  CLAIMED    quote present, cannot be independently verified  evidence 0.5
  NONE       no quote, or quote not locatable                 evidence 0.0

format_score
  1.0 valid · 0.5 coercible · 0.0 invalid

effective_conf =
  0                                      if evidence = 0 or format = 0
  min(evidence, format) × (0.75 + 0.25 × model_conf)   otherwise
```

**The format term is not optional.** A malformed date that literally appears in the PDF would otherwise score 0.975. Format is a gate, not a modifier. This is the correction to the previous draft's formula.

The model can never lift a field above its evidence. That sentence is the whole trust design.

| Score | UI | Meaning |
|---|---|---|
| ≥ 0.85 | neutral | Acceptable unless a check names it |
| 0.55–0.85 | amber | Must be confirmed |
| < 0.55 | red | Must be corrected or manually entered |

**Any field named by an open WARN/BLOCK is flagged regardless of score.** A confident number contradicted by the packing list is still wrong.

These are operational scores, not calibrated probabilities. Say that in the TDD.

### 5.2 Failure modes — designed, not discovered

| Failure | Behaviour |
|---|---|
| Invalid JSON | One repair pass → still invalid → `NEEDS_MANUAL_ENTRY`, reason shown |
| Provider timeout / 429 | Exponential backoff ×3 → manual entry; never a spinner forever |
| Unreadable page | That page goes manual; other pages and documents proceed |
| Quote not locatable | `CLAIMED` or `NONE`, never a fabricated highlight box |
| Missing required document | Shipment `NEEDS_REVIEW` with an explicit BLOCK — missing ≠ passed |
| Model returns extra fields | Dropped; schema is closed |
| Duplicate upload | Deduped by hash, linked, not duplicated |
| Worker crash mid-write | Transaction rolls back; job retried; no partial fields |
| Spend cap reached | Extraction queued with a clear org-level error; no silent failure |

---

## 6. Cross-document checks

Pure functions in `checks/rules/`, tolerances from `org`, deterministic, replayable after every correction.

| # | Check | Severity | Cleared by |
|---|---|---|---|
| 1 | line amount = qty × unit price (±0.01) | BLOCK | Exec corrects |
| 2 | total = Σ lines + freight + insurance − discount (±0.01) | BLOCK | Exec corrects |
| 3 | declared line count = returned line count | BLOCK | Exec corrects / re-extract |
| 4 | invoice qty = packing-list qty on matched lines | BLOCK | Exec corrects |
| 5 | gross weight invoice / PL / BL within ±0.5% | **WARN** | Exec acknowledges + reason |
| 6 | packages equal across all three documents | BLOCK | Exec corrects |
| 7 | container numbers: ISO 6346 check digit, duplicates, count vs B/L | BLOCK | Exec corrects |
| 8 | party match (buyer/consignee/notify) similarity ≥ 0.90 | WARN | Exec confirms |
| 9 | currency consistent; ISO 4217 valid | BLOCK | Exec corrects |
| 10 | Incoterm in Incoterms 2020; freight terms agree | WARN | Exec confirms |
| 11 | dates: ≤ today, ≤ B/L date, ≤ 90 days old | WARN | Exec confirms |
| 12 | UoM normalisation (lb→kg × 0.45359237) | informational | — |
| 13 | missing required document | BLOCK | Upload / manager override |

### 6.1 Line matching

```
normalise(description):
  lowercase · strip punctuation · expand DN, SS, PCS, CTN, KG
  · remove unit tokens · collapse whitespace

score(a,b) =
  0.5 × (exact part-no / HSN match ? 1 : 0)
+ 0.3 × token_set_ratio(a,b)/100
+ 0.2 × (quantities equal ? 1 : 0)

accept ≥ 0.75, greedy one-to-one
ambiguous (two candidates above threshold) → flag, do not guess
leftovers:
  invoice line with no PL line  → BLOCK "not on packing list"
  PL line with no invoice line  → WARN  "packed but not invoiced"
```

Many-to-one aggregation is **not** in v1. v1 fails loudly rather than silently mis-matching.

### 6.2 The gate

```
exportable =
      all required documents are EXTRACTED
  AND every required field is CONFIRMED or CORRECTED
  AND no open BLOCK
  AND every WARN acknowledged with a reason
  AND shipment.status = READY   (manager approved)
  AND at least one manager approval newer than the last field edit
```

Any edit after approval returns the shipment to `NEEDS_REVIEW` and voids the approval. That single rule prevents the classic "approved, then quietly changed" hole.

The export screen is a checklist. Each unmet item links to the exact field or document. No dead end, no modal maze.

**D1:** executive may acknowledge a WARN with a reason; only a manager may override a BLOCK, with a written reason, and the original failed check is preserved.

---

## 7. UI

### 7.1 Screens — 8 routes

| # | Route | Purpose |
|---|---|---|
| 1 | `/login` | Email + password, role-aware landing |
| 2 | `/shipments` | **Home.** List, status filter chips, search, supplier filter, "3 fields need you" |
| 3 | `/shipments/new` | Create + three drop slots, auto-type detection, progress |
| 4 | `/shipments/:id/review` | **The product.** Viewer ↔ fields, evidence, checks, edits |
| 5 | `/shipments/:id` | Status timeline, documents, audit; manager approval actions |
| 6 | `/shipments/:id/export` | Column-map preview, gate checklist, CSV download |
| 7 | `/reports` | Field and supplier accuracy, first-pass acceptance (manager) |
| 8 | `/settings` | Tolerances, templates, users (manager) |

Extraction progress is a state inside `/shipments/:id`, not a separate route.

### 7.2 Review screen

```
┌──────────────────────────────────────────────────────────────────┐
│ SHP-24811 · Company B            NEEDS REVIEW    [Submit] [···]  │
├──────────────────────────┬───────────────────────────────────────┤
│  [1] [2] [3]   −  100%   │  INVOICE        ⌄                      │
│                          │  Invoice no.   INV-24811       ✓       │
│   ┌──────────────────┐   │  Date          2026-10-20      ✓       │
│   │                  │   │  Currency      USD             ✓       │
│   │   page image     │   │  Incoterm      FOB             ✓       │
│   │   ▢ highlight    │   │  Gross wt      3,120 kg        ✓       │
│   │                  │   │                                        │
│   └──────────────────┘   │  LINE ITEMS                   3 / 3    │
│                          │  LED panel 40W  2400  6.80   16,320  ✓ │
│  [Source: p.1 "Gross    │                                        │
│   weight 3120.00 KGS"]   │  CHECKS                         2 open │
│                          │  ⚠ Weight 3,120 vs 3,165  +1.44% →    │
│                          │  ⛔ Packages missing on B/L            │
├──────────────────────────┴───────────────────────────────────────┤
│  [✓ Confirm all high-confidence]   [Submit for approval]         │
└──────────────────────────────────────────────────────────────────┘
```

- One-click jump from field → page → rectangle when `EXACT`; page badge when not.
- Evidence quote always visible under the active field.
- `Tab` / `Shift-Tab` between fields, `Enter` confirm, `Cmd+Z` undo, `J`/`K` next/previous document, `1/2/3` switch document.
- Unsaved edits are impossible — every change persists immediately and is undoable from the audit trail.
- "Show only uncertain" toggle for the 15-minute target.

### 7.3 Design system

| Token | Value |
|---|---|
| Canvas | `#FAFAF8` warm off-white |
| Surface | `#FFFFFF` |
| Ink | `#14161A` |
| Muted | `#6B6F76` |
| Border | `#E6E4DE` |
| Accent | `#0F6B5C` deep teal — actions and focus only |
| Warn | `#B45309` on `#FEF3C7` |
| Block | `#B42318` on `#FEE4E2` |
| Confirm | `#067647` used sparingly, icons not fills |

- Type: Inter (or Geist), 14 px base, 12 px meta, **tabular numerals** on every money and weight value.
- 8 px rhythm, 4 px base unit, 6 px radius, no shadows except dialogs.
- Table rows 44 px; review field rows 40 px. Dense but breathable.
- **Do not paint the screen green.** Accepted fields are neutral. Only uncertainty and failure carry colour — otherwise six minor warnings look like a Christmas tree and the executive stops seeing them.
- Mobile: list and approval are responsive; the review screen is desktop-first with a stacked fallback (viewer above fields), because the brief says desktop use.

### 7.4 States

Every list and panel ships with **loading** (skeleton, not spinner), **empty** (illustration-free, one sentence, one action), and **error** (what happened, what to do, retry). No screen is allowed to render a blank div.

---

## 8. Roles

| Capability | Executive | Manager |
|---|---|---|
| Create shipment, upload | ✓ | ✓ |
| Review, correct, confirm | ✓ | ✓ |
| Acknowledge WARN with reason | ✓ | ✓ |
| Submit for approval | ✓ | ✓ |
| Approve / reject | — | ✓ |
| Override BLOCK with reason | — | ✓ |
| Export READY shipment | ✓ | ✓ |
| Reports | — | ✓ |
| Settings, templates, users | — | ✓ |

Enforced in FastAPI dependencies, not just hidden in React. Cross-org access returns **404**, not 403.

---

## 9. Security, DPDP, hosting

**Application**
- Argon2id (`pwdlib`), server-side sessions table, httpOnly + SameSite=Lax, CSRF double-submit on mutations.
- Org scoping enforced by a single query helper; a test asserts every router uses it.
- Immutable `correction`, `approval`, `audit_event`; no hard delete of reviewed shipments.
- Rate limits on login, upload and extraction.

**Files**
- Magic-byte check, ≤25 MB, ≤40 pages, reject encrypted PDFs, sha256 dedupe.
- Private buckets, 5-minute presigned URLs, no public objects ever.
- Optional ClamAV pass — documented, off by default in the demo.

**Prompt injection**
- Documents are untrusted input. The extraction model has **no tools**, output must satisfy a closed schema, unknown fields are dropped, strings are escaped on render, and a human gate precedes export.
- A test fixture contains a document instructing the model to change a total; the assertion is that the schema is unchanged and the field is flagged.

**DPDP**
- Mumbai region end to end; importer contacts minimised before any model call.
- Retention 180 days post-export, scheduled deletion job, delete-on-request endpoint with audit.
- Vertex DPA and no-training terms captured in the TDD; if any processing leaves India, it is disclosed by region.

**Deployment**
- One Docker image, two entrypoints; App Runner ap-south-1 or Fly `bom`.
- Postgres on RDS Mumbai or Supabase Mumbai (paid tier — the free tier pauses, which breaks a demo link).
- Secrets in the platform store. `.env.example` only. No keys in git.

---

## 10. Testing and evaluation

| Layer | What | Count | Tool |
|---|---|---|---|
| Rules | exact, boundary, ±tolerance, lb↔kg, multi-currency, missing doc | 45+ | pytest |
| Normalisation | `03/11/26` vs `11/03/26`, currencies, Incoterms, UoM | 20 | pytest |
| Line matching | 1:1, unmatched both ways, ambiguous, near-duplicate text, qty mismatch | 12 | pytest |
| Evidence | EXACT / CONTAINED / CLAIMED / NONE, quote absent, wrong page | 10 | pytest |
| Confidence | format gate, evidence cap, model cannot inflate | 8 | pytest |
| Idempotency | worker twice → same rows; export twice → one file | 4 | pytest |
| Authz | exec 403 on approve/override/settings; cross-org 404 | 8 | httpx |
| Injection | malicious document → schema intact, field flagged | 2 | pytest |
| Export | header order, gating, CSV quoting, UTF-8 BOM, row count | 6 | pytest |
| E2E | happy path to CSV, blocked path, manual-entry path | 3 | Playwright |

**Golden set:** 10 documents with hand-verified ground truth. `eval/` runs the real pipeline and prints per-field precision/recall, evidence-NONE rate, and a confusion list. It runs on **day 4**, because its result decides whether OCR fallback is needed — day 6 is too late to act on it.

Metrics the report must show, and the TDD must define:

```
field accuracy        = correct / ground-truth fields
first-pass acceptance = fields confirmed without edit / extracted fields
correction rate       = corrected fields / extracted fields, by key and supplier
discrepancy recall    = true mismatches flagged / all true mismatches
false-positive rate   = WARN+BLOCK raised on agreeing documents
```

The last two are separate from extraction accuracy: correct values can still be compared incorrectly, and that is the failure the client actually pays for.

---

## 11. Seed data

Generated as **real PDFs**, not seed JSON. Nine shipments:

| Ref | Supplier | Demonstrates |
|---|---|---|
| SHP-24811 | Company B, China | **Headline.** 3,120 vs 3,165 vs B/L 3,160 → weight WARN; clean line-item match |
| SHP-24812 | Company C, Sweden | Clean EUR pass, one-click accept |
| SHP-24813 | Company B | Skewed phone photo of packing list → CLAIMED evidence |
| SHP-24814 | Company D, China | Bilingual CN/EN invoice, descriptions kept verbatim |
| SHP-24815 | Company C | B/L missing → BLOCK, upload later to clear |
| SHP-24816 | Company E | Unreadable page → manual entry, rest proceeds |
| SHP-24817 | Company B | Package count mismatch 120 vs 118 → BLOCK |
| SHP-24818 | Company C | Exported — shows history and CSV |
| SHP-24819 | Company D | Awaiting approval — shows manager queue |

**Assumption A2:** the brief supplies no B/L for SHP-24811. We synthesise a realistic one so the three-way check — the hard part — is actually visible; the missing-document state is demonstrated separately on SHP-24815.

Seed users: `exec@demo` / `manager@demo`. Seed ~30 correction records so Reports is not empty on first load.

**Demo, three minutes:** open SHP-24811 → weight WARN already visible with both figures and 1.44% → click it, both source rectangles light up → acknowledge with reason → packages BLOCK resolves after correcting → submit → manager approves → export preview → CSV → Reports shows the correction attributed to supplier and field.

---

## 12. Seven-day plan

| Day | Build | Done when |
|---|---|---|
| **1** | Repo, compose (Postgres + MinIO), schema, Alembic, auth, roles, org scoping, design tokens, app shell | Login works both roles; empty list renders; tests run |
| **2** | Upload → S3 → document rows → Procrastinate → first real Gemini call → raw JSON; **deploy** | Three PDFs uploaded, job runs, raw response stored, app live on a Mumbai URL |
| **3** | Per-type schemas, PyMuPDF text layer, Pillow pass, evidence model, `extraction_run`, failure paths | Seeded shipment shows fields with levels; broken doc lands in manual entry |
| **4** | Review UI: viewer, overlays, evidence panel, inline edit, correction log, audit; **10-doc eval** | Executive can review and correct without touching JSON; eval prints accuracy table |
| **5** | Checks, line matching, WARN/BLOCK, acknowledgement, manager approval, gate | SHP-24811 blocks on weight until cleared; exec cannot approve; edit-after-approval voids it |
| **6** | CSV export + preview + template map, list states, reports, retention job | Approved shipment downloads a correct CSV; reports show corrections |
| **7** | E2E, security pass, prompt-injection fixture, TDD, deployment.md, demo rehearsal, buffer | All three E2E paths green; docs submitted |

**Protected slice:** review + checks + export. Reports and settings are the first to give.

**Deploy daily from day 2.** Not once, at the end.

---

## 13. Production roadmap — the remaining five weeks

The seven-day slice is roughly weeks 1–2 of the client's six-week build. The rest buys trust, not features:

| Week | Focus | Exit criterion |
|---|---|---|
| 3 | Client inputs: real filing template (A1), 200 historical shipments with ground truth | Export opens in the actual filing software; eval harness runs at scale |
| 4 | Extraction tuning on real scans and bilingual documents; OCR fallback if eval demands it | ≥95% field accuracy on the dev split |
| 5 | Shadow pilot: 14 users, real shipments, no filing dependency; measure time and corrections | Median review under 15 minutes |
| 6 | Fix, train, hand over, instrument amendment rate | Signed-off pilot; baseline for the 3-month amendment metric |

The amended-BoE reduction cannot be proven in six weeks. It is measured over three months of live filing, and the TDD should say so.

---

## 14. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Vertex/GCP access or regional model unavailable | Blocks day 2 | Day-1 check; Developer API for synthetic demo; disclose region change |
| Filing template unknown | Export unverifiable | Configurable map + seeded plausible layout; **A1** stated plainly |
| Gemini drops a table row silently | Wrong line items | Line-count check + total reconciliation → BLOCK |
| False-positive checks erode trust | Product abandoned | Evidence-first copy, WARN≠BLOCK, tolerances configurable, 1.44% demo shows nuance |
| Scans produce no verifiable evidence | Low confidence everywhere | CLAIMED tier + manual entry; OCR only when eval proves the need |
| Two-language drift (Python/TS) | Stale client | Types generated from OpenAPI; CI fails on diff |
| 7-day overrun | Incomplete submission | Protected slice; reports/settings cut first; deploy day 2 |
| AI spend runaway | Cost surprise | Per-org monthly cap, per-document retry ceiling, page cache by hash |

---

## 15. Assumptions

| # | Assumption | If wrong |
|---|---|---|
| **A1** | Filing software's import layout is unavailable; column names are configurable | Plug in real template at week 3 — mapping layer already isolates it |
| **A2** | SHP-24811 needs a synthesised B/L to demonstrate three-way checks | Drop to two-way; weaker demo, same code |
| **A3** | A billing-enabled GCP project exists by day 1 | Demo on paid Developer API with synthetic data only; Vertex documented as production path |
| **A4** | The chosen Gemini model is served from `asia-south1` | `asia-southeast1` fallback, disclosed in TDD |
| **A5** | Documents are English or Simplified Chinese | Additional languages need prompt work; schema unchanged |
| **A6** | B/L often arrives after invoice and packing list | Late upload is a first-class flow, not an error |
| **A7** | Weight tolerance ±0.5%, value ±0.01, quantity exact | Values are org config, not constants |
| **A8** | All three documents are required before approval | Per-importer requirements are a settings table later |
| **A9** | CSV is sufficient for the assessment; XLSX when the template arrives | XLSX is one `openpyxl` function behind the same mapping |
| **A10** | One organisation, two roles; multi-tenant columns present but one seeded org | Schema already carries `org_id` everywhere |

---

## 16. Cut list and next

**Cut from the slice:** charts, supplier trend lines, Excel formatting, importer portal, WhatsApp, HSN assist, duty, portal filing, email notifications, bulk import.

**Next, in order:**
1. 200-shipment eval on real documents (the only honest route to "95%").
2. Real filing template → XLSX.
3. Duplicate-invoice and repeat-shipment detection.
4. Supplier document checklists — prevent the missing-B/L case upstream.
5. OCR fallback, if and only if the eval says so.
6. Audit export for customs queries.

---

## 17. Open decisions

| # | Decision | Default if unanswered |
|---|---|---|
| D1 | Manager-only BLOCK override with written reason | Yes |
| D2 | Production storage S3 ap-south-1; R2 only for synthetic demo | Yes, disclosed in TDD |
| D3 | Filing template configurable, seeded with plausible Shipping Bill layout | Yes, labelled A1 |
| D4 | Vertex primary; Developer API only for synthetic demo | Yes |

---

## Appendix A — Confidence and check ownership, one page

- Extraction proposes. Evidence caps. Format gates. Checks contradict. Human decides. Manager approves. Export refuses until all four agree.
- A high score never suppresses a check.
- A missing document is a failure, not a pass.
- A correction is never destructive: old value, new value, actor, reason, timestamp.
- An approval is invalidated by any later edit.

## Appendix B — Extraction schemas

**Invoice:** supplier_name, buyer_name, invoice_number, invoice_date, currency, incoterm, items[{description, hsn_code, quantity, uom, unit_price, total_amount}], freight, insurance, discount, other_charges, invoice_total, gross_weight_kg, net_weight_kg, packages, package_type, container_numbers[].

**Packing list:** supplier_name, buyer_name, invoice_reference, packages, package_type, items[{description, quantity, gross_weight_kg, net_weight_kg}], total_gross_weight_kg, total_net_weight_kg, container_numbers[].

**Bill of lading:** shipper, consignee, notify_party, bl_number, bl_date, vessel_name, voyage, port_of_loading, port_of_discharge, container_numbers[], packages, gross_weight_kg, measurement_cbm, freight_terms.

Every field carries `quote` and `page` in the model response. Fields absent from a document are explicitly `null`, never guessed.
