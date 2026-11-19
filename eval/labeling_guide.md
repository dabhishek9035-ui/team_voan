# Labeling guide

## Purpose

Create ground truth for screenshot type, visible values, evidence relationships and claim-level review outcomes. Labels describe what the image shows and how items relate; they do not establish whether a person actually travelled or whether an operator issued a ticket.

## Record per screenshot

For each consented, masked image, record:

- `evidence_id`, `trip_id` when known, sender pseudonym, channel and received time.
- Source provenance (`real_consented`, `synthetic_authored`, or another accurately named source) and consent scope.
- Screenshot class: `TICKET_QR`, `UPI_SUCCESS`, `UPI_FAILED_PENDING`, `BANK_SMS`, `REFUND_NOTICE`, `BOT_ERROR`, `CLAIM_SUBMISSION`, `SUSPECT_NOTICE` or `OTHER`.
- The exact visible field values for the shared field contract. Use `null` when absent or unreadable; do not repair OCR values in the ground truth without preserving the raw visible value separately.
- Language, app/context, journey group, and whether the image is an exact resend, crop, recompression or screenshot of a screenshot.
- Human labels such as `clean`, `duplicate`, `out_of_window`, `no_ticket`, `fake`, `suspect_notice`, `partial_amount` or `claim_mismatch`, with a short rationale and source provenance.

## Relationship labels

Record each expected pair once with its basis and a plain explanation:

- `EXACT`: a shared readable transaction or ticket identifier supports the relationship.
- `INFERRED`: contextual fields align but there is no shared identifier. Mark as mandatory review.
- `MANUAL`: an authorized coordinator explicitly linked the items. This records the coordinator's action, not a machine conclusion.
- `UNMATCHED`: insufficient or conflicting evidence. Preserve candidate IDs and why no link was made.

Do not turn perceptual similarity into an exact relationship by itself. It is a reuse signal. A bank record can support a debit attribute; it cannot establish ticket issuance or travel.

## Splits and evaluation

Group-split by traveller/journey/trip so related evidence and image variants do not leak across calibration and held-out sets. Freeze the threshold on calibration data before scoring the held-out split. Keep a separate manifest of provenance and consent. Report the number of real and synthetic examples in each group.

The bundled 30-item corpus is synthetic and already labelled. Use it to exercise the label schema and code paths, not to claim representative accuracy. The synthetic fake-like examples are hand-authored; do not give them AI-image-generator provenance.
