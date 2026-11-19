# Pratibimb: Work Distribution, File 3 of 3
## Member C: Coordinator Product, Evidence of the Problem, Evaluation and Pitch (the "proof")

**Your one-line mission:** prove the problem is real, give the coordinator a screen where they review only what does not balance, measure how well the system works honestly, and tell the story to the judges.

**You own:** user interviews, the labelled dataset, the coordinator dashboard (roster, exceptions inbox, claim sheet, audit view), the evaluation harness and the three reported numbers, the "break me" station, the demo script and the pitch deck.

**You do not own:** screenshot reading and chat channel (Member A), or the ledger, linking and trust logic (Member B). You consume their APIs.

> Assumptions: a 3-person team, a 7-day plan. All numeric targets are **proposed**, not measured. Report only what you measure.

---

## 0. Non-negotiable principles (they decide what you may claim on stage)

1. Pratibimb does **not** establish truth. It establishes **ownership, evidence relationships, consistency and accountability.** Say this early in the pitch; it is the answer to the judges' hardest question.
2. **Four separate records:** Evidence (what was submitted), Interpretation (what was extracted), Relationship (why items were linked), Decision (what a human decided). The UI must show them separately, never as one blended "status."
3. **Evidence levels**, scoped to a specific attribute: Extracted, Corroborated, Independently verified. A bank statement can verify a debit, not ticket issuance.
4. **Relationship types** visible in the inbox and exported sheet: EXACT, INFERRED, MANUAL, UNMATCHED.
5. Forbidden words in UI and pitch about the product's output: "fraud", "verified" (unless truly independently verified), "proof". Use *unverified*, *needs review*, *corroborated*.
6. State limits yourself before the judges find them (section 8).

---

## 1. Shared contract (identical in all three files)

### 1.1 Screenshot types
`TICKET_QR, UPI_SUCCESS, UPI_FAILED_PENDING, BANK_SMS, REFUND_NOTICE, BOT_ERROR, CLAIM_SUBMISSION, SUSPECT_NOTICE, OTHER`

### 1.2 Records (append-only, hash-chained by Member B)

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

### 1.3 Endpoints you call (hosted by Member B)

| Endpoint | Purpose |
|---|---|
| `POST /trips`, `POST /trips/{id}/join-code` | Create a trip, get the join code to share |
| `GET /trips/{id}/summary` | Roster and counts |
| `GET /trips/{id}/inbox` | Exceptions with reasons |
| `GET /records/{id}/trail` | Full evidence trail for one item |
| `POST /decisions` | Approve, request proof, reject, link manually |
| `GET /audit/verify` | Hash-chain check |
| `GET /export/claims?trip_id=` | Claim sheet |

---

## 2. Deliverables

| # | Deliverable | Done when |
|---|---|---|
| C1 | **Problem proof** (interviews and baseline) | At least one real coordinator interviewed; baseline timed |
| C2 | **Labelled dataset** | 20 to 30 masked real screenshots per context plus synthetic, with ground-truth labels and links |
| C3 | **Coordinator dashboard** | Roster, exceptions inbox, trail view, decision buttons, audit view |
| C4 | **Claim sheet export** | Includes relationship type and evidence level per row |
| C5 | **Evaluation harness** | Three metrics reproducible in one command |
| C6 | **"Break me" station and tamper demo** | Judges can try to fool it; chain break is visible |
| C7 | **Demo script and backup recording** | Rehearsed three-minute flow |
| C8 | **Pitch deck** | Problem, proof, redesign, evidence model, results, limits |

---

## 3. Detailed tasks

### C1. Prove where it breaks (Day 1 start, runs in parallel with Day-0)

Interview **at least one real coordinator** (an HR or admin person who reimburses commutes, an event organiser, a class representative, a trek leader). Aim for three if possible. Ask:

1. How many ticket or payment screenshots do you handle per week?
2. How many hours per week do you spend checking and chasing?
3. When did something last go missing, get reused or turn out wrong? What did it cost?
4. How do you find an old screenshot? What happens at handover?
5. When you doubt a screenshot, what do you actually do?
6. Which of these hurts most: knowing who has a ticket, handling failed payments, or checking claims?

Also interview or survey a few **travellers** about failed payments: how often, how long the refund took, what they sent to whom.

Time a human on the same labelled set (C2) doing the coordinator's job manually. **That is your baseline.** Record time, errors and missed duplicates.

Use real public evidence of the problem carefully: complaint-site posts about "debited, no ticket" exist, but they are **anecdotes, not a measured rate.** Cite them as illustrations only.

### C2. Labelled dataset

