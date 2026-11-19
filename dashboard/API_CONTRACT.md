# Member B API fields used by the dashboard

The project brief defines endpoint paths but not response bodies. The dashboard adapter uses the shapes below so A, B and C can integrate without guessing. The local fixture adapter already returns this shape. If B uses different names, update the server-side mapper once rather than adding endpoint-specific logic to the page.

## `GET /trips/{trip_id}/summary`

```json
{
  "trip_id": "trip-123",
  "trip_window": {"service_date": "2026-10-30"},
  "counts": {
    "traveller_count": 40,
    "evidence_count": 40,
    "ticket_screenshots": 36,
    "review_cases": 3
  },
  "roster": [
    {
      "sender_id": "traveller-1",
      "display_name": "Traveller 1",
      "evidence_count": 2,
      "payment_seen": true,
      "ticket_seen": true,
      "relationship_types": ["EXACT"],
      "travel_assertion": "Not provided",
      "observed_state": "Payment and ticket evidence seen",
      "evidence_ids": ["evidence-1", "evidence-2"]
    }
  ],
  "records": [
    {
      "evidence_id": "evidence-1",
      "trip_id": "trip-123",
      "sender_id": "traveller-1",
      "channel": "telegram",
      "received_at": "2026-10-30T09:02:00+05:30",
      "sha256": "…",
      "phash": "…",
      "ahash": "…",
      "screenshot_type": "UPI_SUCCESS",
      "fields": {"amount": "60.00", "currency": "INR"}
    }
  ],
  "relationships": [],
  "decisions": []
}
```

The summary returns masked fields only. `travel_assertion` is clearly a traveller statement. Do not return raw images in this endpoint.

## `GET /trips/{trip_id}/inbox`

Return either an array or `{ "items": [...] }`:

```json
{
  "items": [
    {
      "case_id": "case-1",
      "title": "Contextual payment and ticket match",
      "reason": "The amount and time align, but no shared identifier exists.",
      "evidence_ids": ["evidence-1", "evidence-2"],
      "relationship_type": "INFERRED",
      "decision_support": "needs_review",
      "evidence_levels": {"amount": "corroborated", "ticket_issued": "extracted", "travelled": "unverified"}
    }
  ]
}
```

## `GET /records/{id}/trail`

```json
{
  "evidence": {"evidence_id": "evidence-1", "trip_id": "trip-123", "sender_id": "traveller-1", "channel": "telegram", "received_at": "…", "sha256": "…", "phash": "…", "ahash": "…"},
  "interpretation": {"interp_id": "interpretation-1", "producer": "sarvam", "model_version": "…", "screenshot_type": "UPI_SUCCESS", "type_confidence": 0.98, "fields": {"amount": "60.00"}, "field_confidence": {"amount": 0.98}, "language_detected": "en"},
  "relationships": [{"rel_id": "relationship-1", "from_id": "evidence-1", "to_id": "evidence-2", "type": "EXACT", "basis": ["utr"], "score": 1.0, "reason": "Shared UTR", "auto_clear_eligible": true}],
  "decisions": []
}
```

`reason` is structured by B's signal logic. The dashboard displays it without inventing a new conclusion. Raw images stay hidden unless B offers a separately logged access action.

## `POST /decisions`

The coordinator action is explicit and bound to what the page showed:

```json
{
  "subject_ref": "case-1",
  "action": "proof_requested",
  "decided_by": "coordinator-1",
  "reason": "The UTR is unreadable; request the payment history screen.",
  "seen_snapshot_hash": "sha256-of-visible-case-evidence-and-relationships",
  "link_to_evidence_id": null
}
```

Actions used: `approve`, `proof_requested`, `reject`, `manual_link`. A manual link includes `link_to_evidence_id`. The page label for `proof_requested` is **Request evidence**.

## Audit and claim exports

- `GET /audit/verify`: `{ "valid": true|false, "record_count": n, "first_broken_record": id|null, "broken_index": n|null }`.
- `GET /export/claims?trip_id=…&format=csv|xlsx`: returns the requested file with relationship type and attribute-level evidence labels on every row.

The dashboard does not mutate the four immutable record types. It only posts coordinator Decisions through B's endpoint.
