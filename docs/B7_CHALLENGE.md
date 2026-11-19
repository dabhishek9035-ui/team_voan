# B7: Adaptive Evidence Challenge

Implemented in [`pratibimb/challenge.py`](../pratibimb/challenge.py) and exposed via `POST /challenge/{claim_ref}` and `POST /challenge-response/{challenge_id}` in [`pratibimb/api.py`](../pratibimb/api.py).

## 1. Trigger
A challenge is issued only when a claim's `decision_support` is `needs_review` or `insufficient` **and** a specific unresolved attribute is identified from the structured trust signals (`trust.assess`). Clear claims raise a `ValidationError` if challenged.

## 2. Rule Table (Explainable Selection)
`challenge.unresolved` maps the highest-priority unresolved signal to `(attribute, request_type, reason_code)`:

| Signal | Condition | Attribute | Request Type | Reason Code |
|---|---|---|---|---|
| `unreadable_key_field` / `low_extraction_confidence` | `"utr"` in fields | `utr` | `bank_sms` | `utr_unreadable` |
| `unreadable_key_field` / `low_extraction_confidence` | `"ticket_id"` or `"qr_payload"` in fields | `ticket_id` | `ticket_with_status_bar` | `ticket_fields_unreadable` |
| `unreadable_key_field` / `low_extraction_confidence` | other key fields | `amount_or_time` | `payment_history` | `amount_or_time_unreadable` |
| `no_counterpart` | `missing == "ticket"` | `ticket_issued` | `ticket_with_status_bar` | `no_ticket_seen` |
| `no_counterpart` | payment missing | `debit` | `payment_history` | `no_second_source_for_payment` |
| `inferred_link_only` | no `BANK_SMS` in claim | `debit` | `bank_sms` | `link_by_amount_time_only` |

Every structured `reason_code` and `request_type` produces plain-language message templates (`challenge.message_for`) that Member A can translate without letting an LLM invent reasons.

## 3. Response & No-Response Path
- **Response:** When the traveller submits a follow-up screenshot, it enters as ordinary `Evidence` -> `Interpretation` -> `Relationship` records. `challenge.auto_respond` (or `POST /challenge-response/{challenge_id}`) supersedes the `issued` challenge row with `status = "responded"` and `response_evidence_id`.
- **No response:** When `due_at` (`challenge_response_hours`, default `48h`) elapses without a response, `challenge.expire` supersedes the challenge row with `status = "no_response"`.
- **Never auto-rejected:** Neither expiry nor inability to respond writes a `Decision` or rejects a claim. `trust.assess` attaches the `challenge_no_response` informational signal and keeps the claim at `needs_review` ("unverified: needs review") for the human coordinator.

## 4. Threat Model (Stated Openly)
- **Defeats:** accidental omission, single pre-made fabricated screenshots (which fail when asked for a corroborating bank SMS or live status bar), and simple reuse.
- **Does NOT stop:** an adversary who generates a complete, internally consistent set of screenshots across multiple apps/sources. Corroboration measures consistency, not ground truth.
