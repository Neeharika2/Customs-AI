# Phase 2 — Ingestion, rendering and first deploy

> **Day 2** · **Estimate:** 10 h · **Depends on:** Phase 1
> **Exit:** three PDFs upload through the browser, pages render, a worker job completes, and the app is live on a Mumbai URL.

## 1. Objective

Get bytes from a browser into private storage, turn a PDF into page images and a text layer, and prove the whole path works on the deployed environment. This phase deliberately stops short of structured extraction — the goal is a reliable pipe, not intelligence.

**Deploy at the end of this phase.** Everything after this point is iterated against a live URL. Deploying on Day 7 is the most common way a good build fails.

## 2. Tasks

| # | Task | Est. | Output |
|---|---|---|---|
| 2.1 | Create-shipment endpoint and minimal upload screen | 1.0 h | Draft shipment with three slots |
| 2.2 | Presigned upload, magic-byte validation, SHA-256, dedupe | 2.0 h | Files land in S3; duplicates rejected |
| 2.3 | Document confirm and per-document status | 1.0 h | `UPLOADED → QUEUED` |
| 2.4 | Procrastinate app, schema, worker entrypoint, retry policy | 1.5 h | Jobs execute and retry |
| 2.5 | PyMuPDF render + `words.json` extraction | 2.0 h | Page images and word boxes stored |
| 2.6 | Pillow normalisation for images and photos | 0.5 h | Correct orientation, bounded size |
| 2.7 | Status polling endpoint and upload progress UI | 0.5 h | Live document states |
| 2.8 | **Deploy** and end-to-end smoke test on the live URL | 1.5 h | Working URL |

## 3. Technical detail

### 3.1 Upload flow

```
1. Client hashes the file (Web Crypto SHA-256) and asks for a presigned PUT.
2. API checks: type allowed, size ≤ MAX_UPLOAD_MB, org quota, duplicate.
3. API returns a presigned URL valid for 10 minutes, keyed
   org/{org}/shipment/{shipment}/doc-{uuid}.{ext}
4. Client PUTs directly to S3 with Content-Type and x-amz-checksum-sha256.
5. Client calls confirm. API HEADs the object, verifies size, checksum and
   magic bytes, then creates the document row and enqueues a job.
```

The API never proxies file bytes. At 25 MB per scan and 10 concurrent uploads, proxying would put avoidable pressure on a small container and would make upload latency a function of application memory.

### 3.2 Validation rules

| Rule | Value | Failure |
|---|---|---|
| Allowed types | PDF, JPEG, PNG (magic bytes) | 415 with the detected type |
| Max size | 25 MB | 413 before the upload URL is issued |
| Max pages | 40 | 422 after render, document `FAILED` |
| Encrypted PDF | Reject | 422 "password-protected; upload an unlocked copy" |
| Zero-byte / truncated | Reject at HEAD | 422 |
| Duplicate on shipment | Reject with existing document id | 409 `duplicate_document` |
| Filename | Sanitised, never used as the storage key | — |

Magic bytes are checked **server-side on confirm**, not trusted from the browser. Client-side hashing is an optimisation to enable dedupe; the authoritative checksum is the S3 checksum recorded on the object.

### 3.3 Rendering

```python
# api/app/extract/render.py
DPI_TARGET = 200
MAX_EDGE_PX = 2000

with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
    if doc.is_encrypted:
        raise EncryptedPDF()
    if doc.page_count > settings.max_pages:
        raise TooManyPages()
    for idx, page in enumerate(doc):
        pix = page.get_pixmap(dpi=DPI_TARGET)
        # resize so long edge <= MAX_EDGE_PX
        image_key = store.put_jpeg(pix.tobytes("jpeg", jpg_quality=88))
        words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,word_no
        words_key = store.put_json(normalise_boxes(words, page.rect))
```

`words.json` stores normalised coordinates in the range 0–1, so the UI can scale the overlay to any rendered width without recomputation:

```json
{ "page": 1, "width": 1654, "height": 2339,
  "words": [ { "t": "Gross", "x0": 0.12, "y0": 0.44, "x1": 0.19, "y1": 0.46 } ] }
```

For scanned pages, `page.get_text("words")` returns nothing. The page is still rendered, `source` is set to `NONE`, and `words_key` stays null. The UI must not claim a highlight it does not have.

### 3.4 Image normalisation

Photos arrive with EXIF orientation and often at 12 MP. Pillow fixes both:

```python
from PIL import Image, ImageOps
img = Image.open(BytesIO(raw))
img = ImageOps.exif_transpose(img)
img.thumbnail((2000, 2000), Image.LANCZOS)
if img.mode not in ("RGB", "L"):
    img = img.convert("RGB")
img.save(buf, "JPEG", quality=88, optimize=True)
```

A 12 MP phone photo becomes roughly 1.5 MB. That reduces model tokens and upload time by a factor of three to five and fixes the most common "sideways document" failure without OpenCV.

### 3.5 Queue

Procrastinate uses Postgres, so there is no Redis to operate.

```python
# api/app/worker.py
app = procrastinate.App(connector=PsycopgConnector(dsn=settings.database_url))

@app.task(name="extract_document", queue="extraction",
          retry=RetryStrategy(max_attempts=3, exponential_wait=2))
def extract_document(document_id: str) -> None:
    ...
```

