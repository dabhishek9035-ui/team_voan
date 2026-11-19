# Member C coordinator dashboard

The dashboard is a dependency-free local web app. It supports the Member C demo flow with the synthetic corpus and includes a same-origin adapter for Member B's REST API.

## Run the fixture dashboard

From the repository root:

```powershell
python dashboard/server.py
```

Open `http://127.0.0.1:8765`. The server binds to loopback by default. The default `dashboard/config.json` keeps the app in fixture mode. In this mode:

- Sample decisions are held in memory and disappear when the process stops.
- The audit view builds a synthetic hash chain. Its tamper button changes only an in-memory copy.
- CSV and XLSX claim exports are generated locally using the Python standard library.
- Screenshot files are returned only after an explicit reveal action; that request is recorded in an in-memory access log.
- An uploaded judge image stays in the browser and is not transmitted. Classification is unavailable until Member A connects an intake/classification service.

## Connect Member B's API

Set `backend_url` in `config.json` to the local URL where B's API is listening and set `trip_id` (or `trip_ids`) to a trip created by B. Restart the dashboard server. The browser calls the dashboard's same-origin proxy, which forwards the documented requests to B. See [API_CONTRACT.md](API_CONTRACT.md) for the response fields this interface expects.

The live adapter reads summary, inbox, trail and audit endpoints; forwards coordinator decisions; and downloads B's claim export. It keeps raw-image access disabled until B supplies a logged-access endpoint. The synthetic break-me examples remain available in either mode and are always labelled as fixtures.

## Views

- **Trip overview:** roster, machine-observed evidence states and exception count. Travel remains a separate traveller assertion.
- **Exceptions inbox:** reason, relationship type, evidence level by attribute, evidence references and coordinator actions.
- **Evidence trail:** four separate Evidence, Interpretation, Relationship and Decision sections.
- **Claim sheet:** CSV/XLSX export with relationship types, attribute-level evidence labels, flags and any local-session decision.
- **Audit check:** Member B's live endpoint or the synthetic fixture-chain demonstration.
- **Break-me station:** five pre-authored examples. It shows expected fixture handling, not model results.

No external fonts, packages, upload service or real data are needed for fixture mode.
