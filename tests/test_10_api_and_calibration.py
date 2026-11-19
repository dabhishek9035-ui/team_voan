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
        self.assertEqual(self.call("POST", f"/trips/{trip_id}/join-code")[0], "201 Created")
        self.assertEqual(self.call("GET", f"/trips/{trip_id}/summary")[0], "200 OK")
        self.assertTrue(self.call("GET", "/audit/verify")[1]["ok"])

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
