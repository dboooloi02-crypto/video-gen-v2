"""
src/tts/mixed_tts.py
Mixed-language TTS — Chinese voice for Chinese segments,
English voice for English keywords.

Network unavailable? Graceful fallback:
  • Estimated duration from character count
  • Silent WAV generated locally (ffmpeg)
  • Video still renders with correct keyword timing animation

On the user's own machine with internet access, real Edge TTS audio is used.
"""

import io
import ssl
import struct
import subprocess
import sys
import wave
from pathlib import Path
from typing import Dict, List, Tuple

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import TTS_VOICE_MAP, OUTPUT_DIR
from tts.edge_tts_engine import EdgeTTSEngine

# ── SSL bypass (applied once at import) ───────────────────────────────────────
try:
    import edge_tts.communicate as _ec
    _bypass_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    _bypass_ctx.check_hostname = False
    _bypass_ctx.verify_mode    = ssl.CERT_NONE
    _ec._SSL_CTX = _bypass_ctx
except Exception:
    pass


# ── Audio helpers ─────────────────────────────────────────────────────────────

def _silence_wav(path: str, duration: float, sample_rate: int = 22050):
    """Write a silent WAV file of given duration."""
    n = max(1, int(sample_rate * duration))
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n)
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def _wav_to_mp3(wav_path: str, mp3_path: str) -> bool:
    """Convert WAV → MP3 via ffmpeg."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-q:a", "9", "-f", "mp3", mp3_path],
        capture_output=True,
    )
    return r.returncode == 0


def concat_mp3(paths: List[str], out_path: str) -> bool:
    """Merge MP3/WAV files in order using ffmpeg concat."""
    valid = [p for p in paths if Path(p).exists() and Path(p).stat().st_size > 0]
    if not valid:
        return False
    if len(valid) == 1:
        import shutil; shutil.copy(valid[0], out_path); return True

    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False, dir="/tmp")
    try:
        for p in valid:
            tmp.write(f"file '{p}'\n")
        tmp.close()
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", tmp.name, "-c", "copy", out_path],
            capture_output=True,
        )
        return r.returncode == 0
    finally:
        import os; os.unlink(tmp.name)


def _estimate_dur(text: str) -> float:
    """Estimate speech duration from text length."""
    is_zh = sum(1 for c in text if "\u4e00" <= c <= "\u9fff") > len(text) * 0.3
    cps = 4.2 if is_zh else 3.8   # characters per second
    return max(0.4, len(text.strip()) / cps)


# ── MixedTTSEngine ────────────────────────────────────────────────────────────

class MixedTTSEngine:
    """
    Synthesise paragraph audio, mixing Chinese TTS and English TTS per token.
    Falls back to estimated timing + silent audio on any network error.
    """

    def __init__(self, zh_voice: str = "zh", en_voice: str = "en"):
        self.zh_voice = TTS_VOICE_MAP.get(zh_voice, TTS_VOICE_MAP["zh"])
        self.en_voice = TTS_VOICE_MAP.get(en_voice, TTS_VOICE_MAP["en"])
        self._tts     = EdgeTTSEngine()

    # ── Public ────────────────────────────────────────────────────────────────

    def synthesise_paragraph(
        self,
        tokens,
        out_dir,
        para_idx:      int   = 0,
        global_offset: float = 0.0,
    ) -> Tuple[str, Dict[int, object], float]:
        """
        Synthesise one paragraph. Returns (merged_path, kw_beats, total_dur).
        kw_beats: {kw_idx: WordBeat}
        """
        from subtitle.subtitle_builder import WordBeat

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        seg_paths: List[str] = []
        cumulative: float    = 0.0
        kw_beats              = {}
        # Track success/failure PER LANGUAGE so we can tell the user exactly
        # which language is failing instead of a single misleading flag.
        lang_stats = {"zh": [0, 0], "en": [0, 0]}   # lang -> [success, total]

        for i, tok in enumerate(tokens):
            raw = tok.text.strip()
            if not raw:
                continue

            voice    = self.en_voice if tok.lang == "en" else self.zh_voice
            mp3_path = str(out_dir / f"p{para_idx}_s{i:04d}.mp3")
            wav_path = str(out_dir / f"p{para_idx}_s{i:04d}.wav")

            lang_stats.setdefault(tok.lang, [0, 0])
            lang_stats[tok.lang][1] += 1

            # ── Try real TTS (raw — exceptions propagate, no internal masking) ──
            try:
                _, dur = self._tts._generate_one_raw(raw, voice, mp3_path)
                seg_paths.append(mp3_path)
                lang_stats[tok.lang][0] += 1
                tag = "✓"
            except Exception as exc:
                # ── Fallback: silent audio + estimated timing ─────────────
                dur = _estimate_dur(raw)
                _silence_wav(wav_path, dur)
                if _wav_to_mp3(wav_path, mp3_path):
                    seg_paths.append(mp3_path)
                tag = f"~({type(exc).__name__})"

            lang_tag = f"[{tok.lang}]"
            preview  = raw[:28] + "…" if len(raw) > 28 else raw
            print(f"    {tag} {lang_tag} {preview!r:35s}  {dur:.2f}s")

            if tok.is_keyword:
                kw_beats[tok.kw_idx] = WordBeat(
                    word=tok.text,
                    start=round(global_offset + cumulative, 4),
                    end=round(global_offset + cumulative + dur, 4),
                )
            cumulative += dur

        # ── Merge segments ────────────────────────────────────────────────────
        merged = str(out_dir / f"para{para_idx}_merged.mp3")
        if seg_paths:
            concat_mp3(seg_paths, merged)
        else:
            merged = ""

        parts = []
        for lang, (ok, total) in lang_stats.items():
            if total > 0:
                parts.append(f"{lang}={ok}/{total}")
        status = "  ".join(parts) if parts else "no segments"
        print(f"    → para{para_idx}: {cumulative:.2f}s  [{status}]")
        return merged, kw_beats, round(cumulative, 3)

    def synthesise_all(
        self,
        paragraphs: List[dict],
        out_dir,
    ) -> List[Tuple[str, Dict, float]]:
        """Synthesise all paragraphs; update each para dict in-place."""
        results  = []
        t_offset = 0.0
        for i, para in enumerate(paragraphs):
            tokens = para.get("_tokens", [])
            merged, beats, dur = self.synthesise_paragraph(
                tokens, out_dir, para_idx=i, global_offset=t_offset
            )
            para["_duration"] = dur
            para["_audio"]    = merged
            para["_kw_beats"] = beats
            results.append((merged, beats, dur))
            t_offset += dur
        return results
