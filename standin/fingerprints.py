"""Fingerprints identical to data/generate_synthetic_dataset.py (so recomputed values must match manifest.json)."""
import hashlib
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def sha256_file(path):
    d = hashlib.sha256()
    with Path(path).open("rb") as h:
        for chunk in iter(lambda: h.read(65536), b""):
            d.update(chunk)
    return d.hexdigest()


def p_hash(path):
    arr = cv2.cvtColor(np.asarray(Image.open(path).convert("RGB")), cv2.COLOR_RGB2GRAY)
    small = cv2.resize(arr, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    vals = cv2.dct(small)[:8, :8].flatten()[1:]
    med, v = float(np.median(vals)), 0
    for bit in vals > med:
        v = (v << 1) | int(bit)
    return f"{v:016x}"


def a_hash(path):
    vals = np.asarray(Image.open(path).convert("L").resize((8, 8), Image.Resampling.LANCZOS), dtype=np.float32)
    avg, v = float(vals.mean()), 0
    for bit in vals.flatten() > avg:
        v = (v << 1) | int(bit)
    return f"{v:016x}"


def hamming(a, b):
    return (int(a, 16) ^ int(b, 16)).bit_count()
