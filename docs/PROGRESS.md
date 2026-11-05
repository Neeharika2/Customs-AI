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
| Cross-checks | 13 rules, line matching, tolerances, input-hash-bound resolutions |
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
35 backend tests           passing
3 Playwright E2E paths     passing (full flow incl. line edit, history and reopen;
                           manual entry; blocked export)
eval harness               260/260 fields on 24 synthetic documents
demo dataset               9 shipments, 26 PDFs, 2 manual-entry, 1 missing document
```

The 260/260 is the deterministic **fixture** extractor on synthetic data, not Gemini. TDD §16.3 and §18.1 state this.

## Submission artifacts

- `TDD.md` + `TDD.pdf` (51–52 pages, as-built, screenshots included)
- `deployment.md` (local, Docker, production, env var names, demo logins)
- `Customs-AI-submission.zip` (TDD.pdf + deployment.md)
- Repository: https://github.com/Neeharika2/Customs-AI

## What is genuinely left

These are not UI gaps; they need inputs or infrastructure:

1. **Live model run.** The provider path is wired. A free Gemini Developer API key on the synthetic documents would give a real model baseline; production still needs the client's Vertex project. Then the 200-shipment evaluation with real documents is the only path to an honest 95% claim and confidence calibration.
2. **OCR fallback decision.** Only after the real scan evidence rate is measured. Image-only pages currently go to manual entry.
3. **Durable worker + scheduler.** Extraction runs as an in-process background task; the job function is isolated. Retention is a CLI, not a nightly job. Both are deployment wiring.
4. **Production hardening.** Upload rate limits, optional malware scan, monitoring/alerts, backups/restore drill.
5. **Public deployment.** No cloud account/domain was available; the TDD says “not publicly deployed”. Local run is fully documented.
6. **XLSX export.** Deferred until the client's actual import template is supplied (A9). The column map is ready.

## Next session order

1. Vertex credentials → run the adapter on the 10-document golden set → fix prompt/schema gaps.
2. Obtain the 200-shipment history + filing template from the client.
3. Move extraction to Procrastinate; schedule retention; add upload rate limits.
4. Deploy to Mumbai; run the reviewer checklist.

## Demo

| Role | Email | Password |
|---|---|---|
| Executive | `exec@demo.local` | `demo-exec-2026` |
| Manager | `manager@demo.local` | `demo-manager-2026` |

Start on **SHP-24811** (45 kg weight mismatch), open a line item to edit it, then **History** to see the correction. **SHP-24816** shows manual entry for an illegible bill of lading.
