import io
import json
import unittest

from pratibimb import Store
from pratibimb.api import create_app
from pratibimb.calibration import calibrate, drift_report


class TestApiAndCalibration(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def call(self, method, path, payload=None):
        body = json.dumps(payload or {}).encode("utf-8")
        status = []
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "RAW_URI": path,
                   "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)}
        response = b"".join(create_app(self.store)(
            environ, lambda value, headers: status.append(value)))
        return status[0], json.loads(response)

    def test_api_trip_summary_and_audit(self):
        status, trip = self.call("POST", "/trips",
                                 {"name": "API trip", "coordinator_id": "coordinator:c"})
        self.assertEqual(status, "201 Created")
        trip_id = trip["trip_id"]
        st_jc, jc = self.call("POST", f"/trips/{trip_id}/join-code")
        self.assertEqual(st_jc, "201 Created")
        self.assertEqual(self.call("GET", "/trips")[0], "200 OK")
        st_lk, lk = self.call("GET", f"/trips/lookup?join_code={jc['code']}")
        self.assertEqual(st_lk, "200 OK")
        self.assertEqual(lk["trip_id"], trip_id)
        self.assertEqual(self.call("GET", f"/trips/{trip_id}/summary")[0], "200 OK")
        self.assertTrue(self.call("GET", "/audit/verify")[1]["ok"])

    def test_api_ingest_inbox_trail_decisions_and_export(self):
        _, trip = self.call("POST", "/trips", {"name": "End-to-End API", "coordinator_id": "coordinator:c"})
        trip_id = trip["trip_id"]

        st1, ev1 = self.call("POST", "/records/evidence", {
            "evidence_id": "ev_api_pay01",
            "trip_id": trip_id,
            "sender_id": "s1",
            "channel": "telegram",
            "received_at": "2026-11-19T10:00:00Z",
            "sha256": "a" * 64,
            "phash": "11" * 8,
            "status": "received",
        })
        self.assertEqual(st1, "200 OK")
        self.assertEqual(ev1["evidence_id"], "ev_api_pay01")

        st2, in1 = self.call("POST", "/records/interpretation", {
            "interp_id": "in_api_pay01",
            "evidence_id": "ev_api_pay01",
            "producer": "pratibimb-intake-v1",
            "model_version": "sarvam-vision-1.5",
            "screenshot_type": "UPI_SUCCESS",
            "type_confidence": 0.96,
            "fields": {"amount": 40.0, "utr": "401928374615", "timestamp": "2026-11-19T10:00:00Z"},
            "field_confidence": {"amount": 0.96, "utr": 0.95, "timestamp": 0.90},
            "field_source": {"amount": "sarvam_digitise", "utr": "sarvam_digitise", "timestamp": "sarvam_digitise"},
        })
        self.assertEqual(st2, "200 OK")
        self.assertEqual(in1["interp_id"], "in_api_pay01")

        # Ticket arrives with matching amount/time -> INFERRED link -> must appear in inbox
        self.call("POST", "/records/evidence", {
            "evidence_id": "ev_api_tkt01",
            "trip_id": trip_id,
            "sender_id": "s1",
            "channel": "telegram",
            "received_at": "2026-11-19T10:03:00Z",
            "sha256": "b" * 64,
            "phash": "22" * 8,
            "status": "received",
        })
        self.call("POST", "/records/interpretation", {
            "interp_id": "in_api_tkt01",
            "evidence_id": "ev_api_tkt01",
            "producer": "pratibimb-intake-v1",
            "model_version": "sarvam-vision-1.5",
            "screenshot_type": "TICKET_QR",
            "type_confidence": 0.95,
            "fields": {"fare": 40.0, "ticket_id": "TKT-901", "timestamp": "2026-11-19T10:03:00Z"},
            "field_confidence": {"fare": 0.95, "ticket_id": 0.95, "timestamp": 0.90},
            "field_source": {"fare": "qr_decoder", "ticket_id": "qr_decoder", "timestamp": "sarvam_digitise"},
        })

        st_in, inbox = self.call("GET", f"/trips/{trip_id}/inbox")
        self.assertEqual(st_in, "200 OK")
        self.assertEqual(inbox["needs_review"], 1)
        self.assertEqual(inbox["items"][0]["relationship_type"], "INFERRED")

        st_tr, trail = self.call("GET", "/records/ev_api_pay01/trail")
        self.assertEqual(st_tr, "200 OK")
        self.assertIsNone(trail["evidence"]["file_ref"])
        self.assertEqual(trail["interpretations"][0]["fields"]["utr"], "********4615")

        st_dc, dec = self.call("POST", "/decisions", {
            "subject_ref": "in_api_pay01",
            "action": "approved",
            "decided_by": "coord_01",
            "reason": "Checked bank debit manually",
        })
        self.assertEqual(st_dc, "201 Created")
        self.assertTrue(dec["dec_id"].startswith("dc_"))

        _, inbox_after = self.call("GET", f"/trips/{trip_id}/inbox")
        self.assertEqual(inbox_after["needs_review"], 0)

        st_ex, exported = self.call("GET", f"/export/claims?trip_id={trip_id}")
        self.assertEqual(st_ex, "200 OK")
        self.assertEqual(len(exported["rows"]), 1)
        self.assertEqual(exported["rows"][0]["coordinator_decision"], "approved")

    def test_calibration_reports_false_accept_and_drift(self):
        rows = [{"score": 0.99, "label": True, "type": "ticket"},
                {"score": 0.95, "label": False, "type": "ticket"},
                {"score": 0.40, "label": False, "type": "payment"}]
        report = calibrate(rows, thresholds=(0.9,))
        self.assertEqual(report[0]["false_accept_rate"], 0.5)
        self.assertEqual(report[0]["coverage"], 2 / 3)
        drift = drift_report(rows, {"ticket": 1.0})
        self.assertEqual(drift["new_types"], ["payment"])


if __name__ == "__main__":
    unittest.main()
