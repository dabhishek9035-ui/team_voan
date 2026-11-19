"""
Fingerprint integrity + threshold behaviour on the synthetic corpus.

  python eval/fingerprint_check.py

1. Recompute sha256 / pHash / aHash from the PNG/JPEG files and compare with manifest.json (data integrity).
2. Compare recomputed variant distances with data/fingerprint_distances.json.
3. For each candidate threshold, count (a) genuine same-ticket pairs caught and (b) unrelated pairs wrongly flagged,
   per split. Thresholds are meant to be read on CALIBRATION only; heldout is printed for reporting.
Writes eval/results/fingerprint_check.json.
"""
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from standin.dataset import load, DATA  # noqa: E402
from standin.fingerprints import a_hash, hamming, p_hash, sha256_file  # noqa: E402


def main():
    D = load()
    recs = D["records"]
    bad = []
    fp = {}
    for r in recs:
        path = DATA / r["image_file"]
        got = {"sha256": sha256_file(path), "phash": p_hash(path), "ahash": a_hash(path)}
        fp[r["evidence_id"]] = got
        for k, v in got.items():
            if v != r[k]:
                d = hamming(v, r[k]) if k != "sha256" else None
                bad.append({"item": r["evidence_id"], "field": k, "manifest": r[k], "recomputed": v, "bit_distance": d})
    ref = json.load(open(DATA / "fingerprint_distances.json"))["pairs"]
    dist_bad = []
    for p in ref:
        a, b = fp[p["variant_evidence_id"]], fp[p["parent_evidence_id"]]
        got = (hamming(a["phash"], b["phash"]), hamming(a["ahash"], b["ahash"]), a["sha256"] == b["sha256"])
        want = (p["phash_hamming_distance"], p["ahash_hamming_distance"], p["same_sha256"])
        if got != want:
            dist_bad.append({"pair": p["variant_evidence_id"], "got": got, "want": want})
    tid = {r["evidence_id"]: (r["fields"].get("ticket_id") if r["screenshot_type"] == "TICKET_QR" else None) for r in recs}  # image duplicates = same ticket screen
    table = {}
    for split in ("calibration", "heldout"):
        rs = [r for r in recs if r["split"] == split]
        pairs = []
        for a, b in itertools.combinations(rs, 2):
            same = bool(tid[a["evidence_id"]]) and tid[a["evidence_id"]] == tid[b["evidence_id"]]
            pairs.append({"a": a["evidence_id"], "b": b["evidence_id"], "same_ticket": same,
                          "phash": hamming(fp[a["evidence_id"]]["phash"], fp[b["evidence_id"]]["phash"]),
                          "ahash": hamming(fp[a["evidence_id"]]["ahash"], fp[b["evidence_id"]]["ahash"])})
        rows = []
        for t in (0, 2, 4, 6, 8, 10, 12):
            hit = lambda p: p["phash"] <= t and p["ahash"] <= t
            g = [p for p in pairs if p["same_ticket"]]
            u = [p for p in pairs if not p["same_ticket"]]
            rows.append({"threshold_both_le": t, "same_ticket_pairs_caught": f"{sum(map(hit, g))}/{len(g)}",
                         "unrelated_pairs_flagged": f"{sum(map(hit, u))}/{len(u)}"})
        table[split] = rows
    res = {"files_checked": len(recs), "hash_mismatches_vs_manifest": bad,
           "mismatch_note": "sha256 must match exactly. A 1-2 bit perceptual difference is expected across Pillow/OpenCV versions (resampling); that is why perceptual hashes are similarity signals, not identifiers.", "variant_distance_mismatches": dist_bad,
           "threshold_behaviour": table,
           "reading": ("If unrelated pairs are flagged at the smallest threshold that catches the genuine variants, "
                       "perceptual hashes cannot be used alone on this corpus: gate them behind a semantic ID match "
                       "(as standin/config.json does). Corpus is small and screens share one template; this is a plumbing finding, "
                       "not a production threshold.")}
    json.dump(res, open(ROOT / "eval/results/fingerprint_check.json", "w"), indent=2)
    print(f"files={len(recs)} hash mismatches={len(bad)} {[(b['item'], b['field'], b['bit_distance']) for b in bad]} variant-distance mismatches={len(dist_bad)}")
    for s, rows in table.items():
        print(s)
        for r in rows:
            print("  ", r)
    return res


if __name__ == "__main__":
    main()
