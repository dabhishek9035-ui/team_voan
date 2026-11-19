# Member C checklist (7 days + definition of done)

| Day | Tasks |
|---|---|
| 1 | [ ] Book interviews  [ ] Join Day-0 with A  [ ] Labelling guide  [ ] Dashboard against B's fixtures |
| 2 | [ ] Interviews + notes  [ ] Start labelling  [ ] Roster + inbox on fixtures  [ ] Send `docs/api_assumptions.md` requirements to B |
| 3 | [ ] First labelled batch to A and B  [ ] Trail view  [ ] Baseline timing run |
| 4 | [ ] Decision buttons on `/decisions`  [ ] Claim sheet export  [ ] Synthetic + AI-fake generation (2 generators) |
| 5 | [ ] Audit + tamper view  [ ] Integrate A's live channel  [ ] Start deck  [ ] Dry run |
| 6 | [ ] Evaluation on held-out  [ ] Break-me station  [ ] Backup video  [ ] Deck complete |
| 7 | [ ] Freeze  [ ] Rehearse demo + Q&A twice  [ ] No-network fallback |

## Definition of done
- [ ] >= 1 real coordinator interviewed; baseline timed on the labelled set
- [ ] Labelled dataset with calibration + held-out; AI fakes from 2 generators labelled by source
- [ ] Dashboard shows relationship type and evidence level on every row; four records visible separately
- [ ] Claim sheet separates EXACT from INFERRED and UNMATCHED
- [ ] Three metrics reproducible in one command; false-accept always with coverage
- [ ] Where-it-fails table filled from real runs
- [ ] Break-me station and tamper demo rehearsed; backup video recorded
- [ ] Deck has no forbidden words and no unmeasured numbers (`make check`)

## Status after the corpus integration
- [x] Labelled starter dataset with calibration / held-out split (synthetic, 30 items)
- [x] Dashboard runs on the corpus; claim sheet export; tamper demo; break-me scoreboard
- [x] Harness reproducible with `make all` (plumbing run)
- [ ] Real consented screenshots, AI fakes from two generators, interviews, timed baseline
- [ ] Live API integration with B, predictions from A + B instead of the stand-in
