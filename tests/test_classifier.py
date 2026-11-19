"""
Unit tests for Screenshot Classifier (Rule-based & Sarvam-105B fallback).
"""

from intake.models import ScreenshotType
from extraction.classifier import ScreenshotClassifier


def test_classify_ticket_qr():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="Namma Metro BMRCL Single Journey QR Ticket\nTicket ID: TKT-123\nFare: Rs. 40",
        has_qr_code=True,
        qr_payload="BMRCL|TKT-123|MG_ROAD|INDIRANAGAR|40",
    )
    assert res["screenshot_type"] == ScreenshotType.TICKET_QR
    assert res["confidence"] >= 0.85


def test_classify_upi_success():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="Google Pay\nPayment Successful\nPaid to BMRCL Metro\n₹40.00\nUPI Ref No 401928374615",
        has_qr_code=False,
    )
    assert res["screenshot_type"] == ScreenshotType.UPI_SUCCESS
    assert res["confidence"] >= 0.85


def test_classify_upi_failed_pending():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="PhonePe\nPayment Processing / Failed\n₹50.00 to BMRCL\nMoney will be refunded if debited",
        has_qr_code=False,
    )
    assert res["screenshot_type"] == ScreenshotType.UPI_FAILED_PENDING
    assert res["confidence"] >= 0.85


def test_classify_bank_sms():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="HDFC Bank Alert: INR 40.00 debited from A/C XX1234 towards BMRCL UPI Ref 401928374615",
        has_qr_code=False,
    )
    assert res["screenshot_type"] == ScreenshotType.BANK_SMS
    assert res["confidence"] >= 0.85


def test_classify_bot_error():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="Namma Metro Chatbot: Booking failed. Money debited but ticket not booked. Refunded to source within 7 working days.",
        has_qr_code=False,
    )
    assert res["screenshot_type"] == ScreenshotType.BOT_ERROR
    assert res["confidence"] >= 0.85


def test_classify_refund_notice():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="Bank SMS: Refund of Rs 40.00 credited back to your source account towards failed BMRCL booking ORD-123",
        has_qr_code=False,
    )
    assert res["screenshot_type"] == ScreenshotType.REFUND_NOTICE
    assert res["confidence"] >= 0.85


def test_classify_suspect_notice_phishing():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="Dear customer your metro recharge refund failed! Download metro-refund.apk or install AnyDesk to get immediate refund",
        has_qr_code=False,
    )
    assert res["screenshot_type"] == ScreenshotType.SUSPECT_NOTICE
    assert res["confidence"] >= 0.90


def test_classify_claim_submission():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="Corporate Conveyance Reimbursement Claim Submission\nClaim ID: CLM-102\nAmount: Rs 40",
        has_qr_code=False,
    )
    assert res["screenshot_type"] == ScreenshotType.CLAIM_SUBMISSION


def test_classify_other_abstention():
    clf = ScreenshotClassifier()
    res = clf.classify(
        raw_text="Random photo of a dog sitting in a park with no financial text",
        has_qr_code=False,
    )
    assert res["screenshot_type"] == ScreenshotType.OTHER
    assert res["confidence"] < 0.60
