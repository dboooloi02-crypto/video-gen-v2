"""
src/export/video_exporter.py
Video export using MoviePy.

Accepts a make_frame function + audio segments → writes MP4.
Handles:
  • intro / outro black padding
  • per-segment or merged audio
  • MoviePy v1 / v2 compatibility
"""

import sys
import warnings
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import FPS, WIDTH, HEIGHT, OUTPUT_DIR

# MoviePy compatibility shim
try:
    from moviepy.editor import VideoClip, AudioFileClip, concatenate_audioclips
    _MOVIEPY_V = 1
except ImportError:
    try:
        from moviepy import VideoClip, AudioFileClip, concatenate_audioclips
        _MOVIEPY_V = 2
    except ImportError:
        raise ImportError("MoviePy not found. Run: pip install moviepy")


class VideoExporter:
    """
    Wraps MoviePy to produce the final MP4.

    Usage:
        exporter = VideoExporter()
        exporter.export(
            make_frame=fn,
            total_duration=42.0,
            output_path="output/video.mp4",
            audio_paths=["output/audio/line_000.mp3", ...],
        )
    """

    INTRO  = 0.30    # black intro seconds
    OUTRO  = 0.40    # black outro seconds
    CRF    = "20"    # libx264 quality (lower = better, bigger file)
    PRESET = "medium"

    def export(
        self,
        make_frame:      Callable[[float], np.ndarray],
        total_duration:  float,
        output_path:     str,
        audio_paths:     Optional[List[str]] = None,
        intro_offset:    float = 0.0,
    ) -> str:
        """
        Export video to MP4.

        Args:
            make_frame      — fn(t: float) → uint8 np.ndarray (H×W×3)
                              t is in content seconds (after intro)
            total_duration  — total content duration (NOT including intro/outro)
            output_path     — output MP4 path
            audio_paths     — list of audio segment paths in order
            intro_offset    — additional time offset already applied in make_frame

        Returns:
            Absolute output path string.
        """
        video_dur = self.INTRO + total_duration + self.OUTRO

        # Probe actual frame size from make_frame (supports any aspect ratio,
        # not just the default 9:16 from config) — avoids shape mismatch
        # during intro/outro black-frame padding.
        try:
            probe_t = min(max(0.0, -intro_offset), total_duration)
            _probe  = make_frame(probe_t)
            frame_h, frame_w = _probe.shape[0], _probe.shape[1]
        except Exception:
            frame_h, frame_w = HEIGHT, WIDTH   # fallback to config default

        def _make_frame(t: float) -> np.ndarray:
            ct = t - self.INTRO + intro_offset   # content time
            if ct < 0 or ct > total_duration:
                return np.zeros((frame_h, frame_w, 3), dtype=np.uint8)
            return make_frame(ct)

        clip = VideoClip(_make_frame, duration=video_dur)

        # Attach audio
        if audio_paths:
            audio_clip = self._build_audio(audio_paths, video_dur)
            if audio_clip:
                clip = clip.with_audio(audio_clip)

        # Write
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self._write(clip, output_path)
        clip.close()
        return str(Path(output_path).resolve())

    # ── Audio ─────────────────────────────────────────────────────────────────

    def _build_audio(self, paths: List[str], max_dur: float):
        """Concatenate audio files; return AudioClip or None."""
        valid = [p for p in paths if Path(p).exists()]
        if not valid:
            return None
        try:
            clips = [AudioFileClip(p) for p in valid]
            combined = concatenate_audioclips(clips)
            return combined.subclipped(0, min(combined.duration, max_dur))
        except Exception as exc:
            warnings.warn(f"Audio build failed: {exc}")
            return None

    # ── Write ─────────────────────────────────────────────────────────────────

    def _write(self, clip: VideoClip, path: str):
        kwargs = dict(
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset=self.PRESET,
            ffmpeg_params=["-crf", self.CRF, "-pix_fmt", "yuv420p"],
        )
        try:
            clip.write_videofile(path, **kwargs, logger=None)
        except TypeError:
            clip.write_videofile(path, **kwargs)
