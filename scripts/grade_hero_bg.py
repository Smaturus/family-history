#!/usr/bin/env python3
"""Regrade the hero background to match the etalon mock's color.

Maps assets/hero-reference.png (navy field, strong cyan-blue glow) onto the
tonal distribution of assets/Header structure.jpg (near-black field,
desaturated violet midtones, pale-lavender filaments). Two steps:

1. Glow suppression: the top-left cyan-blue radial glow is smooth and
   low-frequency, unlike the structured filament haze. We estimate the
   low-frequency field with a large Gaussian blur and subtract it where a
   structure-density map (blurred local detail) says there are no filaments.
2. Per-channel quantile (histogram) matching against the etalon mock.

Usage: python3 scripts/grade_hero_bg.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ETALON = ASSETS / "Header structure.jpg"
SOURCE = ASSETS / "hero-reference.png"

FULL_SIZE = (1920, 1072)
SMALL_SIZE = (1280, 714)
JPEG_QUALITY = 85
WEBP_QUALITY = 82


def channel_lut(src: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """256-entry LUT mapping the quantiles of src onto ref (one channel)."""
    src_hist = np.bincount(src.ravel(), minlength=256).astype(np.float64)
    ref_hist = np.bincount(ref.ravel(), minlength=256).astype(np.float64)
    src_cdf = np.cumsum(src_hist) / src_hist.sum()
    ref_cdf = np.cumsum(ref_hist) / ref_hist.sum()
    lut = np.interp(src_cdf, ref_cdf, np.arange(256))
    # Enforce monotonicity (interp on non-strictly-increasing CDFs can wobble).
    lut = np.maximum.accumulate(lut)
    return lut


def match_histograms(src: np.ndarray, ref: np.ndarray) -> np.ndarray:
    out = np.empty_like(src, dtype=np.float64)
    for c in range(3):
        lut = channel_lut(src[..., c], ref[..., c])
        out[..., c] = lut[src[..., c]]
    return out


def suppress_glow(img: Image.Image) -> np.ndarray:
    """Subtract the low-frequency glow field in structureless regions (uint8)."""
    a = np.asarray(img).astype(np.float64)
    # Estimate maps at quarter resolution: the fields are smooth and this is
    # much faster than blurring the 4K master directly.
    small = img.resize((img.width // 4, img.height // 4), Image.LANCZOS)
    low = np.asarray(small.filter(ImageFilter.GaussianBlur(80))).astype(np.float64)
    med = np.asarray(small.filter(ImageFilter.GaussianBlur(3))).astype(np.float64)
    detail = np.abs(np.asarray(small).astype(np.float64) - med).mean(axis=2)
    detail_img = Image.fromarray(np.clip(detail * 8, 0, 255).astype(np.uint8))
    density = np.asarray(detail_img.filter(ImageFilter.GaussianBlur(40))).astype(np.float64) / 255.0

    # Smoothstep: 1 where structureless (pure glow), 0 inside the filament haze.
    t = np.clip((density - 0.04) / (0.18 - 0.04), 0.0, 1.0)
    keep = t * t * (3 - 2 * t)
    subtract = low * (1.0 - keep)[..., None]

    subtract_full = np.asarray(
        Image.fromarray(np.clip(subtract + 0.5, 0, 255).astype(np.uint8)).resize(
            img.size, Image.BILINEAR
        )
    ).astype(np.float64)
    return np.clip(a - subtract_full + 0.5, 0, 255).astype(np.uint8)


def main() -> None:
    ref = np.asarray(Image.open(ETALON).convert("RGB"))
    src_img = Image.open(SOURCE).convert("RGB")
    src = suppress_glow(src_img)

    graded = match_histograms(src, ref)
    graded_img = Image.fromarray(np.clip(graded + 0.5, 0, 255).astype(np.uint8))

    full = graded_img.resize(FULL_SIZE, Image.LANCZOS)
    small = graded_img.resize(SMALL_SIZE, Image.LANCZOS)

    full.save(ASSETS / "hero-bg.jpg", quality=JPEG_QUALITY, optimize=True, progressive=True)
    full.save(ASSETS / "hero-bg.webp", quality=WEBP_QUALITY, method=6)
    small.save(ASSETS / "hero-bg-1280.jpg", quality=JPEG_QUALITY, optimize=True, progressive=True)
    small.save(ASSETS / "hero-bg-1280.webp", quality=WEBP_QUALITY, method=6)

    for name in ("hero-bg.jpg", "hero-bg.webp", "hero-bg-1280.jpg", "hero-bg-1280.webp"):
        path = ASSETS / name
        print(f"{name}: {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
