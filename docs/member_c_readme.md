# Pratibimb: Member C workspace (product, evaluation, pitch)

Everything Member C owns: **C1** problem proof, **C2** labelled dataset, **C3** coordinator dashboard, **C4** claim sheet,
**C5** evaluation harness, **C6** break-me station + tamper demo, **C7** demo script, **C8** deck.

Status: runs end to end today on the **synthetic corpus in `data/`** (30 screenshots). Nothing here is a measured result about the real system.

## Quick start
```bash
pip install -r requirements.txt
make all              # dataset -> stand-in predictions -> fingerprint/QR checks -> eval -> export -> lint -> tests
make dashboard        # streamlit; default source = Synthetic dataset; Live API (Member B) in the sidebar
```
Single steps: `make dataset | standin | checks | eval | selftest | export | tamper | check | test`.

## Layout
```
data/        synthetic corpus: screenshots/, manifest.json, relationships.json, demo_cases.json, splits.json, fingerprints
standin/     rule-based reference engine (links, flags, levels, decisions) + loader + fingerprints. Stand-in for Member B.
dashboard/   app.py (Roster, Exceptions inbox, Trail, Demo cases, Audit, Claim sheet, Break me, Results), client.py
             (SyntheticClient, FixtureClient, ApiClient: same methods, switch in the sidebar)
eval/        make_dataset_from_manifest.py, make_predictions_standin.py, run_eval.py (3 metrics + where-it-fails),
             fingerprint_check.py, qr_decode_check.py, schema/, data/, results/
export/       claims.py (CSV + XLSX, relationship types colour-marked, never merged)
breakme/     scoreboard.py (append-only attempts log), safe_items.md (5 backup items)
tamper/      tamper_demo.py (offline chain-break demo)
tools/       check_forbidden.py
fixtures/    Member B's earlier generator + fixtures (still supported as dashboard sources)
docs/        data_notes.md (read first), interview guide, labelling guide, baseline protocol, demo script, judge Q&A,
             limits, deck outline, API assumptions + requirements for B, 7-day checklist
```

## What is real vs placeholder
| Piece | State |
|---|---|
| Dataset | 30 synthetic items (15 calibration / 15 held-out), English + Kannada, 4 relationship types, 4 image variants. Not a benchmark |
| Dashboard | works on the corpus; relationships are the authored ones, flags/levels from the stand-in engine. Raw image only behind a logged "dev only" action |
| Eval harness | scorer works (selftest); `make eval` runs on **stand-in predictions with oracle fields**, so the banner says plumbing only |
| Live API client | written against the contract; response shapes are assumptions (docs/api_assumptions.md), confirm with B |
| Fingerprint + QR checks | measured on the corpus: SHA-256 matches 30/30, QR decodes 10/10 (clean synthetic), perceptual hashes do not separate unrelated screens (see data_notes.md) |
| Interviews, baseline timing, AI fakes, real screenshots | still yours; templates provided, deck figures stay `[MEASURED: ...]` until then |

## Hand-offs
- **To A:** `data/` + `eval/data/ground_truth.json` (labelled batch with field truth per item) and `data/fingerprint_distances.json`.
- **To B:** `docs/api_assumptions.md` requirements, `data/relationships.json` as expected links, `eval/data/evaluation_cases.json` for calibration.
- **From B/A (needed for a real run):** predictions in the format in `eval/run_eval.py`, replacing `eval/data/predictions.json`.

## Rules that decide what you may say
1. Pratibimb establishes ownership, evidence relationships, consistency and accountability. It does not establish truth.
2. Never use "fraud", "verified" (unless independently verified for that attribute) or "proof" about the product's output (`make check`).
3. Report only what is measured, with n. False-accept is always reported with coverage.
4. Never tune on the held-out split. Report the stand-in run as plumbing, never as accuracy.
