# Notes on the synthetic corpus (data/) and what we did with it

Source: `data.zip` (30 hand-authored screenshots, 15 calibration / 15 held-out, two trip windows, English + Kannada).
Everything is synthetic and watermarked. It is a plumbing and demo corpus, **not** a benchmark.

## What was wired in
| Piece | How |
|---|---|
| `eval/data/ground_truth.json` | built by `eval/make_dataset_from_manifest.py` from `manifest.json` + `relationships.json`; split taken from `splits.json` |
| `eval/data/evaluation_cases.json` | **derived by us**: `data/README.md` lists this file but it was not in the zip |
| Dashboard source "Synthetic dataset" | `SyntheticClient` builds a hash-chained ledger in memory (evidence, interpretation, authored relationships, cases) |
| Flags, reasons, levels, clear / needs_review | `standin/engine.py`, rules over extracted fields; reads no labels |
| `eval/data/predictions.json` | `eval/make_predictions_standin.py`: engine run per split on **oracle fields** |
| Fingerprint and QR checks | `eval/fingerprint_check.py`, `eval/qr_decode_check.py` |

## Decisions we made (change them if you disagree)
1. **Link direction** follows `relationships.json`: bank SMS -> payment -> ticket, claim -> ticket, bot error / refund -> failed payment, duplicate -> original. Item-level truth = the relationship whose `from` is the item; anchors (a lone ticket, a failed payment) have type NONE.
2. **MANUAL** (`SYN-E-TEST-026`, claim with fare 80 vs ticket 60) is an authored coordinator action. A machine cannot produce it, so the scorer lists it as "not machine-scorable" instead of counting a miss. The stand-in engine links that claim EXACT by ticket ID and flags `fare_mismatch`, so it is still not cleared.
3. **should_clear** is true for 7 of 30 items (CAL-001..004, TEST-016..018): clean, EXACT, auto-clear eligible. A later duplicate or a bad claim pointing at a clean ticket does not make the ticket unclearable. Inferred pairs, duplicates, cases, fakes, notices and OTHER never clear.
4. **Trip-less items** (suspect notices and OTHER have `trip_id: null`) are assigned to the trip whose date matches `received_at`. The real system would use the join code.
5. **OTHER** screenshots get `insufficient`, count in the total, and are hidden from the inbox (not claim-related).

## Findings worth saying out loud
- **Perceptual hashes cannot stand alone here.** On the calibration split the one cropped duplicate sits at pHash 6 / aHash 2, while many unrelated screens sit at pHash <= 2 and aHash 0 (they share a template). Any threshold that catches the duplicate also flags unrelated pairs (`eval/results/fingerprint_check.json`). So similarity is used only next to a ticket-ID match (as B's brief says), and the **screenshot-of-screenshot** variant (pHash 24) is caught only by the ticket ID.
- One aHash recomputes 1 bit off the manifest (`SYN-E-CAL-014`), probably a Pillow/OpenCV version difference. SHA-256 matches for all 30. Fine for similarity signals, a reminder that they are not identifiers.
- Local QR decode: all 10 ticket images decode to the ground-truth payload, including cropped, recompressed and screenshot-of-screenshot. Synthetic QR codes are clean, so this is not a real-world QR rate.
- The two "fake" items are hand-authored inconsistent mocks, **not** AI-generator output. The requirement for fakes from two generators is still open.
- The stand-in engine's rules were written after reading both splits. Its held-out numbers are plumbing checks, not blind results.

## Still to collect (nothing here replaces it)
Real consented masked screenshots (20 to 30 per context), AI fakes from two generators labelled `ai_fake:<generator>`, interviews, and the timed manual baseline (`eval/data/timing.csv`).
