# Phase 5 — Verification, approval and the gate

> **Day 5** · **Estimate:** 13 h · **Depends on:** Phase 4
> **Exit:** contradictions surface before a human does; nothing can be approved or exported while a blocking issue is open; every override is attributable.

## 1. Objective

Build the business logic that makes the product defensible. Extraction proposes; this phase decides whether the proposal is *internally consistent*. It also builds the human decision layer: acknowledgement, approval, rejection and override, with the rules enforced on the server.

If this phase is weak, the product is a PDF reader with a nice font. If it is strong, the review screen has something worth reviewing.

## 2. Tasks

| # | Task | Est. | Output |
|---|---|---|---|
| 5.1 | Normalisation utilities (money, weight, dates, parties, containers) | 1.5 h | `checks/normalize.py` |
| 5.2 | Thirteen rules, pure functions | 3.0 h | `checks/rules/` |
| 5.3 | Line-item matching | 1.5 h | `checks/matching.py` |
| 5.4 | Check persistence, `input_hash`, resolution staleness | 1.0 h | `checks/engine.py` |
| 5.5 | Gate service | 1.0 h | `services/gate.py` |
| 5.6 | Submit, approve, reject, override endpoints | 1.5 h | State transitions enforced |
| 5.7 | Checks panel and approval UI | 1.5 h | Two-click workflow |
| 5.8 | Test suite for rules and gate | 2.5 h | 45+ cases |

## 3. Normalisation

Checks never compare raw strings.

| Domain | Function | Rules |
|---|---|---|
| Money | `money(value, currency)` | Strip symbols and separators; `Decimal`, 2 dp; reject mixed currency |
| Weight | `weight_kg(value, uom)` | kg base; `lb × 0.45359237`; `MT × 1000`; 3 dp |
| Quantity | `qty(value, uom)` | Integer for count UoMs; 3 dp otherwise |
| Date | `date(value)` | ISO first; `dd/mm/yyyy`, `dd-mm-yyyy`, `dd Mon yyyy`; **ambiguous `03/11/26` returns `AMBIGUOUS`**, never a guess |
| Incoterm | `incoterm(value)` | Upper-case, punctuation stripped, validated against Incoterms 2020 |
| Container | `container(value)` | Strip spaces and hyphens; 4 letters + 7 digits; ISO 6346 check digit |
| Party | `party(value)` | Case-fold, strip legal suffixes, collapse punctuation, `rapidfuzz` token-set ratio |
| HSN | `hsn(value)` | Digits only; length 6 or 8 |
| Description | `desc(value)` | Lower-case, expand units, strip punctuation, sort tokens |

Ambiguity is a first-class result, not an exception. A date that cannot be resolved deterministically produces a WARN asking for confirmation rather than a silently chosen day.

### 3.1 ISO 6346 check digit

```
letter values: A=10, B=12, C=13, ... skipping multiples of 11
weights: 2^position for positions 0..9
sum(value × 2^pos) mod 11, mod 10 = check digit
```

Unit-tested against known valid and invalid containers, including the common trick of a valid format with a wrong check digit.

## 4. Rule catalogue

Each rule is a pure function:

```python
def weight_match(ctx: CheckContext) -> CheckResult:
    values = [ctx.invoice.gross_kg, ctx.packing.gross_kg, ctx.bl.gross_kg]
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return CheckResult("DOCS_COMPLETE", BLOCK, "Weight cannot be compared: document missing")
    delta = max(present) - min(present)
    base = min(present)
    pct = delta / base * 100 if base else 0
    if pct <= ctx.tolerance.weight_pct:
        return CheckResult("WEIGHT_MATCH", PASS, ...)
    return CheckResult("WEIGHT_MATCH", WARN,
        f"Invoice {values[0]} kg vs packing list {values[1]} kg (+{pct:.2f}%)",
        fields=[...])
```

| Code | Rule | Severity | Tolerance |
|---|---|---|---|
| `LINE_AMOUNT` | qty × unit price = amount | BLOCK | ±0.01 |
| `INVOICE_TOTAL` | Σ lines + freight + insurance + other − discount = total | BLOCK | ±0.01 |
| `LINE_COUNT` | Printed item count = returned item count | BLOCK | exact |
| `QTY_MATCH` | Invoice qty = PL qty on matched lines | BLOCK | exact |
| `WEIGHT_MATCH` | Gross weight agrees across available documents | WARN | ±0.5% |
| `PACKAGES_MATCH` | Package count agrees across documents | BLOCK | exact |
| `CONTAINER_CHECK` | ISO 6346 valid, no duplicates, count matches B/L | BLOCK | exact |
| `PARTY_MATCH` | Buyer/consignee/notify consistent | WARN | ≥0.90 |
| `CURRENCY_MATCH` | ISO 4217, consistent | BLOCK | exact |
| `INCOTERM_VALID` | Valid 2020 term, freight terms consistent | WARN | exact |
| `DATE_SANITY` | Invoice ≤ today, ≤ B/L date, ≤ 90 days | WARN | exact |
| `UOM_CONSISTENCY` | Same UoM basis per line | WARN | exact |
| `DOCS_COMPLETE` | All required document types extracted | BLOCK | exact |

