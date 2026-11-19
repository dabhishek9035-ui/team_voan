# Where it fails (from this run)

| Failure mode | Count | Examples |
|---|---|---|
| Key field unreadable (truth present, prediction null) | 0 |  |
| Field read wrongly | 0 |  |
| Link wrong or missed | 0 |  |
| Bad item auto-cleared (false accept) | 0 |  |
| No shared identifier available | 0 |  |
| Latency (s), n=0 | - | not recorded |
| Not auto-cleared (sent to a human or marked insufficient) | 12 of 15 | by design: duplicates, cases, INFERRED/UNMATCHED, notices, OTHER |
| Perceptual hashes alone cannot separate duplicates from unrelated screens | see fingerprint_check.json | gated behind a semantic ID match; screenshot-of-screenshot is missed by hashes and caught only by ticket_id |

AI-generated fakes that passed are listed under false accept; add the generator name via `source`.
Fakes in the synthetic corpus are hand-authored inconsistent mocks, not generator output: this table says nothing about AI-image fakes.
