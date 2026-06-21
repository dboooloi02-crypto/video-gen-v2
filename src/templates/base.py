"""
src/templates/base.py
Abstract base class for all video templates.

Each template is responsible for composing the text/graphic layer
(RGBA PIL Image) for a given Scene + local time.
The FrameRenderer handles background, vignette, and grain on top.

To add a new template:
    1. Subclass BaseTemplate
    2. Implement render_layer()
    3. Register in templates/__init__.py REGISTRY
"""

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import WIDTH, HEIGHT

if TYPE_CHECKING:
    from renderer.cache import FontManager, TextCache, GlowCache
    from subtitle.subtitle_builder import Scene


class BaseTemplate(ABC):
    """
    All rendering templates inherit from this class.

    render_layer() must return a transparent RGBA PIL Image (WIDTH × HEIGHT).
    The base FrameRenderer alpha-composites this over the background.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier used in CLI --template flag."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for help text."""
        ...

    @abstractmethod
    def render_layer(
        self,
        scene:    "Scene",
        local_t:  float,
        alpha:    float,
        fm:       "FontManager",
        tc:       "TextCache",
        gc:       "GlowCache",
    ) -> Image.Image:
        """
        Draw the text / graphic layer for this frame.

        Args:
            scene   — current Scene object
            local_t — time within scene (0 … scene.duration)
            alpha   — master opacity from fade-in/out (0 … 1)
            fm      — FontManager  (get font handles)
            tc      — TextCache    (get pre-rendered text images)
            gc      — GlowCache    (get pre-rendered glow halos)

        Returns:
            RGBA PIL Image of size (WIDTH, HEIGHT).
            Transparent background expected; opaque pixels are composited.
        """
        ...

    # ── Shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def blank() -> Image.Image:
        """Return an empty RGBA canvas."""
        return Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

    @staticmethod
    def paste_centered(
        layer: Image.Image,
        img:   Image.Image,
        cx:    int,
        cy:    int,
        alpha_scale: float = 1.0,
    ):
        """
        Paste img centred at (cx, cy) onto layer with optional alpha scaling.
        Modifies layer in place.
        """
        x = cx - img.width  // 2
        y = cy - img.height // 2

        if alpha_scale < 1.0 and img.mode == "RGBA":
            arr = __import__("numpy").array(img, dtype=float)
            arr[:, :, 3] = (arr[:, :, 3] * alpha_scale).clip(0, 255)
            img = Image.fromarray(arr.astype("uint8"), "RGBA")

        layer.paste(img, (x, y), img)


    # ── Optional overrides for post-processing ─────────────────────────────────
    @property
    def output_size(self) -> tuple:
        """(width, height) — override for non-default resolutions."""
        from config import WIDTH, HEIGHT
        return (WIDTH, HEIGHT)

    @property
    def use_vignette(self) -> bool:
        """Return False to skip vignette (e.g. for light-background templates)."""
        return True

    @property
    def use_grain(self) -> bool:
        """Return False to skip film grain."""
        return True

    @staticmethod
    def apply_alpha(img: Image.Image, alpha: float) -> Image.Image:
        """Return a copy of img with its alpha channel scaled by alpha."""
        import numpy as np
        arr = np.array(img, dtype=float)
        arr[:, :, 3] = (arr[:, :, 3] * alpha).clip(0, 255)
        return Image.fromarray(arr.astype("uint8"), "RGBA")

    # ── Post-processing flags (override in subclasses) ─────────────────────────

    @property
    def output_size(self) -> tuple:
        """(width, height) — override for non-default resolutions."""
        from config import WIDTH, HEIGHT
        return (WIDTH, HEIGHT)

    @property
    def use_vignette(self) -> bool:
        """Apply dark-edge vignette. Set False for light-background templates."""
        return True

    @property
    def use_grain(self) -> bool:
        """Apply film grain noise."""
        return True

    @property
    def use_cam_push(self) -> bool:
        """Apply background camera-push zoom."""
        return True

    @property
    def override_bg(self) -> bool:
        """If True, render_layer draws its own background (fully opaque)."""
        return False
