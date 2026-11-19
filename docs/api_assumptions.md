# API shapes assumed by the dashboard (confirm with Member B on Day 2)

The brief fixes the endpoint list, not the JSON. `dashboard/client.py` (`ApiClient`) assumes the shapes below, which
`FixtureClient` also returns. If B's differ, change the client only; the UI does not move.

| Endpoint | Response used |
|---|---|
| `GET /trips` | `[{trip_id, name, window_start, window_end}]` (not in the brief's list: ask B, or hardcode the trip id) |
| `GET /trips/{id}/summary` | `{trip, counts{ready,pending,stuck,"no evidence yet"}, roster[{traveller, payment_seen, ticket_seen, link_type, state_machine_observed, traveller_asserts_travel, coordinator_decision}]}` |
| `GET /trips/{id}/inbox` | `{needs_review, total_screenshots, items[{evidence_id, screenshot_type, sender, amount, route, status, decision_support, reasons[], relationship_type, evidence_level{attribute: level}, earlier_sighting{evidence_id,sender,date}\|null, case_ref}]}` |
| `GET /records/{id}/trail` | `{evidence, interpretations[], relationships[], decisions[], later_changes[]}`; no image path by default |
| `POST /decisions` | body `{subject_ref, action: approved\|proof_requested\|rejected\|link_manually, decided_by, reason, link_to?}` |
| `GET /audit/verify` | `{ok, broken_index, kind, length}` |
| `GET /export/claims?trip_id=` | list of rows with the C4 columns |

# Requirements C sends to B (Day 2 hand-off)

**Inbox**
- One row per journey, not per screenshot (a payment linked from a ticket is reviewed via the ticket's row).
- Every row: structured reasons (flag names + params, A translates), relationship type, evidence level **per attribute**, earlier-sighting reference as fields.
- Headline counts: `needs_review` and `total_screenshots`.
- Items with a human decision of approved/rejected/link_manually leave the inbox; `proof_requested` stays, marked.

**Decisions**
- Store `seen_snapshot_hash` (hash of what the coordinator saw). `link_manually` creates a MANUAL Relationship that `supersedes` the previous one.
- Decisions are append-only; the trail must show what changed afterwards.

**Other**
- Raw-image access is a separate, logged action; the default API never returns images.
- Chain hash rule: tell C exactly how `record_hash` is computed so the offline tamper demo matches (client currently assumes `H(canon(record minus record_hash) + prev_hash)` as in B's fixture generator).
- Trip ids and a trips list endpoint.
- Predictions export for the harness: `{evidence_id: {screenshot_type, fields, relationship{to,type}, decision_support, latency_s}}`.

**Link direction for predictions export** (so the scorer can match targets): bank SMS -> payment -> ticket, claim -> ticket, bot error / refund -> failed payment, duplicate -> original ticket. A lone ticket or failed payment has no outgoing link (type UNMATCHED/NONE).
