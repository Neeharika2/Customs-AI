# Phase 4 — Review interface

> **Day 4** · **Estimate:** 12 h · **Depends on:** Phase 3
> **Exit:** an executive can review, correct and confirm every field of SHP-24811 without seeing raw JSON, using keyboard or mouse, at desk width.

## 1. Objective

Build the screen the product is judged on. Everything before this phase is plumbing; everything after it depends on the quality of this one interaction.

The design target is not "a form with a PDF next to it". It is a review instrument: the document and the claim are always in the same viewport, the evidence for the active field is visible without a click, uncertainty is obvious without being noisy, and every action is one click or one key away.

## 2. Tasks

| # | Task | Est. | Output |
|---|---|---|---|
| 4.1 | Route, layout and data loading | 1.0 h | `/shipments/:id/review` |
| 4.2 | Page viewer: navigation, zoom, fit-to-width, thumbnails | 2.0 h | Document pane |
| 4.3 | Bounding-box overlay with scroll-into-view | 1.5 h | Active field highlighted |
| 4.4 | Field groups, confidence styling, check badges | 2.0 h | Fields pane |
| 4.5 | Evidence panel (quote, page, level) | 1.0 h | Source under the active field |
| 4.6 | Inline edit, optimistic update, 409 reconciliation | 1.5 h | Corrections persist |
| 4.7 | Correction history and audit drawer | 1.0 h | Who changed what, when |
| 4.8 | Keyboard model, uncertain-only filter, confirm-all | 1.5 h | Daily-use speed |
| 4.9 | Responsive stack below 1024 px | 0.5 h | Usable on a tablet |

## 3. Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ SHP-24811 · Company B · USD · FOB          NEEDS REVIEW     [Submit]  [···]  │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ [INV] [PL] [BL]    −  100%  [+]  │  INVOICE                        3 / 3     │
│                                  │  ─────────────────────────────────────    │
│  ┌────────────────────────────┐  │  Invoice number    INV-24811        ✓     │
│  │                            │  │  Invoice date      20 Oct 2026      ✓     │
│  │        page image          │  │  Currency          USD              ✓     │
│  │                            │  │  Incoterm          FOB              ✓     │
│  │      ┌──────────────┐      │  │  Gross weight      3,120 kg         ✓     │
│  │      │  highlight   │      │  │                                           │
│  │      └──────────────┘      │  │  LINE ITEMS                      3 / 3    │
│  │                            │  │  LED panel 40W   2,400  6.80  16,320  ✓  │
│  └────────────────────────────┘  │                                           │
│                                  │  CHECKS                          2 open  │
│  Source · page 1 · EXACT         │  ⚠ Weight 3,120 vs 3,165  +1.44%   [ack] │
│  "Gross weight 3120.00 KGS"      │  ⛔ Packages 120 vs 118             [fix] │
│                                  │                                           │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ ✓ Confirm high-confidence (24)     3 fields need you     [Submit for appr.]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

| Constraint | Value | Reason |
|---|---|---|
| Document pane width | 42–55% of the main area | Below 40% the quote becomes unreadable |
| Fields pane min width | 420 px | Two-column labels and values |
| Sticky action bar | 56 px, always visible | Submit state must never be off-screen |
| Page zoom | 50–200%, fit-to-width default | Scans vary wildly in density |
| Breakpoint | Stack below 1024 px | Desktop-first per the brief |

## 4. Viewer

**Rendering.** The browser receives a page image from a presigned URL, not a PDF. No PDF.js, no client-side parser, no risk of executing PDF JavaScript.

```tsx
<div ref={container} className="overflow-auto">
  <div style={{ width: renderedWidth, height: renderedHeight, position: "relative" }}>
    <img src={pageUrl} style={{ width: "100%" }} />
    {bbox && (
      <div
        className="absolute border-2 border-amber-500 bg-amber-200/20"
        style={{
          left: `${bbox.x0 * 100}%`, top: `${bbox.y0 * 100}%`,
          width: `${(bbox.x1 - bbox.x0) * 100}%`,
          height: `${(bbox.y1 - bbox.y0) * 100}%`,
        }}
      />
    )}
  </div>
</div>
```

