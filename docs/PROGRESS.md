# Progress — 4 November 2026

## Where we are

The core build is complete, and the **core completeness** slice is now built and tested. Everything below runs locally against the seeded demo and is pushed to `main`.

## Built in this pass

| Item | What it does |
|---|---|
| **Editable line items** | The review table now edits description, HSN, quantity, unit, price, amount, gross and net per line. Each line carries its own evidence level, confidence, page and quote. Saves log a correction, rerun all 13 checks, and the E2E proves the gate reacts. |
| **Activity / history** | A per-shipment timeline merges corrections, approvals, exports and audit events: uploads, extraction, manual entry, submissions, acknowledgements, overrides, reopen and approval invalidation. Available from the shipment page and the review header. |
| **Document remove / re-extract** | Each document slot has Re-extract and Remove. Removal deletes the file, fields and lines, recomputes checks and updates the shipment status. Both actions are audited and blocked after approval. |
| **Pagination** | The shipment list now pages 50 at a time with a range and previous/next controls; filters and search reset the page. Server-side pagination already existed. |
| **Export template editor** | Managers can edit the column map — header, source, format, required — with versioning. Saving creates vN+1 and deactivates the old template; existing exports keep the version they used. |
| **Reopen** | Managers can reopen a READY or EXPORTED shipment; approval is voided, status returns to review, and the history records it. |
| **Audit coverage** | Extraction and manual entry now write audit events; the seed writes upload events so the demo history is populated. |

## Verification

```
31 backend tests           passed
3 Playwright E2E paths     passed
eval harness               260/260 fields on 24 synthetic documents
demo dataset               9 shipments, 26 PDFs
```

The evaluation number is the deterministic **fixture** extractor on synthetic data. It is not a Gemini measurement. See `TDD.md` §16.3 and §18.1.

## Repository state

- Branch `main`, pushed to https://github.com/Neeharika2/Customs-AI
- Demo database reseeded clean (no E2E leftovers)
- `api/app/static` rebuilt so the single-server demo at port 8000 has the new UI

## Still stale — first task tomorrow

1. **`TDD.md` and `TDD.pdf` are behind the code.** They still say 24 tests and do not describe line-item editing, history, document lifecycle, pagination, template editing or reopen. Update §1 build status, §6/§11/§16/§18, then regenerate:
   ```bash
   .venv/bin/python scripts/build_tdd.py
   ```
2. **`Customs-AI-submission.zip` is stale.** It predates this slice. Rebuild it after the TDD refresh (TDD.pdf + deployment.md only).
3. Add screenshots of the line editor, history drawer and template editor to `docs/screenshots/` if the TDD references them.

## Next build priorities

1. **Real Vertex AI run** — the adapter is written but has never been exercised against the model. Then the 200-shipment golden set with a holdout split: this is the only way to make a real accuracy claim.
2. **Durable extraction** — move the in-process background task to the Procrastinate worker; add retries, dead-letter and job status.
3. **Retention job + delete-on-request endpoint** — the policy and data model exist; the scheduler does not.
4. **Rate limits and malware scanning** on uploads; monitoring/alerts; a real Mumbai deployment.
5. **OCR fallback** only if the real scan evidence rate demands it.

## Demo

| Role | Email | Password |
|---|---|---|
| Executive | `exec@demo.local` | `demo-exec-2026` |
| Manager | `manager@demo.local` | `demo-manager-2026` |

Start on **SHP-24811**; the 45 kg weight difference is already flagged. Open a line item to edit it, then History to see the correction logged.
