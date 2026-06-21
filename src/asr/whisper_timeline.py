"""
src/asr/whisper_timeline.py
Optional Whisper-based word timing to replace/correct Edge TTS boundaries.

When Edge TTS word boundaries are accurate enough (they usually are for English),
this module is NOT needed.  Use it when you need:
  • Chinese word timing
  • Corrected timings after audio processing
  • Higher accuracy for long sentences

Install: pip install openai-whisper  (requires ffmpeg)
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import ASR_MODEL, ASR_DEVICE


# ── Data model (re-exported for convenience) ──────────────────────────────────

@dataclass
class WordTiming:
    word:    str
    start:   float
    end:     float
    speaker: str = ""


# ── Whisper timeline ──────────────────────────────────────────────────────────

class WhisperTimeline:
    """
    Transcribes audio with word-level timestamps using OpenAI Whisper.

    Usage:
        wt = WhisperTimeline(model="base")
        timings = wt.transcribe("audio.mp3")

    Then align with dialogue:
        aligned = wt.align(timings, dialogue_lines)
    """

    def __init__(self, model: str = ASR_MODEL, device: str = ASR_DEVICE):
        self.model_name = model
        self.device     = device
        self._model     = None    # lazy load

    def _load(self):
        if self._model is None:
            try:
                import whisper
                print(f"  🎙  Loading Whisper '{self.model_name}' on {self.device} …")
                self._model = whisper.load_model(self.model_name, device=self.device)
            except ImportError:
                raise ImportError(
                    "openai-whisper not installed.\n"
                    "Run: pip install openai-whisper\n"
                    "Also requires ffmpeg: brew install ffmpeg / apt install ffmpeg"
                )

    # ── Public ────────────────────────────────────────────────────────────────

    def transcribe(self, audio_path: str) -> List[WordTiming]:
        """
        Transcribe audio file and return word-level timings.

        Args:
            audio_path — path to MP3/WAV file

        Returns:
            List[WordTiming] with start/end in seconds
        """
        self._load()
        import whisper

        result = self._model.transcribe(
            audio_path,
            word_timestamps=True,
            language=None,         # auto-detect
        )

        timings: List[WordTiming] = []
        for segment in result.get("segments", []):
            for word_info in segment.get("words", []):
                timings.append(WordTiming(
                    word=word_info["word"].strip(),
                    start=round(word_info["start"], 4),
                    end=round(word_info["end"],   4),
                ))

        return timings

    def transcribe_segments(self, audio_paths: List[str]) -> List[List[WordTiming]]:
        """
        Transcribe multiple audio files (one per dialogue line).
        Returns one list of WordTiming per file.
        """
        return [self.transcribe(p) for p in audio_paths]

    # ── Alignment ─────────────────────────────────────────────────────────────

    @staticmethod
    def align(
        per_segment_timings: List[List[WordTiming]],
        segment_offsets: List[float],
    ) -> List[WordTiming]:
        """
        Convert per-segment local timings into a global timeline.

        Args:
            per_segment_timings — list of WordTiming lists, one per audio segment
            segment_offsets     — start time (seconds) of each segment in the video

        Returns:
            Flat list of WordTiming with global timestamps
        """
        global_timings: List[WordTiming] = []
        for timings, offset in zip(per_segment_timings, segment_offsets):
            for wt in timings:
                global_timings.append(WordTiming(
                    word=wt.word,
                    start=round(wt.start + offset, 4),
                    end=round(wt.end   + offset, 4),
                    speaker=wt.speaker,
                ))
        return global_timings

    @staticmethod
    def tag_keywords(
        timings: List[WordTiming],
        keywords: List[str],
    ) -> List[WordTiming]:
        """
        Add keyword tag to word timings that match vocabulary words.
        Returns the same list (mutated in place).
        """
        kw_set = {k.lower() for k in keywords}
        for wt in timings:
            clean = wt.word.lower().strip(".,!?;:")
            if clean in kw_set:
                # Mark keyword — convention: prefix with "*"
                wt.word = f"*{wt.word.strip()}"
        return timings
