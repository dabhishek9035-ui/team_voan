#!/usr/bin/env python3
"""Serve the Member C fixture dashboard using only Python's standard library."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import os
import sys
import threading
import urllib.parse
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG_PATH = DASHBOARD / "config.json"
DEFAULT_PORT = int(os.environ.get("PORT", "8765"))
MIME_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def live_request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[bytes, str]:
    base = str(CONFIG.get("backend_url", "")).strip().rstrip("/")
    if not base:
        raise RuntimeError("No live backend URL is configured.")
    url = base + path
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.read(), response.headers.get("Content-Type", "application/json")
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"Member B API request failed: {error}") from error


CONFIG = read_json(CONFIG_PATH)
MANIFEST = read_json(DATA / "manifest.json")
RELATIONSHIPS = read_json(DATA / "relationships.json")
DEMO_CASES = read_json(DATA / "demo_cases.json")
RECORDS = MANIFEST["records"]
RECORD_BY_ID = {record["evidence_id"]: record for record in RECORDS}
RUNTIME_DECISIONS: list[dict[str, Any]] = []
RUNTIME_RELATIONSHIPS: list[dict[str, Any]] = []
RAW_ACCESS_LOG: list[dict[str, Any]] = []
LOCK = threading.Lock()


def now_local() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")


def record_digest(record: dict[str, Any], previous_hash: str) -> str:
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((canonical + previous_hash).encode("utf-8")).hexdigest()


def build_demo_chain() -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    previous_hash = "0" * 64
    for record in RECORDS:
        clone = json.loads(json.dumps(record, ensure_ascii=False))
        row_hash = record_digest(clone, previous_hash)
        chain.append({"record_id": record["evidence_id"], "record": clone, "prev_hash": previous_hash, "record_hash": row_hash})
        previous_hash = row_hash
    return chain


AUDIT_CHAIN = build_demo_chain()
ORIGINAL_AUDIT_CHAIN = json.loads(json.dumps(AUDIT_CHAIN, ensure_ascii=False))


def verify_chain() -> dict[str, Any]:
    expected_previous = "0" * 64
    for index, row in enumerate(AUDIT_CHAIN):
        if row["prev_hash"] != expected_previous:
            return {"valid": False, "record_count": len(AUDIT_CHAIN), "first_broken_record": row["record_id"], "broken_index": index}
        expected_hash = record_digest(row["record"], expected_previous)
        if expected_hash != row["record_hash"]:
            return {"valid": False, "record_count": len(AUDIT_CHAIN), "first_broken_record": row["record_id"], "broken_index": index}
        expected_previous = row["record_hash"]
    return {"valid": True, "record_count": len(AUDIT_CHAIN), "first_broken_record": None, "broken_index": None}


def link_rows_for(evidence_id: str) -> list[dict[str, Any]]:
    return [
        relation for relation in all_relationships()
        if evidence_id in (relation["from_evidence_id"], relation["to_evidence_id"])
    ]


def all_relationships() -> list[dict[str, Any]]:
    return RELATIONSHIPS + RUNTIME_RELATIONSHIPS


def records_for_trip(trip_id: str) -> list[dict[str, Any]]:
    return [record for record in RECORDS if record.get("trip_id") == trip_id]


def cases_for_trip(trip_id: str) -> list[dict[str, Any]]:
    return [case for case in DEMO_CASES if case.get("trip_id") == trip_id]


def claim_rows(trip_id: str) -> tuple[list[str], list[list[str]]]:
    headers = [
        "traveller", "date", "route", "fare", "ticket_reference", "payment_reference",
        "relationship_type", "evidence_level_per_attribute", "flags_and_reasons",
        "coordinator_decision", "decision_time", "evidence_id", "image_file",
    ]
    decisions_by_evidence: dict[str, dict[str, Any]] = {}
    for decision in RUNTIME_DECISIONS:
        for evidence_id in decision.get("evidence_ids", []):
            decisions_by_evidence[evidence_id] = decision
    output: list[list[str]] = []
    for record in records_for_trip(trip_id):
        fields = record["ground_truth_fields"]
        relations = link_rows_for(record["evidence_id"])
        relation_types = sorted({relation["type"] for relation in relations})
        relation_label = " / ".join(relation_types) if relation_types else "UNMATCHED"
        evidence_levels = []
        if record["screenshot_type"] in ("UPI_SUCCESS", "BANK_SMS"):
            debit_level = "corroborated" if any("utr" in relation.get("basis", []) for relation in relations) else "extracted"
            evidence_levels.append(f"debit={debit_level}")
        if record["screenshot_type"] == "TICKET_QR":
            evidence_levels.append("ticket_issued=extracted")
        if record["screenshot_type"] == "REFUND_NOTICE":
            evidence_levels.append("refund_status=extracted")
        evidence_levels.append("travelled=unverified")
        labels = [label.replace("_", " ") for label in record.get("labels", []) if label != "clean"]
        if not labels:
            flags = "None in authored ground truth"
        else:
            flags = "; ".join(labels) + ". " + record.get("notes", "")
        decision = decisions_by_evidence.get(record["evidence_id"], {})
        action_labels = {"approve": "Coordinator approved", "proof_requested": "Evidence requested", "reject": "Coordinator rejected", "manual_link": "Linked manually"}
        route = " to ".join(filter(None, [fields.get("origin_station"), fields.get("destination_station")]))
        trip_window = next((row for row in MANIFEST["trip_windows"] if row["trip_id"] == trip_id), {})
        date_value = (fields.get("timestamp") or "")[:10] or trip_window.get("service_date", "")
        fare = fields.get("fare") or fields.get("amount") or ""
        output.append([
            record.get("sender_id") or "Unassigned synthetic sender", date_value, route, str(fare),
            str(fields.get("ticket_id") or ""), str(fields.get("utr") or fields.get("order_id") or ""),
            relation_label, "; ".join(evidence_levels), flags,
            action_labels.get(decision.get("action"), "No coordinator decision recorded"), decision.get("created_at", ""),
            record["evidence_id"], record["image_file"],
        ])
    return headers, output


def safe_excel_text(value: str) -> str:
    # All cells are inline strings; leading formula characters are prefixed too.
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def xlsx_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    content_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    ET.register_namespace("", main_ns)
    ET.register_namespace("r", rel_ns)
    workbook = ET.Element(f"{{{main_ns}}}workbook")
    sheets = ET.SubElement(workbook, f"{{{main_ns}}}sheets")
    ET.SubElement(sheets, f"{{{main_ns}}}sheet", {"name": "Claims", "sheetId": "1", f"{{{rel_ns}}}id": "rId1"})

    worksheet = ET.Element(f"{{{main_ns}}}worksheet")
    sheet_data = ET.SubElement(worksheet, f"{{{main_ns}}}sheetData")
    for row_number, values in enumerate([headers, *rows], start=1):
        row_node = ET.SubElement(sheet_data, f"{{{main_ns}}}row", {"r": str(row_number)})
        for column_number, value in enumerate(values, start=1):
            cell = ET.SubElement(row_node, f"{{{main_ns}}}c", {"r": f"{column_name(column_number)}{row_number}", "t": "inlineStr"})
            inline = ET.SubElement(cell, f"{{{main_ns}}}is")
            text = ET.SubElement(inline, f"{{{main_ns}}}t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
            text.text = safe_excel_text(str(value))

    workbook_rels = ET.Element(f"{{{pkg_rel_ns}}}Relationships")
    ET.SubElement(workbook_rels, f"{{{pkg_rel_ns}}}Relationship", {
        "Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet1.xml",
    })
    root_rels = ET.Element(f"{{{pkg_rel_ns}}}Relationships")
    ET.SubElement(root_rels, f"{{{pkg_rel_ns}}}Relationship", {
        "Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "Target": "xl/workbook.xml",
    })
    content_types = ET.Element(f"{{{content_ns}}}Types")
    ET.SubElement(content_types, f"{{{content_ns}}}Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(content_types, f"{{{content_ns}}}Default", {"Extension": "xml", "ContentType": "application/xml"})
    ET.SubElement(content_types, f"{{{content_ns}}}Override", {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
    ET.SubElement(content_types, f"{{{content_ns}}}Override", {"PartName": "/xl/worksheets/sheet1.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})

    files = {
        "[Content_Types].xml": ET.tostring(content_types, encoding="utf-8", xml_declaration=True),
        "_rels/.rels": ET.tostring(root_rels, encoding="utf-8", xml_declaration=True),
        "xl/workbook.xml": ET.tostring(workbook, encoding="utf-8", xml_declaration=True),
        "xl/_rels/workbook.xml.rels": ET.tostring(workbook_rels, encoding="utf-8", xml_declaration=True),
        "xl/worksheets/sheet1.xml": ET.tostring(worksheet, encoding="utf-8", xml_declaration=True),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def group_roster(trip_id: str) -> list[dict[str, Any]]:
    records = records_for_trip(trip_id)
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        key = record.get("sender_id") or "unassigned"
        groups.setdefault(key, []).append(record)
    roster = []
    for sender_id, evidence in sorted(groups.items()):
        types = {record["screenshot_type"] for record in evidence}
        evidence_ids = {record["evidence_id"] for record in evidence}
        relations = [
            relation for relation in all_relationships()
            if relation["from_evidence_id"] in evidence_ids or relation["to_evidence_id"] in evidence_ids
        ]
        relation_types = sorted({relation["type"] for relation in relations})
        if "UPI_SUCCESS" in types and "TICKET_QR" in types:
            observed_state = "Payment and ticket evidence seen"
        elif "UPI_FAILED_PENDING" in types and "TICKET_QR" not in types:
            observed_state = "Payment attempt seen; no ticket evidence"
        elif "TICKET_QR" in types:
            observed_state = "Ticket evidence seen"
        elif "BANK_SMS" in types:
            observed_state = "Bank message received"
        else:
            observed_state = "Evidence received"
        roster.append({
            "sender_id": sender_id,
            "display_name": "Traveller " + sender_id.rsplit("-", 1)[-1],
            "evidence_count": len(evidence),
            "payment_seen": bool(types & {"UPI_SUCCESS", "UPI_FAILED_PENDING", "BANK_SMS"}),
            "ticket_seen": "TICKET_QR" in types,
            "relationship_types": relation_types or ["UNMATCHED"],
            "travel_assertion": "Not provided in fixture data",
            "observed_state": observed_state,
            "evidence_ids": [record["evidence_id"] for record in evidence],
        })
    return roster


def dashboard_payload(trip_id: str) -> dict[str, Any]:
    records = records_for_trip(trip_id)
    cases = cases_for_trip(trip_id)
    roster = group_roster(trip_id)
    return {
        "mode": "fixture",
        "synthetic_only": True,
        "trip_id": trip_id,
        "trip_window": next((row for row in MANIFEST["trip_windows"] if row["trip_id"] == trip_id), None),
        "summary": {
            "traveller_count": len(roster),
            "evidence_count": len(records),
            "ticket_screenshots": sum(record["screenshot_type"] == "TICKET_QR" for record in records),
            "review_cases": len(cases),
        },
        "roster": roster,
        "cases": cases,
        "records": records,
        "relationships": [
            relation for relation in all_relationships()
            if relation["from_evidence_id"] in {record["evidence_id"] for record in records}
            or relation["to_evidence_id"] in {record["evidence_id"] for record in records}
        ],
        "decisions": list(RUNTIME_DECISIONS),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "PratibimbFixtureDashboard/1.0"

    def log_message(self, format_string: str, *args: Any) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), format_string % args))

    def send_bytes(self, status: int, body: bytes, content_type: str, *, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value: Any, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, body, "application/json; charset=utf-8", headers={"Cache-Control": "no-store"})

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Request body is too large.")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/" or path == "/index.html":
            return self.serve_static(DASHBOARD / "index.html")
        if path in ("/app.css", "/app.js"):
            return self.serve_static(DASHBOARD / path.lstrip("/"))
        if path == "/api/config":
            is_live = bool(str(CONFIG.get("backend_url", "")).strip())
            return self.send_json({**CONFIG, "mode": "live" if is_live else "fixture", "synthetic_only": not is_live})
        if path == "/api/trips":
            if str(CONFIG.get("backend_url", "")).strip():
                configured = CONFIG.get("trip_ids") or [CONFIG.get("trip_id")]
                return self.send_json({"items": [{"trip_id": trip_id, "service_date": "Live trip", "split": "live"} for trip_id in configured if trip_id], "mode": "live"})
            return self.send_json({"items": MANIFEST["trip_windows"], "mode": "fixture"})
        if path == "/api/fixture/records":
            return self.send_json({"items": RECORDS, "mode": "fixture", "synthetic_only": True})
        if path == "/api/data":
            trip_id = query.get("trip_id", [CONFIG.get("trip_id") or TEST_TRIP_ID])[0]
            if str(CONFIG.get("backend_url", "")).strip():
                try:
                    summary_bytes, _ = live_request("GET", f"/trips/{urllib.parse.quote(trip_id, safe='')}/summary")
                    inbox_bytes, _ = live_request("GET", f"/trips/{urllib.parse.quote(trip_id, safe='')}/inbox")
                    summary = json.loads(summary_bytes.decode("utf-8"))
                    inbox = json.loads(inbox_bytes.decode("utf-8"))
                    cases = inbox.get("items", inbox.get("cases", [])) if isinstance(inbox, dict) else inbox
                    counts = summary.get("counts", summary.get("summary", {}))
                    return self.send_json({
                        "mode": "live", "synthetic_only": False, "trip_id": trip_id,
                        "trip_window": summary.get("trip_window"), "summary": counts,
                        "roster": summary.get("roster", summary.get("travellers", [])),
                        "cases": cases, "records": summary.get("records", []),
                        "relationships": summary.get("relationships", []),
                        "decisions": summary.get("decisions", []),
                    })
                except (RuntimeError, json.JSONDecodeError, AttributeError) as error:
                    return self.send_json({"error": str(error)}, 502)
            if trip_id not in {row["trip_id"] for row in MANIFEST["trip_windows"]}:
                return self.send_json({"error": "Unknown synthetic trip ID."}, 404)
            return self.send_json(dashboard_payload(trip_id))
        if path.startswith("/api/trail/"):
            evidence_id = path.rsplit("/", 1)[-1]
            if str(CONFIG.get("backend_url", "")).strip():
                try:
                    body, content_type = live_request("GET", f"/records/{urllib.parse.quote(evidence_id, safe='')}/trail")
                    return self.send_bytes(200, body, content_type)
                except RuntimeError as error:
                    return self.send_json({"error": str(error)}, 502)
            record = RECORD_BY_ID.get(evidence_id)
            if record is None:
                return self.send_json({"error": "Evidence not found."}, 404)
            related = [
                row for row in all_relationships()
                if evidence_id in (row["from_evidence_id"], row["to_evidence_id"])
            ]
            return self.send_json({
                "record": record,
                "evidence": {key: record.get(key) for key in ("evidence_id", "trip_id", "sender_id", "channel", "received_at", "image_file", "sha256", "phash", "ahash")},
                "interpretation": {
                    "interp_id": "SYN-I-" + evidence_id.removeprefix("SYN-E-"),
                    "producer": "hand-authored ground-truth fixture",
                    "model_version": "fixture-v1",
                    "screenshot_type": record["screenshot_type"],
                    "fields": record["ground_truth_fields"],
                    "field_confidence": {key: (1.0 if value is not None else 0.0) for key, value in record["ground_truth_fields"].items()},
                    "language_detected": record["ground_truth_fields"].get("language_detected"),
                },
                "relationships": related,
                "decisions": [decision for decision in RUNTIME_DECISIONS if evidence_id in decision.get("evidence_ids", [])],
                "fixture_warning": "These values are labels authored for synthetic UI fixtures, not model predictions.",
            })
        if path == "/api/audit/verify":
            if str(CONFIG.get("backend_url", "")).strip():
                try:
                    body, content_type = live_request("GET", "/audit/verify")
                    return self.send_bytes(200, body, content_type)
                except RuntimeError as error:
                    return self.send_json({"error": str(error)}, 502)
            return self.send_json({**verify_chain(), "mode": "synthetic_fixture_chain"})
        if path == "/api/decisions":
            return self.send_json({"items": RUNTIME_DECISIONS, "mode": "in_memory_fixture"})
        if path == "/api/access-log":
            return self.send_json({"items": RAW_ACCESS_LOG, "mode": "in_memory_fixture"})
        if path == "/api/claims/preview":
            trip_id = query.get("trip_id", [CONFIG.get("trip_id") or TEST_TRIP_ID])[0]
            if str(CONFIG.get("backend_url", "")).strip():
                try:
                    body, _ = live_request("GET", f"/export/claims?trip_id={urllib.parse.quote(trip_id, safe='')}&format=csv")
                    table = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
                    headers = table[0] if table else []
                    return self.send_json({"headers": headers, "rows": table[1:], "trip_id": trip_id, "mode": "live"})
                except (RuntimeError, UnicodeDecodeError, csv.Error) as error:
                    return self.send_json({"error": str(error)}, 502)
            headers, rows = claim_rows(trip_id)
            return self.send_json({"headers": headers, "rows": rows, "trip_id": trip_id})
        if path == "/api/export/claims.csv":
            trip_id = query.get("trip_id", [CONFIG.get("trip_id") or TEST_TRIP_ID])[0]
            if str(CONFIG.get("backend_url", "")).strip():
                try:
                    body, content_type = live_request("GET", f"/export/claims?trip_id={urllib.parse.quote(trip_id, safe='')}&format=csv")
                    return self.send_bytes(200, body, content_type, headers={"Content-Disposition": 'attachment; filename="claims.csv"'})
                except RuntimeError as error:
                    return self.send_json({"error": str(error)}, 502)
            headers, rows = claim_rows(trip_id)
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow([safe_excel_text(value) for value in headers])
            writer.writerows([[safe_excel_text(value) for value in row] for row in rows])
            return self.send_bytes(200, buffer.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="claims.csv"'})
        if path == "/api/export/claims.xlsx":
            trip_id = query.get("trip_id", [CONFIG.get("trip_id") or TEST_TRIP_ID])[0]
            if str(CONFIG.get("backend_url", "")).strip():
                try:
                    body, content_type = live_request("GET", f"/export/claims?trip_id={urllib.parse.quote(trip_id, safe='')}&format=xlsx")
                    return self.send_bytes(200, body, content_type, headers={"Content-Disposition": 'attachment; filename="claims.xlsx"'})
                except RuntimeError as error:
                    return self.send_json({"error": str(error)}, 502)
            headers, rows = claim_rows(trip_id)
            body = xlsx_bytes(headers, rows)
            return self.send_bytes(200, body, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="claims.xlsx"'})
        if path.startswith("/api/raw-image/") or path.startswith("/api/fixture/raw-image/"):
            fixture_image = path.startswith("/api/fixture/raw-image/")
            if not fixture_image and str(CONFIG.get("backend_url", "")).strip():
                return self.send_json({"error": "Connect B's logged raw-image access endpoint before revealing live images."}, 501)
            evidence_id = path.rsplit("/", 1)[-1]
            record = RECORD_BY_ID.get(evidence_id)
            if record is None:
                return self.send_json({"error": "Evidence not found."}, 404)
            image_path = (DATA / record["image_file"]).resolve()
            if DATA.resolve() not in image_path.parents or not image_path.is_file():
                return self.send_json({"error": "Image path is unavailable."}, 404)
            with LOCK:
                RAW_ACCESS_LOG.append({"evidence_id": evidence_id, "requested_at": now_local(), "requested_by": "local demo coordinator", "reason": "Explicit reveal of synthetic fixture image"})
            return self.send_bytes(200, image_path.read_bytes(), mimetypes.guess_type(image_path.name)[0] or "application/octet-stream", headers={"Cache-Control": "no-store"})

        static_path = (DASHBOARD / path.lstrip("/")).resolve()
        if DASHBOARD.resolve() in static_path.parents and static_path.is_file():
            return self.serve_static(static_path)
        return self.send_json({"error": "Not found."}, 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/decisions":
            try:
                payload = self.read_body()
            except (json.JSONDecodeError, ValueError) as error:
                return self.send_json({"error": str(error)}, 400)
            valid_actions = {"approve", "proof_requested", "reject", "manual_link"}
            action = payload.get("action")
            case_id = payload.get("case_id")
            if str(CONFIG.get("backend_url", "")).strip():
                api_action = {"approve": "approve", "proof_requested": "proof_requested", "reject": "reject", "manual_link": "manual_link"}.get(action)
                if not api_action:
                    return self.send_json({"error": "Unsupported decision action."}, 400)
                live_payload = {
                    "subject_ref": payload.get("subject_ref", case_id),
                    "action": api_action,
                    "decided_by": CONFIG.get("coordinator_id", "coordinator"),
                    "reason": payload.get("reason", ""),
                    "seen_snapshot_hash": payload.get("seen_snapshot_hash"),
                    "link_to_evidence_id": payload.get("link_to_evidence_id"),
                }
                try:
                    body, content_type = live_request("POST", "/decisions", live_payload)
                    return self.send_bytes(201, body, content_type)
                except RuntimeError as error:
                    return self.send_json({"error": str(error)}, 502)
            case = next((row for row in DEMO_CASES if row["case_id"] == case_id), None)
            if action not in valid_actions or case is None:
                return self.send_json({"error": "Use a supported action and known fixture case."}, 400)
            linked_evidence_id = payload.get("link_to_evidence_id")
            if action == "manual_link":
                trip_evidence_ids = {record["evidence_id"] for record in records_for_trip(case["trip_id"])}
                if linked_evidence_id not in trip_evidence_ids or linked_evidence_id in case["evidence_ids"]:
                    return self.send_json({"error": "Choose another evidence item from this trip for a manual link."}, 400)
            snapshot_hash = payload.get("seen_snapshot_hash") or hashlib.sha256(json.dumps(case, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            decision = {
                "dec_id": f"SYN-DEC-{len(RUNTIME_DECISIONS) + 1:03d}",
                "case_id": case_id,
                "subject_ref": case_id,
                "evidence_ids": list(dict.fromkeys(case["evidence_ids"] + ([linked_evidence_id] if linked_evidence_id else []))),
                "action": action,
                "decided_by": "local demo coordinator",
                "reason": str(payload.get("reason", "")).strip()[:500],
                "link_to_evidence_id": linked_evidence_id if action == "manual_link" else None,
                "seen_snapshot_hash": snapshot_hash,
                "created_at": now_local(),
                "fixture_only": True,
            }
            with LOCK:
                RUNTIME_DECISIONS.append(decision)
                if action == "manual_link":
                    RUNTIME_RELATIONSHIPS.append({
                        "relationship_id": f"SYN-R-LOCAL-{len(RUNTIME_RELATIONSHIPS) + 1:03d}",
                        "from_evidence_id": case["evidence_ids"][0],
                        "to_evidence_id": linked_evidence_id,
                        "type": "MANUAL",
                        "basis": ["coordinator_action"],
                        "score": None,
                        "created_by": "local demo coordinator",
                        "created_at": decision["created_at"],
                        "reason": decision["reason"] or "Coordinator manually linked these evidence items for review.",
                        "auto_clear_eligible": False,
                        "fixture_only": True,
                    })
            return self.send_json({"decision": decision, "mode": "in_memory_fixture"}, 201)
        if parsed.path == "/api/audit/tamper":
            with LOCK:
                if AUDIT_CHAIN:
                    AUDIT_CHAIN[0]["record"]["ground_truth_fields"]["amount"] = "999999.00"
            return self.send_json({**verify_chain(), "mode": "synthetic_fixture_chain"})
        if parsed.path == "/api/audit/reset":
            with LOCK:
                AUDIT_CHAIN[:] = json.loads(json.dumps(ORIGINAL_AUDIT_CHAIN, ensure_ascii=False))
            return self.send_json({**verify_chain(), "mode": "synthetic_fixture_chain"})
        return self.send_json({"error": "Not found."}, 404)

    def serve_static(self, path: Path) -> None:
        if not path.is_file():
            return self.send_json({"error": "Static file not found."}, 404)
        content_type = MIME_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return self.send_bytes(200, path.read_bytes(), content_type, headers={"Cache-Control": "no-store"})


TEST_TRIP_ID = "SYN-TRIP-HELDOUT-01"


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, DEFAULT_PORT), Handler)
    print(f"Pratibimb synthetic dashboard: http://{host}:{DEFAULT_PORT}")
    print("Fixture mode only. Decisions and tamper actions are held in memory and reset when the server stops.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping fixture dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
