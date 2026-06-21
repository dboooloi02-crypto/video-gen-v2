"""
src/renderer/frame_renderer.py
Core frame renderer — composes background, template text layer,
vignette, and film grain into a final RGB numpy array per frame.

Performance:
  • TextCache  — text images pre-rendered on first use
  • GlowCache  — keyword glow pre-rendered on first use
  • SceneTimeline — O(log n) bisect lookup (no linear scan)
  • Grain pool  — 32 pre-computed noise variants cycled each frame
"""

import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    WIDTH, HEIGHT, FPS,
    C_BG, C_GRAD_TOP,
    VIGNETTE, GRAIN_INTENSITY, GRAIN_POOL,
    CAM_PUSH, FADE_IN, FADE_OUT,
)
from renderer.cache import (
    get_font_manager, get_text_cache, get_glow_cache,
    FontManager, TextCache, GlowCache,
)
from renderer.animation import (
    get_alpha, get_cam_push,
    build_vignette, build_grain_pool,
    apply_vignette, apply_grain,
)
from subtitle.subtitle_builder import Scene, SceneTimeline

if TYPE_CHECKING:
    from templates.base import BaseTemplate


# ── FrameRenderer ─────────────────────────────────────────────────────────────

class FrameRenderer:
    """
    Renders one video frame:
      1. Background (gradient + camera push)
      2. Template text layer (delegate to BaseTemplate)
      3. Vignette
      4. Film grain

    Usage:
        renderer = FrameRenderer(template)
        frame_array = renderer.render(scene, t=2.35)  # → H×W×3 uint8
    """

    def __init__(self, template: "BaseTemplate"):
        self.template = template

        # Shared caches (singletons)
        self.fm = get_font_manager()
        self.tc = get_text_cache()
        self.gc = get_glow_cache()

        # Per-template output dimensions (supports non-default aspect ratios)
        self._W, self._H = getattr(template, "output_size", (WIDTH, HEIGHT))

        # Pre-computed effects
        self._vignette  = build_vignette(self._W, self._H, VIGNETTE)
        self._grains    = build_grain_pool(self._W, self._H, GRAIN_INTENSITY, GRAIN_POOL)
        self._gidx      = 0
        self._bg_base   = self._build_bg()

    # ── Public ────────────────────────────────────────────────────────────────

    def render(self, scene: Scene, t: float) -> np.ndarray:
        """
        Render frame at global time t.

        Args:
            scene — the Scene currently on screen
            t     — global video time in seconds

        Returns:
            uint8 numpy array shape (HEIGHT, WIDTH, 3)
        """
        local_t = max(0.0, min(t - scene.start, scene.duration))
        alpha   = get_alpha(local_t, scene.duration, FADE_IN, FADE_OUT)
        scale   = get_cam_push(local_t, scene.duration, CAM_PUSH)

        # Layer 1: background (skip if template provides its own)
        if self.template.override_bg:
            bg = Image.new("RGBA", (self._W, self._H), (0, 0, 0, 255))
        else:
            push = scale if self.template.use_cam_push else 1.0
            bg = self._push_bg(push).convert("RGBA")

        # Layer 2: template text / graphics layer
        text_layer = self.template.render_layer(
            scene=scene,
            local_t=local_t,
            alpha=alpha,
            fm=self.fm,
            tc=self.tc,
            gc=self.gc,
        )

        # Composite
        composite = Image.alpha_composite(bg, text_layer).convert("RGB")

        # Post-process (gated by template flags)
        arr = np.array(composite, dtype=np.uint8)
        if self.template.use_vignette:
            arr = apply_vignette(arr, self._vignette)
        if self.template.use_grain:
            arr = apply_grain(arr, self._grains[self._gidx % GRAIN_POOL])
        self._gidx += 1
        return arr

    def make_frame_fn(self, timeline: SceneTimeline):
        """
        Return a MoviePy-compatible make_frame(t) function.

        Usage:
            fn = renderer.make_frame_fn(timeline)
            clip = VideoClip(fn, duration=timeline.total_duration)
        """
        black = np.zeros((self._H, self._W, 3), dtype=np.uint8)
        INTRO = 0.30

        def make_frame(t: float) -> np.ndarray:
            gt = t - INTRO           # global content time
            if gt < 0:
                return black
            scene = timeline.at(gt)
            if scene is None:
                return black
            return self.render(scene, gt)

        return make_frame, INTRO

    # ── Background ────────────────────────────────────────────────────────────

    def _build_bg(self) -> Image.Image:
        W, H = self._W, self._H
        img  = Image.new("RGB", (W, H), C_BG)
        draw = ImageDraw.Draw(img)
        gh   = H // 3
        for y in range(gh):
            t = 1.0 - y / gh
            c = tuple(int(C_BG[i] + (C_GRAD_TOP[i] - C_BG[i]) * t * 0.65)
                      for i in range(3))
            draw.line([(0, y), (W - 1, y)], fill=c)
        return img

    def _push_bg(self, scale: float) -> Image.Image:
        W, H = self._W, self._H
        if abs(scale - 1.0) < 5e-4:
            return self._bg_base.copy()
        nw = int(W * scale)
        nh = int(H * scale)
        big  = self._bg_base.resize((nw, nh), Image.LANCZOS)
        l, t = (nw - W) // 2, (nh - H) // 2
        return big.crop((l, t, l + W, t + H))
