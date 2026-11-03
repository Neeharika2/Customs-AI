# Phase 1 — Foundation

> **Day 1** · **Estimate:** 11 h · **Depends on:** Phase 0
> **Exit:** an executive and a manager can log in, see an empty shipment list, and every table exists in a database built from migrations alone.

## 1. Objective

Stand up the skeleton that every later phase hangs on: schema, authentication, role enforcement, organisation scoping, design tokens and the application shell. No document processing, no AI.

This phase is deliberately conservative. A schema change on Day 4 costs three other phases; a schema change on Day 1 costs nothing.

## 2. Tasks

| # | Task | Est. | Output |
|---|---|---|---|
| 1.1 | Repository scaffold, Docker Compose, Makefile, `.env.example` | 1.0 h | `make dev` starts Postgres + MinIO + API + Vite |
| 1.2 | SQLAlchemy models for all 17 tables, enums and constraints | 2.5 h | `api/app/models/` |
| 1.3 | Alembic init, initial migration, seed script | 1.5 h | `alembic upgrade head` on an empty DB |
| 1.4 | Auth: login, logout, me, Argon2, sessions, CSRF, rate limit | 2.0 h | Cookie session working end to end |
| 1.5 | Organisation scoping helper and `require_role` | 1.0 h | 403/404 behaviour tested |
| 1.6 | Design tokens, Tailwind, app shell, login screen, empty list | 2.0 h | Screens render at 375 px and 1440 px |
| 1.7 | pytest harness, factory helpers, CI workflow | 1.0 h | CI green on the phase branch |

## 3. Technical detail

### 3.1 Local environment

```yaml
# docker-compose.yml (services only)
postgres:  postgres:16-alpine   port 5432   db: customs, user: customs
minio:     minio/minio          port 9000/9001  bucket: customs-local
api:       build .              port 8000   mounts ./api
web:       node:22              port 5173   mounts ./web
```

`make dev` runs compose plus `uvicorn --reload` and `vite`. `make test` runs pytest. `make seed` generates and loads sample data.

Local storage uses MinIO with the same S3 API as production. The storage service is written against the interface, and the endpoint is configuration — no code path is local-only.

### 3.2 Schema

Models exactly as specified in `TDD.md` §6.2. Create in this order to respect foreign keys:

```
org → user → session → supplier → shipment → document → page
→ extraction_run → field → line_item → check → check_resolution
→ correction → approval → export_template → export → audit_event
```

Rules that must be encoded in the migration, not left to application code:

- `UNIQUE (org_id, email)` on `user`.
- `UNIQUE (org_id, ref)` on `shipment`.
- `UNIQUE (shipment_id, sha256)` on `document`.
- `UNIQUE (document_id, key, line_no)` on `field`.
- `UNIQUE (document_id, content_sha256, prompt_version, schema_version)` on `extraction_run`.
- `UNIQUE (shipment_id, template_id, content_hash)` on `export`.
- `UNIQUE (shipment_id, code, subject_key, input_hash)` on `check_resolution`.
- `CHECK (qty > 0)` on `line_item`.
- `CHECK (effective_conf BETWEEN 0 AND 1)` on `field`.
- `CHECK (char_length(currency) = 3)` on `shipment`.
- Append-only trigger on `audit_event` (`BEFORE UPDATE OR DELETE` → raise).

Use Postgres enums for the status machines (`TDD.md` §6.3). Adding a value later requires `ALTER TYPE ... ADD VALUE`, which is a non-transactional migration — acceptable, but note it now so it is not a surprise.

### 3.3 Authentication

```python
# password
pwdlib.PasswordHash.recommended()   # Argon2id

# session
sid = secrets.token_urlsafe(32)
store hash(sid) in session.token_hash, never the raw value
cookie: HttpOnly, Secure (prod), SameSite=Lax, Path=/, Max-Age=8h
```

| Property | Decision |
|---|---|
| Session store | Database, not JWT — revocation must be immediate |
| Idle expiry | 8 hours |
| Absolute expiry | 7 days |
| Rotation | New session ID on login; old sessions for the user are revocable |
| CSRF | Double-submit: `csrf` cookie (readable) + `X-CSRF-Token` header on every mutation |
| Login rate limit | 5 attempts per 15 minutes per IP + email pair |
| Error message | "Invalid email or password" — never reveals which |

`POST /api/auth/login` accepts `{email, password}` and sets both cookies. `GET /api/me` returns the user, role and org. `POST /api/auth/logout` revokes the session row.

### 3.4 Authorisation

Two layers, both required:

```python
# 1. role gate
def require_role(*roles):
    def dep(user = Depends(current_user)):
        if user.role not in roles: raise Forbidden()
        return user

# 2. tenant scope — every query
def scoped(stmt, model, user):
    return stmt.where(model.org_id == user.org_id)
```

A cross-organisation fetch raises `NotFound` (404), not `Forbidden` (403). The API must not confirm that another tenant's shipment exists.

