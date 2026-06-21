"""
src/renderer/animation.py
Pure animation utilities — easing, value calculators, image effects.
No PIL Image objects; all functions are side-effect-free.
"""

import math
from typing import List

import numpy as np


# ── Easing ────────────────────────────────────────────────────────────────────

def ease_io(t: float) -> float:
    """Smooth ease in-out (cubic S-curve)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def ease_out3(t: float) -> float:
    """Ease out cubic — fast start, slow finish."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in3(t: float) -> float:
    """Ease in cubic — slow start, fast finish."""
    t = max(0.0, min(1.0, t))
    return t ** 3


def spring(t: float, amp: float = 0.18) -> float:
    """Spring overshoot — for keyword pop-in."""
    t = max(0.0, min(1.0, t))
    return 1.0 + amp * math.sin(t * math.pi) * (1.0 - t * 0.6)


def pulse(t: float, freq: float = 2.0) -> float:
    """Subtle pulse oscillation [0, 1] — for speaker indicators."""
    return 0.5 + 0.5 * math.sin(t * freq * math.pi * 2)


# ── Per-frame value calculators ───────────────────────────────────────────────

def get_alpha(t: float, dur: float, fi: float, fo: float) -> float:
    """
    Opacity [0, 1] with fade-in and fade-out.
    t   — local time within scene (seconds, 0 = scene start)
    dur — scene total duration
    fi  — fade-in duration
    fo  — fade-out duration
    """
    if t <= 0.0:
        return 0.0
    if t < fi:
        return ease_io(t / fi)
    if t > dur - fo:
        return ease_io(max(0.0, (dur - t) / fo))
    return 1.0


def get_kw_scale(t: float, appear: float, dur: float) -> float:
    """Scale factor for keyword spring pop-in."""
    if t < appear:
        return 0.0
    elapsed = t - appear
    if elapsed >= dur:
        return 1.0
    return spring(elapsed / dur)


def get_cam_push(t: float, scene_dur: float, max_s: float) -> float:
    """Background zoom: max_s → 1.0 over the scene (slow push-in)."""
    p = t / max(scene_dur, 1e-4)
    return max_s - (max_s - 1.0) * ease_io(p)


def get_word_alpha(t: float, word_start: float, word_end: float) -> float:
    """
    Word-karaoke alpha — returns 1.0 when the word is 'active'
    (being spoken), fades slightly before and after.
    """
    if t < word_start - 0.1:
        return 0.5           # dim before
    if t > word_end + 0.2:
        return 0.6           # slightly dim after
    return 1.0               # bright during


# ── Pre-computed effect arrays ────────────────────────────────────────────────

def build_vignette(w: int, h: int, strength: float) -> np.ndarray:
    """Build vignette mask (float32, H×W×3, range [0, 1])."""
    y_c, x_c = np.ogrid[:h, :w]
    dx = (x_c - w / 2.0) / (w / 2.0)
    dy = (y_c - h / 2.0) / (h / 2.0)
    dist = np.sqrt(dx * dx + dy * dy)
    v = 1.0 - strength * np.clip(dist / 1.35, 0.0, 1.0) ** 1.9
    v = np.clip(v, 0.0, 1.0)
    return np.stack([v, v, v], axis=-1).astype(np.float32)


def build_grain_pool(w: int, h: int, intensity: int, n: int) -> List[np.ndarray]:
    """Pre-generate n film-grain frames (int16, H×W×3, luminance grain)."""
    pool = []
    for _ in range(n):
        luma = np.random.normal(0, intensity, (h, w, 1)).astype(np.int16)
        pool.append(np.repeat(luma, 3, axis=2))
    return pool


def apply_vignette(arr: np.ndarray, vignette: np.ndarray) -> np.ndarray:
    """arr: uint8 → multiply by float vignette → uint8."""
    return np.clip(arr.astype(np.float32) * vignette, 0, 255).astype(np.uint8)


def apply_grain(arr: np.ndarray, grain: np.ndarray) -> np.ndarray:
    """arr: uint8 + grain: int16 → clamp → uint8."""
    return np.clip(arr.astype(np.int16) + grain, 0, 255).astype(np.uint8)
