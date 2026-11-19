# Member C evaluation kit

This folder contains the evaluation harness and the templates needed to collect problem evidence and compare review time. No coordinator interview, model output or timed study is supplied, so the repository contains no performance results.

## 1. Labeling guide

Use [labeling_guide.md](labeling_guide.md) when adding any consented real examples. Keep real files out of Git unless the participants approved that storage. Mask names, account details and phone numbers before sharing them. Write down provenance and consent scope.

The current corpus under `data/` is fully synthetic. Use it for page wiring, file-format checks and rehearsing the case flow. It cannot support a real-world accuracy or time-saving claim.

## 2. Evaluator input format

`evaluate.py` accepts a prediction JSON file with all evidence and claim cases from one split. It does not produce predictions or fill missing fields from ground truth.

```json
{
  "split": "heldout",
  "model_version": "extractor-and-linker-version",
  "decision_threshold": 0.85,
  "records": [
    {
      "evidence_id": "SYN-E-TEST-016",
      "screenshot_type": "TICKET_QR",
      "fields": {
        "amount": "60.00",
        "currency": "INR",
        "ticket_id": "SYN-TKT-TEST-101"
      }
    }
  ],
  "relationships": [
    {
      "from_evidence_id": "SYN-E-TEST-017",
      "to_evidence_id": "SYN-E-TEST-016",
      "type": "EXACT"
    }
  ],
  "claims": [
    {"claim_case_id": "SYN-CLAIM-TEST-001", "auto_clear": true}
  ]
}
```

The example above shows the shape only; a runnable file must include every evidence ID and every claim case ID for the selected split. Missing values should be `null`; do not infer them from the label file. Pair ordering is ignored when scoring relationships. Types are compared as `EXACT`, `INFERRED`, `MANUAL` and `UNMATCHED`.

Run from the repository root:

```powershell
python eval/evaluate.py --split heldout --predictions path/to/heldout_predictions.json --timings eval/timing_template.csv --output eval/results/heldout.json
```

Use the calibration split when selecting B's threshold. Freeze that threshold before scoring the held-out split. The false-accept result includes both the share of bad claims wrongly cleared and the share auto-cleared. The held-out result is valid only for cases resembling the calibration data.

The harness reports extraction/classification and field exact-match accuracy overall and grouped by screenshot type, app and language. It reports relationship precision, recall and F1 per relationship type. For coordinator time, it requires manual and system timings for every case in the selected split; otherwise it returns `not_measured` or `incomplete` instead of filling blanks with zero.

Every result is stamped `synthetic_only` and `valid_for_real_world_claims: false` when run against the bundled fixtures. Do not remove that caveat or present fixture scores as measured product performance.

## 3. Interview and baseline

Use [interview_guide.md](interview_guide.md) to speak with at least one real coordinator and a few travellers. Do not create an interview quote or baseline number until the interview and timing run have happened. The blank [timing_template.csv](timing_template.csv) has one row for each held-out synthetic case and is deliberately unfilled.

When measuring review time, use the same case set for manual review and the dashboard-assisted pass. Record seconds per case and errors/missed duplicates separately. Store the identity of interviewees outside this repository; only add anonymized notes with their consent.
