# Member C handoff

## Ready in this repository

- **Synthetic starter corpus:** 30 hand-authored screenshots, field labels, split membership, relationships, evaluation cases and measured duplicate-image hash distances. See `data/README.md`.
- **Coordinator dashboard:** local fixture mode with roster, exceptions inbox, four-part evidence trail, decision actions, claim sheet, audit tamper demo and break-me station. See `dashboard/README.md`.
- **CSV and XLSX claim export:** generated locally from fixture records. Coordinator actions in fixture mode remain in memory and do not change the source data.
- **Evaluation harness:** accepts a complete A/B prediction file, reports extraction/linking, false-accept with coverage and coordinator time, and refuses incomplete prediction coverage. See `eval/README.md`.
- **Research templates:** coordinator/traveller interview guide and an unfilled timing sheet.
- **Pitch:** an eight-slide browser presentation and a three-minute demo/Q&A script in `pitch/`.

## Run the dashboard

From the repository root:

```powershell
python dashboard/server.py
```

Then open `http://127.0.0.1:8765`. To connect Member B, set `backend_url` and `trip_id` in `dashboard/config.json`; the expected API response fields are listed in `dashboard/API_CONTRACT.md`.

## Evaluation command

After Member A and B produce predictions for every evidence and claim case in the held-out split:

```powershell
python eval/evaluate.py --split heldout --predictions path/to/heldout_predictions.json --timings eval/timing_template.csv --output eval/results/heldout.json
```

Use the calibration split to select B's threshold, then freeze it before evaluating held-out cases. The synthetic fixture output is always marked unsuitable for real-world performance claims.

## Evidence still needed

The following items require real work or services and are deliberately not simulated:

- A real coordinator interview and traveller conversations.
- A timed manual baseline on the same labelled cases as the dashboard run.
- Consented, masked real screenshots and real A/B model outputs.
- Measured extraction/linking accuracy, false-accept rate with coverage and coordinator time.
- A recorded backup demo after the A/B services are integrated.
- Adversarial screenshots with provenance from two actual image generators.

The pitch is an HTML slide deck; a PowerPoint export is not included. All figures currently shown are synthetic fixture counts, not product results.
