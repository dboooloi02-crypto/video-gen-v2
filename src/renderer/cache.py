"""
src/renderer/cache.py
Pre-rendering caches — the biggest single performance win.

TextCache  : rendered text images keyed by (text, size, color, lang)
GlowCache  : blurred glow halos keyed by (text, size)
FontManager: loads & caches font handles
"""

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    FONTS_DIR,
    GLOW_R, GLOW_BOOST,
    C_KW_GLOW,
)

# ── Type aliases ──────────────────────────────────────────────────────────────
_TextKey  = Tuple[str, int, Tuple[int, int, int], str]  # (text,size,color,lang)
_GlowKey  = Tuple[str, int]                             # (text, size)


# ── FontManager ───────────────────────────────────────────────────────────────

class FontManager:
    """Loads and caches PIL font handles. Singleton-friendly."""

    _ZH = [
        str(FONTS_DIR / "NotoSansSC-Bold.ttf"),
        str(FONTS_DIR / "NotoSansSCBold.ttf"),
        str(FONTS_DIR / "NotoSansCJK-Bold.ttc"),
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]
    _EN = [
        str(FONTS_DIR / "BebasNeue-Regular.ttf"),
        str(FONTS_DIR / "Montserrat-Bold.ttf"),
        str(FONTS_DIR / "Oswald-Bold.ttf"),
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]

    def __init__(self):
        self._cache: Dict[Tuple[int, str], ImageFont.FreeTypeFont] = {}
        self.zh_path = self._find(self._ZH, "Chinese/CJK")
        self.en_path = self._find(self._EN, "English Bold")

    @staticmethod
    def _find(candidates: list, label: str) -> Optional[str]:
        for p in candidates:
            if os.path.exists(p):
                return p
        warnings.warn(
            f"\n⚠  No {label} font found — run: python setup_fonts.py\n"
            f"   Or place fonts in: {FONTS_DIR}",
            stacklevel=4,
        )
        return None

    def get(self, size: int, lang: str = "zh") -> ImageFont.FreeTypeFont:
        key = (size, lang)
        if key in self._cache:
            return self._cache[key]
        path = self.en_path if lang == "en" else self.zh_path
        try:
            font = ImageFont.truetype(path, size) if path else None
        except Exception:
            font = None
        if font is None:
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:
                font = ImageFont.load_default()
        self._cache[key] = font
        return font


# ── TextCache ─────────────────────────────────────────────────────────────────

class TextCache:
    """
    Caches pre-rendered text as RGBA PIL Images.

    First call: renders text → saves to cache.
    Subsequent calls: returns cached image directly (~10x speedup).

    Key: (text, font_size, rgb_color, lang)
    """

    def __init__(self, font_manager: FontManager):
        self._fm = font_manager
        self._cache: Dict[_TextKey, Image.Image] = {}
        self.hits = 0
        self.misses = 0

    def get_image(
        self,
        text: str,
        size: int,
        color: Tuple[int, int, int],
        lang: str = "zh",
    ) -> Image.Image:
        """Return cached RGBA image of rendered text."""
        key: _TextKey = (text, size, tuple(color[:3]), lang)

        if key in self._cache:
            self.hits += 1
            return self._cache[key]

        self.misses += 1
        img = self._render(text, size, color, lang)
        self._cache[key] = img
        return img

    def get_size(
        self,
        text: str,
        size: int,
        lang: str = "zh",
    ) -> Tuple[int, int]:
        """Return (width, height) of text without color information."""
        font = self._fm.get(size, lang)
        tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        try:
            bb = tmp.textbbox((0, 0), text, font=font)
            return bb[2] - bb[0], bb[3] - bb[1]
        except AttributeError:
            return tmp.textsize(text, font=font)

    def _render(
        self,
        text: str,
        size: int,
        color: Tuple[int, int, int],
        lang: str,
    ) -> Image.Image:
        font = self._fm.get(size, lang)
        tmp_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        try:
            bb = tmp_draw.textbbox((0, 0), text, font=font)
            w, h = bb[2] - bb[0], bb[3] - bb[1]
        except AttributeError:
            w, h = tmp_draw.textsize(text, font=font)

        # Add small padding so glow/descenders aren't clipped
        pad = max(4, size // 10)
        canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.text((pad, pad), text, font=font, fill=(*color, 255))
        return canvas

    def clear(self):
        self._cache.clear()
        self.hits = self.misses = 0

    def stats(self) -> str:
        total = self.hits + self.misses
        pct   = f"{self.hits / total * 100:.0f}%" if total else "n/a"
        return f"TextCache  hits={self.hits}/{total} ({pct})  keys={len(self._cache)}"


# ── GlowCache ─────────────────────────────────────────────────────────────────

class GlowCache:
    """
    Caches pre-rendered keyword glow halos as RGBA PIL Images.

    The glow is the most expensive per-frame operation (GaussianBlur on a
    large surface).  By pre-rendering at first use, we pay the cost once
    regardless of how many frames the keyword appears across.

    Key: (text, font_size)
    """

    def __init__(self, font_manager: FontManager, text_cache: TextCache):
        self._fm    = font_manager
        self._tc    = text_cache
        self._cache: Dict[_GlowKey, Image.Image] = {}

    def get_glow(self, text: str, size: int) -> Image.Image:
        """Return full-frame-size RGBA glow halo (WIDTH × HEIGHT)."""
        from config import WIDTH, HEIGHT          # avoid circular at module level
        key: _GlowKey = (text, size)

        if key in self._cache:
            return self._cache[key]

        glow = self._render(text, size, WIDTH, HEIGHT)
        self._cache[key] = glow
        return glow

    def _render(
        self, text: str, size: int, frame_w: int, frame_h: int
    ) -> Image.Image:
        font   = self._fm.get(size, "en")
        tw, th = self._tc.get_size(text, size, "en")
        cx     = frame_w // 2
        ty     = frame_h // 2    # placeholder; caller shifts vertically

        # Draw glow text in orange onto full-frame surface
        surf = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(surf)
        r, g, b = C_KW_GLOW
        draw.text((cx - tw // 2, ty - th // 2), text, font=font,
                  fill=(r, g, b, 255))

        # Blur
        blurred = surf.filter(ImageFilter.GaussianBlur(GLOW_R))

        # Boost
        arr = np.array(blurred).astype(np.float32)
        arr[:, :, :3] = np.clip(arr[:, :, :3] * GLOW_BOOST, 0, 255)
        return Image.fromarray(arr.astype(np.uint8), "RGBA")

    def clear(self):
        self._cache.clear()

    def stats(self) -> str:
        return f"GlowCache  keys={len(self._cache)}"


# ── Singleton helpers ─────────────────────────────────────────────────────────

_fm: Optional[FontManager] = None
_tc: Optional[TextCache]   = None
_gc: Optional[GlowCache]   = None


def get_font_manager() -> FontManager:
    global _fm
    if _fm is None:
        _fm = FontManager()
    return _fm


def get_text_cache() -> TextCache:
    global _tc
    if _tc is None:
        _tc = TextCache(get_font_manager())
    return _tc


def get_glow_cache() -> GlowCache:
    global _gc
    if _gc is None:
        _gc = GlowCache(get_font_manager(), get_text_cache())
    return _gc


def cache_stats() -> str:
    lines = []
    if _tc:
        lines.append(_tc.stats())
    if _gc:
        lines.append(_gc.stats())
    return "\n".join(lines) if lines else "(no caches initialised)"
