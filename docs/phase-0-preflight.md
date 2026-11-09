# Phase 0 — Preflight and access

> **When:** before Day 1 · **Estimate:** 4 h · **Depends on:** nothing
> **Exit:** Vertex returns a valid extraction on a real synthetic PDF, and the bucket and deploy target exist.

## 1. Objective

Eliminate every external blocker before writing product code. The two failure modes this phase prevents are: discovering on Day 2 that Vertex access is not enabled, and discovering on Day 7 that the deployment target cannot reach the database.

Nothing here is product code. It is the difference between a build that starts on Day 1 and one that starts on Day 3.

## 2. Tasks

| # | Task | Est. | Output |
|---|---|---|---|
| 0.1 | Google Cloud project, billing, Vertex AI API, service account, region test | 2 h | Smoke-test script and recorded result |
| 0.2 | AWS account, S3 bucket in `ap-south-1`, IAM policy, versioning | 1 h | Bucket name and policy document |
| 0.3 | Hosting target: App Runner or Fly `bom`; Postgres instance | 0.5 h | Live URL placeholder, connection string in secret store |
| 0.4 | Public GitHub repository, branch protection, README stub | 0.25 h | Repo URL |
| 0.5 | Confirm decisions D1–D4 from `plan.md` §17 | 0.25 h | Recorded in this file |

## 3. Technical detail

### 3.1 Vertex AI smoke test

This is the go/no-go for the entire AI design. Do it first.

```bash
# 1. Authenticate
gcloud auth application-default login
gcloud config set project "$GOOGLE_CLOUD_PROJECT"

# 2. Enable the API
gcloud services enable aiplatform.googleapis.com

# 3. Confirm the model is available in Mumbai
gcloud ai models list --region=asia-south1 --filter="displayName:gemini"
```

If the listing is empty, try `asia-southeast1` and record the change. **Do not proceed silently** — `TDD.md` §8.1 and A4 promise Mumbai.

Smoke test requirements:

- One synthetic invoice PDF, one page, at least one table.
- Send the rendered page image, not the PDF, because that is what the production path does.
- Request a small structured response: supplier, invoice number, total, three line items.
- Record: model ID, latency, input/output tokens, whether the JSON parsed, whether the returned quotes appear on the page.

Write the result to `docs/preflight-results.md`. No credentials, no client data — model ID, region, latency and pass/fail only.

### 3.2 GCP access model

| Item | Requirement |
|---|---|
| Project | Billing enabled; new-project quota is often 5–10 requests/minute |
| API | `aiplatform.googleapis.com` |
| Identity (local) | Application default credentials |
| Identity (deployed) | Service account with `roles/aiplatform.user` only |
| Region | `asia-south1`, fallback `asia-southeast1` with disclosure |
| Model | Pin the exact ID in `VERTEX_MODEL`; never use a floating alias in production |

Request a quota increase for requests per minute on Day 0 if the smoke test shows throttling. Approval is not instant.

### 3.3 S3 bucket

| Setting | Value | Why |
|---|---|---|
| Region | `ap-south-1` | Residency claim in the TDD |
| Public access | Blocked at bucket and account level | Documents are confidential |
| Versioning | Enabled | Accidental overwrite recovery |
| Encryption | SSE-S3 minimum | At-rest requirement |
| Lifecycle | Transition to cheaper storage after 90 days; expire per retention | Cost and DPDP storage limitation |
| CORS | Only the app origin, `PUT` and `GET` | Presigned browser upload |
| Prefix | `org/{org_id}/shipment/{shipment_id}/` | Isolation is visible in the key |

IAM policy for the application — nothing broader:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
    "Resource": "arn:aws:s3:::BUCKET/org/*"
  }, {
    "Effect": "Allow",
    "Action": ["s3:ListBucket"],
    "Resource": "arn:aws:s3:::BUCKET",
    "Condition": {"StringLike": {"s3:prefix": ["org/*"]}}
  }]
}
```

No `s3:*`, no bucket administration, no access to other prefixes. The deployed service account is not the account used to create the bucket.

### 3.4 Hosting decision

| Option | Choose when | Notes |
|---|---|---|
| **AWS App Runner `ap-south-1`** | Default | Managed TLS, autoscaling, private VPC connector to RDS |
| **Fly.io `bom`** | Faster setup, lower cost | Mumbai region; Postgres via Supabase Mumbai or Fly Postgres |
| Single EC2 + Caddy | Budget ceiling | You own TLS, restarts and patching — not recommended for this timeline |

Whichever is chosen, confirm before Day 2 that:

1. The container can reach Postgres.
2. The container can reach S3 and Vertex.
3. A second process (worker) can run from the same image.
4. Environment variables can be set without rebuilding.

### 3.5 Repository

- Public, as required by the brief.
- `main` protected: no direct pushes after Day 1.
- One branch per phase: `phase/0-preflight` … `phase/7-hardening`.
- Conventional commit messages; the history is read at review.
- No `.env`, no service-account JSON, no client documents. `.gitignore` covers `*.pem`, `*.json` keys, `.env*` except `.env.example`, `uploads/`, `seed/output/`.

## 4. Decisions to record

| # | Decision | Default |
|---|---|---|
| D1 | Manager-only BLOCK override with written reason | Yes |
| D2 | Production storage S3 `ap-south-1`; R2 only for synthetic demo | Yes |
| D3 | Export template configurable, seeded with a plausible Bill of Entry layout | Yes |
| D4 | Vertex primary; Developer API only for synthetic demo | Yes |

Record the actual answers in `docs/preflight-results.md`, including who answered and when.

## 5. Exit checklist

- [ ] Vertex returned a parsed JSON response from `asia-south1` (or the fallback is recorded and disclosed).
- [ ] Model ID, latency and token counts written to `docs/preflight-results.md`.
- [ ] Quota is sufficient for 10 concurrent documents; a request is filed if not.
- [ ] S3 bucket exists in `ap-south-1`, public access blocked, versioning on.
- [ ] Application IAM policy is scoped to `org/*` and tested with a denied path.
- [ ] Deploy target can run a container that reaches Postgres, S3 and Vertex.
- [ ] Public repo exists; `main` protected; `.gitignore` verified with a dummy secret.
- [ ] D1–D4 recorded.
- [ ] `docs/access-checklist.md` lists every account and permission, with **no secret values**.

## 6. Risks

| Risk | Mitigation |
|---|---|
| New GCP project quota is 5 req/min | Request increase now; batch documents; queue smooths bursts |
| Model not in `asia-south1` | Fall back to Singapore and disclose; do not claim Mumbai |
| App Runner VPC connector misconfigured | Test with a trivial container on Day 0, not Day 7 |
| Bucket name collision | Use a project-specific suffix; bucket names are global |
| Service-account JSON committed | `.gitignore` first, secret scan in CI, rotate if it happens |

## 7. Artifacts

- `docs/preflight-results.md` — region, model, latency, pass/fail, decisions.
- `docs/access-checklist.md` — accounts and permissions, names only.
- `.env.example` — every variable the app will need, empty values.
- `scripts/smoke_vertex.py` — reproducible region test.
- Live URL placeholder in the README.

## 8. Handoff

Phase 1 can assume: a working project/billing account, an S3 bucket, a deploy target, a public repo, and a confirmed model ID. If any of these is missing, Phase 1 still starts — but the missing item is the top of the day's risk list and is resolved before Phase 2.
