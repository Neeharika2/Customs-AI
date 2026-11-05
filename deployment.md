# Deployment

Customs-AI — AI document intake, cross-document verification and human approval for import shipments.

Two files matter alongside this guide: `TDD.md` (design) and `README.md` (overview). This file is the runbook.

---

## 1. Local development

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12 |
| uv | 0.12 or newer |
| Node | 22 |
| pnpm | 12 |
| PostgreSQL | 16 — either the bundled `pgserver` or any local server |

No Docker is required for local development. A bundled PostgreSQL binary is used through `scripts/dev_db.py`, so a reviewer does not need to install Postgres.

### 1.1 Install

```bash
git clone https://github.com/Neeharika2/Customs-AI.git
cd customs-ai

# Python dependencies (creates api/.venv from api/uv.lock)
cd api
uv sync
cd ..

# Web dependencies
cd web
pnpm install
cd ..
```

### 1.2 Start the database

The bundled database keeps its data in `/tmp/opencode/pgdata`. Leave this terminal running.

```bash
cd api
uv run python ../scripts/dev_db.py
```

Expected output:

```
Postgres running
DATABASE_URL=postgresql+psycopg://postgres@/postgres?host=/tmp/opencode/pgdata
```

If you prefer your own PostgreSQL, skip this step and set `DATABASE_URL` in `.env` instead.

### 1.3 Create the schema and demo data

In a second terminal:

```bash
cd api
uv run python ../seed/generate.py     # writes 26 synthetic PDFs to seed/output
uv run python ../seed/seed_demo.py    # users, 9 shipments, extraction, checks
```

`seed_demo.py` is idempotent: it removes and rebuilds the derived rows for the nine demo shipments.

### 1.4 Run the application

```bash
# terminal 2
cd api
uv run uvicorn app.main:app --reload --port 8000
```

```bash
# terminal 3
cd web
pnpm dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api` to port 8000.

Alternative single-process mode (production build served by FastAPI):

```bash
make build          # builds web/dist and copies it to api/app/static
cd api && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000**.

### 1.5 Demo accounts

| Role | Email | Password |
|---|---|---|
| Documentation executive | `exec@demo.local` | `demo-exec-2026` |
| Documentation manager | `manager@demo.local` | `demo-manager-2026` |

These are demo credentials only, supplied through `DEMO_EXEC_PASSWORD` and `DEMO_MANAGER_PASSWORD`. Change them before any shared deployment.

### 1.6 Tests

```bash
# 35 backend tests: checks, gate staleness, line edits, history, AI conversion, authz, CSV
cd api && uv run pytest -q

# 3 end-to-end paths: full approval/export, manual entry, blocked export
cd web && pnpm test:e2e
```

The E2E suite starts the API and Vite if they are not already running. It needs the database from step 1.2 and the demo seed from step 1.3.

### 1.7 Evaluation harness

```bash
cd api && uv run python ../eval/run.py
```

Prints per-field accuracy and evidence distribution for the synthetic golden set and writes `eval/results.json`. The local demo uses a deterministic fixture extractor; this measures the pipeline, not Gemini.

### 1.8 Optional: run the live model on synthetic documents

The live path is wired. A free Gemini Developer API key is acceptable for **synthetic documents only** — its free tier is used to improve Google's products, so never send client documents through it. Production uses Vertex AI (`AI_BACKEND=vertex`).

```bash
cd api
AI_BACKEND=developer GEMINI_API_KEY=<key> GEMINI_MODEL=gemini-2.5-flash \
  uv run python ../seed/seed_demo.py
