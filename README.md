# Pratibimb: Member B core engine

Append-only evidence ledger with a hash-chained audit log. Standard library only (Python 3, SQLite).
Built and verified on Python 3.12.3 / SQLite 3.45.1.

## Verify everything (one command)

    ./run_tests.sh          # or: sh run_tests.sh

It runs the complete regression suite, an end-to-end demo and a mutation check.
The B8 baseline is documented in `VERIFICATION_B8.txt`.

## Try it

    python3 scripts/load_fixtures.py --db demo.db            # seed 11 synthetic scenarios; prints the anchor
    python3 scripts/verify_chain.py  --db demo.db --anchor <HEAD_HASH>
    python3 scripts/tamper.py --db demo.db --record-id <in_...> --column type_confidence --value 0.01
    python3 scripts/verify_chain.py  --db demo.db             # now reports the first broken link

    from pratibimb import Store
    s = Store("demo.db")
    ev = s.add_evidence(sender_id="s1", channel="telegram", received_at="2026-11-18T09:00:00+05:30",
                        sha256="a"*64, phash="ab"*8)
    it = s.add_interpretation(ev, "sarvam", "vision-x", "UPI_SUCCESS", 0.97,
                              {"amount": "40.00"}, {"amount": 0.95}, {"amount": "sarvam_extract"})
    s.verify()

## Layout

    pratibimb/   store.py (writes + reads), audit.py (verify), schema.py, validate.py, canon.py, fixtures.py
    scripts/     load_fixtures, verify_chain, tamper, demo_day1, build_fixtures, mutation_check
    fixtures/    scenarios.json (synthetic)
    tests/       111 tests
    docs/        DAY1_DESIGN.md, B7_CHALLENGE.md, privacy_and_retention.md

Read `docs/DAY1_DESIGN.md` first. The current package includes duplicate signals, deterministic linking, trip/case
projections, structured trust assessment, adaptive challenges, masking, and a
dependency-free WSGI API (`pratibimb.api.create_app`). The API intentionally
returns fields rather than raw images; raw-image requests must be explicitly
logged. `openapi.json` describes the stable read endpoints.

The engine never calls a claim true or false. `INFERRED`, `UNMATCHED`, low
confidence and missing fields remain reviewable outcomes. Calibration and drift
reporting are available through `scripts/calibrate.py`; their false-accept and
coverage numbers are only meaningful when labelled data resembles future cases.

Run the cross-platform verification command with:

    python run_all.py

The included B10 utility is ready for labelled data, but no real labelled
dataset is committed, so measured false-accept guarantees must not be claimed
from the synthetic fixtures.
