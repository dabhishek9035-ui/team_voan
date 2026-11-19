"""
Fingerprinting service for Pratibimb intake.
Computes SHA-256, perceptual hash (pHash), and average hash (aHash).

Note on perceptual hashes:
Perceptual hashes (pHash and aHash) are visual similarity signals, NOT cryptographic
integrity guarantees. They indicate whether two images look substantially similar
(surviving recompression, slight cropping, or brightness changes), but cannot replace
semantic IDs (such as UTR or Ticket ID). High visual similarity may suggest reuse,
which must be reviewed according to agreed Hamming distance thresholds.
"""

from __future__ import annotations
import hashlib
import io
from pathlib import Path
from typing import Union, Dict, Tuple
from PIL import Image
import imagehash


def compute_sha256(data_or_path: Union[str, Path, bytes]) -> str:
    """Compute SHA-256 hash of image bytes or file."""
    if isinstance(data_or_path, (str, Path)):
        hasher = hashlib.sha256()
        with open(data_or_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    elif isinstance(data_or_path, (bytes, bytearray)):
        return hashlib.sha256(data_or_path).hexdigest()
    else:
        raise ValueError("Unsupported type for sha256 calculation")


def load_image(data_or_path: Union[str, Path, bytes, Image.Image]) -> Image.Image:
    """Safely load an image to PIL format in RGB mode."""
    if isinstance(data_or_path, Image.Image):
        return data_or_path.convert("RGB")
    elif isinstance(data_or_path, (str, Path)):
        img = Image.open(data_or_path)
        return img.convert("RGB")
    elif isinstance(data_or_path, (bytes, bytearray)):
        img = Image.open(io.BytesIO(data_or_path))
        return img.convert("RGB")
    else:
        raise ValueError("Unsupported type for image loading")


def compute_fingerprints(
    data_or_path: Union[str, Path, bytes, Image.Image],
    hash_size: int = 8
) -> Dict[str, str]:
    """
    Computes sha256, phash, and ahash for an image.
    Returns:
        {
            'sha256': <hex string>,
            'phash': <hex string>,
            'ahash': <hex string>
        }
    """
    # 1. SHA-256 calculation
    if isinstance(data_or_path, Image.Image):
        buf = io.BytesIO()
        data_or_path.save(buf, format="PNG")
        sha256_val = hashlib.sha256(buf.getvalue()).hexdigest()
        img = data_or_path.convert("RGB")
    elif isinstance(data_or_path, (bytes, bytearray)):
        sha256_val = hashlib.sha256(data_or_path).hexdigest()
        img = Image.open(io.BytesIO(data_or_path)).convert("RGB")
    else:
        sha256_val = compute_sha256(data_or_path)
        img = Image.open(data_or_path).convert("RGB")

    # 2. Perceptual hashes
    # pHash uses Discrete Cosine Transform (DCT)
    phash_val = str(imagehash.phash(img, hash_size=hash_size))
    # aHash uses simple average luminance
    ahash_val = str(imagehash.average_hash(img, hash_size=hash_size))

    return {
        "sha256": sha256_val,
        "phash": phash_val,
        "ahash": ahash_val,
    }


def compute_hamming_distance(hash1_str: str, hash2_str: str) -> int:
    """
    Computes Hamming distance between two hex-encoded perceptual hashes.
    A lower distance means higher visual similarity:
      - 0: Identical or imperceptible changes.
      - 1-6: Likely crops, recompressions, or screenshot-of-screenshot.
      - 7-12: Ambiguous / similar layout.
      - > 12: Distinct visual content.
    """
    h1 = imagehash.hex_to_hash(hash1_str)
    h2 = imagehash.hex_to_hash(hash2_str)
    return h1 - h2


def compare_images(
    img1: Union[str, Path, bytes, Image.Image],
    img2: Union[str, Path, bytes, Image.Image],
    hash_size: int = 8
) -> Dict[str, Any]:
    """
    Compares two images across SHA-256 and perceptual fingerprints.
    """
    fp1 = compute_fingerprints(img1, hash_size=hash_size)
    fp2 = compute_fingerprints(img2, hash_size=hash_size)

    exact_match = fp1["sha256"] == fp2["sha256"]
    phash_dist = compute_hamming_distance(fp1["phash"], fp2["phash"])
    ahash_dist = compute_hamming_distance(fp1["ahash"], fp2["ahash"])

    return {
        "exact_sha256_match": exact_match,
        "phash_distance": phash_dist,
        "ahash_distance": ahash_dist,
        "fingerprints_1": fp1,
        "fingerprints_2": fp2,
    }
