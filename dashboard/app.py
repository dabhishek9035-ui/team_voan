"""
Pratibimb coordinator dashboard (Member C, C3/C4/C6).  Run:  streamlit run dashboard/app.py

Design rules enforced here (from the brief):
  * relationship type + per-attribute evidence level on EVERY row, never one blended "OK"
  * four records shown separately in the trail
  * no raw images by default; exceptions count is the headline
  * no "fraud" / "proof" wording about the product's output (see tools/check_forbidden.py)
"""
import io
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "breakme"))
sys.path.insert(0, str(ROOT / "export"))
from client import ApiClient, FixtureClient, SyntheticClient  # noqa: E402
import scoreboard  # noqa: E402
from claims import to_xlsx_bytes  # noqa: E402

st.set_page_config(page_title="Pratibimb - coordinator", layout="wide")
TYPE_HELP = {"EXACT": "shared identifier", "INFERRED": "context only - always reviewed",
             "MANUAL": "linked by a coordinator", "UNMATCHED": "not enough evidence - kept, not forced"}
BADGE = {"EXACT": "🟢 EXACT", "MANUAL": "🔵 MANUAL", "INFERRED": "🟠 INFERRED", "UNMATCHED": "⚪ UNMATCHED"}

# ---------------- sidebar: data source ----------------
st.sidebar.title("Pratibimb")
src = st.sidebar.radio("Data source", ["Synthetic dataset (30 screenshots)", "Fixtures: exact IDs", "Fixtures: inferred-only",
                                       "Live API (Member B)"])
api_url = st.sidebar.text_input("API base URL", "http://localhost:8000") if src.startswith("Live") else None
coord = st.sidebar.text_input("Coordinator id", "coord_01")
key = (src, api_url)
if st.session_state.get("key") != key:       # new source => fresh client (decisions persist per source)
    st.session_state["key"] = key
    if src.startswith("Live"):
        st.session_state["client"] = ApiClient(api_url)
    elif src.startswith("Synthetic"):
        st.session_state["client"] = SyntheticClient()
    else:
        m = "exact" if "exact" in src else "inferred_only"
        st.session_state["client"] = FixtureClient(ROOT / f"fixtures/fixtures_{m}.json",
                                                   ROOT / f"fixtures/ground_truth_{m}.json")
c = st.session_state["client"]
try:
    trips = c.trips_list()
except Exception as e:  # API down: say so, don't crash the demo
    st.error(f"Cannot reach the data source: {e}")
    st.stop()
trip_id = st.sidebar.selectbox("Trip", [t["trip_id"] for t in trips],
                               format_func=lambda i: next(t["name"] for t in trips if t["trip_id"] == i))
views = ["Roster", "Exceptions inbox", "Trail", "Audit", "Claim sheet", "Break me", "Results"]
if hasattr(c, "demo_cases"):
    views.insert(3, "Demo cases")
view = st.sidebar.radio("View", views)
st.sidebar.caption("Corroborated means consistent, not true. Two fabricated items can agree.")
if c.mode == "fixture":
    st.sidebar.warning("Fixture data: synthetic, not measured.")


def levels(d):
    return " | ".join(f"{k}: {v}" for k, v in d.items())


# ---------------- Roster ----------------
if view == "Roster":
    s = c.summary(trip_id)
    st.header(s["trip"]["name"])
    names = [n for n in ("ready", "needs review", "pending", "stuck", "no evidence yet") if n in s["counts"]]
    k = st.columns(len(names))
    for col, name in zip(k, names):
        col.metric(name.capitalize(), s["counts"].get(name, 0))
    st.caption("State is machine-observed. 'Traveller asserts travel' is a self-report; "
               "'coordinator decision' is a human decision. Neither is a machine conclusion.")
    df = pd.DataFrame(s["roster"])
    df["link_type"] = df["link_type"].map(lambda x: BADGE.get(x, "-"))
    st.dataframe(df, hide_index=True)