uv run python ../eval/run.py
```

This re-extracts all 26 demo documents through the model, then measures the persisted fields. The review screen shows **Live model** instead of **Demo extractor**. If the model fails a document, it routes to manual entry rather than silently falling back.

To return to the offline demo, unset `AI_BACKEND` (default `fixture`) and reseed.

---

## 2. Docker Compose (self-contained demo)

```bash
cp .env.example .env
# set SECRET_KEY in .env
docker compose up --build
```

The application runs migrations on boot. On a fresh database, seed it once:

```bash
docker compose exec app uv run python /seed/generate.py
docker compose exec app uv run python /seed/seed_demo.py
```

Open **http://localhost:8000**. Data survives restarts in the `appdata` and `pgdata` volumes.

The compose file uses local disk storage (`STORAGE_BACKEND=local`). For a real deployment use S3, described below.

---

## 3. Production deployment (Mumbai)

The intended shape:

| Component | Service | Region |
|---|---|---|
| Application + worker process | AWS App Runner or Fly.io | `ap-south-1` / `bom` |
| PostgreSQL | RDS or Supabase | Mumbai |
| Object storage | S3 | `ap-south-1` |
| Model inference | Vertex AI Gemini | `asia-south1` |

### 3.1 Build and push

```bash
docker build -t customs-ai .
docker tag customs-ai <registry>/customs-ai:<commit>
docker push <registry>/customs-ai:<commit>
```

The image contains the built SPA, the API and the Alembic migrations. `CMD` runs `alembic upgrade head` before starting uvicorn.

### 3.2 Configure the platform

Set the environment variables in §4. Minimum for a working deployment:

- `DATABASE_URL`
- `SECRET_KEY`
- `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_REGION`, credentials
- `AI_BACKEND=vertex`
- `GOOGLE_CLOUD_PROJECT`, `VERTEX_MODEL`, `VERTEX_LOCATION`
- `APP_ENV=production`, `APP_BASE_URL`

For Vertex AI, mount an ADC service-account file through the platform's secret mechanism or use workload identity. The service account needs `roles/aiplatform.user` only. The repository never contains the key.

If `AI_BACKEND=fixture` or the Vertex configuration is incomplete, the application uses the deterministic fixture extractor and labels the review screen **Demo extractor**. The live adapter is `api/app/extract/ai.py`; it selects the backend from `AI_BACKEND` and records the model and prompt version per extraction run.

### 3.3 Storage

Create a private S3 bucket in `ap-south-1`:

- Block all public access.
- Enable versioning.
- Enable default encryption.
- Add a lifecycle rule aligned with `RETENTION_DAYS`.
- Scope the application IAM policy to `arn:aws:s3:::<bucket>/org/*` with `PutObject`, `GetObject`, `DeleteObject`, and `ListBucket` on the `org/*` prefix only.

Presigned URLs are short-lived. The bucket is never public.

### 3.4 Database

Create the database, set `DATABASE_URL`, and let the container run `alembic upgrade head`.

For a fresh production database, do **not** run `seed_demo.py` — it creates demo shipments with synthetic data. Create the real organisation and users through your onboarding process (the seed script is the reference implementation). For a demo deployment, seeding is expected.

### 3.5 Verify

```bash
curl https://<host>/healthz
# {"ok":true,"env":"production","time":"..."}
```

Then sign in and run one shipment through upload → review → approval → export. The checklist in `docs/phase-7-hardening.md` §10 covers the rest.

---

## 4. Environment variables

Names only. Values live in the platform secret store; `.env` is ignored by git.

| Variable | Required | Purpose |
|---|---|---|
| `APP_ENV` | yes | `local`, `test` or `production` |
| `APP_BASE_URL` | yes | Public origin, used for links |
| `SECRET_KEY` | yes | Session/token derivation; rotate to revoke |
| `DATABASE_URL` | yes | `postgresql+psycopg://…` |
| `STORAGE_BACKEND` | yes | `local` or `s3` |
| `LOCAL_STORAGE_DIR` | local | Filesystem path for local storage |
| `S3_ENDPOINT` | optional | S3-compatible endpoint; blank for AWS |
| `S3_REGION` | s3 | `ap-south-1` |
| `S3_BUCKET` | s3 | Private document bucket |
| `S3_ACCESS_KEY_ID` | s3 | Scoped application credentials |
| `S3_SECRET_ACCESS_KEY` | s3 | Scoped application credentials |
| `AI_BACKEND` | optional | `fixture` (default), `developer` (synthetic only) or `vertex` |
| `GEMINI_API_KEY` | developer | Gemini Developer API key; synthetic documents only |
| `GEMINI_MODEL` | developer | Model ID for the Developer API |
| `GOOGLE_CLOUD_PROJECT` | Vertex | GCP project for Vertex AI |
| `VERTEX_LOCATION` | Vertex | `asia-south1` |
| `VERTEX_MODEL` | Vertex | Pinned model ID; empty selects the fixture |
| `AI_MONTHLY_CAP_PAISE` | optional | Spend guard per organisation |
| `MAX_UPLOAD_MB` | optional | Default 25 |
| `MAX_PAGES` | optional | Default 40 |
| `SESSION_TTL_HOURS` | optional | Default 8 |
| `RETENTION_DAYS` | optional | Default 180 |
| `DEMO_EXEC_PASSWORD` | demo only | Demo executive password |
| `DEMO_MANAGER_PASSWORD` | demo only | Demo manager password |
| `GOOGLE_APPLICATION_CREDENTIALS` | Vertex | Path to mounted ADC file, if not using workload identity |

Never commit any of these values. `.env.example` contains names and local defaults only.

---

## 5. What is mocked, and what is real

| Area | State |
|---|---|
| Document upload, rendering, evidence | Real |
| Cross-document checks and gate | Real |
| Correction history, approval, export | Real |
| CSV generation in a configurable filing layout | Real |
| Model extraction | **Live path wired** (`AI_BACKEND=developer` for synthetic, `vertex` for production); fixture is the offline default |
| Customs portal filing | Out of scope — the export is the hand-off |
| Importer email intake | Out of scope — staff upload documents |
| Payments / WhatsApp | Not present |
| Procrastinate worker | Not used in this slice; extraction runs as an in-process background task |

That last row is a known limitation. The extraction function is isolated behind `process_document`, so replacing the background task with a durable queue is a contained change. A process restart during extraction can leave a document in `PROCESSING`; the status is visible and the document can be re-uploaded.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `connection to server on socket … failed` | Bundled Postgres not running | Start `uv run python ../scripts/dev_db.py` and leave it open |
| `ModuleNotFoundError: app` | Running from the wrong directory | Run API commands from `api/` |
| Login returns 401 | Wrong demo password or stale session | Use the demo button; clear cookies |
| Mutations return 403 `csrf_failed` | Missing CSRF header | The SPA sends it automatically; API clients must send `X-CSRF-Token` from the `csrf` cookie |
| Review shows **Demo extractor** | `AI_BACKEND=fixture` or no model key | Expected offline; set `AI_BACKEND=vertex` + Vertex credentials, or `developer` + a key for synthetic docs |
| Upload rejected `document_type_exists` | One invoice/packing list/BL per shipment | Create a new shipment or remove the existing document |
| Export disabled with blockers | Gate is doing its job | Open review and clear the listed fields/checks |
| E2E cannot find the database | Seed not run | `cd api && uv run python ../seed/seed_demo.py` |

---

## 7. Demo path for a reviewer

1. Sign in as **Executive** (`exec@demo.local`).
2. Open **SHP-24811**. The weight check already shows 3,120 / 3,165 / 3,160 kg (+1.44%).
3. Click **Review shipment**. Select **Gross weight** in the invoice: the document highlights the exact source line and shows the quote.
4. Click **Acknowledge** on the weight warning, enter “pallet weight included in packing list”, record it.
5. Confirm the three gross-weight fields, then **Submit for approval**.
6. Sign out, sign in as **Manager** (`manager@demo.local`), open SHP-24811 and **Approve**.
7. Open **Export**, inspect the CSV preview, **Generate CSV**.
8. Open **Reports** to see correction rate, evidence coverage and supplier rows.
9. For the failure path, open **SHP-24816** — the bill of lading has no text layer and is completed by manual entry.

---

## 8. Operational notes

- **Backups.** Enable Postgres PITR (7 days) and daily snapshots (30 days). Enable S3 versioning. A backup that has never been restored is a hypothesis.
- **Migrations.** Expand → deploy → contract. Never drop a column in the same release as the code that stops using it.
- **Monitoring.** Log `request_id`, `org_id`, `user_id`; never log document content. Alert on extraction failure rate, queue depth and 5xx rate.
- **Retention.** `RETENTION_DAYS` is the cutoff. Run the purge as a nightly job:
  ```bash
  cd api && uv run python ../scripts/retention.py --apply
  ```
  The default is a dry run. It deletes source files, page images and raw model responses for exported shipments past the window, keeps extracted values and the audit trail, and logs `retention.purged`. Scheduling the command is a deployment-platform concern (cron, EventBridge, or a scheduled task).
- **AI spend.** `AI_MONTHLY_CAP_PAISE` is the configured guard; enforce it before adding a production model key.
