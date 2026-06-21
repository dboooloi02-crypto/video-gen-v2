"""
src/templates/tiktok.py
TikTok-style bold text template.

Visual style:
  • Full-screen dark background with per-scene accent colour
  • ONE line of text at a time — huge font
  • Keywords in gold with strong glow
  • No separator / no hint card — pure visual impact
  • Subtle colour-band behind keyword
"""

import sys
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    WIDTH, HEIGHT,
    C_TEXT_ZH, C_TEXT_EN, C_KEYWORD,
    C_KW_GLOW, GLOW_R, GLOW_BOOST,
    LINE_GAP, FADE_IN, KW_SCALE_DUR,
)
from renderer.animation import get_kw_scale
from templates.base import BaseTemplate

import numpy as np
from PIL import ImageFilter


# ── TikTok-specific constants ─────────────────────────────────────────────────

_FS_ZH_TT  = 82      # slightly bigger Chinese text
_FS_EN_TT  = 72      # English line
_FS_KW_TT  = 110     # keyword — very large

# Cycling accent colours (one per scene index, wraps)
_ACCENT_COLOURS: List[Tuple[int, int, int]] = [
    (255, 208,  68),   # gold
    ( 80, 200, 255),   # cyan
    (255, 110, 110),   # coral
    (130, 255, 160),   # mint
    (200, 130, 255),   # lavender
    (255, 180,  60),   # amber
]

_KW_BAND_ALPHA = 30   # semi-transparent band behind keyword


class TikTokTemplate(BaseTemplate):
    """
    Bold, minimal, full-screen text in TikTok style.
    Accent colour cycles per scene for visual variety.
    """

    @property
    def name(self) -> str:
        return "tiktok"

    @property
    def description(self) -> str:
        return "Bold full-screen text, cycling accent colours, strong glow"

    # ── Main entry point ──────────────────────────────────────────────────────

    def render_layer(self, scene, local_t, alpha, fm, tc, gc) -> Image.Image:
        layer = self.blank()
        draw  = ImageDraw.Draw(layer)
        cx    = WIDTH // 2

        # Accent colour cycles with scene start time (cheap hash)
        accent_idx = int(scene.start * 0.5) % len(_ACCENT_COLOURS)
        accent     = _ACCENT_COLOURS[accent_idx]

        ks = get_kw_scale(local_t, FADE_IN * 0.5, KW_SCALE_DUR) if scene.has_kw else 1.0

        # ─ Layout: stack zh → en/kw vertically ───────────────────────────
        elements = []   # (kind, text)

        if scene.zh:
            elements.append(("zh", scene.zh))
        if scene.en and not scene.has_kw:
            elements.append(("en", scene.en))
        if scene.has_kw:
            elements.append(("kw", scene.keyword.word))

        # Measure total height
        heights = []
        for kind, text in elements:
            size = self._size_for(kind, ks)
            _, h = tc.get_size(text, size, "en" if kind != "zh" else "zh")
            heights.append(h)

        gap       = LINE_GAP + 8
        total_h   = sum(heights) + gap * max(0, len(heights) - 1)
        y         = HEIGHT // 2 - total_h // 2

        # ─ Render ─────────────────────────────────────────────────────────
        for idx, ((kind, text), h) in enumerate(zip(elements, heights)):
            size = self._size_for(kind, ks)

            if kind == "zh":
                img = tc.get_image(text, size, C_TEXT_ZH, "zh")
                self.paste_centered(layer, img, cx, y + h // 2, alpha_scale=alpha)

            elif kind == "en":
                img = tc.get_image(text, size, C_TEXT_EN, "en")
                self.paste_centered(layer, img, cx, y + h // 2, alpha_scale=alpha)

            elif kind == "kw" and ks > 0.01:
                self._draw_kw(layer, draw, text, cx, y, h, size,
                              ks, alpha, accent, tc)

            y += h + gap

        return layer

    # ── Keyword ───────────────────────────────────────────────────────────────

    def _draw_kw(self, layer, draw, text, cx, y_top, h, size,
                 ks, alpha, accent, tc):
        tw, th = tc.get_size(text, size, "en")
        x_text = cx - tw // 2
        y_text = y_top + max(0, (h - th) // 2)

        # Accent colour band (wide horizontal stripe)
        band_h = th + 24
        band_y = y_text - 12
        try:
            draw.rounded_rectangle(
                [x_text - 20, band_y,
                 x_text + tw + 20, band_y + band_h],
                radius=12,
                fill=(*accent, _KW_BAND_ALPHA),
            )
        except AttributeError:
            draw.rectangle(
                [x_text - 20, band_y, x_text + tw + 20, band_y + band_h],
                fill=(*accent, _KW_BAND_ALPHA),
            )

        # Glow (region-only)
        pad  = GLOW_R * 3
        rx0  = max(0, x_text - pad)
        ry0  = max(0, y_text - pad)
        rx1  = min(WIDTH,  x_text + tw + pad)
        ry1  = min(HEIGHT, y_text + th + pad)
        rw, rh = rx1 - rx0, ry1 - ry0

        if rw > 0 and rh > 0:
            from renderer.cache import get_font_manager
            gsurf = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
            gd    = ImageDraw.Draw(gsurf)
            font  = get_font_manager().get(size, "en")
            r, g, b = C_KW_GLOW
            gd.text((x_text - rx0, y_text - ry0), text, font=font,
                    fill=(r, g, b, int(255 * alpha)))
            blurred = gsurf.filter(ImageFilter.GaussianBlur(GLOW_R))
            arr = np.array(blurred).astype(np.float32)
            arr[:, :, :3] = np.clip(arr[:, :, :3] * GLOW_BOOST * 1.3, 0, 255)
            layer.paste(Image.fromarray(arr.astype(np.uint8), "RGBA"),
                        (rx0, ry0),
                        Image.fromarray(arr.astype(np.uint8), "RGBA"))

        # Keyword text in accent colour
        kw_img = tc.get_image(text, size, accent, "en")
        self.paste_centered(layer, kw_img,
                            cx, y_text + th // 2,
                            alpha_scale=alpha)

    # ── Helper ────────────────────────────────────────────────────────────────

    @staticmethod
    def _size_for(kind: str, ks: float) -> int:
        if kind == "zh":
            return _FS_ZH_TT
        if kind == "en":
            return _FS_EN_TT
        # keyword — scale-animated
        return max(14, int(_FS_KW_TT * max(ks, 0.1)))