| Policy | Value |
|---|---|
| Queue name | `extraction` |
| Concurrency | 2 per worker (Vertex rate limits are the constraint) |
| Attempts | 3, exponential 2 s / 8 s / 30 s |
| Timeout | 180 s per document |
| Dead letter | Document `FAILED`, reason stored, shipment stays reviewable |
| Payload | `document_id` only — the worker reloads state, so retries see current data |

The job is idempotent at the data level: it deletes and re-inserts that document's derived rows in one transaction.

### 3.6 Status derivation

Document status is stored. Shipment status is derived, never set directly by a job:

```
any document PROCESSING/QUEUED     → shipment EXTRACTING
any document FAILED/MANUAL_ENTRY   → shipment NEEDS_REVIEW
all documents EXTRACTED            → shipment NEEDS_REVIEW
no documents                       → shipment DRAFT
```

A single function `derive_shipment_status(shipment_id)` is the only writer. Later phases extend it with approval states, but the rule stays: status is a function of facts, not a mutable field someone forgets to update.

### 3.7 Polling

`GET /api/shipments/{id}/status` returns document states, shipment state and a version counter. The SPA polls every 2 seconds while any document is `QUEUED` or `PROCESSING`, then stops. Polling is preferred over websockets here: one endpoint, no connection management, and the maximum wait is 60 seconds.

### 3.8 Deployment

Multi-stage Dockerfile:

```dockerfile
FROM node:22 AS web
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY web/ .
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app
COPY api/pyproject.toml api/uv.lock ./
RUN pip install uv && uv sync --frozen
COPY api/ .
COPY --from=web /web/dist ./app/static
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Worker command on the same image:

```
procrastinate --app=app.worker.app worker --concurrency=2
```

Release order: run `alembic upgrade head` and `procrastinate schema --apply`, then start the web process, then the worker. The health endpoint checks DB and S3; the platform restarts on failure.

## 4. API surface added

| Method | Route | Role | Notes |
|---|---|---|---|
| POST | `/api/shipments` | both | `{ref, supplier_id, incoterm, currency}` |
| GET | `/api/shipments/{id}` | both | Documents, status, counts |
| GET | `/api/shipments/{id}/status` | both | Lightweight polling payload |
| POST | `/api/shipments/{id}/documents/presign` | both | `{filename, mime, size, sha256, type}` |
| POST | `/api/shipments/{id}/documents/confirm` | both | `{document_id}`; validates and enqueues |
| GET | `/api/documents/{id}/pages/{idx}` | both | Returns a 5-minute presigned GET |
| DELETE | `/api/documents/{id}` | both | Only before extraction completes |

## 5. UI for this phase

The upload screen is functional but deliberately plain:

- Three slots: Invoice, Packing list, Bill of lading.
- Drag-and-drop plus file picker.
- Per-file state: choosing → uploading (progress) → queued → processing → extracted / failed.
- Type is auto-suggested from the filename and can be changed from a dropdown before confirm.
- Failures show the exact reason and a retry that reuses the file.
- A "pages" thumbnail strip appears once rendering completes, proving the file is legible.

The review screen does not exist yet. Clicking a document at this stage opens the first page image in a plain viewer.

## 6. Tests

| Test | Assertion |
|---|---|
| `test_presign_rejects_oversize` | 413 before a URL is issued |
| `test_confirm_rejects_wrong_magic` | A `.pdf` that is actually a ZIP returns 415 |
| `test_duplicate_sha_409` | Same file twice on one shipment returns the existing id |
| `test_render_page_count` | 3-page PDF produces 3 page rows and 3 objects |
| `test_words_boxes_normalised` | Every coordinate is between 0 and 1 |
| `test_scanned_page_has_no_words` | `source = NONE`, `words_key` null |
| `test_job_retry` | A forced exception retries and eventually marks `FAILED` |
| `test_status_derivation` | Mixed document states produce `NEEDS_REVIEW`, never `EXTRACTED` |
| `test_encrypted_pdf_rejected` | Clear 422, no job enqueued |

## 7. Exit checklist

- [ ] Upload works in the browser against the deployed environment, not only locally.
- [ ] Files are private; an unsigned object URL returns 403.
- [ ] Pages render at 2000 px long edge; text PDFs produce `words.json`.
- [ ] A scanned photo is orientation-corrected and bounded to 2000 px.
- [ ] Worker processes a job and retries a forced failure.
- [ ] Status polling shows queued → processing → extracted without a refresh.
- [ ] `derive_shipment_status` is the only writer of shipment status.
- [ ] Live URL is reachable over HTTPS and the health check is green.
- [ ] Redeploy from a clean commit is reproducible in under 10 minutes.

## 8. Risks and gotchas

| Risk | Mitigation |
|---|---|
| S3 CORS blocks the browser PUT | Configure CORS for the exact app origin; test with `curl -X OPTIONS` |
| Presigned URL expires during a slow upload | 10-minute TTL; retry re-presigns |
| PyMuPDF wheel unavailable on ARM | Pin a version with ARM wheels or build on amd64 |
| Procedural PDFs render blank | Test with 3 different generator tools before trusting the pipeline |
| Procrastinate schema applied twice | `--apply` is idempotent; run it in the release step, not on every boot |
| Worker and web drift | Same image, same commit, one build |

## 9. Handoff

Phase 3 can assume: a document row with pages and word boxes, a worker that runs tasks, a deployed environment, and a status endpoint the UI already polls.
