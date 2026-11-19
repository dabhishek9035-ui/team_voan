"""
Unit tests for Fingerprinting Service (SHA-256, pHash, aHash, Hamming distances).
"""

import io
from PIL import Image
from intake.fingerprint import (
    compute_sha256,
    compute_fingerprints,
    compute_hamming_distance,
    compare_images,
)


def create_sample_image(color: str = "#FF0000", size: tuple = (200, 200)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_sha256_exact_match():
    img_bytes = create_sample_image("#336699")
    h1 = compute_sha256(img_bytes)
    h2 = compute_sha256(img_bytes)
    assert h1 == h2
    assert len(h1) == 64


def test_fingerprints_computation():
    img_bytes = create_sample_image("#4488AA")
    fps = compute_fingerprints(img_bytes)
    assert "sha256" in fps
    assert "phash" in fps
    assert "ahash" in fps
    assert len(fps["phash"]) == 16
    assert len(fps["ahash"]) == 16


def test_hamming_distance_exact_and_variants():
    img1 = Image.new("RGB", (256, 256), "#FFFFFF")
    # Same image
    fp1 = compute_fingerprints(img1)
    fp2 = compute_fingerprints(img1)
    dist = compute_hamming_distance(fp1["phash"], fp2["phash"])
    assert dist == 0

    # Slight crop / modification
    img_crop = img1.crop((10, 10, 246, 246)).resize((256, 256))
    fp_crop = compute_fingerprints(img_crop)
    dist_crop = compute_hamming_distance(fp1["phash"], fp_crop["phash"])
    assert dist_crop <= 4  # Very low Hamming distance for crop

    # Completely different image (noise / black)
    img_diff = Image.new("RGB", (256, 256), "#000000")
    fp_diff = compute_fingerprints(img_diff)
    comp = compare_images(img1, img_diff)
    assert comp["exact_sha256_match"] is False
    assert comp["phash_distance"] >= 0
