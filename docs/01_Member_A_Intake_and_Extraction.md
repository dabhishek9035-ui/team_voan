# Pratibimb: Work Distribution, File 1 of 3
## Member A: Intake, Extraction and Reply (the "front door")

**Your one-line mission:** turn any screenshot a traveller sends into a clean, typed **Interpretation** record, and turn the system's answer back into a reply card in the traveller's language.

**You own:** the chat channel, Sarvam Vision / Sarvam-105B / Sarvam Translate integration, QR decoding, screenshot classification, reply-card images, and the Day-0 feasibility test.

**You do not own:** linking, scoring, the ledger (Member B) or the dashboard, dataset and pitch (Member C).

> Assumptions: a 3-person team, a 7-day plan, Python backend. Tools are suggestions and can be swapped. All numeric targets below are **proposed**, not measured. Verify Sarvam model IDs and limits at docs.sarvam.ai before coding.

---

## 0. Project principles you must follow

1. Pratibimb does **not** establish truth. It establishes ownership, evidence relationships, consistency and accountability.
2. Four record types stay separate and immutable: **Evidence, Interpretation, Relationship, Decision**. You produce the first two. Never overwrite; a re-extraction is a new Interpretation.
3. Never use the word "fraud" or "verified" in anything user-facing. Use *extracted*, *corroborated*, *needs review*, *unverified*.
4. The user's only action is sending a screenshot. No forms, no typing, no app install.

---

## 1. Shared contract (identical in all three files)

### 1.1 Screenshot types (enum, owned by A, used by everyone)

| Code | Meaning |
|---|---|
| `TICKET_QR` | Metro QR ticket screen |
| `UPI_SUCCESS` | UPI payment success screen |
| `UPI_FAILED_PENDING` | Payment failed, pending or processing screen |
| `BANK_SMS` | Bank debit or credit alert |
| `REFUND_NOTICE` | Official-looking refund message or bank refund credit |
| `BOT_ERROR` | Metro bot message saying booking failed |
| `CLAIM_SUBMISSION` | Ticket sent as a reimbursement claim |
| `SUSPECT_NOTICE` | Message that looks like a refund or KYC scam, not an official notice |
| `OTHER` | Anything else |

### 1.2 Records (all append-only, all hash-chained by Member B's store)

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

### 1.3 The `fields{}` object you must produce (nulls allowed, never guess)

```
amount, currency, timestamp, utr, order_id, ticket_id, qr_payload,
origin_station, destination_station, fare, payer_name_masked, payee_name,
status_text, app_name, bank_name, language_detected
```
Every field has a matching entry in `field_confidence` (0 to 1) and a `source` (`sarvam_extract`, `sarvam_digitise`, `qr_decoder`, `llm_structuring`). If a field is unreadable, return `null` with confidence 0. **A null is correct. An invented value is a bug.**

### 1.4 API surface (Member B hosts the store; you call it)

| Call | Direction | Purpose |
|---|---|---|
| `store.add_evidence(...)` | A to B | Save the evidence record, returns `evidence_id` |
| `store.add_interpretation(...)` | A to B | Save the extraction |
| `GET /trips/{id}/summary` | B to A | Data for the reply card |
| `POST /challenge/{id}` | B to A | B asks you to send an adaptive evidence challenge message |

---

## 2. Deliverables

| # | Deliverable | Done when |
|---|---|---|
| A1 | **Day-0 feasibility report** | Real screenshots collected, field table filled, gate decision written |
| A2 | **Chat channel** (Telegram first, Twilio WhatsApp sandbox second) | A screenshot sent to the bot reaches `add_evidence` |
| A3 | **Sarvam Vision extraction service** | Per-type schemas return fields with confidences |
| A4 | **QR decoder + normalisers** | QR payload decoded locally; amounts, dates, UTRs normalised |
| A5 | **Screenshot classifier** | Type plus confidence for every image |
| A6 | **Fingerprinting** | SHA-256, perceptual hash and average hash computed at intake |
| A7 | **Reply-card generator** | PNG cards in the traveller's language |
| A8 | **Raw-image lifecycle worker** | Images deleted or locked per the retention rule |
| A9 | **Extraction test set + scoring script** | Field accuracy per type, reproducible |

