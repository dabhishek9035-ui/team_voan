"""
Local QR Code Decoder and Payload Parser for Pratibimb Intake.
Decodes QR codes locally using OpenCV with multiple preprocessing passes.
Parses payloads when recognizable and marks opaque/signed tokens honestly.
"""

from __future__ import annotations
import io
import json
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Union
import cv2
import numpy as np
from PIL import Image


class QRDecoder:
    """Robust local QR code decoder with multi-pass image preprocessing."""

    def __init__(self):
        self.detector = cv2.QRCodeDetector()

    def _to_cv2_image(self, data_or_path: Union[str, Path, bytes, Image.Image, np.ndarray]) -> np.ndarray:
        """Converts input image to cv2 BGR uint8 array."""
        if isinstance(data_or_path, np.ndarray):
            return data_or_path
        elif isinstance(data_or_path, Image.Image):
            rgb = np.array(data_or_path.convert("RGB"))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        elif isinstance(data_or_path, (str, Path)):
            img = cv2.imread(str(data_or_path))
            if img is None:
                raise ValueError(f"Unable to read image at {data_or_path}")
            return img
        elif isinstance(data_or_path, (bytes, bytearray)):
            nparr = np.frombuffer(data_or_path, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Unable to decode image bytes with OpenCV")
            return img
        else:
            raise TypeError("Unsupported image format for QR decoding")

    def decode(self, data_or_path: Union[str, Path, bytes, Image.Image, np.ndarray]) -> Tuple[Optional[str], Optional[Dict[str, Any]], bool]:
        """
        Attempts to decode a QR code using multi-pass preprocessing.
        Returns:
            (raw_payload, parsed_dict, is_parseable)
        """
        img = self._to_cv2_image(data_or_path)

        # Pass 1: Direct detection on original BGR
        payload, points, _ = self.detector.detectAndDecode(img)
        if payload and payload.strip():
            parsed, parseable = self.parse_payload(payload.strip())
            return payload.strip(), parsed, parseable

        # Pass 2: Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        payload, points, _ = self.detector.detectAndDecode(gray)
        if payload and payload.strip():
            parsed, parseable = self.parse_payload(payload.strip())
            return payload.strip(), parsed, parseable

        # Pass 3: Otsu's thresholding
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        payload, points, _ = self.detector.detectAndDecode(thresh)
        if payload and payload.strip():
            parsed, parseable = self.parse_payload(payload.strip())
            return payload.strip(), parsed, parseable

        # Pass 4: Adaptive thresholding
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 10
        )
        payload, points, _ = self.detector.detectAndDecode(adaptive)
        if payload and payload.strip():
            parsed, parseable = self.parse_payload(payload.strip())
            return payload.strip(), parsed, parseable

        # Pass 5: Contrast enhancement (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        payload, points, _ = self.detector.detectAndDecode(enhanced)
        if payload and payload.strip():
            parsed, parseable = self.parse_payload(payload.strip())
            return payload.strip(), parsed, parseable

        # No QR code found
        return None, None, False

    def parse_payload(self, raw_payload: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Parses standard transit / metro / UPI QR payloads.
        Returns (parsed_fields_dict, is_parseable).
        If payload is opaque, cryptographic, or proprietary binary token:
            returns (None, False).
        """
        if not raw_payload:
            return None, False

        # 1. Try JSON payload
        try:
            data = json.loads(raw_payload)
            if isinstance(data, dict):
                return data, True
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. Try URI / URL scheme
        if raw_payload.startswith(("http://", "https://", "upi://")):
            parsed_url = urllib.parse.urlparse(raw_payload)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            # Flatten single values
            flattened = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
            flattened["_scheme"] = parsed_url.scheme
            flattened["_path"] = parsed_url.path
            return flattened, True

        # 3. Try pipe or delimiter separated BMRCL ticket pattern
        # e.g.: BMRCL|TICKET_102938|MG_ROAD|INDIRANAGAR|40.00|2026-11-19T10:00:00
        if "|" in raw_payload:
            parts = [p.strip() for p in raw_payload.split("|")]
            if len(parts) >= 3 and ("BMRCL" in parts[0].upper() or "METRO" in parts[0].upper()):
                parsed = {
                    "operator": parts[0],
                    "ticket_id": parts[1] if len(parts) > 1 else None,
                    "origin_station": parts[2] if len(parts) > 2 else None,
                    "destination_station": parts[3] if len(parts) > 3 else None,
                    "fare": float(parts[4]) if len(parts) > 4 and parts[4].replace('.', '', 1).isdigit() else None,
                    "validity": parts[5] if len(parts) > 5 else None,
                }
                return parsed, True

        # 4. Otherwise, payload is likely opaque or encrypted
        # Principle: "If the QR payload is opaque or signed, it is used as a duplicate key only, never as a validity claim."
        return None, False
