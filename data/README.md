# Synthetic Pratibimb data

This folder contains a hand-authored, fully synthetic starter corpus for Member C's dashboard, labelling, evaluation-harness plumbing and demo work. The values are fixed in `generate_synthetic_dataset.py`; the generator uses no random values, real customer data or network calls.

## What is included

- **30 screenshot records:** 15 calibration records and 15 held-out records, split by separate trip windows and synthetic journey IDs.
- **All nine screenshot classes:** `TICKET_QR`, `UPI_SUCCESS`, `UPI_FAILED_PENDING`, `BANK_SMS`, `REFUND_NOTICE`, `BOT_ERROR`, `CLAIM_SUBMISSION`, `SUSPECT_NOTICE` and `OTHER`.
- **English and Kannada examples**, including a contextual-only payment/ticket pair that must remain `INFERRED` and require review.
- **Image variants:** a byte-for-byte duplicate, a four-pixel crop, a JPEG quality-42 re-encoding and a gallery-style screenshot of a screenshot.
- **All four relationship types:** `EXACT`, `INFERRED`, `MANUAL` and `UNMATCHED`, with explicit reasons and matched attributes.
- **Five dashboard case fixtures** in `demo_cases.json`, including a payment with no ticket, an inferred match, a manual link with a fare mismatch, an unmatched candidate and a clean exact-link example.
- **Claim-level evaluation labels** in `evaluation_cases.json`, including which examples are unsafe to auto-clear.
- **Explicit split membership** in `splits.json`; each relationship stays within one split.
- **Field truth and image fingerprints** in `manifest.json`, `ground_truth.csv` and `fingerprint_distances.json`.

## Files

| File | Use |
|---|---|
| `screenshots/` | Clearly watermarked PNG/JPEG mock screenshots; QR codes encode only `SYNTHETIC://...` payloads. |
| `manifest.json` | Main record-level ground truth, metadata, field values, split and relationship labels. |
| `ground_truth.csv` | Spreadsheet-friendly version of the record labels; JSON-valued columns are encoded as JSON strings. |
| `relationships.json` | Expected relationship pairs, types, bases, reasons and auto-clear eligibility. |
| `demo_cases.json` | Prepared coordinator inbox examples. `coordinator_decision` is null; no human decision is implied. |
| `evaluation_cases.json` | Claim-level synthetic labels for false-accept and coverage harness plumbing. |
| `splits.json` | Fixed calibration and held-out evidence IDs, grouped by trip. |
| `fingerprint_distances.json` | SHA-256 equality and measured pHash/aHash Hamming distances for the generated duplicate variants. |
| `generate_synthetic_dataset.py` | Deterministic generator and built-in consistency checks. |

## Ground truth and safe use

Every screenshot has a visible **SYNTHETIC DATA / NOT A REAL TRANSACTION** disclosure. Sender IDs, names, UTRs, order IDs, ticket IDs, QR payloads, timestamps and amounts are fabricated. Metro stations are used only to make the fictional journey legible. The reserved `.invalid` domain appears only in suspicious-message examples.

The two fabricated or inconsistent claim examples are manually authored UI mocks. They are **not** images produced by AI image generators, and the corpus does not claim generator provenance. A future evaluation that requires fakes from two image generators still needs those separately sourced and labelled samples.

Use the corpus to build screens, check data plumbing, demonstrate edge cases and confirm that the evaluator can read the intended labels. It is **not** a real-world accuracy benchmark: the scenarios are small, deliberately curated and much cleaner than real screenshots. Do not report model accuracy, false-accept rate, coordinator time savings, or generalize findings from this corpus. Keep any real coordinator baseline and consented data separate from these fixtures.

An `EXACT` fixture means the authored pair shares an explicit ticket/order/payment identifier, except duplicate variants where the shared ticket ID is accompanied by the relevant image-similarity signal. `INFERRED` means the authored pair is supported by context only and must never auto-clear. `MANUAL` records an explicit synthetic coordinator action, not an automated match. `UNMATCHED` preserves a candidate that lacks a reliable basis for linking.

Evidence levels are attribute-scoped. These examples never reach independent verification: for example, a bank-style mock can corroborate the synthetic debit details, but it cannot independently confirm that a ticket was issued or that travel occurred. No coordinator decision is pre-populated.

## Regenerate

From the repository root, run:

```powershell
python data/generate_synthetic_dataset.py
```

The generator needs Pillow, NumPy and OpenCV (`cv2`), plus a Kannada-capable font such as Windows Nirmala UI or Noto Sans Kannada. It writes the manifest, CSV, relationship/case fixtures, fingerprints and image files under this folder. All data values are specified directly in the script; the output does not depend on a random seed.