---

## 3. Detailed tasks

### A1. Day-0 feasibility gate (Day 1, first priority, blocks the whole team)

Run this before anything else. Team-wide decision depends on it.

1. Buy **5 real tickets** across at least two channels (the WhatsApp bot and the Namma Metro app; add a third such as Paytm if possible). Cancel one.
2. Screenshot everything: ticket, UPI success, bank SMS, cancellation, refund SMS, any bot error.
3. Fill this table from the real screens:

| Screen | Fields visible | QR decodable? | Shared identifier with another screen? | Language |
|---|---|---|---|---|

4. Run each screenshot through **Sarvam Vision Extract** and **Digitise**. Record: fields returned, fields missed, wrong values, latency per job.
5. Test duplicates: resend the same screenshot as (a) the exact file, (b) a cropped copy, (c) a recompressed copy, (d) a screenshot of the screenshot.
6. Write the result against the gate:

| Test | Required outcome |
|---|---|
| Ticket extraction | Readable fields and QR payload identified |
| Payment extraction | Amount, timestamp, UTR extracted where present |
| Sarvam suitability | Usable fields on real screenshots (English and Kannada), latency recorded |
| Cross-source linking | Whether a shared identifier exists |
| Duplicate detection | Exact and cropped versions both tested |
| Refund correlation | Whether a refund references the original transaction |
| Failure handling | Unmatched evidence preserved without inventing relationships |

**Decision (agree with B and C by end of Day 1):** proceed with exact linking / proceed with inferred linking (mandatory review) / reconsider scope. If Sarvam Vision fails on screenshots, use Digitise for raw text and Sarvam-105B for structuring, and keep Sarvam for translation and reasons.

Set numeric thresholds (for example, minimum field accuracy to proceed) **before** you look at results, and write them in the report.

### A2. Chat channel