# ---------------- Inbox ----------------
elif view == "Exceptions inbox":
    ib = c.inbox(trip_id)
    st.header(f"{ib['needs_review']} of {ib['total_screenshots']} screenshots need review")
    st.caption("Only items that do not balance. INFERRED and UNMATCHED never auto-clear."
               + (f" {ib['not_claim_related']} screenshot(s) classed OTHER are not claim-related and are hidden here." if ib.get("not_claim_related") else ""))
    for it in ib["items"]:
        eid = it["evidence_id"]
        title = f"{BADGE[it['relationship_type']]}  ·  {it['screenshot_type']}  ·  {it['sender']}  ·  {eid}"
        with st.expander(title + (f"  ·  ({it['status']})" if it["status"] != "open" else ""), expanded=False):
            st.markdown("**Why it is here**")
            for r in it["reasons"]:
                st.markdown(f"- {r}")
            a, b = st.columns(2)
            a.markdown(f"**Relationship:** {it['relationship_type']} ({TYPE_HELP[it['relationship_type']]})")
            a.markdown(f"**Evidence level:** {levels(it['evidence_level'])}")
            if it.get("route"):
                a.markdown(f"**Route:** {it['route']}  ·  **Amount:** ₹{it['amount']}")
            if it.get("earlier_sighting"):
                e = it["earlier_sighting"]
                b.markdown(f"**Earlier sighting:** {e['evidence_id']} from {e['sender']} on {e['date']} (fields only)")
            if it.get("case_ref"):
                b.markdown(f"**Case:** {it['case_ref']}")
            reason = st.text_input("Reason (recorded with your decision)", key=f"r_{eid}")
            cols = st.columns(4)
            for col, (label, act) in zip(cols[:3], [("Approve", "approved"), ("Request proof", "proof_requested"),
                                                    ("Reject", "rejected")]):
                if col.button(label, key=f"{act}_{eid}"):
                    c.post_decision(eid, act, coord, reason or "-")
                    st.rerun()
            with cols[3]:
                tgt = st.text_input("Link to evidence id", key=f"t_{eid}", placeholder="ev_xxx")
                if st.button("Link manually", key=f"l_{eid}") and tgt:
                    c.post_decision(eid, "link_manually", coord, reason or "-", link_to=tgt)
                    st.rerun()
    st.caption("Raw images are not shown. A raw-image request must be logged by the backend (who, when, why).")

# ---------------- Trail ----------------
elif view == "Trail":
    ib = c.inbox(trip_id)
    ids = [i["evidence_id"] for i in ib["items"]] or ["ev_001"]
    eid = st.text_input("Evidence id", ids[0])
    st.write("Quick pick:", ", ".join(ids[:8]))
    t = c.trail(eid)
    st.header(f"Trail for {eid}")
    p1, p2 = st.columns(2)
    p1.subheader("1 · Evidence (what was sent)")
    p1.json(t["evidence"])
    p2.subheader("2 · Interpretation (what was read)")
    p2.json(t["interpretations"])
    p3, p4 = st.columns(2)
    p3.subheader("3 · Relationships (why linked)")
    p3.json(t["relationships"])
    p4.subheader("4 · Decisions (who decided)")
    p4.json(t["decisions"])
    if t["later_changes"]:
        st.info("Changed afterwards: " + "; ".join(t["later_changes"]))
    if getattr(c, "can_show_images", False):
        with st.expander("Dev only: show the synthetic image (logged)"):
            why = st.text_input("Reason for raw-image access", key=f"why_{eid}")
            if st.button("Show image", key=f"img_{eid}"):
                try:
                    st.image(c.image_path(eid, coord, why), width=280)
                except ValueError as e:
                    st.warning(str(e))
            if c.access_log:
                st.dataframe(pd.DataFrame(c.access_log), hide_index=True)
            st.caption("Real screenshots must never be shown by default. Every view is written to the access log.")

