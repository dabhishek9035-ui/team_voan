"""End-to-end integration tests wiring Member A (intake/extraction), Member B (core store/API), and Member C (dashboard client)."""
import io
import json
import unittest
from PIL import Image

from extraction.service import ExtractionService
from intake.channel import ChannelHandler
from intake.store_client import StoreClient
from pratibimb import Store
from pratibimb.api import create_app


def _make_png():
    img = Image.new("RGB", (300, 300), "#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _WsgiAdapter:
    """In-memory adapter matching requests.Session for dashboard.client.ApiClient."""

    def __init__(self, app):
        self.app = app

    def _call(self, method, url, params=None, json_body=None):
        from urllib.parse import urlencode
        path = url.split("://testserver", 1)[-1]
        if params:
            path = f"{path}?{urlencode(params)}"
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
        status_holder = []
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path.split("?", 1)[0],
            "RAW_URI": path,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }
        raw = b"".join(self.app(environ, lambda s, h: status_holder.append(s)))
        code = int(status_holder[0].split(" ", 1)[0])

        class _Resp:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code}: {self._payload}")

            def json(self):
                return self._payload

        return _Resp(code, json.loads(raw.decode("utf-8")))

    def get(self, url, params=None, timeout=15):
        return self._call("GET", url, params=params)

    def post(self, url, json=None, timeout=15):
        return self._call("POST", url, json_body=json)


