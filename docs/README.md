# Build Phases — Customs-AI

Working plan for the 7-day build, split into phases. Each phase has its own file with scope, tasks, technical detail, tests and an exit checklist.

**Read first:** [`../plan.md`](../plan.md) for scope and trade-offs · [`../TDD.md`](../TDD.md) for architecture and data model.

---

## Phase map

| Phase | File | Day | Est. | Depends on | Exit gate |
|---|---|---|---|---|---|
| 0 | [phase-0-preflight.md](phase-0-preflight.md) | before Day 1 | 4 h | — | Vertex answers on a real PDF; bucket and deploy target exist |
| 1 | [phase-1-foundation.md](phase-1-foundation.md) | Day 1 | 11 h | Phase 0 | Login both roles; schema from scratch; seeded org |
| 2 | [phase-2-ingestion.md](phase-2-ingestion.md) | Day 2 | 10 h | Phase 1 | Upload → S3 → render → job → live URL |
| 3 | [phase-3-extraction.md](phase-3-extraction.md) | Day 3 | 10.5 h | Phase 2 | Fields with values, evidence, confidence; failure → manual |
| 4 | [phase-4-review.md](phase-4-review.md) | Day 4 | 12 h | Phase 3 | Review and correct without touching JSON |
| 5 | [phase-5-verification.md](phase-5-verification.md) | Day 5 | 13 h | Phase 4 | Checks, gate, approval, override — all enforced server-side |
| 6 | [phase-6-export.md](phase-6-export.md) | Day 6 | 10.5 h | Phase 5 | Correct CSV; list and reports live |
| 7 | [phase-7-hardening.md](phase-7-hardening.md) | Day 7 | 10.5 h | Phase 6 | E2E green; TDD + deployment.md; demo rehearsed |

Total ≈ 82 hours across 7 days — roughly 11–12 hour days. This is a sprint plan, not a comfortable one. The phase gates exist so that an overrun is visible on the day it happens, not on Day 7. **Deploy at the end of Phase 2 and redeploy after every phase.**

```
Phase 0 ──▶ 1 ──▶ 2 ──▶ 3 ──▶ 4 ──▶ 5 ──▶ 6 ──▶ 7
                     │                       │
                     └── deploy ─────────────┘  (redeploy daily)
```

## Phase gate

A phase is done only when its **Exit checklist** is entirely green. Do not start the next phase with a red item — carry it as a known defect and note it in the phase file, or cut the feature.

If a phase overruns, cut from the right using this order:

| Priority | Cut first |
|---|---|
| 1 | Reports beyond a single table |
| 2 | Settings UI (env/config is acceptable for the demo) |
| 3 | Separate manager queue (use the shipment detail page) |
| 4 | Confirm-all-high-confidence (keep per-field confirm) |
| 5 | XLSX (never in scope) |
| **Never** | Review screen, evidence, checks, gate, CSV export, auth |

## Conventions

| Item | Convention |
|---|---|
| Timezone | UTC in DB; `Asia/Kolkata` in UI |
| Money | `Decimal` in Python, `NUMERIC` in Postgres; never float |
| IDs | UUID v4 for entities; human `ref` like `SHP-24811` |
| JSON casing | `snake_case` end to end; types generated from OpenAPI |
| Errors | RFC 7807 `application/problem+json` with `code`, `detail`, `fields` |
| Commits | Conventional: `feat:`, `fix:`, `test:`, `chore:`, `docs:` — one branch/PR per phase |
| Branches | `phase/1-foundation` … `phase/7-hardening` |
| Secrets | `.env` local only; `.env.example` committed; platform secret store deployed |
| Tests | No phase merges with failing tests; rules engine tests are mandatory |
| Python | 3.12, `uv` for env and lockfile |
| Node | 22, `pnpm` |

### Local ports

| Service | Port |
|---|---|
| FastAPI | 8000 |
| Vite dev server | 5173 (proxies `/api` to 8000) |
| Postgres | 5432 |
| MinIO API / console | 9000 / 9001 |

### Repository layout

```
customs-ai/
├── api/
│   ├── app/
│   │   ├── main.py            FastAPI app, static mount, health
│   │   ├── config.py          env parsing (pydantic-settings)
│   │   ├── db.py              engine, session, scoping helper
│   │   ├── models/            SQLAlchemy models
│   │   ├── schemas/           Pydantic request/response
│   │   ├── routers/           auth, shipments, documents, fields, checks, export, reports
│   │   ├── services/          gate, export, retention, storage
│   │   ├── extract/           gemini client, prompts, evidence, pipeline
│   │   ├── checks/            rules/, normalize.py, engine.py
│   │   └── worker.py          Procrastinate app and tasks
│   ├── migrations/
│   └── tests/
├── web/
│   ├── src/
│   │   ├── routes/
│   │   ├── components/
│   │   ├── lib/               api client, query hooks, types (generated)
│   │   └── styles/
│   └── index.html
├── seed/                      synthetic PDFs + generator
├── eval/                      golden set + harness
├── docs/                      this folder
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── .env.example
└── README.md
```

### Definition of done (every phase)

1. Code merged to `main` via its phase branch.
2. Tests written and green locally.
3. Deployed and smoke-tested on the live URL.
4. `.env.example` updated if a variable was added.
5. The phase file's exit checklist ticked, with any carry-over noted at the bottom.
6. Commit history reads as a sequence of decisions, not a single dump.

## Status

| Phase | Status | Notes |
|---|---|---|
| 0 | ✅ | Access checklist superseded by a local bundled Postgres; Vertex adapter present, no committed credentials |
| 1 | ✅ | 17 tables, Alembic, auth, roles, org scoping, shell |
| 2 | ✅ | Upload, validation, render, word boxes, local/S3 storage adapter |
| 3 | ✅ | Fixture extractor, evidence, confidence, manual-entry path, `extraction_run` |
| 4 | ✅ | Review workspace: viewer, overlays, evidence, inline edits, keyboard |
| 5 | ✅ | 14 checks, input-hash resolutions, gate, approval, override |
| 6 | ✅ | CSV export, template, preview, list, reports, settings |
| 7 | ✅ | 24 backend tests, 3 Playwright paths, eval harness, Docker, docs |

### Build outcome

- 9 seeded shipments, 26 synthetic documents, 260 evaluated fields.
- `eval/run.py`: 260/260 on extractable synthetic documents, 2 manual-entry documents, 1 missing document.
- 24 pytest tests and 3 end-to-end paths passing.
- One container image; Alembic migrations; S3/Vertex adapters present.
- Honest deviation log in `TDD.md` §18.1: fixture extractor locally, background task instead of Procrastinate, multipart upload instead of presigned PUT.

The full phase files remain as the working plan; the code and `TDD.md` are the as-built record.
