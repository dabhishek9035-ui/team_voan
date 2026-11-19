# Pratibimb: Work Distribution, File 2 of 3
## Member B: Core Engine, Ledger and Trust (the "brain")

**Your one-line mission:** take typed Interpretations from Member A and turn them into an append-only record of **who owns what, which evidence relates to which, how well each claim is supported, and who decided what**, exposing it through an API that Members A and C consume.

**You own:** the data store, the four record types, linking logic, duplicate detection decisions, trip/obligation states, evidence levels, the trust assessment with reasons and abstention, the adaptive evidence challenge, the hash-chained audit log, and privacy/retention rules.

**You do not own:** screenshot reading, chat channel and reply cards (Member A), or dashboard, dataset, evaluation and pitch (Member C).

> Assumptions: a 3-person team, a 7-day plan, Python (FastAPI plus SQLite or Postgres). All numeric targets are **proposed**, not measured.

---

## 0. Non-negotiable principles

1. Pratibimb does **not** establish truth. It establishes ownership, evidence relationships, consistency and accountability.
2. **Four record types stay separate and immutable:**
   - **Evidence:** what the user submitted.
   - **Interpretation:** what the system extracted.
   - **Relationship:** why two pieces of evidence were linked.
   - **Decision:** what an authorised human decided.
   Never merge them into one mutable transaction row. Corrections are new records that point to the old one.
3. **Evidence levels** (always scoped to a specific claim attribute):

| Level | Meaning |
|---|---|
| Extracted | Fields successfully extracted from submitted evidence |
| Corroborated | Independent evidence sources agree on relevant transaction attributes |
| Independently verified | An authoritative source confirms **that specific** transaction or ticket |

   A bank statement can verify a *debit*, not *ticket issuance*. Store verification per attribute (for example `debit: verified`, `ticket_issued: not verified`).
4. **Relationship types survive everywhere** (store, API, dashboard, exported sheet): `EXACT`, `INFERRED`, `MANUAL`, `UNMATCHED`. INFERRED and UNMATCHED never auto-clear.
5. Assertions are labelled as assertions: "traveller asserts travel", "coordinator decision: approved". The machine never produces an "approved" or "travelled" state.
6. Never use "fraud" or "verified" in user-facing text. The system says *unverified*, *needs review*.

---

## 1. Shared contract (identical in all three files)

### 1.1 Screenshot types
`TICKET_QR, UPI_SUCCESS, UPI_FAILED_PENDING, BANK_SMS, REFUND_NOTICE, BOT_ERROR, CLAIM_SUBMISSION, SUSPECT_NOTICE, OTHER`

### 1.2 Records

```
Evidence       { evidence_id, trip_id?, sender_id, channel, received_at,
                 file_ref, sha256, phash, ahash?, status }
Interpretation { interp_id, evidence_id, producer, model_version, sarvam_job_id?,
                 screenshot_type, type_confidence, fields{}, field_confidence{},
                 raw_text_ref, language_detected, created_at, supersedes? }
Relationship   { rel_id, from_id, to_id, type: EXACT|INFERRED|MANUAL|UNMATCHED,
                 basis[], score, created_by, created_at, supersedes? }
Decision       { dec_id, subject_ref, action, decided_by, reason,
                 seen_snapshot_hash, created_at, supersedes? }
```
Every record also carries `prev_hash` and `record_hash` (your hash chain).

### 1.3 `fields{}` from Member A
`amount, currency, timestamp, utr, order_id, ticket_id, qr_payload, origin_station, destination_station, fare, payer_name_masked, payee_name, status_text, app_name, bank_name, language_detected`. Nulls are valid. Never assume a field exists.

### 1.4 API (you host; A and C consume)

| Endpoint | Used by | Purpose |
|---|---|---|
| `store.add_evidence`, `store.add_interpretation` (library or POST) | A | Ingest |
| `POST /trips`, `POST /trips/{id}/join-code` | C, A | Coordinator creates a trip, gets a join code |
| `GET /trips/{id}/summary` | A, C | Roster, counts, per-traveller state |
| `GET /trips/{id}/inbox` | C | Exceptions only, with reasons |
| `GET /records/{id}/trail` | C | Evidence, Interpretation, Relationships, Decisions for one item |
| `POST /decisions` | C | Coordinator approve, request proof, reject, link manually |
| `POST /challenge/{id}` | A | Trigger an adaptive evidence challenge message |
| `GET /audit/verify` | C | Hash-chain integrity check |
| `GET /export/claims?trip_id=` | C | Claim sheet with relationship types and evidence levels |

---

## 2. Deliverables

