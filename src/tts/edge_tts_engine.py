_TTS_WARNED = False  # suppress repeated TTS warnings

"""
src/tts/edge_tts_engine.py
Edge TTS with word-boundary timing.

Hardening:
  • SSL bypass via ssl.create_default_context patch
  • Silent-audio fallback when TTS service is unreachable
    (sandbox / firewall / offline) — video still animates correctly
"""

import asyncio
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import TTS_VOICE_MAP, TTS_RATE, TTS_VOLUME, OUTPUT_DIR


# ── Apply SSL patch (proxy environments / self-signed certs) ──────────────────
def _patch_ssl():
    import ssl as _ssl
    if getattr(_ssl, "_no_verify_patched", False):
        return
    _orig = _ssl.create_default_context
    def _no_verify(*a, **kw):
        ctx = _orig(*a, **kw)
        ctx.check_hostname = False
        ctx.verify_mode    = _ssl.CERT_NONE
        return ctx
    _ssl.create_default_context = _no_verify
    _ssl._no_verify_patched = True

_patch_ssl()


# ── Silent-audio generator (ffmpeg) ──────────────────────────────────────────

def generate_silence(duration: float, out_path: str) -> bool:
    """Create a silent MP3 of the given duration using ffmpeg."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y",
             "-f", "lavfi",
             "-i", f"anullsrc=r=24000:cl=mono",
             "-t", str(max(0.1, duration)),
             "-q:a", "9", "-acodec", "libmp3lame",
             out_path],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class WordTiming:
    word:  str
    start: float
    end:   float


@dataclass
class AudioSegment:
    speaker:      str
    text:         str
    lang:         str
    audio_path:   str
    word_timings: List[WordTiming] = field(default_factory=list)
    duration:     float = 0.0


# ── Engine ────────────────────────────────────────────────────────────────────

class EdgeTTSEngine:
    """
    Synthesise audio with word-level timing.
    Falls back to silent audio + estimated timing if Edge TTS is unreachable.
    """

    def __init__(self, voice_key: str = "en"):
        self.voice = TTS_VOICE_MAP.get(voice_key, TTS_VOICE_MAP["en"])

    # ── Public ────────────────────────────────────────────────────────────────

    def synthesise(self, lines, out_dir=None, voice_override="") -> List[AudioSegment]:
        out_dir = Path(out_dir) if out_dir else OUTPUT_DIR / "audio"
        out_dir.mkdir(parents=True, exist_ok=True)
        voice   = TTS_VOICE_MAP.get(voice_override, self.voice) if voice_override else self.voice

        segments = []
        for i, line in enumerate(lines):
            text     = line.en
            out_path = out_dir / f"line_{i:03d}_{line.speaker}.mp3"
            print(f"  🔊  [{i+1}/{len(lines)}] {line.speaker}: {text[:45]}…")
            timings, dur = self._generate_one(text, voice, str(out_path))
            segments.append(AudioSegment(
                speaker=line.speaker, text=text, lang="en",
                audio_path=str(out_path),
                word_timings=timings, duration=dur,
            ))
        return segments

    def _generate_one(
        self, text: str, voice: str, out_path: str
    ) -> Tuple[List[WordTiming], float]:
        """Generate audio. On failure return silence + estimated timing."""
        try:
            return self._run_async(text, voice, out_path)
        except Exception as exc:
            global _TTS_WARNED
            if not _TTS_WARNED:
                import warnings
                warnings.warn(
                    f"Edge TTS unavailable ({type(exc).__name__}) — "
                    "using silence + estimated timing. "
                    "On your local machine with internet this uses real TTS.",
                    stacklevel=2,
                )
                _TTS_WARNED = True
            dur = self._estimate_duration(text, voice)
            generate_silence(dur, out_path)
            return [], round(dur, 3)

    def _generate_one_raw(
        self, text: str, voice: str, out_path: str
    ) -> Tuple[List[WordTiming], float]:
        """
        Same as _generate_one() but does NOT swallow exceptions —
        re-raises on failure so callers (e.g. MixedTTSEngine) can
        accurately detect per-segment success/failure instead of
        silently masking it behind a fake "success" silence fallback.
        """
        return self._run_async(text, voice, out_path)

    # ── Core async ────────────────────────────────────────────────────────────

    def _run_async(self, text, voice, out_path):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    f = pool.submit(asyncio.run, _tts_async(text, voice, out_path))
                    return f.result()
            return loop.run_until_complete(_tts_async(text, voice, out_path))
        except RuntimeError:
            return asyncio.run(_tts_async(text, voice, out_path))

    @staticmethod
    def _estimate_duration(text: str, voice: str) -> float:
        """Rough duration estimate from character/word count."""
        is_en = any(v in voice for v in ("en-US", "en-GB", "en-AU"))
        if is_en:
            return max(0.5, len(text.split()) * 0.38)
        else:
            return max(0.5, len(text) * 0.13)


async def _tts_async(
    text: str, voice: str, out_path: str
) -> Tuple[List[WordTiming], float]:
    """Core async TTS call using Edge TTS stream API."""
    import edge_tts

    communicate = edge_tts.Communicate(
        text=text, voice=voice,
        rate=TTS_RATE, volume=TTS_VOLUME,
    )

    audio_bytes   = bytearray()
    raw_bounds: list = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            raw_bounds.append(chunk)

    with open(out_path, "wb") as f:
        f.write(audio_bytes)

    timings = [
        WordTiming(
            word=b["text"],
            start=round(b["offset"]                    / 10_000_000, 4),
            end=  round((b["offset"] + b["duration"]) / 10_000_000, 4),
        )
        for b in raw_bounds
    ]

    # IMPORTANT: WordBoundary events are unreliable for Chinese text — Edge
    # TTS frequently returns zero WordBoundary events for zh-CN voices, so
    # `timings` can be empty even on a fully successful synthesis. The old
    # fallback `len(audio_bytes) / 16_000` assumed a fixed byte-rate that
    # does not match the actual MP3 encoding rate, silently producing
    # wildly-wrong (usually far too short) durations — this is what caused
    # keyword highlight animations to race ahead of the real audio.
    # Always prefer the REAL decoded duration from the audio file itself.
    duration = _probe_duration(out_path)
    if duration <= 0:
        # Last-resort fallback only if ffprobe itself is unavailable
        duration = timings[-1].end if timings else len(audio_bytes) / 16_000

    return timings, round(duration, 3)


def _probe_duration(path: str) -> float:
    """Read the real audio duration via ffprobe (accurate regardless of
    codec/bitrate, unlike byte-count estimation)."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10,
        )
        val = r.stdout.strip()
        return float(val) if val else 0.0
    except Exception:
        return 0.0
