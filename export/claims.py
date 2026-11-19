"""
C4 claim sheet: CSV + XLSX. Columns: traveller, date, route, fare, ticket reference, payment reference,
relationship type, evidence level per attribute, flags with reasons, coordinator decision, decision time.
INFERRED / UNMATCHED rows are colour-marked and sorted AFTER EXACT/MANUAL; never merged.

  python export/claims.py --synthetic                 # data/ corpus, one file pair per trip window
  python export/claims.py --fixture fixtures/fixtures_exact.json --truth fixtures/ground_truth_exact.json
  python export/claims.py --api http://localhost:8000 --trip trip_001
"""
import argparse
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COLS = ["traveller", "date", "route", "fare", "ticket_reference", "payment_reference", "relationship_type",
        "evidence_level", "flags_with_reasons", "decision_support", "coordinator_decision", "decision_time"]
FILL = {"EXACT": "C6EFCE", "MANUAL": "BDD7EE", "INFERRED": "FFE699", "UNMATCHED": "D9D9D9"}


def to_xlsx_bytes(rows):
    from openpyxl.styles import PatternFill, Font
    df = pd.DataFrame(rows)
    df = df[[c for c in COLS if c in df.columns]]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="claims")
        ws = w.sheets["claims"]
        ws.auto_filter.ref = ws.dimensions       # finance can filter by relationship type
        ws.freeze_panes = "A2"
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ti = list(df.columns).index("relationship_type") + 1
        for row in ws.iter_rows(min_row=2):
            fill = FILL.get(row[ti - 1].value)
            if fill:
                row[ti - 1].fill = PatternFill("solid", fgColor=fill)
        for i, col in enumerate(df.columns, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(60, max(12, int(df[col].astype(str).str.len().max() or 10) + 2))
        n = pd.DataFrame({"note": ["Relationship types: EXACT = shared identifier; INFERRED = context only (reviewed); "
                                   "MANUAL = coordinator link; UNMATCHED = not enough evidence.",
                                   "Evidence levels describe consistency of submitted evidence, per attribute. "
                                   "'independently_verified' appears only if an authoritative source confirmed that attribute."]})
        n.to_excel(w, index=False, sheet_name="legend")
    return buf.getvalue()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture"); ap.add_argument("--truth"); ap.add_argument("--api"); ap.add_argument("--trip", default="trip_001")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "export"))
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT / "dashboard"))
    from client import ApiClient, FixtureClient, SyntheticClient
    if a.synthetic:
        cl = SyntheticClient()
        for t in cl.trips_list():
            rows = cl.claims(t["trip_id"])
            df = pd.DataFrame(rows)[COLS]
            df.to_csv(f"{a.out}/claims_{t['trip_id']}.csv", index=False)
            Path(f"{a.out}/claims_{t['trip_id']}.xlsx").write_bytes(to_xlsx_bytes(rows))
            print(f"{t['trip_id']}: {len(df)} rows -> {a.out}/claims_{t['trip_id']}.csv, .xlsx")
            print(df["relationship_type"].value_counts().to_string())
        sys.exit(0)
    cl = ApiClient(a.api) if a.api else FixtureClient(a.fixture, a.truth)
    rows = cl.claims(a.trip)
    df = pd.DataFrame(rows)[COLS]
    df.to_csv(f"{a.out}/claims.csv", index=False)
    Path(f"{a.out}/claims.xlsx").write_bytes(to_xlsx_bytes(rows))
    print(f"wrote {len(df)} rows -> {a.out}/claims.csv, claims.xlsx")
    print(df["relationship_type"].value_counts().to_string())
