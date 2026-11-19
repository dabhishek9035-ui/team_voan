"""
Local QR decode check (Member A's A4, measured here on the synthetic tickets, including image variants).

  python eval/qr_decode_check.py

Decodes the QR in every TICKET_QR image with OpenCV and compares with ground-truth qr_payload.
Synthetic QR codes are clean; real phone screenshots will be harder. Report as 'synthetic, clean', never as a QR accuracy claim.
Writes eval/results/qr_decode_check.json.
"""
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from standin.dataset import load, DATA  # noqa: E402


def main():
    D = load()
    det = cv2.QRCodeDetector()
    rows = []
    for r in D["records"]:
        if r["screenshot_type"] != "TICKET_QR":
            continue
        val, _, _ = det.detectAndDecode(cv2.imread(str(DATA / r["image_file"])))
        rows.append({"item": r["evidence_id"], "variant": r["variant"], "decoded": val or None,
                     "truth": r["all_fields"]["qr_payload"], "match": (val or None) == r["all_fields"]["qr_payload"]})
    ok = sum(x["match"] for x in rows)
    res = {"n": len(rows), "matched": ok, "rows": rows, "caveat": "synthetic, clean QR codes; not a real-world QR accuracy figure"}
    json.dump(res, open(ROOT / "eval/results/qr_decode_check.json", "w"), indent=2)
    print(f"QR decode: {ok}/{len(rows)} match (synthetic, clean)")
    for x in rows:
        print("  ", x["item"], x["variant"], "OK" if x["match"] else f"MISS {x['decoded']!r}")


if __name__ == "__main__":
    main()
