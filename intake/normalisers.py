"""
Field Normalisers for Pratibimb Intake.
Handles amounts, timestamps, Indian formats, Kannada numerals,
and OCR correction for UTRs and order IDs.
"""

from __future__ import annotations
import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

# Kannada numeral translation table
KANNADA_DIGITS = {
    '೦': '0', '೧': '1', '೨': '2', '೩': '3', '೪': '4',
    '೫': '5', '೬': '6', '೭': '7', '೮': '8', '೯': '9'
}

def translate_kannada_numerals(text: str) -> str:
    """Replaces Kannada numerals with ASCII digits."""
    if not text:
        return text
    for kn, en in KANNADA_DIGITS.items():
        text = text.replace(kn, en)
    return text


def normalize_amount(raw_val: Any) -> Tuple[Optional[float], Optional[str]]:
    """
    Normalizes currency amounts from strings with symbols, commas, or Kannada numerals.
    Returns: (float_amount, currency) or (None, None)
    Examples:
        '₹ 45.00' -> (45.0, 'INR')
        'Rs. 1,250.50' -> (1250.5, 'INR')
        '₹೪೦' -> (40.0, 'INR')
        '40' -> (40.0, 'INR')
    """
    if raw_val is None:
        return None, None
    if isinstance(raw_val, (int, float)):
        return float(raw_val), "INR"

    text = str(raw_val).strip()
    text = translate_kannada_numerals(text)

    # Detect currency
    currency = "INR"
    if "$" in text or "USD" in text:
        currency = "USD"
    elif "€" in text or "EUR" in text:
        currency = "EUR"

    # Remove currency symbols and extraneous characters
    cleaned = re.sub(r'[₹$€]|Rs\.?|INR', '', text, flags=re.IGNORECASE).strip()
    # Remove thousand separators
    cleaned = cleaned.replace(',', '').strip()

    # Match numeric pattern: digits with optional decimal point
    match = re.search(r'(\d+(?:\.\d{1,2})?)', cleaned)
    if match:
        try:
            return float(match.group(1)), currency
        except ValueError:
            return None, None
    return None, None


def normalize_timestamp(raw_val: Any) -> Optional[str]:
    """
    Normalizes various date and time formats into standard ISO 8601 string:
    'YYYY-MM-DDTHH:MM:SS'.
    Handles 12-hour/24-hour, Indian date formats (DD/MM/YYYY, DD-MM-YYYY, DD Month YYYY),
    and Kannada digits.
    """
    if raw_val is None:
        return None
    text = str(raw_val).strip()
    text = translate_kannada_numerals(text)

    # Clean multiple spaces and non-standard separators
    text = re.sub(r'\s+', ' ', text)

    # Common patterns
    formats = [
        # ISO formats
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        # Indian formats with 12-hour / 24-hour time
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %I:%M %p",
        "%d-%m-%Y %I:%M:%S %p",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        # With abbreviated/full month name
        "%d %b %Y, %I:%M %p",
        "%d %B %Y, %I:%M %p",
        "%d %b %Y %I:%M %p",
        "%d %B %Y %I:%M %p",
        "%d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M",
        "%d %b %Y",
        "%d %B %Y",
        # UPI / PhonePe / GPay style: e.g. "19 Nov 2026 at 11:25 AM"
        "%d %b %Y at %I:%M %p",
        "%d %B %Y at %I:%M %p",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.isoformat()
        except ValueError:
            continue

    # Try extracting date and time parts with regex
    date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    time_match = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm)?', text)

    if date_match:
        d, m, y = map(int, date_match.groups())
        hour, minute, second = 0, 0, 0
        if time_match:
            h_str, m_str, s_str, am_pm = time_match.groups()
            hour = int(h_str)
            minute = int(m_str)
            second = int(s_str) if s_str else 0
            if am_pm:
                am_pm = am_pm.upper()
                if am_pm == "PM" and hour < 12:
                    hour += 12
                elif am_pm == "AM" and hour == 12:
                    hour = 0
        try:
            dt = datetime(y, m, d, hour, minute, second)
            return dt.isoformat()
        except ValueError:
            pass

    return text  # fallback to raw string if unparsed