A test iterates the router table and asserts that every route except `/healthz` and `/auth/login` has both a current-user dependency and an org-scoped query. This is the single most valuable test in the phase — it catches the route someone adds at 11 pm on Day 6.

### 3.5 Seed data

`make seed` is idempotent (upsert on natural keys) and creates:

| Entity | Values |
|---|---|
| Org | `Demo Freight`, weight tolerance 0.5%, retention 180 days |
| Users | `exec@demo.local` (EXEC), `manager@demo.local` (MANAGER) |
| Suppliers | Company B (CN), Company C (SE), Company D (CN), Company E (IN) |
| Shipments | none yet — Phase 2 adds documents, Phase 3 adds fields |

Passwords come from `DEMO_EXEC_PASSWORD` / `DEMO_MANAGER_PASSWORD` in the environment, defaulted only in local development. `deployment.md` records the demo credentials; the repository does not.

### 3.6 Design tokens

Implement as CSS custom properties consumed by Tailwind:

```css
:root {
  --canvas: #FAFAF8;  --surface: #FFFFFF;  --ink: #14161A;
  --muted:  #6B6F76;  --border:  #E6E4DE;  --accent: #0F6B5C;
  --warn-bg:#FEF3C7;  --warn-fg: #B45309;
  --block-bg:#FEE4E2; --block-fg:#B42318;
  --ok-fg:  #067647;
}
```

Type: Inter, 14 px base, 12 px meta, tabular numerals via `font-variant-numeric: tabular-nums` on a `.num` utility. Spacing on 4/8 px. Radius 6 px. No shadows except dialogs.

### 3.7 Application shell

- Sidebar 240 px: Shipments, Reports, Settings (the last two hidden for EXEC).
- Top bar: org name, user menu, sign out.
- Content max-width 1440 px, 32 px gutters.
- Below 1024 px the sidebar collapses to icons; below 768 px to a bottom tab bar with three items.
- Skip-to-content link; focus ring 2 px accent.

Login screen: centred card 400 px, email, password, one primary button, inline error region with `role="alert"`. No marketing copy, no illustration — this is a tool used daily.

Shipment list in this phase is an empty state only: "No shipments yet — create your first shipment", with a disabled-looking but present primary action that becomes live in Phase 2.

## 4. API surface created in this phase

| Method | Route | Auth | Notes |
|---|---|---|---|
| POST | `/api/auth/login` | public | Sets `sid` + `csrf` |
| POST | `/api/auth/logout` | user | Revokes session |
| GET | `/api/me` | user | User, role, org, CSRF token |
| GET | `/api/shipments` | user | Returns `{items: [], total: 0}` for now |
| GET | `/healthz` | public | DB + storage reachability |

Error format:

```json
{ "type": "about:blank", "title": "Forbidden", "status": 403,
  "code": "role_required", "detail": "Manager role required." }
```

## 5. Tests

| Test | Assertion |
|---|---|
| `test_login_sets_cookies` | `sid` is HttpOnly; `csrf` is readable; both Secure in prod config |
| `test_login_bad_password` | 401, generic message, no user enumeration |
| `test_session_revoked_on_logout` | Subsequent request returns 401 |
| `test_csrf_required` | Mutation without header returns 403 |
| `test_role_gate` | EXEC on a manager route returns 403 |
| `test_cross_org_404` | Another org's shipment ID returns 404 |
| `test_every_route_scoped` | Router table has user + org dependency |
| `test_audit_append_only` | UPDATE/DELETE on `audit_event` raises |
| `test_migration_from_scratch` | `alembic upgrade head` on empty DB succeeds |
| `test_seed_idempotent` | Running seed twice does not duplicate |

## 6. Exit checklist

- [ ] `make dev` starts all four services from a clean clone.
- [ ] `alembic upgrade head` builds the schema; `alembic downgrade base` reverses it.
- [ ] Both demo users log in; roles gate correctly.
- [ ] Session cookie is HttpOnly, SameSite=Lax; CSRF enforced on mutations.
- [ ] Every API route is org-scoped and covered by the route-scan test.
- [ ] `audit_event` rejects updates and deletes.
- [ ] Login and empty list render at 375 px and 1440 px without horizontal scroll.
- [ ] CI green: lint, types, tests, migration check.
- [ ] `.env.example` includes every variable introduced.
- [ ] No secret or real personal data in the repository.

## 7. Risks and gotchas

| Risk | Mitigation |
|---|---|
| Enum values drift between Python and Postgres | Define once in Python, generate the migration from the same enum |
| Naive datetimes leak into the DB | Always `DateTime(timezone=True)`; test stores UTC |
| CSRF breaks the upload flow later | Exempt nothing; the presign call is a normal mutation with the header |
| Seed passwords committed | Read from env; default only when `APP_ENV=local` |
| Sidebar layout breaks the review screen | Shell uses a slot, and the review route opts into a full-width variant in Phase 4 |

## 8. Handoff

Phase 2 can assume: a running app, a schema with `document` and `page` tables, an S3-compatible client, a session for both roles, and a shell that can host the upload screen.