class TestIntegratedPipeline(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.app = create_app(self.store)

    def tearDown(self):
        self.store.close()

    def test_member_a_into_member_b_store_links_and_verifies_chain(self):
        trip_id = self.store.add_trip("Bengaluru Fest Trip", "coordinator:c1",
                                     window_start="2026-11-18T00:00:00Z",
                                     window_end="2026-11-20T23:59:59Z")
        jc = self.store.add_join_code(trip_id, "coordinator:c1", code="FEST2026")
        self.assertEqual(jc["trip_id"], trip_id)

        client = StoreClient(store=self.store)
        svc = ExtractionService()
        handler = ChannelHandler(extraction_service=svc, store_client=client)

        # 1. Traveller sends UPI payment screenshot with join code caption
        svc.sarvam_client._simulate_digitise = lambda _: (
            "Google Pay\nPayment Successful\nPaid to BMRCL\nRs 40.00\n"
            "UPI Ref No 401928374615\nOrder ID ORD-108920\n"
            "19/11/2026 10:00 AM\n",
            "en",
        )
        svc.qr_decoder.decode = lambda _: (None, None, False)
        res_pay = handler.handle_incoming_screenshot(
            sender_id="tg_meera",
            image_bytes=_make_png(),
            channel="telegram",
            caption="FEST2026",
        )
        self.assertEqual(res_pay["status"], "success")
        self.assertEqual(res_pay["screenshot_type"], "UPI_SUCCESS")
        self.assertTrue(res_pay["interp_id"].startswith("in_"))

        # 2. Traveller sends QR ticket sharing the same Order ID
        svc.sarvam_client._simulate_digitise = lambda _: (
            "Namma Metro Single Journey QR Ticket\n"
            "Ticket ID: TKT-108920\nOrder ID: ORD-108920\n"
            "From: Indiranagar\nTo: MG Road\nFare: Rs. 40.00\n"
            "19/11/2026 10:02 AM\n",
            "en",
        )
        svc.qr_decoder.decode = lambda _: (
            "BMRCL|TKT-108920|INDIRANAGAR|MG_ROAD|40.00|2026-11-19T23:59:59",
            {
                "operator": "BMRCL",
                "ticket_id": "TKT-108920",
                "origin_station": "INDIRANAGAR",
                "destination_station": "MG ROAD",
                "fare": 40.0,
            },
            True,
        )
        res_tkt = handler.handle_incoming_screenshot(
            sender_id="tg_meera",
            image_bytes=_make_png(),
            channel="telegram",
        )
        self.assertEqual(res_tkt["status"], "success")
        self.assertEqual(res_tkt["screenshot_type"], "TICKET_QR")

        # 3. Verify Member B linked them EXACT, preserved the chain, and projects summary
        rels = self.store.list_records("relationships")
        self.assertTrue(any(r["type"] == "EXACT" and "order_id" in r["basis"] for r in rels))
        summary = client.get_trip_summary(trip_id)
        self.assertEqual(len(summary["claims"]), 1)
        self.assertEqual(summary["claims"][0]["relationship_type"], "EXACT")
        self.assertTrue(self.store.verify()["ok"])

    def test_member_c_api_client_against_member_b_wsgi_app(self):
        from dashboard.client import ApiClient

        trip_id = self.store.add_trip("API Integration Trip", "coordinator:c2")
        self.store.add_traveller(trip_id, "s1", label="Meera")
        ev_p = self.store.add_evidence(
            sender_id="s1", channel="telegram", received_at="2026-11-19T10:00:00Z",
            sha256="1" * 64, phash="aa" * 8, trip_id=trip_id,
        )
        in_p = self.store.add_interpretation(
            ev_p, "pratibimb-intake-v1", "sarvam-vision-1.5", "UPI_SUCCESS", 0.96,
            {"amount": 40.0, "utr": "401928374615", "timestamp": "2026-11-19T10:00:00Z"},
            {"amount": 0.96, "utr": 0.95, "timestamp": 0.90},
            {"amount": "sarvam_digitise", "utr": "sarvam_digitise", "timestamp": "sarvam_digitise"},
        )
        ev_t = self.store.add_evidence(
            sender_id="s1", channel="telegram", received_at="2026-11-19T10:05:00Z",
            sha256="2" * 64, phash="bb" * 8, trip_id=trip_id,
        )
        in_t = self.store.add_interpretation(
            ev_t, "pratibimb-intake-v1", "sarvam-vision-1.5", "TICKET_QR", 0.95,
            {"fare": 40.0, "ticket_id": "TKT-555", "origin_station": "Indiranagar",
             "destination_station": "MG Road", "timestamp": "2026-11-19T10:05:00Z"},
            {"fare": 0.95, "ticket_id": 0.95, "origin_station": 0.9,
             "destination_station": 0.9, "timestamp": 0.9},
            {"fare": "qr_decoder", "ticket_id": "qr_decoder", "origin_station": "qr_decoder",
             "destination_station": "qr_decoder", "timestamp": "sarvam_digitise"},
        )
        from pratibimb import linking
        from pratibimb.config import load_config
        linking.link_interpretation(self.store, in_t, load_config())

        api_client = ApiClient("http://testserver")
        api_client.s = _WsgiAdapter(self.app)

        trips = api_client.trips_list()
        self.assertEqual([t["trip_id"] for t in trips], [trip_id])

        summary = api_client.summary(trip_id)
        self.assertEqual(summary["counts"]["needs review"], 1)
        self.assertEqual(summary["roster"][0]["link_type"], "INFERRED")

        inbox = api_client.inbox(trip_id)
        self.assertEqual(inbox["needs_review"], 1)
        self.assertEqual(inbox["items"][0]["relationship_type"], "INFERRED")

        trail = api_client.trail(inbox["items"][0]["evidence_id"])
        self.assertIsNone(trail["evidence"]["file_ref"])
        self.assertEqual(len(trail["interpretations"]), 1)

        dec = api_client.post_decision(in_p, "approved", "coord_01", "Matched manually by coordinator")
        self.assertTrue(dec["dec_id"].startswith("dc_"))

        inbox_after = api_client.inbox(trip_id)
        self.assertEqual(inbox_after["needs_review"], 0)

        rows = api_client.claims(trip_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["relationship_type"], "INFERRED")
        self.assertEqual(rows[0]["coordinator_decision"], "approved")

        audit = api_client.audit_verify()
        self.assertTrue(audit["ok"])
        self.assertIsNone(audit["broken_index"])


if __name__ == "__main__":
    unittest.main()
