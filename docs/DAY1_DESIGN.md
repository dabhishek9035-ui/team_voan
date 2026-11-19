# Day 1 design notes (Member B: Core Engine, Ledger and Trust)

Scope delivered: **B1** schema and append-only store, **B2** hash-chained audit log with tamper script,
hand-made fixtures, stubs for `add_evidence` / `add_interpretation` (fully working, not stubs),
plus relationship, decision and access-log writers that Day 2 to 5 build on.

## Decisions you should know about

| Decision | Choice | Why |
|---|---|---|
| Language / deps | Python 3 standard library only (`sqlite3`, `unittest`) | Runs anywhere, nothing to install, and everything here was actually executed and verified. Day 2's HTTP API will use `wsgiref` for the same reason; it can be swapped for FastAPI later without touching the store. |
| Chain scope | **One global chain** for all four record types, in write order | One linear order is simplest to verify and to explain. Per-trip chains would add nothing at this scale. |
| Hash | `record_hash = SHA-256(canonical_json(record_body) + prev_hash)`; first link uses 64 zeros | Canonical JSON = sorted keys, no whitespace, UTF-8 (Kannada is hashed as Kannada). |
| Append-only | No update/delete method exists **and** SQLite triggers abort UPDATE/DELETE on every table (including `INSERT OR REPLACE`) | Two independent layers. The triggers are a guard rail, not the security boundary; see limits. |
| Corrections | New row with `supersedes = old_id`. One successor per record (no branching). Current view = latest non-superseded. | Matches the spec. A re-extraction must stay on the same evidence. |
| Atomicity | Each write (record row + chain row) is one `BEGIN IMMEDIATE` transaction | A crash or rejected write cannot leave a record without a chain link. |

## Additive changes to the shared contract (backward compatible, tell A and C)

1. `Interpretation.field_source` (object): the per-field `source` that section 1.3 of A's file requires. Optional to read.
2. `Relationship.reason` (string, required): B4 says each relationship stores "a plain reason".
3. `Evidence.supersedes` and `created_at`, so evidence corrections also follow the supersede rule.
4. `fields{}` is normalised to all 16 keys on write. Missing keys become `null` with confidence `0`.
5. Stricter rules than the contract states, enforced on write: null field must have confidence 0; a present field needs confidence above 0 and a known source; EXACT/INFERRED must be `system:*`; MANUAL and every Decision must be `coordinator:*`. This is how "the machine never produces approved" is made structural.
6. `Evidence.status` is limited to `received` or `quarantined`. Later lifecycle events (image deleted) will be access-log entries on Day 3, not edits.
7. `cases` table exists but is empty; its logic is Day 4. The schema is **v0.1, not frozen** (freeze is Day 2 for response shapes, Day 7 for the schema).

## What the chain does and does not give you (say this on stage)

* It gives **tamper evidence**: editing, deleting, inserting or reordering any record makes `verify()` report the first broken link and why.
* It does **not** give tamper prevention. Someone with raw access to the database file can drop the triggers and rewrite everything. `scripts/tamper.py --mode rewrite` demonstrates exactly that: `verify()` passes, and only an **externally stored head hash** (the anchor) catches it. Print the anchor, email it, or put it on the slide.
* It is **not a blockchain**: one writer, no consensus, no distribution.
* A clean cut of the newest records is invisible without an anchor. A later write after such a cut shows up as a `chain_gap`.

## Break reasons returned by `verify()`

`chain_gap`, `chain_prev_mismatch`, `record_missing`, `record_prev_mismatch`, `record_modified`,
`chain_hash_mismatch`, `record_not_in_chain`, `length_mismatch`, `head_mismatch`.

## Fixtures (for Members A and C)

`fixtures/scenarios.json`: 11 scenarios, 21 evidence items, **all synthetic**. Covers the 8 required cases
(clean journey, payment with no ticket, exact duplicate, cropped duplicate, out-of-window ride, inferred-only link,
unmatched refund, suspect notice) plus cross-sender duplicate, ambiguous two-candidate refund and a manual link.
Every scenario carries an `expect` block (relationship types, dup layers, phash distance) that Day 2 to 4 tests assert against.
Duplicate scenarios reuse hashes on purpose, so load them one per store (`load_into(store, only=[name])`).
The data shapes are guesses until Member A's Day-0 report supplies real masked ones.

## Not done yet (by design)

| Day | Work |
|---|---|
| 2 | Semantic and exact-file duplicate layers (B3), HTTP endpoints from section 1.4 (B9), API freeze |
| 3 | Perceptual layer with real distance data, EXACT / INFERRED linking, masking rules |
| 4 | Cases and trip states, trust signals and abstention |
| 5 | Adaptive challenge, decisions endpoint, claim export |
| 6 | False-accept calibration, drift check |
| 7 | Schema freeze, regression run |
