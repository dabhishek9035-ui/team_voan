# Member C (Pratibimb) - one-command entry points
PY ?= python3
.PHONY: all setup dashboard dataset standin checks eval selftest export tamper check test
all: dataset standin checks eval export check test   ## rebuild everything on the synthetic corpus (plumbing run, not a result)
setup:       ## install dependencies
	pip install -r requirements.txt
dashboard:   ## coordinator UI (synthetic corpus by default; switch to the live API in the sidebar)
	streamlit run dashboard/app.py
dataset:     ## eval ground truth from data/ (splits from data/splits.json)
	$(PY) eval/make_dataset_from_manifest.py
standin:     ## predictions from the rule-based stand-in engine on ORACLE fields (plumbing only)
	$(PY) eval/make_predictions_standin.py
checks:      ## fingerprint integrity + threshold behaviour, local QR decode
	$(PY) eval/fingerprint_check.py
	$(PY) eval/qr_decode_check.py
eval:        ## three metrics on the held-out split from eval/data/predictions.json
	$(PY) eval/run_eval.py --split heldout
selftest:    ## validate the SCORER only (predictions = truth). Not a system result.
	$(PY) eval/run_eval.py --selftest
export:      ## claim sheets (CSV + XLSX), one pair per trip window
	$(PY) export/claims.py --synthetic
tamper:      ## edit a past ledger row in a COPY, show the chain break
	$(PY) tamper/tamper_demo.py
check:       ## forbidden-words lint (fraud / verified / proof)
	$(PY) tools/check_forbidden.py
test:
	$(PY) -m pytest -q tests