| # | Deliverable | Done when |
|---|---|---|
| B1 | **Schema and append-only store** | Four record types, no UPDATE or DELETE path, supersedes pointers |
| B2 | **Hash-chained audit log** | Verification endpoint detects any edit |
| B3 | **Duplicate detection engine** | Three layers with agreed thresholds |
| B4 | **Linking engine** | EXACT, INFERRED, MANUAL, UNMATCHED produced with basis and score |
| B5 | **Trip state view and case logic** | Payment with no ticket after N hours becomes a case |
| B6 | **Trust assessment and abstention** | Per-claim reasons, evidence level, "needs review" when unsure |
| B7 | **Adaptive evidence challenge** | Request, reason, and no-response path defined and working |
| B8 | **Privacy, masking and retention** | Fields-not-images access, retention rule, access log |
| B9 | **API and fixtures** | All endpoints in 1.4 live against fixture data |
| B10 | **False-accept calibration** | Threshold chosen on labelled data, with coverage reported |

---

## 3. Detailed tasks

### B1. Schema and append-only store

- Tables: `evidence, interpretations, relationships, decisions, trips, travellers, cases, audit_chain, access_log`.
- No UPDATE or DELETE on the four record tables. Corrections insert a new row with `supersedes = old_id`. Current view = latest non-superseded.
- Interpretations record producer and version, so a model upgrade is a new Interpretation, not an edit.
- Seed a **fixtures file** (JSON) from Member A's first 10 Interpretations so C can build against real shapes from Day 2. Until then, publish hand-written fixtures on Day 1.

### B2. Hash-chained audit log

- Every record write appends `record_hash = H(record_json + prev_hash)`. Chain per trip or global (choose one and document).
- `GET /audit/verify` recomputes and reports the first broken link.
- Provide a **tamper script** that edits one past row so C can run the live tamper demo. State plainly that the chain gives tamper evidence, not tamper prevention, and that it is not a blockchain.

### B3. Duplicate detection engine (three layers, kept separate)

| Layer | Key | Signal | Output |
|---|---|---|---|
| Semantic | Normalised `ticket_id`, `utr`, `order_id`, `qr_payload` | Strongest | Earlier sighting reference |
| Exact file | `sha256` | Exact resend | Same-file flag |
| Perceptual | `phash`/`ahash` within a Hamming threshold | Similarity only | "Looks similar to evidence #X" |

- Perceptual matches are **signals, not conclusions**. Use A's measured distance data to pick thresholds and report the false-positive behaviour.
- Same ID from the *same* sender (resend) is a different case from the *same* ID from a *different* sender. Output both distinctly with the earlier sighting's date and owner (visible to the coordinator as fields, not images).
- Neither fingerprint replaces extracted IDs.

### B4. Linking engine

Given an Interpretation, find candidate relationships to existing ones:

| Type | Rule (proposed) | Auto-clear? |
|---|---|---|
| **EXACT** | Shared transaction or ticket identifier | Eligible (if no other flag) |
| **INFERRED** | Amount, timestamp window, payer and journey context agree | Never; goes to coordinator |
| **MANUAL** | Coordinator explicitly links | n/a (a Decision) |
| **UNMATCHED** | Insufficient evidence | Preserved, shown, never forced |

- Each Relationship stores `basis[]` (which attributes matched), a score and a plain reason.
- The **Day-0 gate result decides the default**: exact linking if real shared identifiers exist; inferred-only with mandatory review otherwise. Build both paths; the gate chooses which is enabled.
- Tuneable windows (for example time tolerance between payment and ticket) live in config, not code.
- Ambiguity (two candidate matches) produces UNMATCHED with both candidates listed, not a coin flip.

### B5. Trip view and case logic

Machine-observed states only:

```
payment_seen → ticket_seen → linked (EXACT | INFERRED)
payment_seen (no ticket after N hours) → case_opened → refund_evidence_seen
```
Human or user assertions, stored separately and labelled:
- `traveller_asserts_travel` (self-report)
- `coordinator_decision: approved | rejected | proof_requested`

Case record: reference number, evidence list, age, last action. Cases are opened automatically but **resolved only by evidence plus human decision**. Add a stale-case flag (the real refund window in complaints is about 7 working days or more, so track elapsed time rather than assuming a number).

### B6. Trust assessment with reasons and abstention

Produce, per claim, an object (not a single score):

```
evidence_level: extracted | corroborated | independently_verified (per attribute)
relationship_type: EXACT | INFERRED | MANUAL | UNMATCHED
signals: [ {name, direction, weight, plain_reason} ]
decision_support: clear | needs_review | insufficient
```
- Signals (proposed): earlier sighting of ID, date outside window, fare/route mismatch, payer mismatch, low extraction confidence, perceptual similarity to other sender's evidence, unreadable key field, `SUSPECT_NOTICE` class.
- **Abstention is a first-class outcome.** Low confidence or conflicting signals route to the coordinator with the reason.
- Reasons are generated as structured data first; Member A turns them into language-specific text. Do not let a free-text LLM invent reasons that are not tied to a signal.
- Say in the UI what the level means: "corroborated" is consistency, not truth. Two fabricated screenshots can agree.

### B7. Adaptive evidence challenge (renamed from "liveness challenge")

Spec to implement and document:

