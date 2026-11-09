# Progress — 5 November 2026

## Where we are

The core build and the core-completeness slice are done and tested. The TDD, PDF and submission ZIP reflect the current code. The remaining gaps are production/AI validation work that needs client inputs or cloud credentials, not missing product features.

## Built and verified

| Area | State |
|---|---|
| Shipment intake | Three documents, PDF/JPG/PNG, validation, private storage |
| Extraction | Live Gemini adapter wired behind `AI_BACKEND`; deterministic fixture is the offline default |
| Evidence | Quote, page, EXACT/CONTAINED/CLAIMED/NONE, derived highlight boxes |
| Line items | Editable description, HSN, quantity, unit, price, amount, gross/net; per-line evidence and confidence; edits rerun all checks |
| Cross-checks | 14 rules, line matching, tolerances, input-hash-bound resolutions |
| Gate | Field confirmation, WARN acknowledgement, BLOCK override, approval invalidation |
| Review | Document beside fields, source highlight, evidence panel, keyboard flow |
| History | Per-shipment activity drawer: uploads, extraction, corrections, checks, approvals, exports |
| Document lifecycle | Re-extract and remove with check recomputation; blocked after approval |
| List | Filters, search, pagination, attention-first ordering |
| Export | Configurable CSV with BOM/CRLF/formula escaping, preview and gate |
| Export template | Versioned editor for headers, sources, formats and required columns |
| Reports | Evidence coverage, first-pass acceptance, correction rate by field and supplier |
| Settings | Tolerances, retention, template, users |
| Roles | Executive and manager, enforced server-side |
| Retention | `scripts/retention.py`, dry-run by default; deletes document objects past the cutoff and audits the purge |

## Verification

```
38 backend tests           passing
3 Playwright E2E paths     passing (full flow incl. line edit, history and reopen;
                           manual entry; blocked export)
eval harness               live Gemini: 267–268/268 fields (99.6–100%) over two runs on 25 synthetic docs
                           fixture baseline: 260/260 on 24 docs
demo dataset               9 shipments, 26 PDFs, 2 manual-entry, 1 missing document
```

The live 267–268/268 is Gemini on synthetic documents, not the client's 200. The fixture baseline is the offline path. TDD §16.3 and §18.1 state both.

## Submission artifacts

- `TDD.md` + `TDD.pdf` (45 pages, v1.5, as-built, screenshots included)
- `deployment.md` (local, Docker, production, env var names, demo logins)
- `Customs-AI-submission.zip` (TDD.pdf + deployment.md)
- Repository: https://github.com/Neeharika2/Customs-AI
- Live demo: https://prod-main-app-170155-005gnnd7hct.compute.instacloud-edge.com/

## What is genuinely left

These are not UI gaps; they need inputs or infrastructure:

1. **200-shipment evaluation.** The live model scored 267–268/268 (99.6–100%) over two runs on 25 synthetic documents. Real client documents, their filing template and a Vertex project are still needed for the only honest 95% claim and confidence calibration.
2. **OCR fallback decision.** Only after the real scan evidence rate is measured. Image-only pages currently go to manual entry.
3. **Durable worker + scheduler.** Extraction runs as an in-process background task; the job function is isolated. Retention is a CLI, not a nightly job. Both are deployment wiring.
4. **Production hardening.** Upload rate limits, optional malware scan, monitoring/alerts, backups/restore drill.
5. **Public deployment — done.** Live demo: https://prod-main-app-170155-005gnnd7hct.compute.instacloud-edge.com/. The deployment uses the Developer API on synthetic documents; Vertex remains the production path.
6. **XLSX export.** Deferred until the client's actual import template is supplied (A9). The column map is ready.

## Next session order

1. Obtain the 200-shipment history + filing template from the client; run the holdout evaluation.
2. Move extraction to Procrastinate; schedule retention; add upload rate limits.
3. Deploy to Mumbai; run the reviewer checklist.

## Demo

| Role | Email | Password |
|---|---|---|
| Executive | `exec@demo.local` | `demo-exec-2026` |
| Manager | `manager@demo.local` | `demo-manager-2026` |

Start on **SHP-24811** (45 kg weight mismatch), open a line item to edit it, then **History** to see the correction. **SHP-24816** shows manual entry for an illegible bill of lading.