- Collect with consent and **mask** personal details before sharing with the team.
- Cover: ticket screens from at least two channels (WhatsApp bot, app, other), UPI success, pending or failed screens, bank SMS, cancellation and refund messages, bot error messages, and scam-style refund messages.
- Add **synthetic** items for variants you cannot collect safely: exact duplicates, cropped duplicates, recompressed copies, screenshot-of-screenshot, out-of-window dates, payment without ticket, wrong payee, partial amount, and AI-generated fakes (use at least two image generators, label which).
- Ground-truth file per item: screenshot type, correct field values, which items belong to the same journey, the **true relationship type** (EXACT, INFERRED, none), and a label: clean, duplicate, cropped, out-of-window, no-ticket, fake, suspect notice.
- Split into **calibration** (for Member B's thresholds) and **held-out test** (for your reported numbers). Never tune on the test split.
- Share the first labelled batch with A and B by **Day 3**.

### C3. Coordinator dashboard

Keep it to what the coordinator needs. Suggested stack: a simple React or Streamlit front end against B's API. Four views:

| View | Contents |
|---|---|
| **Roster** | Per traveller: payment seen, ticket seen, link type, traveller's own assertion of travel (labelled as assertion). Counts: ready, pending, stuck |
| **Exceptions inbox** | Only items needing review. Each row: reason, relationship type, evidence level per attribute, earlier-sighting reference (as fields, not images). Buttons: Approve, Request proof, Reject, Link manually |
| **Trail view** | For one item: Evidence, Interpretation, Relationships, Decisions in four labelled panels, with timestamps and what changed afterwards |
| **Audit view** | Chain status from `/audit/verify`, plus a "tamper" demo button |

Design rules:
- Show relationship type and evidence level **on every row**; never collapse them into one "OK."
- Decisions record what the coordinator saw (`seen_snapshot_hash`), so the trail shows what they decided on.
- Raw images are not shown by default; an explicit "request raw image" action is logged by B.
- Show an "exceptions only" count prominently ("3 of 40 need review"). This is the headline benefit.
- Mobile-friendly if time allows (coordinators often work from a phone).

### C4. Claim sheet export

CSV and XLSX with columns: traveller, date, route, fare, ticket reference, payment reference, **relationship type**, **evidence level per attribute**, flags with reasons, coordinator decision, decision time. INFERRED and UNMATCHED rows are visibly marked, never merged with EXACT rows. Finance should be able to filter by relationship type.

### C5. Evaluation harness (the three numbers)

Run on the **held-out** split and report only what is measured.

| # | Metric | How |
|---|---|---|
| 1 | **Extraction and linking accuracy** | Per screenshot type, app and language: field accuracy from A's scorer; linking accuracy by relationship type against ground truth |
| 2 | **False-accept rate with coverage** | At B's chosen threshold: share of wrong or bad items wrongly cleared, and the share auto-cleared. Always report both together |
| 3 | **Coordinator time** | Time with Pratibimb vs the manual baseline from C1, on the same set |

Plus:
- An **honest "where it fails" table**: unreadable fields, ambiguous matches, AI fakes that pass, missing identifiers, latency.
- A **fake-resistance comparison** (optional but strong): a pixel-level edit detector vs the evidence-based approach, on fakes from at least two generators. Report both, including where each fails.
- State the caveat: the false-accept result holds only if new cases resemble the calibration data; show B's drift check.

### C6. "Break me" station and tamper demo

- A station where a judge sends any screenshot from their phone (or a fake they made) and sees the classification, the link type, the evidence level and the reasons.
- Keep a visible **scoreboard** of attempts and outcomes, including the ones that got through. Honesty here builds trust.
- Tamper demo: edit one past ledger row, run `/audit/verify`, show the chain break at the right row.
- Prepare 5 safe test items in advance (a duplicate, a cropped duplicate, an out-of-window ticket, a payment with no ticket, a suspect refund notice) in case judges hesitate.

### C7. Demo script (about 3 minutes)

| Step | Show | Say |
|---|---|---|
| 1. The mess | A chat of mixed screenshots with a duplicate, a payment with no ticket, an out-of-window ride | "This is what a coordinator scrolls today." |
| 2. Drop it in | Roster fills as screenshots are processed | "People keep screenshotting. Nothing changes for them." |
| 3. Inbox | Only the exceptions, each with a reason and a relationship type | "40 screenshots, 3 need a human." |
| 4. Trail | Open one item: Evidence, Interpretation, Relationship, Decision | "We separate what was sent from what we read, why we linked it, and who decided." |
| 5. Judge's turn | A judge sends a screenshot live | Classified and linked on screen |
| 6. Break me | A fake triggers an evidence challenge | "We don't claim it's true. We ask for more and say how well it's supported." |
| 7. Tamper | Edit a past row, chain breaks | "Nothing is silently overwritten." |

Record a **backup video** of the full run on Day 6 in case of network or API latency on the day.

### C8. Pitch deck (about 8 slides)

1. The problem: the bot issues the ticket, then nobody owns it (with real interview quote and baseline).
2. Where it breaks: three moments (before, during failure, after) plus duplicates as the shared engine.
3. The constraint: the screenshot is the way in; WhatsApp is a door, not the database.
4. The redesign: four separate records, relationship types, evidence levels.
5. Why Sarvam: Indian-language screenshots (Kannada, Hindi), extraction and translation of reasons and cards.
6. Results: the three measured numbers and the "where it fails" table.
7. Honest limits and threat model.
8. Future work and one slide on the same engine for society collections (shown, not built).

One-line pitch to open and close with:
> "Pratibimb doesn't claim a screenshot is true. It gives every screenshot an owner, a trail and an honest label for how well it's supported, in the language the traveller uses."

---

## 4. Day-by-day plan

| Day | Tasks | Output |
|---|---|---|
| **1** | Book interviews. Join the Day-0 gate (collect real screenshots with A). Write the labelling guide. Dashboard wireframes against B's fixtures. | Interviews scheduled, label schema |
| **2** | Conduct interviews. Start labelling. Dashboard roster and inbox on fixtures. Send inbox and decision requirements to B. | First interview notes, working roster |
| **3** | First labelled batch to A and B. Trail view. Baseline timing run. | Labelled set v1, baseline |
| **4** | Decision buttons wired to `/decisions`. Claim sheet export. Synthetic and AI-fake generation. | End-to-end dashboard |
| **5** | Audit and tamper view. Integrate with A's live channel. Start deck. Dry-run the demo. | Full loop on screen |
| **6** | Evaluation runs on the held-out split. Break-me station. Record backup video. Deck complete. | The three numbers, backup video |
| **7** | Freeze. Rehearse the demo and Q&A twice. Prepare printouts or a fallback for no-network. | Demo-ready |

---

## 5. Dependencies and hand-offs

| You need from | What | By |
|---|---|---|
| B | Fixtures, then live endpoints | Day 1 to 2 |
| B | Calibration script, false-accept and coverage output | Day 6 |
| A | Real screenshots from Day-0, scoring script | Day 1 to 2, Day 6 |
| **You give A/B** | Labelled batch (Day 3), inbox and decision requirements (Day 2), fake samples (Day 4 to 6) | as listed |

---

## 6. Judge Q&A to rehearse

| Question | Prepared answer |
|---|---|
| "Isn't a screenshot never proof?" | Correct. The screenshot is the claim. We establish ownership, relationships and consistency, and label how well each claim is supported. We never say "verified" unless an authoritative source confirmed that specific attribute. |
| "AI fakes have no edit artifacts." | We don't rely on pixels. We rely on evidence relationships, an adaptive evidence challenge, and human review. Here is where fakes still get through (show the table). |
| "Two fake screenshots can agree with each other." | Yes. That is why "corroborated" means consistent, not true, and why independently verified needs an external source for that specific attribute. |
| "What if there is no shared ID?" | Then links are INFERRED, never auto-cleared, always reviewed, and marked in the export. |
| "Why Sarvam?" | Indian-language screens and messages, plus translating reasons into the traveller's language. |
| "Privacy?" | Coordinator sees fields, not images; fingerprints for duplicate checks; raw images deleted per a retention rule. We use "masked fields plus fingerprints," not zero knowledge. |
| "Can it issue refunds or confirm travel?" | No. It structures evidence, tracks cases and records decisions. Travel is the traveller's assertion. |
| "Why not just use the metro app?" | The app issues tickets. We handle what happens after: who has what, what failed, who gets paid. |

---

## 7. Risks and fallbacks

| Risk | Fallback |
|---|---|
| No coordinator available for interview | Interview any group payer (event organiser, trek leader, college club); label results as small-sample |
| Dataset too small | Report n and confidence honestly; lean on synthetic with clear labels |
| Live demo latency or network failure | Backup video, pre-processed examples, "processing" states shown deliberately |
| Judges find a real failure | Point to the "where it fails" table and the scoreboard; honesty is the strength |
| Evaluation not finished | Cut dashboard polish, never the evaluation |
| Over-claiming under pressure | Use the forbidden-words list; rehearse the answers above |

## 8. Honest limits to state on stage

- A screenshot is a claim, not proof.
- "Travelled" is the traveller's own statement; we cannot see gate scans.
- We cannot issue refunds or confirm the operator's records.
- Corroboration shows consistency, not truth; two fabricated items can agree.
- The adaptive evidence challenge raises the cost of a fake but does not end it.
- Results hold only on data that resembles what we calibrated on.
- Facts about the metro bot (what it sends, how failures appear) come from our own Day-0 test and a small sample.

## 9. Definition of done

- [ ] At least one real coordinator interviewed; baseline timed on the labelled set
- [ ] Labelled dataset with calibration and held-out splits; AI fakes from two generators labelled by source
- [ ] Dashboard shows relationship type and evidence level on every row; four records visible separately in the trail
- [ ] Exported claim sheet separates EXACT from INFERRED and UNMATCHED
- [ ] Three metrics reproducible in one command; false-accept always reported with coverage
- [ ] "Where it fails" table filled from real runs
- [ ] Break-me station and tamper demo rehearsed; backup video recorded
- [ ] Deck contains no forbidden words and no unmeasured numbers
