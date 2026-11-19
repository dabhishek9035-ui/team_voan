#!/usr/bin/env python3
"""Build Pratibimb's deterministic, hand-authored synthetic demo corpus.

Every transaction, name, timestamp, identifier and label is specified below.
There is no random-number use, network access, or external data download.

Dependencies: Pillow, NumPy, OpenCV (cv2).
Run from the repository root: python data/generate_synthetic_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
IMAGES = ROOT / "screenshots"
CANVAS_SIZE = (390, 844)
FIELDS = (
    "amount",
    "currency",
    "timestamp",
    "utr",
    "order_id",
    "ticket_id",
    "qr_payload",
    "origin_station",
    "destination_station",
    "fare",
    "payer_name_masked",
    "payee_name",
    "status_text",
    "app_name",
    "bank_name",
    "language_detected",
)


def field_set(**values: Any) -> dict[str, Any]:
    result = {name: None for name in FIELDS}
    result.update(values)
    return result


def item(
    evidence_id: str,
    *,
    split: str,
    scenario_id: str,
    trip_id: str | None,
    journey_id: str | None,
    sender_id: str | None,
    received_at: str,
    screenshot_type: str,
    fields: dict[str, Any],
    labels: tuple[str, ...] = (),
    notes: str = "",
    variant: str = "base",
    variant_of: str | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "split": split,
        "scenario_id": scenario_id,
        "trip_id": trip_id,
        "journey_id": journey_id,
        "sender_id": sender_id,
        "channel": "synthetic_fixture",
        "received_at": received_at,
        "screenshot_type": screenshot_type,
        "ground_truth_fields": fields,
        "labels": list(labels),
        "notes": notes,
        "variant": variant,
        "variant_of": variant_of,
        "authorship": "hand_authored_synthetic_ui",
        "image_file": None,
    }


CAL_TRIP = "SYN-TRIP-CAL-01"
TEST_TRIP = "SYN-TRIP-HELDOUT-01"

# These are deliberately authored fixtures, not samples or statistical draws.
# The calibration and held-out trips, journeys, and identifiers do not overlap.
ITEMS: list[dict[str, Any]] = [
    item(
        "SYN-E-CAL-001", split="calibration", scenario_id="cal_exact_paid_ticket",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-01", sender_id="SYN-SENDER-01",
        received_at="2026-10-21T08:32:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="40.00", currency="INR", timestamp="2026-10-21T08:31:00+05:30",
                         order_id="SYN-ORD-CAL-001", ticket_id="SYN-TKT-CAL-001",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-CAL-001",
                         origin_station="Indiranagar", destination_station="MG Road", fare="40.00",
                         payer_name_masked="S*** 01", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("clean",), notes="Baseline fictional ticket; QR encodes a reserved synthetic URI.",
    ),
    item(
        "SYN-E-CAL-002", split="calibration", scenario_id="cal_exact_paid_ticket",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-01", sender_id="SYN-SENDER-01",
        received_at="2026-10-21T08:32:10+05:30", screenshot_type="UPI_SUCCESS",
        fields=field_set(amount="40.00", currency="INR", timestamp="2026-10-21T08:29:00+05:30",
                         utr="SYN-UTR-CAL-001", order_id="SYN-ORD-CAL-001",
                         payer_name_masked="S*** 01", payee_name="METRO DEMO",
                         status_text="Payment successful", app_name="Pay Demo", language_detected="en"),
        labels=("clean",), notes="Shares a synthetic order reference with the ticket.",
    ),
    item(
        "SYN-E-CAL-003", split="calibration", scenario_id="cal_exact_paid_ticket",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-01", sender_id="SYN-SENDER-01",
        received_at="2026-10-21T08:33:00+05:30", screenshot_type="BANK_SMS",
        fields=field_set(amount="40.00", currency="INR", timestamp="2026-10-21T08:30:00+05:30",
                         utr="SYN-UTR-CAL-001", payer_name_masked="S*** 01",
                         status_text="Debited", app_name="Sample Bank SMS", bank_name="Sample Bank",
                         language_detected="en"),
        labels=("clean",), notes="Independent-looking mock source repeats the synthetic UTR.",
    ),
    item(
        "SYN-E-CAL-004", split="calibration", scenario_id="cal_exact_paid_ticket",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-01", sender_id="SYN-SENDER-01",
        received_at="2026-10-21T09:05:00+05:30", screenshot_type="CLAIM_SUBMISSION",
        fields=field_set(amount="40.00", currency="INR", timestamp="2026-10-21T09:05:00+05:30",
                         order_id="SYN-ORD-CAL-001", ticket_id="SYN-TKT-CAL-001",
                         origin_station="Indiranagar", destination_station="MG Road", fare="40.00",
                         payer_name_masked="S*** 01", status_text="Claim submitted",
                         app_name="Claim Desk Demo", language_detected="en"),
        labels=("clean",), notes="Claim form reuses the ticket and order references.",
    ),
    item(
        "SYN-E-CAL-005", split="calibration", scenario_id="cal_duplicate_variants",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-01", sender_id="SYN-SENDER-01",
        received_at="2026-10-21T10:02:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="40.00", currency="INR", timestamp="2026-10-21T08:31:00+05:30",
                         order_id="SYN-ORD-CAL-001", ticket_id="SYN-TKT-CAL-001",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-CAL-001",
                         origin_station="Indiranagar", destination_station="MG Road", fare="40.00",
                         payer_name_masked="S*** 01", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("duplicate", "exact_duplicate"), notes="Byte-for-byte resend of SYN-E-CAL-001.",
        variant="exact_copy", variant_of="SYN-E-CAL-001",
    ),
    item(
        "SYN-E-CAL-006", split="calibration", scenario_id="cal_duplicate_variants",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-01", sender_id="SYN-SENDER-01",
        received_at="2026-10-21T10:03:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="40.00", currency="INR", timestamp="2026-10-21T08:31:00+05:30",
                         order_id="SYN-ORD-CAL-001", ticket_id="SYN-TKT-CAL-001",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-CAL-001",
                         origin_station="Indiranagar", destination_station="MG Road", fare="40.00",
                         payer_name_masked="S*** 01", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("duplicate", "cropped"), notes="Four-pixel edge crop of SYN-E-CAL-001; ticket details remain visible.",
        variant="cropped", variant_of="SYN-E-CAL-001",
    ),
    item(
        "SYN-E-CAL-007", split="calibration", scenario_id="cal_payment_no_ticket",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-02", sender_id="SYN-SENDER-02",
        received_at="2026-10-21T08:42:00+05:30", screenshot_type="UPI_FAILED_PENDING",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-21T08:40:00+05:30",
                         order_id="SYN-ORD-CAL-002", payer_name_masked="S*** 02",
                         payee_name="METRO DEMO", status_text="Pending", app_name="Pay Demo",
                         language_detected="en"),
        labels=("no_ticket", "pending"), notes="Payment attempt is pending; no ticket is present in this journey.",
    ),
    item(
        "SYN-E-CAL-008", split="calibration", scenario_id="cal_payment_no_ticket",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-02", sender_id="SYN-SENDER-02",
        received_at="2026-10-21T08:43:00+05:30", screenshot_type="BOT_ERROR",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-21T08:41:00+05:30",
                         order_id="SYN-ORD-CAL-002", payer_name_masked="S*** 02",
                         status_text="Booking failed; no ticket issued", app_name="Metro Demo",
                         language_detected="en"),
        labels=("no_ticket",), notes="Bot message confirms only that this synthetic booking did not issue a ticket.",
    ),
    item(
        "SYN-E-CAL-009", split="calibration", scenario_id="cal_payment_no_ticket",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-02", sender_id="SYN-SENDER-02",
        received_at="2026-10-21T08:44:00+05:30", screenshot_type="REFUND_NOTICE",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-21T08:43:00+05:30",
                         order_id="SYN-ORD-CAL-002", payer_name_masked="S*** 02",
                         payee_name="METRO DEMO", status_text="Refund initiated", app_name="Metro Demo",
                         language_detected="en"),
        labels=("refund_notice", "no_ticket"), notes="Fictional refund status uses the same synthetic order reference.",
    ),
    item(
        "SYN-E-CAL-010", split="calibration", scenario_id="cal_inferred_pair",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-03", sender_id="SYN-SENDER-03",
        received_at="2026-10-21T08:37:00+05:30", screenshot_type="UPI_SUCCESS",
        fields=field_set(amount="50.00", currency="INR", timestamp="2026-10-21T08:35:00+05:30",
                         utr="SYN-UTR-CAL-003", payer_name_masked="S*** 03", payee_name="METRO DEMO",
                         status_text="ಪಾವತಿ ಯಶಸ್ವಿ", app_name="Pay Demo", language_detected="kn"),
        labels=("clean", "inferred_pair"), notes="Kannada-labeled payment; deliberately has no order or ticket identifier.",
    ),
    item(
        "SYN-E-CAL-011", split="calibration", scenario_id="cal_inferred_pair",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-03", sender_id="SYN-SENDER-03",
        received_at="2026-10-21T08:39:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="50.00", currency="INR", timestamp="2026-10-21T08:38:00+05:30",
                         ticket_id="SYN-TKT-CAL-003",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-CAL-003",
                         origin_station="Indiranagar", destination_station="MG Road", fare="50.00",
                         payer_name_masked="S*** 03", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("clean", "inferred_pair"), notes="No shared transaction identifier; same sender, amount, time window and trip context.",
    ),
    item(
        "SYN-E-CAL-012", split="calibration", scenario_id="cal_notice_types",
        trip_id=None, journey_id=None, sender_id="SYN-SENDER-04",
        received_at="2026-10-21T11:00:00+05:30", screenshot_type="SUSPECT_NOTICE",
        fields=field_set(timestamp="2026-10-21T10:59:00+05:30", status_text="Your refund is blocked. Pay a release fee and share your KYC details at metro-refund.sample.invalid.", app_name="Message Demo", language_detected="en"),
        labels=("suspect_notice",), notes="Hand-authored suspicious-message example; uses the reserved .invalid domain.",
    ),
    item(
        "SYN-E-CAL-013", split="calibration", scenario_id="cal_notice_types",
        trip_id=None, journey_id=None, sender_id="SYN-SENDER-05",
        received_at="2026-10-21T11:05:00+05:30", screenshot_type="OTHER",
        fields=field_set(status_text="Photo backup complete", app_name="Gallery Demo", language_detected="en"),
        labels=("other",), notes="Non-transactional gallery notification for classifier abstention coverage.",
    ),
    item(
        "SYN-E-CAL-014", split="calibration", scenario_id="cal_out_of_window",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-05", sender_id="SYN-SENDER-06",
        received_at="2026-10-21T11:10:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="40.00", currency="INR", timestamp="2026-10-04T08:31:00+05:30",
                         ticket_id="SYN-TKT-CAL-004",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-CAL-004",
                         origin_station="Indiranagar", destination_station="MG Road", fare="40.00",
                         payer_name_masked="S*** 06", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("out_of_window",), notes="Ticket date is outside the calibration trip's 2026-10-21 window.",
    ),
    item(
        "SYN-E-CAL-015", split="calibration", scenario_id="cal_unmatched_credit",
        trip_id=CAL_TRIP, journey_id="SYN-J-CAL-06", sender_id="SYN-SENDER-07",
        received_at="2026-10-21T11:15:00+05:30", screenshot_type="BANK_SMS",
        fields=field_set(amount="115.00", currency="INR", timestamp="2026-10-21T11:12:00+05:30",
                         payer_name_masked="S*** 07", status_text="Credit received; reference unavailable",
                         app_name="Sample Bank SMS", bank_name="Sample Bank", language_detected="en"),
        labels=("unmatched",), notes="No transaction identifier or matching payment is supplied.",
    ),
    item(
        "SYN-E-TEST-016", split="heldout", scenario_id="test_exact_paid_ticket",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-01", sender_id="SYN-SENDER-08",
        received_at="2026-10-30T09:02:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-30T09:01:00+05:30",
                         order_id="SYN-ORD-TEST-101", ticket_id="SYN-TKT-TEST-101",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-TEST-101",
                         origin_station="MG Road", destination_station="Cubbon Park", fare="60.00",
                         payer_name_masked="S*** 08", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("clean",), notes="Held-out clean ticket; test-trip identifiers are disjoint from calibration.",
    ),
    item(
        "SYN-E-TEST-017", split="heldout", scenario_id="test_exact_paid_ticket",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-01", sender_id="SYN-SENDER-08",
        received_at="2026-10-30T09:02:10+05:30", screenshot_type="UPI_SUCCESS",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-30T08:59:00+05:30",
                         utr="SYN-UTR-TEST-101", order_id="SYN-ORD-TEST-101",
                         payer_name_masked="S*** 08", payee_name="METRO DEMO",
                         status_text="Payment successful", app_name="Pay Demo", language_detected="en"),
        labels=("clean",), notes="Shares a synthetic order reference with SYN-E-TEST-016.",
    ),
    item(
        "SYN-E-TEST-018", split="heldout", scenario_id="test_exact_paid_ticket",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-01", sender_id="SYN-SENDER-08",
        received_at="2026-10-30T09:03:00+05:30", screenshot_type="BANK_SMS",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-30T09:00:00+05:30",
                         utr="SYN-UTR-TEST-101", payer_name_masked="S*** 08", status_text="Debited",
                         app_name="Sample Bank SMS", bank_name="Sample Bank", language_detected="en"),
        labels=("clean",), notes="Bank mock repeats the held-out UPI transaction's synthetic UTR.",
    ),
    item(
        "SYN-E-TEST-019", split="heldout", scenario_id="test_duplicate_variants",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-01", sender_id="SYN-SENDER-08",
        received_at="2026-10-30T10:02:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-30T09:01:00+05:30",
                         order_id="SYN-ORD-TEST-101", ticket_id="SYN-TKT-TEST-101",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-TEST-101",
                         origin_station="MG Road", destination_station="Cubbon Park", fare="60.00",
                         payer_name_masked="S*** 08", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("duplicate", "recompressed"), notes="JPEG quality-42 re-encoding of SYN-E-TEST-016.",
        variant="recompressed", variant_of="SYN-E-TEST-016",
    ),
    item(
        "SYN-E-TEST-020", split="heldout", scenario_id="test_duplicate_variants",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-01", sender_id="SYN-SENDER-08",
        received_at="2026-10-30T10:03:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-30T09:01:00+05:30",
                         order_id="SYN-ORD-TEST-101", ticket_id="SYN-TKT-TEST-101",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-TEST-101",
                         origin_station="MG Road", destination_station="Cubbon Park", fare="60.00",
                         payer_name_masked="S*** 08", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("duplicate", "screenshot_of_screenshot"), notes="Gallery-style recapture containing SYN-E-TEST-016.",
        variant="screenshot_of_screenshot", variant_of="SYN-E-TEST-016",
    ),
    item(
        "SYN-E-TEST-021", split="heldout", scenario_id="test_payment_no_ticket",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-02", sender_id="SYN-SENDER-09",
        received_at="2026-10-30T09:13:00+05:30", screenshot_type="UPI_FAILED_PENDING",
        fields=field_set(amount="80.00", currency="INR", timestamp="2026-10-30T09:11:00+05:30",
                         order_id="SYN-ORD-TEST-202", payer_name_masked="S*** 09", payee_name="METRO DEMO",
                         status_text="Pending", app_name="Pay Demo", language_detected="en"),
        labels=("no_ticket", "pending"), notes="Pending payment attempt; no ticket evidence for this order.",
    ),
    item(
        "SYN-E-TEST-022", split="heldout", scenario_id="test_payment_no_ticket",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-02", sender_id="SYN-SENDER-09",
        received_at="2026-10-30T09:14:00+05:30", screenshot_type="BOT_ERROR",
        fields=field_set(amount="80.00", currency="INR", timestamp="2026-10-30T09:12:00+05:30",
                         order_id="SYN-ORD-TEST-202", payer_name_masked="S*** 09",
                         status_text="Booking failed; no ticket issued", app_name="Metro Demo",
                         language_detected="en"),
        labels=("no_ticket",), notes="Failure message shares the order reference with SYN-E-TEST-021.",
    ),
    item(
        "SYN-E-TEST-023", split="heldout", scenario_id="test_payment_no_ticket",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-02", sender_id="SYN-SENDER-09",
        received_at="2026-10-30T09:15:00+05:30", screenshot_type="REFUND_NOTICE",
        fields=field_set(amount="80.00", currency="INR", timestamp="2026-10-30T09:14:00+05:30",
                         order_id="SYN-ORD-TEST-202", payer_name_masked="S*** 09",
                         payee_name="METRO DEMO", status_text="Refund initiated", app_name="Metro Demo",
                         language_detected="en"),
        labels=("refund_notice", "no_ticket"), notes="Mock refund message is tied to the failed booking reference.",
    ),
    item(
        "SYN-E-TEST-024", split="heldout", scenario_id="test_inferred_pair",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-03", sender_id="SYN-SENDER-10",
        received_at="2026-10-30T09:22:00+05:30", screenshot_type="UPI_SUCCESS",
        fields=field_set(amount="45.00", currency="INR", timestamp="2026-10-30T09:20:00+05:30",
                         utr="SYN-UTR-TEST-303", payer_name_masked="S*** 10", payee_name="METRO DEMO",
                         status_text="ಪಾವತಿ ಯಶಸ್ವಿ", app_name="Pay Demo", language_detected="kn"),
        labels=("clean", "inferred_pair"), notes="Kannada payment screen with no shared ticket/order identifier.",
    ),
    item(
        "SYN-E-TEST-025", split="heldout", scenario_id="test_inferred_pair",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-03", sender_id="SYN-SENDER-10",
        received_at="2026-10-30T09:24:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="45.00", currency="INR", timestamp="2026-10-30T09:23:00+05:30",
                         ticket_id="SYN-TKT-TEST-303",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-TEST-303",
                         origin_station="Cubbon Park", destination_station="Vidhana Soudha", fare="45.00",
                         payer_name_masked="S*** 10", payee_name="METRO DEMO",
                         status_text="ಟಿಕೆಟ್ ನೀಡಲಾಗಿದೆ", app_name="Metro Demo", language_detected="kn"),
        labels=("clean", "inferred_pair"), notes="Kannada ticket; only amount, time, owner and trip context support the inferred link.",
    ),
    item(
        "SYN-E-TEST-026", split="heldout", scenario_id="test_manual_claim_mismatch",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-01", sender_id="SYN-SENDER-08",
        received_at="2026-10-30T10:30:00+05:30", screenshot_type="CLAIM_SUBMISSION",
        fields=field_set(amount="80.00", currency="INR", timestamp="2026-10-30T10:30:00+05:30",
                         ticket_id="SYN-TKT-TEST-101", origin_station="MG Road",
                         destination_station="Cubbon Park", fare="80.00", payer_name_masked="S*** 08",
                         status_text="Claim submitted", app_name="Claim Desk Demo", language_detected="en"),
        labels=("fake", "claim_mismatch", "manual_review"),
        notes="Hand-authored inconsistent claim: it references a 60.00 ticket but claims 80.00. Not an AI-generated sample.",
    ),
    item(
        "SYN-E-TEST-027", split="heldout", scenario_id="test_notice_types",
        trip_id=None, journey_id=None, sender_id="SYN-SENDER-11",
        received_at="2026-10-30T11:00:00+05:30", screenshot_type="SUSPECT_NOTICE",
        fields=field_set(timestamp="2026-10-30T10:59:00+05:30", status_text="Refund expires today. Share your UPI PIN to receive it at metro-refund.sample.invalid.", app_name="Message Demo", language_detected="en"),
        labels=("suspect_notice",), notes="Hand-authored suspicious-message example using an invalid reserved domain.",
    ),
    item(
        "SYN-E-TEST-028", split="heldout", scenario_id="test_out_of_window_and_fake",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-04", sender_id="SYN-SENDER-12",
        received_at="2026-10-30T11:10:00+05:30", screenshot_type="TICKET_QR",
        fields=field_set(amount="70.00", currency="INR", timestamp="2026-10-11T08:10:00+05:30",
                         order_id="SYN-ORD-TEST-404", ticket_id="SYN-TKT-TEST-404",
                         qr_payload="SYNTHETIC://PRATIBIMB/TICKET/SYN-TKT-TEST-404",
                         origin_station="MG Road", destination_station="Cubbon Park", fare="70.00",
                         payer_name_masked="S*** 12", payee_name="METRO DEMO",
                         status_text="Ticket issued", app_name="Metro Demo", language_detected="en"),
        labels=("fake", "out_of_window", "fabricated_sample"),
        notes="Hand-authored ticket-like sample dated outside the held-out trip window; not an AI-generated sample.",
    ),
    item(
        "SYN-E-TEST-029", split="heldout", scenario_id="test_unmatched_candidate",
        trip_id=TEST_TRIP, journey_id="SYN-J-TEST-05", sender_id="SYN-SENDER-13",
        received_at="2026-10-30T09:01:00+05:30", screenshot_type="BANK_SMS",
        fields=field_set(amount="60.00", currency="INR", timestamp="2026-10-30T09:00:00+05:30",
                         payer_name_masked="S*** 13", status_text="Debited; reference unavailable",
                         app_name="Sample Bank SMS", bank_name="Sample Bank", language_detected="en"),
        labels=("unmatched", "ambiguous_candidate"), notes="Same amount and minute as SYN-E-TEST-017, but a different owner and no shared reference.",
    ),
    item(
        "SYN-E-TEST-030", split="heldout", scenario_id="test_notice_types",
        trip_id=None, journey_id=None, sender_id="SYN-SENDER-14",
        received_at="2026-10-30T11:05:00+05:30", screenshot_type="OTHER",
        fields=field_set(status_text="Cloud sync complete", app_name="Gallery Demo", language_detected="en"),
        labels=("other",), notes="Unrelated gallery status to test the OTHER path.",
    ),
]


RELATIONSHIPS: list[dict[str, Any]] = [
    {
        "relationship_id": "SYN-R-001", "from_evidence_id": "SYN-E-CAL-002", "to_evidence_id": "SYN-E-CAL-001",
        "type": "EXACT", "basis": ["order_id"], "auto_clear_eligible": True,
        "reason": "The payment and ticket share SYN-ORD-CAL-001.",
    },
    {
        "relationship_id": "SYN-R-002", "from_evidence_id": "SYN-E-CAL-003", "to_evidence_id": "SYN-E-CAL-002",
        "type": "EXACT", "basis": ["utr"], "auto_clear_eligible": True,
        "reason": "The bank message and payment share SYN-UTR-CAL-001.",
    },
    {
        "relationship_id": "SYN-R-003", "from_evidence_id": "SYN-E-CAL-004", "to_evidence_id": "SYN-E-CAL-001",
        "type": "EXACT", "basis": ["ticket_id", "order_id"], "auto_clear_eligible": True,
        "reason": "The claim repeats the ticket and order references.",
    },
    {
        "relationship_id": "SYN-R-004", "from_evidence_id": "SYN-E-CAL-005", "to_evidence_id": "SYN-E-CAL-001",
        "type": "EXACT", "basis": ["ticket_id", "sha256"], "auto_clear_eligible": False,
        "reason": "Same ticket and byte-for-byte image resend; do not count the duplicate twice.",
    },
    {
        "relationship_id": "SYN-R-005", "from_evidence_id": "SYN-E-CAL-006", "to_evidence_id": "SYN-E-CAL-001",
        "type": "EXACT", "basis": ["ticket_id", "perceptual_similarity"], "auto_clear_eligible": False,
        "reason": "Same ticket in a cropped image; perceptual similarity is a signal, not a conclusion.",
    },
    {
        "relationship_id": "SYN-R-006", "from_evidence_id": "SYN-E-CAL-008", "to_evidence_id": "SYN-E-CAL-007",
        "type": "EXACT", "basis": ["order_id"], "auto_clear_eligible": True,
        "reason": "The failed booking message and pending payment share SYN-ORD-CAL-002.",
    },
    {
        "relationship_id": "SYN-R-007", "from_evidence_id": "SYN-E-CAL-009", "to_evidence_id": "SYN-E-CAL-007",
        "type": "EXACT", "basis": ["order_id"], "auto_clear_eligible": True,
        "reason": "The refund notice and pending payment share SYN-ORD-CAL-002.",
    },
    {
        "relationship_id": "SYN-R-008", "from_evidence_id": "SYN-E-CAL-010", "to_evidence_id": "SYN-E-CAL-011",
        "type": "INFERRED", "basis": ["amount", "timestamp_window", "payer_name_masked", "trip_context"],
        "auto_clear_eligible": False,
        "reason": "Amount, time, sender and trip context align, but no shared transaction or ticket identifier exists.",
    },
    {
        "relationship_id": "SYN-R-009", "from_evidence_id": "SYN-E-TEST-017", "to_evidence_id": "SYN-E-TEST-016",
        "type": "EXACT", "basis": ["order_id"], "auto_clear_eligible": True,
        "reason": "The payment and ticket share SYN-ORD-TEST-101.",
    },
    {
        "relationship_id": "SYN-R-010", "from_evidence_id": "SYN-E-TEST-018", "to_evidence_id": "SYN-E-TEST-017",
        "type": "EXACT", "basis": ["utr"], "auto_clear_eligible": True,
        "reason": "The bank message and payment share SYN-UTR-TEST-101.",
    },
    {
        "relationship_id": "SYN-R-011", "from_evidence_id": "SYN-E-TEST-019", "to_evidence_id": "SYN-E-TEST-016",
        "type": "EXACT", "basis": ["ticket_id", "perceptual_similarity"], "auto_clear_eligible": False,
        "reason": "Same ticket in a lossy JPEG re-encoding; the image hash differs from the original.",
    },
    {
        "relationship_id": "SYN-R-012", "from_evidence_id": "SYN-E-TEST-020", "to_evidence_id": "SYN-E-TEST-016",
        "type": "EXACT", "basis": ["ticket_id", "perceptual_similarity"], "auto_clear_eligible": False,
        "reason": "Same ticket inside a gallery recapture; the outer screen changes the image appearance.",
    },
    {
        "relationship_id": "SYN-R-013", "from_evidence_id": "SYN-E-TEST-022", "to_evidence_id": "SYN-E-TEST-021",
        "type": "EXACT", "basis": ["order_id"], "auto_clear_eligible": True,
        "reason": "The failed booking message and pending payment share SYN-ORD-TEST-202.",
    },
    {
        "relationship_id": "SYN-R-014", "from_evidence_id": "SYN-E-TEST-023", "to_evidence_id": "SYN-E-TEST-021",
        "type": "EXACT", "basis": ["order_id"], "auto_clear_eligible": True,
        "reason": "The refund notice and pending payment share SYN-ORD-TEST-202.",
    },
    {
        "relationship_id": "SYN-R-015", "from_evidence_id": "SYN-E-TEST-024", "to_evidence_id": "SYN-E-TEST-025",
        "type": "INFERRED", "basis": ["amount", "timestamp_window", "payer_name_masked", "trip_context"],
        "auto_clear_eligible": False,
        "reason": "Amount, time, sender and trip context align; no shared identifier exists, so this needs review.",
    },
    {
        "relationship_id": "SYN-R-016", "from_evidence_id": "SYN-E-TEST-026", "to_evidence_id": "SYN-E-TEST-016",
        "type": "MANUAL", "basis": ["coordinator_action"], "auto_clear_eligible": False,
        "reason": "A coordinator manually linked the claim to the ticket for review; claimed fare 80.00 conflicts with ticket fare 60.00.",
    },
    {
        "relationship_id": "SYN-R-017", "from_evidence_id": "SYN-E-TEST-029", "to_evidence_id": "SYN-E-TEST-017",
        "type": "UNMATCHED", "basis": [], "auto_clear_eligible": False,
        "reason": "Same amount and minute are insufficient; sender differs and no transaction identifier is shared.",
    },
]


DEMO_CASES = [
    {
        "case_id": "SYN-CASE-001", "title": "Pending payment; no ticket evidence",
        "trip_id": CAL_TRIP, "evidence_ids": ["SYN-E-CAL-007", "SYN-E-CAL-008", "SYN-E-CAL-009"],
        "relationship_type": "EXACT", "machine_state": "case_opened_expected",
        "decision_support": "needs_review", "reason": "The payment attempt and failure/refund messages relate by order ID, but no ticket evidence is present.",
        "evidence_levels": {"payment_attempt": "extracted", "ticket_issued": "unverified", "refund_status": "extracted"},
        "coordinator_decision": None,
    },
    {
        "case_id": "SYN-CASE-002", "title": "Contextual payment and ticket match",
        "trip_id": TEST_TRIP, "evidence_ids": ["SYN-E-TEST-024", "SYN-E-TEST-025"],
        "relationship_type": "INFERRED", "machine_state": "linked_needs_review",
        "decision_support": "needs_review", "reason": "Amount, time, owner and trip context align; there is no shared identifier.",
        "evidence_levels": {"amount": "corroborated", "ticket_issued": "extracted", "travelled": "unverified"},
        "coordinator_decision": None,
    },
    {
        "case_id": "SYN-CASE-003", "title": "Manually linked claim with fare mismatch",
        "trip_id": TEST_TRIP, "evidence_ids": ["SYN-E-TEST-026", "SYN-E-TEST-016"],
        "relationship_type": "MANUAL", "machine_state": "needs_review",
        "decision_support": "needs_review", "reason": "The claim says 80.00; the referenced ticket says 60.00.",
        "evidence_levels": {"ticket_issued": "extracted", "claimed_fare": "extracted", "travelled": "unverified"},
        "coordinator_decision": None,
    },
    {
        "case_id": "SYN-CASE-004", "title": "Similar amount without a reliable link",
        "trip_id": TEST_TRIP, "evidence_ids": ["SYN-E-TEST-029", "SYN-E-TEST-017"],
        "relationship_type": "UNMATCHED", "machine_state": "unmatched_needs_review",
        "decision_support": "insufficient", "reason": "Different synthetic senders and no shared transaction identifier.",
        "evidence_levels": {"debit": "extracted", "ticket_issued": "extracted"},
        "coordinator_decision": None,
    },
    {
        "case_id": "SYN-CASE-005", "title": "Consistent payment, bank and ticket references",
        "trip_id": CAL_TRIP, "evidence_ids": ["SYN-E-CAL-001", "SYN-E-CAL-002", "SYN-E-CAL-003"],
        "relationship_type": "EXACT", "machine_state": "linked_exact",
        "decision_support": "clear_candidate", "reason": "Synthetic order and UTR identifiers agree across the submitted screenshots.",
        "evidence_levels": {"debit": "corroborated", "ticket_issued": "extracted", "travelled": "unverified"},
        "coordinator_decision": None,
    },
]


# Claim-level labels for the evaluator. ``is_bad`` identifies a wrong or unsafe
# claim for false-accept accounting; a clean inferred pair is review-only but
# is not itself labelled bad. These are synthetic policy examples, not a rate.
EVALUATION_CASES = [
    {"claim_case_id": "SYN-CLAIM-CAL-001", "split": "calibration", "evidence_ids": ["SYN-E-CAL-001", "SYN-E-CAL-002", "SYN-E-CAL-003"], "label": "clean_exact", "is_bad": False, "auto_clear_eligible": True},
    {"claim_case_id": "SYN-CLAIM-CAL-002", "split": "calibration", "evidence_ids": ["SYN-E-CAL-001", "SYN-E-CAL-005", "SYN-E-CAL-006"], "label": "duplicate_ticket", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-CAL-003", "split": "calibration", "evidence_ids": ["SYN-E-CAL-010", "SYN-E-CAL-011"], "label": "inferred_pair", "is_bad": False, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-CAL-004", "split": "calibration", "evidence_ids": ["SYN-E-CAL-007", "SYN-E-CAL-008", "SYN-E-CAL-009"], "label": "payment_without_ticket", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-CAL-005", "split": "calibration", "evidence_ids": ["SYN-E-CAL-012"], "label": "suspect_notice", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-CAL-006", "split": "calibration", "evidence_ids": ["SYN-E-CAL-014"], "label": "out_of_window", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-TEST-001", "split": "heldout", "evidence_ids": ["SYN-E-TEST-016", "SYN-E-TEST-017", "SYN-E-TEST-018"], "label": "clean_exact", "is_bad": False, "auto_clear_eligible": True},
    {"claim_case_id": "SYN-CLAIM-TEST-002", "split": "heldout", "evidence_ids": ["SYN-E-TEST-016", "SYN-E-TEST-019", "SYN-E-TEST-020"], "label": "duplicate_ticket", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-TEST-003", "split": "heldout", "evidence_ids": ["SYN-E-TEST-021", "SYN-E-TEST-022", "SYN-E-TEST-023"], "label": "payment_without_ticket", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-TEST-004", "split": "heldout", "evidence_ids": ["SYN-E-TEST-024", "SYN-E-TEST-025"], "label": "inferred_pair", "is_bad": False, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-TEST-005", "split": "heldout", "evidence_ids": ["SYN-E-TEST-016", "SYN-E-TEST-026"], "label": "manual_claim_mismatch", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-TEST-006", "split": "heldout", "evidence_ids": ["SYN-E-TEST-027"], "label": "suspect_notice", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-TEST-007", "split": "heldout", "evidence_ids": ["SYN-E-TEST-028"], "label": "fabricated_out_of_window", "is_bad": True, "auto_clear_eligible": False},
    {"claim_case_id": "SYN-CLAIM-TEST-008", "split": "heldout", "evidence_ids": ["SYN-E-TEST-017", "SYN-E-TEST-029"], "label": "unmatched_owner_conflict", "is_bad": True, "auto_clear_eligible": False},
]


TRIP_WINDOWS = [
    {"trip_id": CAL_TRIP, "split": "calibration", "service_date": "2026-10-21", "window_start": "2026-10-21T00:00:00+05:30", "window_end": "2026-10-21T23:59:59+05:30"},
    {"trip_id": TEST_TRIP, "split": "heldout", "service_date": "2026-10-30", "window_start": "2026-10-30T00:00:00+05:30", "window_end": "2026-10-30T23:59:59+05:30"},
]


EN_LABELS = {
    "amount": "Amount", "timestamp": "Time", "utr": "UTR", "order_id": "Order ref",
    "ticket_id": "Ticket ID", "origin_station": "From", "destination_station": "To",
    "fare": "Fare", "payer_name_masked": "Payer", "payee_name": "Payee",
    "status_text": "Status", "bank_name": "Bank",
}
KN_LABELS = {
    "amount": "ಮೊತ್ತ", "timestamp": "ಸಮಯ", "utr": "ಯುಟಿಆರ್", "order_id": "ಆರ್ಡರ್ ಉಲ್ಲೇಖ",
    "ticket_id": "ಟಿಕೆಟ್ ಸಂಖ್ಯೆ", "origin_station": "ಇಲ್ಲಿಂದ", "destination_station": "ವರೆಗೆ",
    "fare": "ದರ", "payer_name_masked": "ಪಾವತಿದವರು", "payee_name": "ಸ್ವೀಕರಿಸುವವರು",
    "status_text": "ಸ್ಥಿತಿ", "bank_name": "ಬ್ಯಾಂಕ್",
}


def get_font_path() -> str:
    candidates = [
        r"C:\Windows\Fonts\Nirmala.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansKannada-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansKannada-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("Install a Kannada-capable font (Nirmala UI or Noto Sans Kannada) before regenerating the corpus.")


FONT_PATH = get_font_path()


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Nirmala's first face is regular and renders the Kannada labels used here.
    try:
        return ImageFont.truetype(FONT_PATH, size=size, index=0)
    except TypeError:
        return ImageFont.truetype(FONT_PATH, size=size)


def text_fit(draw: ImageDraw.ImageDraw, text: str, start_size: int, max_width: int, *, fill: str, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = start_size
    while size > 10:
        candidate = font(size, bold=bold)
        box = draw.textbbox((0, 0), text, font=candidate)
        if box[2] - box[0] <= max_width:
            return candidate
        size -= 1
    return font(10, bold=bold)


def display_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return value


def money(fields: dict[str, Any], key: str = "amount") -> str:
    value = fields.get(key)
    if value is None:
        return ""
    return f"₹{float(value):.2f}"


def qr_image(payload: str, size: int = 148) -> Image.Image:
    matrix = cv2.QRCodeEncoder_create().encode(payload)
    code = Image.fromarray(matrix).convert("L")
    code = code.resize((size - 18, size - 18), Image.Resampling.NEAREST)
    bordered = Image.new("L", (size, size), 255)
    bordered.paste(code, (9, 9))
    return bordered.convert("RGB")


def field_label(key: str, language: str) -> str:
    table = KN_LABELS if language == "kn" else EN_LABELS
    return table.get(key, key.replace("_", " ").title())


def render_screenshot(record: dict[str, Any]) -> Image.Image:
    fields = record["ground_truth_fields"]
    language = fields.get("language_detected") or "en"
    app_name = fields.get("app_name") or "Demo App"
    screenshot_type = record["screenshot_type"]
    canvas = Image.new("RGB", CANVAS_SIZE, "#edf1f5")
    draw = ImageDraw.Draw(canvas)

    # Persistent disclosure is intentionally visible on every image.
    draw.rectangle((0, 0, 390, 31), fill="#18263d")
    draw.text((14, 8), "SYNTHETIC DATA  |  NOT A REAL TRANSACTION", font=font(12), fill="#ffffff")
    draw.rectangle((0, 31, 390, 62), fill="#ffffff")
    draw.text((18, 39), "09:41", font=font(13), fill="#1b2638")
    draw.text((315, 39), "DEMO  •  100%", font=font(12), fill="#1b2638")
    draw.rectangle((0, 62, 390, 113), fill="#243858")
    app_font = text_fit(draw, app_name.upper(), 18, 350, fill="#ffffff", bold=True)
    draw.text((20, 78), app_name.upper(), font=app_font, fill="#ffffff")

    card = (18, 129, 372, 795)
    draw.rounded_rectangle(card, radius=18, fill="#ffffff", outline="#d9e0e8", width=1)
    accent = "#16835d" if screenshot_type in ("TICKET_QR", "UPI_SUCCESS", "BANK_SMS") else "#a34c36"

    if screenshot_type == "TICKET_QR":
        title = "QR Ticket" if language != "kn" else "QR ಟಿಕೆಟ್"
    elif screenshot_type == "UPI_SUCCESS":
        title = "Payment successful" if language != "kn" else "ಪಾವತಿ ಯಶಸ್ವಿ"
    elif screenshot_type == "UPI_FAILED_PENDING":
        title = "Payment pending" if language != "kn" else "ಪಾವತಿ ಬಾಕಿಯಿದೆ"
    elif screenshot_type == "BANK_SMS":
        title = "Bank message" if language != "kn" else "ಬ್ಯಾಂಕ್ ಸಂದೇಶ"
    elif screenshot_type == "REFUND_NOTICE":
        title = "Refund update" if language != "kn" else "ಮರುಪಾವತಿ ಮಾಹಿತಿ"
    elif screenshot_type == "BOT_ERROR":
        title = "Booking update" if language != "kn" else "ಬುಕಿಂಗ್ ಮಾಹಿತಿ"
    elif screenshot_type == "CLAIM_SUBMISSION":
        title = "Claim submitted" if language != "kn" else "ಕ್ಲೇಮ್ ಸಲ್ಲಿಸಲಾಗಿದೆ"
    elif screenshot_type == "SUSPECT_NOTICE":
        title = "Message" if language != "kn" else "ಸಂದೇಶ"
    else:
        title = "Gallery status"

    title_font = text_fit(draw, title, 23, 320, fill="#17283f", bold=True)
    draw.text((35, 148), title, font=title_font, fill="#17283f")

    status = fields.get("status_text") or ""
    if screenshot_type == "SUSPECT_NOTICE":
        draw.rounded_rectangle((34, 188, 356, 225), radius=11, fill="#fff2dc")
        draw.text((46, 198), "Sample message content", font=font(14), fill="#805018")
        body = status
        body_font = font(16)
        words = body.split()
        lines: list[str] = []
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if draw.textbbox((0, 0), candidate, font=body_font)[2] > 300 and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        y = 248
        for line in lines:
            draw.text((36, y), line, font=body_font, fill="#24334a")
            y += 30
        sample_time = display_time(fields.get("timestamp"))
        if sample_time:
            draw.text((36, min(y + 12, 675)), f"Sample time: {sample_time}", font=font(12), fill="#66758a")
        draw.text((36, min(y + 36, 706)), "No real account or payment is involved.", font=font(13), fill="#66758a")
    elif screenshot_type == "OTHER":
        draw.rounded_rectangle((34, 190, 356, 247), radius=12, fill="#e6f4ec")
        draw.text((48, 209), status or "Complete", font=text_fit(draw, status or "Complete", 17, 285, fill="#24563f"), fill="#24563f")
        draw.rounded_rectangle((46, 275, 344, 608), radius=14, fill="#dce7f0")
        draw.ellipse((102, 334, 268, 500), fill="#aac6d9")
        draw.polygon([(46, 520), (120, 430), (198, 520), (260, 440), (344, 540), (344, 608), (46, 608)], fill="#7696a7")
        draw.text((39, 640), "Unrelated notification sample", font=font(14), fill="#66758a")
    elif screenshot_type == "TICKET_QR":
        draw.rounded_rectangle((34, 188, 356, 224), radius=11, fill="#e5f5ee")
        status_font = text_fit(draw, status, 14, 296, fill="#176447")
        draw.text((46, 198), status, font=status_font, fill="#176447")
        route = f"{fields.get('origin_station') or '-'}  to  {fields.get('destination_station') or '-'}"
        route_font = text_fit(draw, route, 18, 306, fill="#182b45", bold=True)
        draw.text((36, 242), route, font=route_font, fill="#182b45")
        amount_text = money(fields, "fare") or money(fields)
        draw.text((36, 272), field_label("amount", language), font=font(12), fill="#728097")
        draw.text((36, 288), amount_text, font=font(23), fill=accent)
        rows = [
            ("ticket_id", fields.get("ticket_id")),
            ("order_id", fields.get("order_id")),
            ("timestamp", display_time(fields.get("timestamp"))),
            ("payer_name_masked", fields.get("payer_name_masked")),
            ("payee_name", fields.get("payee_name")),
            ("fare", money(fields, "fare")),
        ]
        y = 328
        for key, value in rows:
            if value is None:
                continue
            draw.text((36, y), field_label(key, language), font=font(12), fill="#728097")
            val = str(value)
            val_font = text_fit(draw, val, 14, 220, fill="#21334c")
            draw.text((142, y - 1), val, font=val_font, fill="#21334c")
            y += 38
        payload = fields.get("qr_payload")
        if payload:
            qr_size = 132
            qr_y = max(442, y + 6)
            if qr_y + qr_size > 750:
                qr_size = 108
                qr_y = 750 - qr_size
            code = qr_image(payload, qr_size)
            canvas.paste(code, ((390 - qr_size) // 2, qr_y))
            caption_y = min(qr_y + qr_size + 7, 775)
            draw.text((113, caption_y), "Synthetic QR payload", font=font(12), fill="#66758a")
    else:
        badge_fill = "#e5f5ee" if screenshot_type in ("UPI_SUCCESS", "BANK_SMS") else "#fff1e8"
        draw.rounded_rectangle((34, 188, 356, 224), radius=11, fill=badge_fill)
        status_font = text_fit(draw, status, 14, 296, fill=accent)
        draw.text((46, 198), status, font=status_font, fill=accent)
        amount_value = fields.get("amount")
        if amount_value is not None:
            draw.text((36, 242), money(fields), font=font(27), fill="#182b45")
        rows: list[tuple[str, Any]] = []
        for key in ("payer_name_masked", "payee_name", "timestamp", "utr", "order_id", "ticket_id", "bank_name", "origin_station", "destination_station", "fare"):
            value = fields.get(key)
            if value is None:
                continue
            if key == "timestamp":
                value = display_time(str(value))
            rows.append((key, value))
        y = 300
        for key, value in rows[:8]:
            draw.text((36, y), field_label(key, language), font=font(12), fill="#728097")
            val = str(value)
            val_font = text_fit(draw, val, 15, 218, fill="#21334c")
            draw.text((142, y - 1), val, font=val_font, fill="#21334c")
            y += 49
        if screenshot_type == "CLAIM_SUBMISSION":
            draw.rounded_rectangle((36, min(y + 18, 686), 354, min(y + 64, 732)), radius=10, fill="#edf3fa")
            draw.text((49, min(y + 32, 700)), "Coordinator review pending", font=font(13), fill="#425a76")

    # Every image remains clearly marked, including nested captures.
    draw.rectangle((0, 808, 390, 844), fill="#18263d")
    draw.text((18, 819), "FICTIONAL SAMPLE  •  NOT FOR PAYMENT", font=font(12), fill="#ffffff")
    return canvas


def render_screenshot_of_screenshot(parent_path: Path) -> Image.Image:
    outer = Image.new("RGB", CANVAS_SIZE, "#e8ebf0")
    draw = ImageDraw.Draw(outer)
    draw.rectangle((0, 0, 390, 31), fill="#18263d")
    draw.text((14, 8), "SYNTHETIC DATA  |  NOT A REAL TRANSACTION", font=font(12), fill="#ffffff")
    draw.rectangle((0, 31, 390, 62), fill="#ffffff")
    draw.text((18, 39), "09:41", font=font(13), fill="#1b2638")
    draw.text((315, 39), "DEMO  •  100%", font=font(12), fill="#1b2638")
    draw.rectangle((0, 62, 390, 113), fill="#243858")
    draw.text((20, 78), "GALLERY DEMO", font=font(18), fill="#ffffff")
    draw.rounded_rectangle((18, 130, 372, 795), radius=18, fill="#ffffff", outline="#d9e0e8", width=1)
    draw.text((34, 146), "Screenshot preview", font=font(17), fill="#17283f")
    source = Image.open(parent_path).convert("RGB")
    source.thumbnail((300, 600), Image.Resampling.LANCZOS)
    x = (390 - source.width) // 2
    y = 178 + max(0, (590 - source.height) // 2)
    outer.paste(source, (x, y))
    draw.rectangle((0, 808, 390, 844), fill="#18263d")
    draw.text((18, 819), "FICTIONAL SAMPLE  •  NOT FOR PAYMENT", font=font(12), fill="#ffffff")
    return outer


def p_hash(path: Path) -> str:
    image = Image.open(path).convert("RGB")
    array = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(array, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    transformed = cv2.dct(resized)[:8, :8]
    values = transformed.flatten()[1:]
    median = float(np.median(values))
    value = 0
    for bit in values > median:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def a_hash(path: Path) -> str:
    image = Image.open(path).convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    values = np.asarray(image, dtype=np.float32)
    average = float(values.mean())
    value = 0
    for bit in values.flatten() > average:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 64), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_images() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    by_id = {record["evidence_id"]: record for record in ITEMS}
    for record in ITEMS:
        evidence_id = record["evidence_id"]
        if record["variant"] != "base":
            continue
        path = IMAGES / f"{evidence_id}.png"
        render_screenshot(record).save(path, format="PNG", optimize=False)
        record["image_file"] = str(path.relative_to(ROOT)).replace("\\", "/")

    for record in ITEMS:
        variant = record["variant"]
        if variant == "base":
            continue
        parent = by_id[record["variant_of"]]
        parent_path = ROOT / parent["image_file"]
        evidence_id = record["evidence_id"]
        if variant == "exact_copy":
            path = IMAGES / f"{evidence_id}.png"
            shutil.copyfile(parent_path, path)
        elif variant == "cropped":
            path = IMAGES / f"{evidence_id}.png"
            with Image.open(parent_path) as image:
                image.crop((4, 4, image.width - 4, image.height - 4)).save(path, format="PNG", optimize=False)
        elif variant == "recompressed":
            path = IMAGES / f"{evidence_id}.jpg"
            with Image.open(parent_path) as image:
                image.convert("RGB").save(path, format="JPEG", quality=42, subsampling=2, optimize=False, progressive=False)
        elif variant == "screenshot_of_screenshot":
            path = IMAGES / f"{evidence_id}.png"
            render_screenshot_of_screenshot(parent_path).save(path, format="PNG", optimize=False)
        else:
            raise ValueError(f"Unknown screenshot variant: {variant}")
        record["image_file"] = str(path.relative_to(ROOT)).replace("\\", "/")


def validate_authored_data() -> None:
    ids = [record["evidence_id"] for record in ITEMS]
    if len(ids) != len(set(ids)):
        raise ValueError("Evidence IDs must be unique.")
    if len(ITEMS) != 30:
        raise ValueError(f"Expected 30 curated records; found {len(ITEMS)}.")
    for record in ITEMS:
        if set(record["ground_truth_fields"]) != set(FIELDS):
            raise ValueError(f"Field contract mismatch for {record['evidence_id']}.")
        if record["split"] not in ("calibration", "heldout"):
            raise ValueError(f"Invalid split for {record['evidence_id']}.")
        if record["variant"] != "base" and record["variant_of"] not in ids:
            raise ValueError(f"Missing parent for {record['evidence_id']}.")
        timestamp = record["ground_truth_fields"].get("timestamp")
        if timestamp:
            datetime.fromisoformat(timestamp)
    by_id = {record["evidence_id"]: record for record in ITEMS}
    for relation in RELATIONSHIPS:
        left = by_id[relation["from_evidence_id"]]
        right = by_id[relation["to_evidence_id"]]
        if left["split"] != right["split"]:
            raise ValueError(f"Cross-split relationship: {relation['relationship_id']}.")
        if relation["type"] == "INFERRED" and relation["auto_clear_eligible"]:
            raise ValueError("INFERRED relationships must never be eligible for automatic clearing.")


def main() -> None:
    validate_authored_data()
    build_images()
    by_id = {record["evidence_id"]: record for record in ITEMS}

    for record in ITEMS:
        path = ROOT / record["image_file"]
        record["sha256"] = sha256(path)
        record["phash"] = p_hash(path)
        record["ahash"] = a_hash(path)
        record["visible_fields"] = [
            name for name, value in record["ground_truth_fields"].items() if value is not None
        ]

    fingerprint_pairs = []
    for record in ITEMS:
        if record["variant"] == "base":
            continue
        parent = by_id[record["variant_of"]]
        fingerprint_pairs.append({
            "variant_evidence_id": record["evidence_id"],
            "parent_evidence_id": parent["evidence_id"],
            "variant_kind": record["variant"],
            "same_sha256": record["sha256"] == parent["sha256"],
            "phash_hamming_distance": hamming(record["phash"], parent["phash"]),
            "ahash_hamming_distance": hamming(record["ahash"], parent["ahash"]),
        })

    manifest = {
        "dataset_name": "Pratibimb synthetic coordinator and evidence fixtures",
        "schema_version": "pratibimb.synthetic.v1",
        "synthetic_only": True,
        "generation_method": "Explicit hand-authored records; no random values or external data.",
        "canonical_image_dimensions_px": list(CANVAS_SIZE),
        "cropped_variant_dimensions_px": [CANVAS_SIZE[0] - 8, CANVAS_SIZE[1] - 8],
        "record_count": len(ITEMS),
        "split_counts": {
            "calibration": sum(record["split"] == "calibration" for record in ITEMS),
            "heldout": sum(record["split"] == "heldout" for record in ITEMS),
        },
        "screenshot_types": sorted({record["screenshot_type"] for record in ITEMS}),
        "trip_windows": TRIP_WINDOWS,
        "records": ITEMS,
        "relationships": RELATIONSHIPS,
        "limitations": [
            "This authored synthetic corpus is for fixtures, workflow demos and plumbing checks, not a representative accuracy benchmark.",
            "The two fabricated examples are hand-authored inconsistent samples, not outputs from image generators.",
            "Synthetic identifiers, sender IDs, dates and amounts are not real transactions or customer records.",
            "Fingerprint distances are measured on these generated files only; they do not set production thresholds.",
        ],
    }
    write_json(ROOT / "manifest.json", manifest)
    write_json(ROOT / "relationships.json", RELATIONSHIPS)
    write_json(ROOT / "demo_cases.json", DEMO_CASES)
    write_json(ROOT / "evaluation_cases.json", EVALUATION_CASES)
    write_json(ROOT / "splits.json", {
        "split_method": "Group split by separate synthetic trip windows; no relationship crosses splits.",
        "calibration_evidence_ids": [record["evidence_id"] for record in ITEMS if record["split"] == "calibration"],
        "heldout_evidence_ids": [record["evidence_id"] for record in ITEMS if record["split"] == "heldout"],
        "use": "Use heldout only for evaluator plumbing until real labelled data exists; never present its scores as real-world results.",
    })
    write_json(ROOT / "fingerprint_distances.json", {
        "method": {
            "sha256": "SHA-256 of exact image bytes",
            "phash": "8x8 low-frequency DCT hash after resizing grayscale image to 32x32; Hamming distance shown",
            "ahash": "8x8 grayscale mean threshold hash; Hamming distance shown",
            "implementation": {"opencv": cv2.__version__, "pillow": Image.__version__},
        },
        "pairs": fingerprint_pairs,
        "note": "Observed fixture distances only. Choose thresholds on labelled data and report false positives; do not treat similarity as a conclusion.",
    })

    csv_path = ROOT / "ground_truth.csv"
    columns = [
        "evidence_id", "split", "scenario_id", "trip_id", "journey_id", "sender_id", "channel",
        "received_at", "screenshot_type", "language_detected", "image_file", "sha256", "phash", "ahash",
        "variant", "variant_of", "labels", "visible_fields", "ground_truth_fields", "notes", "authorship",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in ITEMS:
            row = {key: record.get(key) for key in columns}
            row["language_detected"] = record["ground_truth_fields"].get("language_detected")
            for key in ("labels", "visible_fields", "ground_truth_fields"):
                row[key] = json.dumps(row[key], ensure_ascii=False, separators=(",", ":"))
            writer.writerow(row)

    print(f"Wrote {len(ITEMS)} records: {manifest['split_counts']['calibration']} calibration, {manifest['split_counts']['heldout']} held-out.")
    print(f"Images: {len(list(IMAGES.glob('*')))} in {IMAGES}")
    print(f"Manifest: {ROOT / 'manifest.json'}")


if __name__ == "__main__":
    main()