def normalize_utr(raw_val: Any) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Cleans UPI UTR (Unique Transaction Reference).
    UPI UTRs are strictly 12 digits.
    Corrects common OCR mistakes:
      - 'O', 'o', 'Q', 'D' -> '0'
      - 'I', 'l', '|' -> '1'
      - 'B' -> '8'
      - 'S' -> '5'
    Logs every applied correction.
    """
    if raw_val is None:
        return None, []

    original = str(raw_val).strip()
    text = translate_kannada_numerals(original)
    corrections = []

    # Strip prefixes like "UTR:", "UPI Ref ID:", etc.
    cleaned = re.sub(r'^(?:UTR|UPI\s*Ref(?:erence)?\s*(?:No|ID)?|Ref\s*No)[\s:#-]*', '', text, flags=re.IGNORECASE)
    cleaned = cleaned.replace(" ", "").replace("-", "")

    # Check if already 12 digits
    if re.fullmatch(r'\d{12}', cleaned):
        return cleaned, []

    # If it's 12 chars long with common OCR confusions:
    if len(cleaned) == 12:
        chars = list(cleaned)
        modified = False
        ocr_map = {
            'O': '0', 'o': '0', 'Q': '0', 'D': '0',
            'I': '1', 'l': '1', '|': '1',
            'S': '5', 's': '5',
            'B': '8', 'Z': '2', 'z': '2'
        }
        for i, ch in enumerate(chars):
            if ch in ocr_map:
                chars[i] = ocr_map[ch]
                modified = True

        corrected_candidate = "".join(chars)
        if re.fullmatch(r'\d{12}', corrected_candidate):
            corrections.append({
                "field": "utr",
                "original": original,
                "corrected": corrected_candidate,
                "rule": "ocr_digit_confusion_substitution"
            })
            return corrected_candidate, corrections

    # Extract any 12-digit sequence if embedded
    seq_match = re.search(r'\b\d{12}\b', text)
    if seq_match:
        extracted = seq_match.group(0)
        if extracted != original:
            corrections.append({
                "field": "utr",
                "original": original,
                "corrected": extracted,
                "rule": "regex_12_digit_isolation"
            })
        return extracted, corrections

    # If it's valid non-12 format or partially readable:
    clean_alphanum = re.sub(r'[^A-Za-z0-9]', '', cleaned)
    return clean_alphanum if clean_alphanum else None, corrections


def normalize_order_or_ticket_id(raw_val: Any, id_type: str = "ticket_id") -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Normalizes Order ID or Ticket ID.
    Strips spaces and non-printable characters.
    Logs transformations.
    """
    if raw_val is None:
        return None, []

    original = str(raw_val).strip()
    text = translate_kannada_numerals(original)
    corrections = []

    # Strip prefixes like "Ticket ID:", "Order ID:", "Booking ID:"
    cleaned = re.sub(r'^(?:Ticket\s*ID|Order\s*ID|Booking\s*ID)[\s:#-]*', '', text, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace(" ", "")

    if cleaned != original:
        corrections.append({
            "field": id_type,
            "original": original,
            "corrected": cleaned,
            "rule": "strip_prefix_and_whitespace"
        })

    return cleaned if cleaned else None, corrections


def mask_payer_name(name: Optional[str]) -> Optional[str]:
    """
    Masks sensitive personal identity information for privacy.
    E.g.: 'Rahul Sharma' -> 'R***l S***a'
    E.g.: 'Meera' -> 'M***a'
    """
    if not name or not name.strip():
        return None
    parts = name.strip().split()
    masked_parts = []
    for part in parts:
        if len(part) <= 2:
            masked_parts.append(part[0] + "*")
        else:
            masked_parts.append(part[0] + "*" * (len(part) - 2) + part[-1])
    return " ".join(masked_parts)