Because coordinates are normalised, zoom is a CSS width change and the overlay follows automatically. No coordinate maths in the browser.

**Navigation.** Page thumbnails, `←`/`→` within the active document, `J`/`K` across documents, and a page indicator. Switching documents resets scroll to the page of the active field, not to page 1 — the user is following the data, not browsing.

**No bbox.** When `bbox` is null, the viewer scrolls to `page_idx` and shows a muted "page 1 · approximate location" chip. It never draws a guess.

## 5. Fields

### 5.1 Grouping

| Group | Fields |
|---|---|
| Parties | Supplier, buyer, consignee, notify party |
| Invoice | Number, date, currency, Incoterm, total, freight, insurance |
| Line items | Description, HSN, quantity, UoM, unit price, amount |
| Packing | Packages, package type, gross weight, net weight |
| Containers | Container numbers, seal numbers |

Groups collapse; the collapsed header shows a count of open issues (`Invoice · 2`). Line items render as a compact table with inline editing, not as a card per item — an invoice with 40 lines must remain scannable.

### 5.2 Field states

| State | Visual | Click |
|---|---|---|
| `SUGGESTED`, conf ≥ 0.85 | Neutral text, faint ✓ | Focus, edit |
| `SUGGESTED`, 0.55–0.85 | Amber underline, amber dot | Focus, evidence shown |
| `SUGGESTED`, < 0.55 | Red left rule, red dot | Focus, evidence shown |
| Referenced by open check | Row tinted, check chip inline | Jumps to the check |
| `CONFIRMED` | Neutral, ✓ glyph | Edit again if needed |
| `CORRECTED` | Neutral, small "edited" marker | Undo available |
| `NONE` / missing | Empty field, red, "required" | Opens manual entry |

The row never changes height when state changes. Layout shift during review is the fastest way to lose a user's place.

### 5.3 Editing

- Click or `Enter` enters edit mode; `Escape` cancels; `Enter` or blur saves.
- Values are validated on the client for *format* only; the server is authoritative.
- Saving is optimistic: the field updates immediately, the request runs, and a failure reverts with an inline message.
- A `409` (someone else edited) shows both values and asks which to keep. It never silently overwrites.
- Every save creates a `correction` row with old value, new value, actor and timestamp. Undo writes a new correction, it does not delete history.

### 5.4 Confirm-all

`Confirm high-confidence (24)` confirms every `SUGGESTED` field with `effective_conf ≥ 0.85` **that is not referenced by an open check**. It shows a preview count and is undoable as a batch. This is the single action that makes the 15-minute target plausible; without it the executive clicks 60 times per shipment.

## 6. Evidence panel

Under the viewer, always for the active field:

```
Source · page 1 · EXACT
"Gross weight 3120.00 KGS"
```

- `EXACT` — accent border, quote in monospace, field value bolded inside the quote.
- `CONTAINED` / `CLAIMED` — amber border, plus "not independently verified" text.
- `NONE` — red border, "no source located; enter manually".

Clicking the quote scrolls the viewer to the corresponding line. If the quote is too long, it truncates with an expand control; the matched value is always visible in the truncated form.

## 7. Keyboard model

| Key | Action | Scope |
|---|---|---|
| `Tab` / `Shift+Tab` | Next / previous field | Not while editing |
| `Enter` | Edit, then save and advance | Field |
| `Escape` | Cancel edit | Field |
| `J` / `K` | Next / previous document | Global |
| `1` `2` `3` | Invoice / packing list / B/L | Global |
| `←` / `→` | Previous / next page | Viewer focused |
| `Cmd/Ctrl+Z` | Undo last correction | Global, not in a text input |
| `Cmd/Ctrl+Enter` | Submit for approval | Global |
| `?` | Shortcut overlay | Global |