- **Primary demo channel:** Telegram bot (setup in minutes). **Second:** Twilio WhatsApp sandbox. Production would use the WhatsApp Business API; check current group-access rules and state that users send or forward to the bot 1:1.
- Handle: single image, multiple images in one message, image-as-document, forwarded images, captions.
- Immediately reply "Received, processing" (Sarvam jobs are asynchronous), then send the final card when the job completes.
- Identify the sender by channel ID; map to a traveller via a one-time join code the coordinator shares (Member B's `trips` table). No typing required beyond tapping the join link once.
- Rate-limit and size-limit uploads. Reject non-images politely.

### A3. Sarvam Vision extraction service

- Use Document AI **Extract** with one JSON schema per screenshot type (schemas in a `/schemas` folder, versioned).
- Use **Digitise** as fallback and for storing raw text (`raw_text_ref`).
- Document AI is **job-based**: create job, poll status, fetch download URL. Build an async worker with timeouts, retries, and a "partially completed" path.
- Record `sarvam_job_id`, model version and latency on every Interpretation.
- Handle both English and Kannada (and Hindi) screenshots.
- Wrap the client so it can be swapped for a fallback extractor without touching other code.
- Check Sarvam's data-retention and residency terms and write one paragraph for Member C's privacy slide. Do not claim "private by design" until you have read them.

### A4. Local QR decoder and normalisers

- Decode the QR locally (for example OpenCV or pyzbar). Do not assume Sarvam decodes QR codes.
- Store `qr_payload` raw plus a parsed form if the format is understood. If the payload is opaque or signed, say so in the Interpretation (`qr_payload_parseable: false`).
- Normalisers: amounts (₹, commas, decimals), dates and times (12h/24h, Indian formats, Kannada numerals if seen), UTR/order ID cleaning (case, spaces, common OCR confusions like O/0 and I/1, logged as "corrected").

### A5. Screenshot classifier

- Step 1: cheap rules on extracted text (keywords, layout cues per app).
- Step 2: **Sarvam-105B** on extracted text for ambiguous cases, returning type, confidence and a one-line reason.
- Must include the `SUSPECT_NOTICE` class (refund-scam style messages exist; BMRCL itself warns about them).
- Below the confidence threshold, return `OTHER` with a flag, never a forced guess.

### A6. Fingerprinting

Compute at intake, store on Evidence:
- `sha256` of the exact file (exact resend, integrity).
- `phash` plus `ahash` perceptual fingerprints (cropped or recompressed reuse).
- Document in one paragraph: these are similarity signals, not integrity guarantees, and do **not** replace extracted IDs.
- Hand B a test set of image variants (exact, cropped, recompressed, screenshot-of-screenshot) with the Hamming distances you measured, so B can choose thresholds.

### A7. Reply-card generator

- Cards are **images** (users screenshot those too).
- Content per outcome:
  - Ticket received (linked type shown: EXACT/INFERRED)
  - Payment found, ticket missing, case opened with reference number
  - Needs more evidence (with the specific item requested and why)
  - Could not read (with what to resend)
- Language: detect or ask once (store preference), then translate fixed strings and B's plain-language reasons with **Sarvam Translate** (or Mayura for its supported languages). Pre-translate the fixed strings and cache them, so only dynamic reasons hit the API.
- Never show "verified" or "fraud". Use the evidence-level labels.
- Optional bonus only if time remains: Bulbul voice reply.

### A8. Raw-image lifecycle worker

- Process image, store extracted fields and fingerprints, then apply the retention rule agreed with B (raw image encrypted and locked until the case closes or a fixed period passes, then deleted). The exact period is a product decision to confirm.
- Write a deletion log entry. Test that deletion actually removes the file.

### A9. Extraction test set and scoring

- With C, build a labelled set (target 20 to 30 real masked screenshots per context plus synthetic).
- Script outputs per-type, per-app, per-language field accuracy and the unreadable rate. Re-runnable in one command.

---

## 4. Day-by-day plan

| Day | Tasks | Output |
|---|---|---|
| **1** | A1 Day-0 gate (morning). Agree gate decision with B and C (afternoon). Start A2. | Feasibility report, go/no-go |
| **2** | A2 channel working end to end. A3 Extract on 20 screenshots. A4 QR decoder. **Publish 10 fixture Interpretations** to B and C. | Fixtures unblock the team |
| **3** | A3 schemas for all types, async worker. A5 classifier. A6 fingerprints. | Typed Interpretations for all types |
| **4** | A7 reply cards (English, then Kannada and Hindi). Wire B's summary endpoint. | Cards for every outcome |
| **5** | A8 lifecycle worker. Challenge message flow with B. Integration with C's dashboard. | Full loop working |
| **6** | A9 scoring runs. Fix top extraction failures. Supply fake and tampered samples to C for the break-me station. | Accuracy numbers |
| **7** | Freeze. Demo channel rehearsal. Latency fallback ("processing" card). Backup recorded run. | Demo-ready |

---

## 5. Dependencies and hand-offs

| You need from | What | By |
|---|---|---|
| B | `store.add_evidence`, `add_interpretation` stubs | Day 1 end |
| B | Retention rule, challenge message spec | Day 3 |
| C | Labelled screenshot set, join-code flow design | Day 2 |
| **You give B/C** | Day-0 report, 10 fixtures (Day 2), fingerprint distance data (Day 3) | as listed |

---

## 6. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Sarvam Vision weak on phone screenshots | Digitise for raw text plus Sarvam-105B structuring; or a general vision model for extraction, Sarvam kept for translation and reasons |
| Async latency hurts the live demo | "Processing" card at once, pre-warmed examples, one pre-recorded run |
| WhatsApp sandbox limits | Telegram as the demo channel |
| QR payload opaque | Use it only as a duplicate key, never as a validity claim |
| Hallucinated fields from structuring LLM | Fields must appear in raw text or be null; add a check that every returned value occurs in the extracted text |
| Kannada numerals or mixed scripts misread | Test early; flag low-confidence fields instead of normalising silently |

## 7. Definition of done

- [ ] Day-0 report written, thresholds set before testing, decision agreed
- [ ] Any screenshot sent to the bot produces Evidence plus Interpretation within the agreed latency
- [ ] Every field is either supported by the text or null
- [ ] Classifier handles all enum types including `SUSPECT_NOTICE`
- [ ] Exact, cropped and recompressed duplicates produce usable fingerprints
- [ ] Reply cards render in English plus at least Kannada or Hindi, with no forbidden words
- [ ] Raw-image deletion tested
- [ ] Scoring script reproduces per-type accuracy in one command