# ---------------- Demo cases ----------------
elif view == "Demo cases":
    st.header("Prepared demo cases (from data/demo_cases.json)")
    st.caption("coordinator_decision is empty on purpose: no human decision is implied by the fixture.")
    for cs in c.demo_cases():
        with st.expander(f"{BADGE[cs['relationship_type']]}  ·  {cs['case_id']}  ·  {cs['title']}"):
            st.markdown(f"**Why:** {cs['reason']}")
            st.markdown(f"**Machine state:** {cs['machine_state']}  ·  **Decision support:** {cs['decision_support']}")
            st.markdown(f"**Evidence level:** {levels(cs['evidence_levels'])}")
            st.markdown("**Evidence:** " + ", ".join(cs["evidence_ids"]))

# ---------------- Audit ----------------
elif view == "Audit":
    st.header("Ledger chain check")
    if st.button("Run chain check"):
        st.session_state["audit"] = c.audit_verify()
    a = st.session_state.get("audit") or c.audit_verify()
    (st.success if a["ok"] else st.error)(
        f"Chain intact across {a['length']} records" if a["ok"]
        else f"Chain broken at record #{a['broken_index']} ({a['kind']})")
    st.markdown("**Tamper demo** - edits one past row in a *copy* and re-runs the check.")
    if st.button("Edit a past row"):
        d = c.tamper_demo()
        st.write(f"Edited `{d['edited']}`")
        r = d["result"]
        (st.error if not r["ok"] else st.warning)(
            f"Chain break detected at record #{r['broken_index']}" if not r["ok"] else "No break detected")
    st.caption("This gives tamper evidence, not tamper prevention. It is not a blockchain.")

# ---------------- Claim sheet ----------------
elif view == "Claim sheet":
    rows = c.claims(trip_id)
    df = pd.DataFrame(rows)
    st.header("Claim sheet")
    pick = st.multiselect("Filter by relationship type", ["EXACT", "MANUAL", "INFERRED", "UNMATCHED"],
                          default=["EXACT", "MANUAL", "INFERRED", "UNMATCHED"])
    df = df[df["relationship_type"].isin(pick)]
    st.dataframe(df, hide_index=True)
    st.download_button("Download CSV", df.to_csv(index=False).encode(), "claims.csv", "text/csv")
    st.download_button("Download XLSX", to_xlsx_bytes(df.to_dict("records")), "claims.xlsx")
    st.caption("INFERRED and UNMATCHED rows are marked and never merged with EXACT rows.")

# ---------------- Break me ----------------
elif view == "Break me":
    st.header("Break me")
    st.caption("A judge sends any screenshot to the bot; log what the system said and what really happened. "
               "Attempts that got through stay on the board.")
    with st.form("attempt"):
        who = st.text_input("Attempt by", "judge")
        what = st.text_input("What was sent (e.g. 'AI-made ticket, valid format')")
        out = st.text_input("System said (type / link / level / reason)")
        res = st.selectbox("Outcome", ["caught: needs review", "caught: challenge issued", "got through",
                                       "could not read", "correctly cleared a genuine item"])
        if st.form_submit_button("Log attempt"):
            scoreboard.log(who, what, out, res)
    sb = scoreboard.summary()
    m = st.columns(4)
    m[0].metric("Attempts", sb["total"])
    m[1].metric("Caught", sb["caught"])
    m[2].metric("Got through", sb["got_through"])
    m[3].metric("Could not read", sb["unreadable"])
    st.dataframe(pd.DataFrame(scoreboard.read_all()), hide_index=True)
    st.subheader("Five safe items to offer if judges hesitate")
    st.markdown((ROOT / "breakme/safe_items.md").read_text())

# ---------------- Results ----------------
else:
    st.header("Evaluation results")
    f = ROOT / "eval/results/metrics.json"
    if not f.exists():
        st.info("No results yet. Run `make eval` on the held-out split once predictions exist.")
    else:
        m = json.loads(f.read_text())
        if m.get("banner"):
            st.warning(m["banner"])
        st.json(m)
        for name in ("fingerprint_check", "qr_decode_check"):
            fj = ROOT / f"eval/results/{name}.json"
            if fj.exists():
                with st.expander(name.replace("_", " ")):
                    st.json(json.loads(fj.read_text()))
        md = ROOT / "eval/results/where_it_fails.md"
        if md.exists():
            st.markdown(md.read_text())