Shortcuts are suppressed when focus is in an input or textarea. The shortcut overlay is reachable from the `···` menu; a tool is allowed to be discoverable without a manual.

## 8. States

| State | Design |
|---|---|
| Loading | Two-pane skeleton matching final geometry; document area shimmer, field rows with fixed heights |
| No documents | Empty state with an "Upload documents" action |
| Extraction in progress | Per-document progress in the header; fields appear as each document completes |
| Document failed | Banner naming the document and reason, with "Enter manually" |
| No fields at all | Manual entry panel, not a blank screen |
| Save error | Inline row error, value retained, retry |
| Conflict | Dialog with both values, "keep mine" / "keep theirs" |
| Read-only (approved/exported) | Fields render disabled with a banner and "Reopen" for a manager |

## 9. Component inventory

| Component | Responsibility |
|---|---|
| `ReviewLayout` | Resizable two-pane shell, sticky bar |
| `DocumentViewer` | Page image, zoom, thumbnails, overlay slot |
| `BBoxOverlay` | Normalised rectangle, scroll-into-view |
| `EvidencePanel` | Quote, page, level, verification note |
| `FieldRow` | Label, value, state, edit, check chip |
| `LineItemsTable` | Compact editable table |
| `ChecksPanel` | Severity, message, action, acknowledgement state |
| `ActionBar` | Counts, confirm-all, submit, overflow |
| `ConflictDialog` | Two values, explicit choice |
| `AuditDrawer` | Chronological corrections and approvals |

## 10. Tests

| Test | Assertion |
|---|---|
| `test_review_loads_fields` | 3 documents, expected field count, no raw JSON in the DOM |
| `test_bbox_position` | Normalised box maps to the correct pixel rectangle at 100% and 150% |
| `test_no_bbox_shows_page_only` | No overlay element is rendered when `bbox` is null |
| `test_edit_persists` | PATCH returns the new value; reload shows it |
| `test_correction_logged` | Old and new values, actor and timestamp recorded |
| `test_conflict_409` | Stale update returns both values; no overwrite |
| `test_confirm_all_skips_flagged` | Fields referenced by an open check are not bulk-confirmed |
| `test_keyboard_navigation` | Tab order matches visual order; J/K switch documents |
| `test_shortcuts_ignored_in_inputs` | Typing "j" in a field does not navigate |
| `test_readonly_after_approval` | Fields disabled; manager can reopen |

## 11. Exit checklist

- [ ] SHP-24811 is reviewable end to end without opening developer tools.
- [ ] Active field's quote is visible without scrolling the fields pane.
- [ ] `EXACT` fields highlight; `CLAIMED` fields show page only, never a box.
- [ ] Confidence bands are distinguishable in greyscale and at 100% zoom.
- [ ] Editing persists, logs a correction and survives reload.
- [ ] Conflict path shows both values and never silently overwrites.
- [ ] Keyboard-only review is possible from first field to submit.
- [ ] `Cmd+Z` reverses the last correction.
- [ ] Layout stacks cleanly at 1024 px; no horizontal scroll at 768 px.
- [ ] Loading, empty, failed and read-only states all render.

## 12. Risks and gotchas

| Risk | Mitigation |
|---|---|
| Overlay drifts from the image on zoom | Position in percentages inside a relatively-positioned wrapper; never calculate pixels from natural size |
| Long invoices make the fields pane unusable | Collapsible groups, sticky group headers, virtualise beyond 50 rows if needed |
| Colour is the only signal | Dot + icon + text label on every state; test in greyscale |
| Optimistic update hides a server rejection | Revert on error with a visible message; never leave the UI ahead of the server |
| Keyboard shortcuts fire while typing | Scope handler; check `event.target` against form elements |
| Viewer becomes a memory hog | One page image mounted at a time; preload only the next page |

## 13. Handoff

Phase 5 can assume: fields are editable, corrections are logged, and the review screen can display a checks panel that is currently empty. The gate and approval actions belong to Phase 5 and slot into the action bar.