Rules return `PASS` too, and passes are stored. A shipment with 13 passes and no failures is a different artifact from one with 13 unknown checks, and the report should be able to tell.

## 5. Line matching

```
score = 0.50 × (part/HSN equal)
      + 0.30 × token_set_ratio(desc_a, desc_b) / 100
      + 0.20 × (qty equal)

accept ≥ 0.75, greedy by invoice line number
> 1 candidate → AMBIGUOUS (WARN, no auto-match)
0 candidates → UNMATCHED_INVOICE (BLOCK "not on packing list")
leftover PL → UNMATCHED_PACKING (WARN "packed but not invoiced")
```

Deterministic ordering matters: the same inputs must always produce the same pairs, or a re-run after an unrelated edit would reshuffle matches and confuse the reviewer.

A wrong automatic match is worse than a visible question. Ambiguity is surfaced with both candidate descriptions and the score, and the executive chooses. The choice is stored as `matched_line_id` on the invoice line and is preserved on re-run unless the underlying values change.

## 6. Check persistence and staleness

Every check row stores `input_hash` — SHA-256 over the normalised values it consumed, in a canonical order.

```python
input_hash = sha256(json.dumps({
    "code": code,
    "values": canonical_values,
    "tolerance": relevant_tolerance,
    "rule_version": rule_version,
}, sort_keys=True))
```

Resolution is keyed by `(shipment_id, code, subject_key, input_hash)`.

This produces the behaviour that matters:

| Event | Effect |
|---|---|
| Acknowledgement recorded | Row in `check_resolution` for the current hash |
| Unrelated field edited elsewhere | Weight check hash unchanged → acknowledgement stands |
| Weight edited | Hash changes → WARN reopens, old reason preserved in history but not applied |
| Tolerance changed in settings | Hash changes → all affected checks reopen |
| Rule version bumped | Hash changes → all checks of that code recompute |

Stale acknowledgements are the quiet failure mode of every review tool. This design makes them impossible rather than unlikely.

## 7. The gate

```python
def evaluate(shipment) -> GateResult:
    blockers = []
    if not docs_complete(shipment):        blockers.append(...)
    if any(f.status == SUGGESTED and f.required for f in fields):
        blockers.append(...)
    if any(c.severity == BLOCK for c in open_checks): blockers.append(...)
    for c in open_warns:
        if not resolution_matches(c): blockers.append(...)
    if shipment.status != READY:           blockers.append("Not approved")
    if shipment.approved_at and shipment.approved_at < max_field_update:
        blockers.append("Approval is older than the latest edit")
    return GateResult(ok=not blockers, blockers=blockers)
```

`GateResult.blockers` is a list of typed items (`code`, `message`, `field_id` or `document_id`), not prose. The UI renders the same list as a checklist; the export endpoint returns it as JSON on refusal. One implementation, two presentations.

### 7.1 Approval invalidation

`approved_at > max(field.updated_at)` is evaluated on every export, not only at submit. Any edit after approval returns the shipment to `NEEDS_REVIEW` and clears `approved_by`. The manager sees "Reopened: weight changed after approval" in the audit feed.

This is the rule that prevents the worst real-world outcome: a shipment approved on Monday, quietly corrected on Tuesday, filed on Wednesday.

## 8. Transitions

```
NEEDS_REVIEW --submit (gate clean)--> AWAITING_APPROVAL
AWAITING_APPROVAL --approve--> READY
AWAITING_APPROVAL --reject(reason)--> NEEDS_REVIEW
READY --export--> EXPORTED
READY --any field edit--> NEEDS_REVIEW  (approval void)
any --manager override BLOCK(reason)--> unchanged status, check resolved
```

| Action | Role | Preconditions |
|---|---|---|
| Submit | EXEC, MANAGER | Gate clean |
| Approve | MANAGER | Gate clean; not the same person who last edited? (see below) |
| Reject | MANAGER | Note required |
| Override BLOCK | MANAGER | Written reason ≥ 10 characters |
| Acknowledge WARN | EXEC, MANAGER | Reason required |
| Reopen | MANAGER | From READY |

**Self-approval.** In a 14-person team the manager may also prepare shipments. Blocking self-approval entirely would be impractical; instead, a shipment prepared by the approver is flagged in the audit and the reports ("approved by preparer"). This is a policy the client can tighten later; silently allowing it without a record is the unacceptable option.

## 9. UI

### 9.1 Checks panel

Collapsed by default when there are zero open checks; expanded when any exist. Sorted BLOCK → WARN → PASS.

