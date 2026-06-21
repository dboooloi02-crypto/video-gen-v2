"""
src/templates/podcast.py
Podcast-style template — two speakers with avatars and waveform animation.

Layout:
  ┌──────────────────────────────────┐
  │  ●A           ●B                 │  ← avatar dots (active speaker glows)
  │                                  │
  │                                  │
  │     今天工作怎么样？               │  ← ZH (centred, larger)
  │                                  │
  │   How's work going recently?     │  ← EN (centred, smaller)
  │                                  │
  │   ▁▃▅▇▅▃▁▂▄▆▄▂▁  (waveform)     │  ← animated bars
  └──────────────────────────────────┘
"""

import math
import sys
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    WIDTH, HEIGHT,
    C_TEXT_ZH, C_TEXT_EN,
    C_SPEAKER_A, C_SPEAKER_B,
    FS_ZH, FS_EN,
    LINE_GAP, FADE_IN,
)
from renderer.animation import get_alpha, pulse
from templates.base import BaseTemplate


# Podcast-specific colours
_C_BG_CIRCLE   = (22, 22, 30)
_C_WAVEFORM    = (100, 180, 255)
_C_INACTIVE    = (55,  55,  70)

_AVATAR_R      = 44     # avatar circle radius (px)
_AVATAR_Y      = 260    # Y centre of avatar row
_AVATAR_A_X    = WIDTH // 4
_AVATAR_B_X    = WIDTH * 3 // 4
_WAVEFORM_Y    = HEIGHT - 340
_WAVEFORM_BARS = 26
_WAVEFORM_W    = 7      # bar width
_WAVEFORM_GAP  = 4      # gap between bars
_WAVEFORM_MAX  = 55     # max bar height


class PodcastTemplate(BaseTemplate):
    """
    Two-speaker podcast style.
    Active speaker's avatar pulses; animated waveform at the bottom.
    """

    @property
    def name(self) -> str:
        return "podcast"

    @property
    def description(self) -> str:
        return "Two-speaker avatar style with animated waveform"

    # ── Main entry point ──────────────────────────────────────────────────────

    def render_layer(self, scene, local_t, alpha, fm, tc, gc) -> Image.Image:
        layer = self.blank()
        draw  = ImageDraw.Draw(layer)

        cx = WIDTH // 2
        active = scene.speaker   # "A" or "B"

        # 1. Avatar circles
        self._draw_avatars(draw, active, alpha, local_t)

        # 2. Speaker label (small, above avatar)
        self._draw_speaker_label(layer, draw, active, alpha, tc)

        # 3. Chinese text
        if scene.zh:
            zh_img = tc.get_image(scene.zh, FS_ZH, C_TEXT_ZH, "zh")
            self.paste_centered(layer, zh_img,
                                cx, HEIGHT // 2 - 20,
                                alpha_scale=alpha)

        # 4. English text
        if scene.en:
            en_size = max(36, FS_EN - 4)
            en_img  = tc.get_image(scene.en, en_size, C_TEXT_EN, "en")
            self.paste_centered(layer, en_img,
                                cx, HEIGHT // 2 + FS_ZH + LINE_GAP + 10,
                                alpha_scale=alpha * 0.85)

        # 5. Waveform
        self._draw_waveform(draw, local_t, alpha)

        return layer

    # ── Avatars ───────────────────────────────────────────────────────────────

    def _draw_avatars(self, draw: ImageDraw.ImageDraw,
                      active: str, alpha: float, local_t: float):
        for speaker, x in [("A", _AVATAR_A_X), ("B", _AVATAR_B_X)]:
            is_active = speaker == active
            base_col  = C_SPEAKER_A if speaker == "A" else C_SPEAKER_B

            if is_active:
                # Pulsing glow ring
                p       = pulse(local_t, freq=1.2)
                glow_r  = int(_AVATAR_R * (1.15 + 0.10 * p))
                glow_a  = int(80 * alpha * p)
                draw.ellipse(
                    [x - glow_r, _AVATAR_Y - glow_r,
                     x + glow_r, _AVATAR_Y + glow_r],
                    fill=(*base_col, glow_a),
                )
                # Solid avatar
                draw.ellipse(
                    [x - _AVATAR_R, _AVATAR_Y - _AVATAR_R,
                     x + _AVATAR_R, _AVATAR_Y + _AVATAR_R],
                    fill=(*base_col, int(230 * alpha)),
                )
            else:
                # Dim inactive avatar
                draw.ellipse(
                    [x - _AVATAR_R, _AVATAR_Y - _AVATAR_R,
                     x + _AVATAR_R, _AVATAR_Y + _AVATAR_R],
                    fill=(*_C_INACTIVE, int(130 * alpha)),
                )

            # Letter inside
            # (we draw directly since letters "A"/"B" are ASCII — no CJK needed)
            draw.text(
                (x - 8, _AVATAR_Y - 14),
                speaker,
                fill=(255, 255, 255, int(200 * alpha)),
            )

    # ── Speaker label ─────────────────────────────────────────────────────────

    def _draw_speaker_label(self, layer, draw, active, alpha, tc):
        label_col = C_SPEAKER_A if active == "A" else C_SPEAKER_B
        lx = _AVATAR_A_X if active == "A" else _AVATAR_B_X

        label_img = tc.get_image(f"Speaker {active}", 36, label_col, "en")
        self.paste_centered(layer, label_img,
                            lx, _AVATAR_Y + _AVATAR_R + 26,
                            alpha_scale=alpha * 0.9)

    # ── Waveform ──────────────────────────────────────────────────────────────

    def _draw_waveform(self, draw: ImageDraw.ImageDraw,
                       local_t: float, alpha: float):
        total_w = _WAVEFORM_BARS * (_WAVEFORM_W + _WAVEFORM_GAP)
        x_start = WIDTH // 2 - total_w // 2

        for i in range(_WAVEFORM_BARS):
            # Animated height via two overlapping sine waves
            h = int(_WAVEFORM_MAX * abs(
                math.sin(local_t * 3.5 + i * 0.45) * 0.6 +
                math.sin(local_t * 2.1 + i * 0.28) * 0.4
            ))
            h = max(4, h)
            x  = x_start + i * (_WAVEFORM_W + _WAVEFORM_GAP)
            y0 = _WAVEFORM_Y - h // 2
            y1 = _WAVEFORM_Y + h // 2

            draw.rectangle(
                [x, y0, x + _WAVEFORM_W - 1, y1],
                fill=(*_C_WAVEFORM, int(180 * alpha)),
            )
