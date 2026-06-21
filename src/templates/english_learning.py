"""
src/templates/english_learning.py
Cinematic English Learning template.

Layout (vertically centred):
  ┌──────────────────────────────────┐
  │                                  │
  │   [Speaker A:]   ← small, muted  │
  │   今天你迟到了    ← ZH, off-white │
  │   ─────────────  ← separator     │
  │   ✦ FIX IT ✦    ← KW gold+glow  │
  │                                  │
  │  ┌────────────────────────────┐  │
  │  │▌ FIX IT                   │  │
  │  │  把它解决掉                 │  │
  │  └────────────────────────────┘  │
  └──────────────────────────────────┘
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    WIDTH, HEIGHT,
    C_TEXT_ZH, C_TEXT_EN, C_KEYWORD, C_KEYWORD as C_KW,
    C_SEPARATOR, C_HINT_BG, C_HINT_KW, C_HINT_MN,
    FS_ZH, FS_EN, FS_KW, FS_SPEAKER, FS_HINT_KW, FS_HINT_MN,
    LINE_GAP, SEP_LENGTH, SEP_H,
    HINT_MARGIN_X, HINT_H, HINT_BOTTOM,
    GLOW_R, GLOW_BOOST, C_KW_GLOW,
    FADE_IN, KW_SCALE_DUR,
)
from renderer.animation import get_kw_scale
from templates.base import BaseTemplate


_C_SPEAKER = (125, 125, 148)    # muted grey for speaker label


class EnglishLearningTemplate(BaseTemplate):
    """
    Cinematic dark background with:
    • Chinese text (main body)
    • English subtitle / keyword (highlighted in gold)
    • Speaker label (optional)
    • Bottom vocabulary hint card
    """

    @property
    def name(self) -> str:
        return "english_learning"

    @property
    def description(self) -> str:
        return "Cinematic dark style, ZH + EN + keyword glow + hint card"

    # ── Main entry point ──────────────────────────────────────────────────────

    def render_layer(self, scene, local_t, alpha, fm, tc, gc) -> Image.Image:
        layer = self.blank()
        draw  = ImageDraw.Draw(layer)

        cx = WIDTH // 2
        ks = get_kw_scale(local_t, FADE_IN * 0.55, KW_SCALE_DUR) if scene.has_kw else 1.0

        # ─ Build render plan ─────────────────────────────────────────────────
        plan = []   # list of (kind, text, reserved_h)

        if scene.speaker:
            lbl = f"{scene.speaker}:"
            _, h = tc.get_size(lbl, FS_SPEAKER, "zh")
            plan.append(("speaker", lbl, h))

        if scene.zh:
            _, h = tc.get_size(scene.zh, FS_ZH, "zh")
            plan.append(("zh", scene.zh, h))

        if scene.zh and (scene.en or scene.has_kw):
            plan.append(("sep", None, SEP_H))

        if scene.en and not scene.has_kw:
            _, h = tc.get_size(scene.en, FS_EN, "en")
            plan.append(("en", scene.en, h))

        if scene.has_kw:
            plan.append(("kw", scene.keyword.word, FS_KW))

        if not plan:
            return layer

        # ─ Vertical centering ─────────────────────────────────────────────
        total_h = sum(h + LINE_GAP for _, _, h in plan) - LINE_GAP
        y = HEIGHT // 2 - total_h // 2

        # ─ Render each element ────────────────────────────────────────────
        for kind, text, h in plan:
            if kind == "speaker":
                img = tc.get_image(text, FS_SPEAKER, _C_SPEAKER, "zh")
                self.paste_centered(layer, img, cx, y + h // 2,
                                    alpha_scale=alpha * 0.85)

            elif kind == "zh":
                img = tc.get_image(text, FS_ZH, C_TEXT_ZH, "zh")
                self.paste_centered(layer, img, cx, y + h // 2,
                                    alpha_scale=alpha)

            elif kind == "sep":
                x0, x1 = cx - SEP_LENGTH // 2, cx + SEP_LENGTH // 2
                draw.line([(x0, y + SEP_H // 2), (x1, y + SEP_H // 2)],
                          fill=(*C_SEPARATOR, int(80 * alpha)), width=1)

            elif kind == "en":
                img = tc.get_image(text, FS_EN, C_TEXT_EN, "en")
                self.paste_centered(layer, img, cx, y + h // 2,
                                    alpha_scale=alpha)

            elif kind == "kw" and ks > 0.01:
                self._draw_keyword(layer, draw, text, cx, y, ks, alpha, tc, gc)
                hint_a = min(1.0, max(0.0, (ks - 0.4) / 0.5)) * alpha
                if hint_a > 0.02 and scene.keyword:
                    self._draw_hint(layer, scene.keyword.word,
                                    scene.keyword.meaning, hint_a, tc, fm)

            y += h + LINE_GAP

        return layer

    # ── Keyword with glow ─────────────────────────────────────────────────────

    def _draw_keyword(self, layer, draw, text, cx, y_top, ks, alpha, tc, gc):
        size   = max(14, int(FS_KW * ks))
        tw, th = tc.get_size(text, size, "en")
        x_text = cx - tw // 2
        y_text = y_top + max(0, (FS_KW - th) // 2)

        # ─ Glow (region-only blur for speed) ──────────────────────────────
        pad  = GLOW_R * 3
        rx0, ry0 = max(0, x_text - pad), max(0, y_text - pad)
        rx1, ry1 = min(WIDTH, x_text + tw + pad), min(HEIGHT, y_text + th + pad)
        rw,  rh  = rx1 - rx0, ry1 - ry0

        if rw > 0 and rh > 0:
            glow_surf = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_surf)
            from renderer.cache import get_font_manager
            font = get_font_manager().get(size, "en")
            r, g, b = C_KW_GLOW
            gd.text((x_text - rx0, y_text - ry0), text, font=font,
                    fill=(r, g, b, int(255 * alpha)))
            blurred = glow_surf.filter(ImageFilter.GaussianBlur(GLOW_R))
            arr = np.array(blurred).astype(np.float32)
            arr[:, :, :3] = np.clip(arr[:, :, :3] * GLOW_BOOST, 0, 255)
            glow_boosted = Image.fromarray(arr.astype(np.uint8), "RGBA")
            layer.paste(glow_boosted, (rx0, ry0), glow_boosted)

        # ─ Keyword text ────────────────────────────────────────────────────
        kw_img = tc.get_image(text, size, C_KEYWORD, "en")
        self.paste_centered(layer, kw_img,
                            cx, y_text + th // 2,
                            alpha_scale=alpha)

    # ── Hint card ─────────────────────────────────────────────────────────────

    def _draw_hint(self, layer, word, meaning, alpha, tc, fm):
        cw   = WIDTH - HINT_MARGIN_X * 2
        card = Image.new("RGBA", (cw, HINT_H), (0, 0, 0, 0))
        cd   = ImageDraw.Draw(card)

        bg_a = int(215 * alpha)
        try:
            cd.rounded_rectangle([0, 0, cw - 1, HINT_H - 1],
                                  radius=18, fill=(*C_HINT_BG, bg_a))
            cd.rounded_rectangle([0, 12, 5, HINT_H - 12],
                                  radius=3,  fill=(*C_HINT_KW, int(255*alpha)))
        except AttributeError:
            cd.rectangle([0, 0, cw-1, HINT_H-1], fill=(*C_HINT_BG, bg_a))
            cd.rectangle([0, 12, 5, HINT_H-12],  fill=(*C_HINT_KW, int(255*alpha)))

        ta = int(255 * alpha)
        kw_img = tc.get_image(word,    FS_HINT_KW, C_HINT_KW, "en")
        mn_img = tc.get_image(meaning, FS_HINT_MN, C_HINT_MN, "zh")

        # Paste at fixed offsets inside card
        card.paste(kw_img, (20, 14), kw_img)
        mn_img_a = self.apply_alpha(mn_img, alpha)
        card.paste(mn_img_a, (20, 74), mn_img_a)

        cy = HEIGHT - HINT_BOTTOM
        layer.paste(card, (HINT_MARGIN_X, cy), card)