```
⛔ PACKAGES_MATCH                      BLOCK
   Invoice 120 · Packing 120 · B/L 118
   [Go to field]

⚠ WEIGHT_MATCH                         WARN
   Invoice 3,120 kg · Packing 3,165 kg (+1.44%)
   [Acknowledge]  reason: ______________________
```

Clicking a check scrolls to and focuses the referenced field, and switches the viewer to the right page. Acknowledgement is inline, not a modal — the user must be able to see the numbers while typing the reason.

### 9.2 Action bar

| State | Left | Right |
|---|---|---|
| Fields open | "24 high-confidence · 3 need you" | `Confirm high-confidence` · `Submit` (disabled with reason) |
| Ready to submit | "All checks clear" | `Submit` |
| Awaiting approval | "Submitted by A. Sharma, 11:42" | `Approve` / `Reject` (manager) |
| Ready | "Approved by R. Iyer, 12:05" | `Export` |
| Exported | "Exported 12:07 · v3 template" | `Download again` |

Disabled buttons always carry a reason in a tooltip or adjacent text. A disabled button with no explanation is a dead end.

### 9.3 Manager queue

`/shipments?status=AWAITING_APPROVAL` is the queue. No separate screen: the list already has filters, and a manager's job is the same object with a different action. This saves a route and avoids a second data-fetching path.

## 10. API surface added

| Method | Route | Role | Notes |
|---|---|---|---|
| GET | `/api/shipments/{id}/checks` | both | With current resolutions |
| POST | `/api/checks/{id}/acknowledge` | both | `{reason}` |
| POST | `/api/checks/{id}/override` | MANAGER | `{reason}`, BLOCK only |
| POST | `/api/shipments/{id}/submit` | both | Gate evaluated |
| POST | `/api/shipments/{id}/approve` | MANAGER | `{decision, note}` |
| POST | `/api/shipments/{id}/reopen` | MANAGER | Voids approval |
| GET | `/api/shipments/{id}/gate` | both | Typed blocker list |
| PATCH | `/api/fields/{id}` | both | Recomputes checks, returns new gate |

Every mutation returns the updated gate snapshot so the UI never has to guess whether an action unblocked the shipment.

## 11. Tests

| Area | Cases | Examples |
|---|---|---|
| Normalisation | 20 | `03/11/26` ambiguous, `1,234.50`, `3,120.00 KGS`, `2,204.62 lb` |
| Rules | 45+ | Exact, boundary, outside tolerance, missing document, zero base, negative |
| Containers | 8 | Valid, wrong check digit, lowercase, duplicate, wrong length |
| Parties | 8 | `Ltd` vs `Limited`, transposed words, genuinely different entities |
| Matching | 12 | 1:1, ambiguous, unmatched both ways, qty mismatch, near-duplicate |
| Gate | 10 | Each blocker, stale resolution, approval invalidation |
| Authz | 6 | Exec cannot approve or override; manager can |
| Transitions | 6 | Reject returns to review; edit voids approval; export requires READY |

Property-style test worth writing: for any set of three weights where max − min ≤ tolerance × min, the rule returns PASS; above it, WARN. Generate 500 random triples.

## 12. Exit checklist

- [ ] SHP-24811 shows a weight WARN with all three values and the percentage.
- [ ] SHP-24817 shows a package BLOCK.
- [ ] SHP-24815 shows a missing-document BLOCK.
- [ ] An executive cannot approve or override; the API returns 403 and the UI hides it.
- [ ] Submitting with an open BLOCK returns a typed blocker list, not a generic error.
- [ ] Acknowledging a WARN requires a reason and is attributed.
- [ ] Editing a field after acknowledgement reopens the check if the value it consumed changed.
- [ ] Editing a field after approval voids the approval and returns the shipment to review.
- [ ] Manager override requires ≥10 characters and preserves the failed check in history.
- [ ] 45+ rule tests and 10 gate tests pass; coverage on `checks/` ≥ 90%.

## 13. Risks and gotchas

| Risk | Mitigation |
|---|---|
| Tolerance too tight → warning fatigue | 0.5% default, configurable; watch the precision metric |
| Tolerance too loose → missed errors | Report the delta on every WARN, even when passed |
| Hash includes irrelevant values → spurious reopen | Hash only the values the rule consumes, canonicalised |
| Float leakage in money | `Decimal` end to end; never `float()` in checks |
| Rule exceptions crash the pipeline | Engine catches per rule, records `RULE_ERROR` as WARN, never blocks the app |
| Manager approves own work silently | Flag `approved_by = prepared_by` in the audit and report |
| Check ordering changes between runs | Sort by severity then code; stable |

## 14. Handoff

Phase 6 can assume: `GET /shipments/{id}/gate` returns a typed blocker list, status transitions are enforced, and every export precondition is queryable. The export screen only needs to render the gate and the mapped rows.