| Question | Answer |
|---|---|
| What does it ask for? | The smallest extra item that would conflict with a weak claim: bank SMS, payment-app history list, or the ticket with status bar and time visible |
| Why? | The message states which check is unresolved ("UTR unreadable", "no second source for this payment") |
| When is it triggered? | By `needs_review` plus a specific unresolved attribute |
| What if the user can't provide it? | Claim stays "corroborated, unverified" and goes to the coordinator with the reason. **Never auto-rejected.** |
| Threat model (state openly) | Defeats accidental omission, single pre-made fakes, simple reuse. Does **not** stop someone who generates a full consistent set |

Implement request selection as a small rule table (unresolved attribute to request type) so it is explainable. Each challenge and response is an Evidence/Interpretation/Relationship chain like any other.

### B8. Privacy, masking and retention

- Coordinator API returns **fields**, not images. Raw-image access requires an explicit request that is written to `access_log` with who, when, why.
- Mask fields at the API layer (payer name partial, UTR partial, phone numbers hidden) unless a Decision requires the full value.
- Retention (proposed, confirm with a privacy or legal reviewer): raw image encrypted and access-controlled until the case closes or a fixed period elapses, then deleted; extracted fields and fingerprints retained per policy. Coordinate the deletion job with Member A.
- Write one page: what is stored, why, how long, who can see it. Member C uses it for the privacy slide. Do not claim "zero knowledge"; the honest term is "masked fields plus fingerprints."

### B9. API and fixtures

- Implement 1.4 endpoints. Keep response shapes stable from Day 2 so A and C can integrate.
- Publish an OpenAPI doc.
- Fixture dataset (hand-made plus A's real ones) must include: clean linked journey, payment with no ticket, exact duplicate, cropped duplicate, out-of-window ride, inferred-only link, unmatched refund, suspect notice.

### B10. False-accept calibration

- Using C's labelled set: choose the threshold for `clear` so the **false-accept rate** is as low as the data supports, and report **coverage** (share auto-cleared).
- Document the assumption: any guarantee holds only if new cases resemble the calibration data. Add a simple drift check (distribution of confidence and types vs calibration) and show it in the evaluation output.
- Provide C with a script that outputs the false-accept and coverage table.

---

## 4. Day-by-day plan

| Day | Tasks | Output |
|---|---|---|
| **1** | Day-0 gate with A and C. B1 schema. Publish hand-made fixtures. Stub `add_evidence`/`add_interpretation`. | Schema, fixtures, stubs |
| **2** | B1 finish. B2 hash chain. B9 endpoints on fixtures. B3 semantic and exact layers. | API live on fixtures |
| **3** | B3 perceptual layer with A's data. B4 EXACT and INFERRED linking. B8 masking rules. | Linking works on real Interpretations |
| **4** | B5 states and cases. B6 signals, reasons, abstention. | Inbox returns exceptions with reasons |
| **5** | B7 challenge flow with A. Decisions endpoint with C. Export with relationship types and evidence levels. | Full loop with dashboard |
| **6** | B10 calibration with C's labelled set. Drift check. Tamper script. Edge-case fixes. | False-accept and coverage table |
| **7** | Freeze schema. Regression tests. Audit verify rehearsal. | Stable demo backend |

---

## 5. Dependencies and hand-offs

| You need from | What | By |
|---|---|---|
| A | Day-0 report, 10 real fixtures | Day 1 to 2 |
| A | Fingerprint distance data | Day 3 |
| C | Labelled screenshot set, ground-truth links | Day 3 to 4 |
| C | Inbox and decision UI requirements | Day 2 |
| **You give A/C** | Stubs (Day 1), endpoints (Day 2), calibration script (Day 6) | as listed |

---

## 6. Risks and fallbacks

| Risk | Fallback |
|---|---|
| No shared identifiers exist | Inferred-only mode with mandatory review; demo shows honest handling |
| Perceptual hash false positives | Treat as a signal only; require a semantic or human check before any flag affects a claim |
| Ambiguous multi-match | UNMATCHED with candidate list |
| Over-flagging buries the coordinator | Tune on labelled set; report coverage; keep reasons short |
| Schema churn breaks A and C | Freeze response shapes on Day 2, version the API |
| Scope creep into scoring models | Keep signals rule-based and explainable; no learned black box |

## 7. Definition of done

- [ ] No code path updates or deletes the four record tables
- [ ] Editing any past row makes `/audit/verify` fail at the right link
- [ ] Exact, cropped and cross-sender duplicates produce distinct, reasoned outputs
- [ ] EXACT, INFERRED, MANUAL and UNMATCHED all appear in the API and the export
- [ ] Payment-without-ticket opens a case automatically; nothing auto-resolves it
- [ ] Every `needs_review` carries at least one structured, plain reason
- [ ] The challenge has a defined no-response path that never auto-rejects
- [ ] Coordinator API returns no raw images by default; access is logged
- [ ] False-accept and coverage table generated from the labelled set, with the drift caveat
