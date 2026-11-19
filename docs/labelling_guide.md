# C2: Labelling guide

One record per screenshot in `eval/data/ground_truth.json` (schema: `eval/schema/ground_truth.schema.json`).
Item ids must equal the system's `evidence_id` so predictions join on them.

## Collect
- Real screenshots only with consent. Mask names, phone numbers, UTRs before sharing with the team.
- Cover >= 2 ticket channels (WhatsApp bot, app, other), UPI success, pending/failed, bank SMS, cancellation/refund,
  bot error, scam-style refund message. Target 20 to 30 real items per context.
- Synthetic for what you cannot collect safely: exact duplicate, cropped, recompressed, screenshot-of-screenshot,
  out-of-window date, payment without ticket, wrong payee, partial amount.
- AI-generated fakes: at least **two generators**, put the name in `source` as `ai_fake:<generator>`.

## Fields per item
| Field | Rule |
|---|---|
| `screenshot_type` | one of the 9 codes |
| `fields` | the **correct** values visible on screen; omit what is not on screen (null is valid, an invented value is a labelling bug) |
| `journey_id` | same for every item of one journey (payment, ticket, SMS, refund) |
| `true_relationship` | `{to, type}`: EXACT only if a shared identifier is really on both screens; INFERRED if only context links them; NONE otherwise |
| `label` | clean, duplicate, cropped, out_of_window, no_ticket, fake, suspect_notice, unmatched, ambiguous |
| `should_clear` | false for anything that must not be auto-cleared (everything except genuinely clean EXACT items). This drives false-accept |

## Split
- **By journey**, never by item. Deterministic (see `make_dataset_from_fixtures.py`). Calibration -> Member B's thresholds. Held-out -> your reported numbers.
- Never look at held-out results to change thresholds or prompts.
- Share the first labelled batch with A and B by **Day 3**.

## Two-person check
Have a second person re-label 20% blind. Report agreement. Disagreements go to the labelling log, not silently fixed.

## Synthetic corpus mapping (data/ -> ground_truth.json)
Built by `eval/make_dataset_from_manifest.py`. `label` is the primary label by priority fake > suspect_notice > out_of_window > cropped > duplicate > no_ticket > unmatched > inferred > other > clean; all source labels stay in `labels_raw`. `true_relationship.type` may be MANUAL (coordinator action, not machine-scored). Real items added later follow the same schema; item ids must equal the system's `evidence_id`.
