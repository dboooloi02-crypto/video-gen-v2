"""
src/subtitle/subtitle_builder.py
Converts TTS AudioSegments + KeywordDefs → List[Scene] for rendering.

Input  (pipeline feeds these):
    AudioSegment  — one per dialogue line, has word_timings
    KeywordDef    — vocabulary words to highlight

Output:
    List[Scene]   — one per dialogue line, with timing + keyword info
"""

import bisect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Keyword:
    word:     str
    meaning:  str
    language: str = "en"


@dataclass
class WordBeat:
    """A single word with its display-window timing (global seconds)."""
    word:       str
    start:      float
    end:        float
    is_keyword: bool = False


@dataclass
class Scene:
    """
    One visual unit rendered to the screen.

    Fields:
        zh          — Chinese text
        en          — English subtitle
        keyword     — optional highlighted vocabulary word
        speaker     — speaker label (e.g. "A" or "B")
        start       — global start time in video (seconds)
        duration    — display duration (seconds)
        word_beats  — per-word timing for word-karaoke animation (future)

    Future:
        tts_audio   : bytes          — raw PCM segment for this scene
        word_timings: List[WordBeat] — word-level timing from Whisper
    """
    zh:         str                    = ""
    en:         str                    = ""
    keyword:    Optional[Keyword]       = None
    speaker:    str                    = ""
    start:      float                  = 0.0
    duration:   float                  = 3.5
    word_beats: List[WordBeat]         = field(default_factory=list)
    meta:       dict                   = field(default_factory=dict)   # template-specific data

    @property
    def end(self) -> float:
        return self.start + self.duration

    meta:       dict                   = field(default_factory=dict)   # template-specific data

    @property
    def has_kw(self) -> bool:
        return self.keyword is not None and bool(self.keyword.word)


# ── Timeline index ────────────────────────────────────────────────────────────

class SceneTimeline:
    """
    O(log n) scene lookup using bisect — replaces the O(n) for-loop.

    Usage:
        tl = SceneTimeline(scenes)
        current_scene = tl.at(t=2.35)
    """

    def __init__(self, scenes: List[Scene]):
        self._scenes = scenes
        # Sorted list of start times for bisect
        self._starts: List[float] = [s.start for s in scenes]

    def at(self, t: float) -> Optional[Scene]:
        if not self._starts:
            return None
        idx = bisect.bisect_right(self._starts, t) - 1
        if idx >= 0:
            scene = self._scenes[idx]
            if t < scene.end:
                return scene
        return None

    @property
    def total_duration(self) -> float:
        if not self._scenes:
            return 0.0
        s = self._scenes[-1]
        return s.start + s.duration

    def __len__(self) -> int:
        return len(self._scenes)

    def __iter__(self):
        return iter(self._scenes)


# ── Builder ───────────────────────────────────────────────────────────────────

class SubtitleBuilder:
    """
    Converts pipeline data → Scene list.

    Supports two input modes:
        1. from_audio_segments()  — uses Edge TTS word timings
        2. from_whisper()         — uses Whisper word timings (higher accuracy)
        3. from_dialogue()        — estimate timing from character count (no audio)
    """

    MIN_SCENE_DUR = 2.0    # seconds — minimum display time per scene
    PAUSE_BETWEEN = 0.15   # gap between consecutive scenes

    # ── Mode 1: Edge TTS word timings ─────────────────────────────────────────

    @classmethod
    def from_audio_segments(
        cls,
        dialogue_lines,           # List[DialogueLine]
        audio_segments,           # List[AudioSegment] from EdgeTTSEngine
        keyword_defs,             # List[KeywordDef]
    ) -> SceneTimeline:
        """
        Build scenes using Edge TTS word boundary timing.
        Each dialogue line becomes one Scene; duration = audio segment duration.
        """
        kw_lookup = {k.word.lower(): k for k in keyword_defs}
        scenes: List[Scene] = []
        t = 0.0

        for line, seg in zip(dialogue_lines, audio_segments):
            # Find first keyword in this line
            kw = cls._find_keyword(line.en, kw_lookup)

            # Build word beats from TTS timings
            beats = cls._make_beats(seg.word_timings, kw, t)

            # Scene duration = actual audio duration + small pause
            dur = max(cls.MIN_SCENE_DUR, seg.duration + cls.PAUSE_BETWEEN)

            scenes.append(Scene(
                zh=line.zh,
                en=line.en,
                keyword=kw,
                speaker=line.speaker,
                start=round(t, 3),
                duration=round(dur, 3),
                word_beats=beats,
            ))
            t += dur

        return SceneTimeline(scenes)

    # ── Mode 2: Whisper word timings ──────────────────────────────────────────

    @classmethod
    def from_whisper(
        cls,
        dialogue_lines,
        global_word_timings,      # List[WordTiming] from WhisperTimeline.align()
        segment_boundaries,       # List[float] — start time of each line
        keyword_defs,
    ) -> SceneTimeline:
        """
        Build scenes using Whisper word-level timing for maximum accuracy.
        """
        kw_lookup = {k.word.lower(): k for k in keyword_defs}
        scenes: List[Scene] = []

        for i, (line, seg_start) in enumerate(zip(dialogue_lines, segment_boundaries)):
            # Collect words belonging to this segment
            seg_end = (segment_boundaries[i + 1]
                       if i + 1 < len(segment_boundaries)
                       else seg_start + 99)

            seg_words = [
                w for w in global_word_timings
                if seg_start <= w.start < seg_end
            ]

            kw = cls._find_keyword(line.en, kw_lookup)
            beats = [
                WordBeat(
                    word=w.word,
                    start=w.start,
                    end=w.end,
                    is_keyword=(kw is not None and
                                w.word.lower().strip(".,!?") == kw.word.lower()),
                )
                for w in seg_words
            ]

            dur = (seg_words[-1].end - seg_start + cls.PAUSE_BETWEEN
                   if seg_words else cls.MIN_SCENE_DUR)
            dur = max(cls.MIN_SCENE_DUR, dur)

            scenes.append(Scene(
                zh=line.zh,
                en=line.en,
                keyword=kw,
                speaker=line.speaker,
                start=round(seg_start, 3),
                duration=round(dur, 3),
                word_beats=beats,
            ))

        return SceneTimeline(scenes)

    # ── Mode 3: Estimated timing (no audio) ───────────────────────────────────

    @classmethod
    def from_dialogue(cls, dialogue_lines, keyword_defs) -> SceneTimeline:
        """
        Estimate scene timing from character/word count — no audio required.
        Useful for quick preview before TTS is run.
        """
        kw_lookup = {k.word.lower(): k for k in keyword_defs}
        scenes: List[Scene] = []
        t = 0.0

        for line in dialogue_lines:
            kw  = cls._find_keyword(line.en, kw_lookup)
            dur = max(cls.MIN_SCENE_DUR, len(line.en.split()) * 0.35 + 0.5)
            dur = min(dur, 7.0)

            scenes.append(Scene(
                zh=line.zh,
                en=line.en,
                keyword=kw,
                speaker=line.speaker,
                start=round(t, 3),
                duration=round(dur, 3),
            ))
            t += dur

        return SceneTimeline(scenes)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _find_keyword(en_text: str, kw_lookup: dict) -> Optional[Keyword]:
        """Return the first keyword found in English text."""
        text_lower = en_text.lower()
        for kw_str, kdef in kw_lookup.items():
            if kw_str in text_lower:
                return Keyword(
                    word=kdef.word.upper(),
                    meaning=kdef.meaning,
                    language="en",
                )
        return None

    @staticmethod
    def _make_beats(
        word_timings,             # List[WordTiming] from EdgeTTSEngine
        kw: Optional[Keyword],
        global_offset: float,
    ) -> List[WordBeat]:
        kw_str = kw.word.lower() if kw else ""
        beats = []
        for wt in word_timings:
            is_kw = kw_str and wt.word.lower().strip(".,!?") == kw_str
            beats.append(WordBeat(
                word=wt.word,
                start=round(wt.start + global_offset, 4),
                end=round(wt.end   + global_offset, 4),
                is_keyword=is_kw,
            ))
        return beats

    # ── Mode 4: Mixed inline paragraph ────────────────────────────────────────

    @classmethod
    def from_mixed_paragraphs(
        cls,
        paragraphs: list,       # List[dict] each: {text, words, duration, slide}
        keyword_defs: list,     # List[KeywordDef] for the bottom panel
        content_w: int = 860,   # layout content width
    ) -> "SceneTimeline":
        """
        Build scenes for the mixed_inline template.

        Each paragraph dict:
            text      : str   — mixed Chinese-English text
            words     : list  — [{"word","pos","meaning"}, ...]
            duration  : float — scene duration in seconds
            slide     : str   — slide indicator e.g. "1/2"
            audio_seg : optional AudioSegment for timing

        Returns SceneTimeline where each scene has:
            meta["layout"]        — pre-computed line layout
            meta["all_keywords"]  — list of keyword dicts for bottom panel
            meta["slide_info"]    — slide indicator string
            word_beats            — keyword beat timings (WordBeat list)
        """
        import sys
        from pathlib import Path
        _ROOT = Path(__file__).parent.parent.parent
        if str(_ROOT) not in sys.path:
            sys.path.insert(0, str(_ROOT))

        from subtitle.mixed_parser import (
            parse_mixed_text,
            compute_layout,
            estimate_keyword_beats,
        )
        from renderer.cache import get_font_manager

        fm = get_font_manager()
        # Content width mirrors mixed_inline template constants
        # content_w is passed as parameter — callers set it per-template   # 860px

        scenes: List[Scene] = []
        t = 0.0

        # Build global keyword list (for bottom panel) from all paragraphs
        global_kws = []
        global_idx_of: dict = {}
        seen_words: set = set()
        for para in paragraphs:
            for w in para.get("words", []):
                wl = w["word"].lower()
                if wl not in seen_words:
                    seen_words.add(wl)
                    global_idx_of[wl] = len(global_kws)
                    global_kws.append({
                        "word":    w["word"].upper(),
                        "meaning": w.get("meaning", ""),
                        "example": w.get("example", ""),
                        "pos":     w.get("pos", ""),
                    })

        for para in paragraphs:
            text     = para.get("text", "")
            words    = para.get("words", [])
            duration = float(para.get("duration", 6.0))
            slide    = para.get("slide", "")
            audio    = para.get("audio_seg")

            tokens = parse_mixed_text(text, words)

            main_font = fm.get(60, "zh")
            en_font   = fm.get(60, "en")
            layout = compute_layout(tokens, content_w, main_font, en_font)

            # Build word_beats from audio timing or estimate.
            # IMPORTANT: beats are stored SCENE-LOCAL (0..duration), matching
            # the local_t that FrameRenderer passes to render_layer — do NOT
            # add the global offset `t` here.
            kw_tokens = [tok for tok in tokens if tok.is_keyword]
            beats: List[WordBeat] = []

            if audio and audio.word_timings:
                for kw_tok in kw_tokens:
                    match = next(
                        (wt for wt in audio.word_timings
                         if wt.word.lower() == kw_tok.text.lower()),
                        None,
                    )
                    if match:
                        beats.append(WordBeat(
                            word=kw_tok.text,
                            start=round(match.start, 3),
                            end=round(match.end,   3),
                        ))
            else:
                for b in estimate_keyword_beats(tokens, duration):
                    beats.append(WordBeat(
                        word="",
                        start=round(b["start"], 3),
                        end=round(b["end"],   3),
                    ))

            # Map paragraph-local kw_idx → index in the GLOBAL keyword list
            kw_global_map = [
                global_idx_of.get(tok.text.lower(), 0) for tok in kw_tokens
            ]

            meta = {
                "layout":         layout,
                "all_keywords":   global_kws,
                "total_keywords": len(global_kws),
                "slide_info":     slide,
                "para_tokens":    tokens,
                "kw_global_map":  kw_global_map,
            }

            scene = Scene(
                zh=text,
                start=round(t, 3),
                duration=round(duration, 3),
                word_beats=beats,
                meta=meta,
            )
            scenes.append(scene)
            t += duration

        return SceneTimeline(scenes)

    # ── Mode 5: Mixed paragraphs with pre-computed TTS beats ──────────────────

    @classmethod
    def from_mixed_paragraphs_with_beats(
        cls,
        paragraphs: list,     # each para has _tokens, _kw_beats, _duration
        keyword_defs: list,
        content_w: int = 860, # content width in px (860 for 9:16, 1700 for 16:9)
    ) -> "SceneTimeline":
        """
        Like from_mixed_paragraphs() but uses real TTS timing from _kw_beats.
        Call after MixedTTSEngine.synthesise_all().
        """
        import sys
        from pathlib import Path
        _ROOT = Path(__file__).parent.parent.parent
        if str(_ROOT) not in sys.path:
            sys.path.insert(0, str(_ROOT))

        from subtitle.mixed_parser import compute_layout
        from renderer.cache import get_font_manager

        fm        = get_font_manager()
        # content_w is passed as parameter — callers set it per-template

        # Build global keyword list (deduplicated, in first-appearance order)
        global_kws = []
        global_idx_of: dict = {}      # word_lower -> index in global_kws
        seen: set  = set()
        for para in paragraphs:
            for tok in para.get("_tokens", []):
                wl = tok.text.lower()
                if tok.is_keyword and wl not in seen:
                    seen.add(wl)
                    global_idx_of[wl] = len(global_kws)
                    global_kws.append({
                        "word":    tok.text.upper(),
                        "meaning": tok.meaning,
                        "pos":     tok.pos,
                        "example": para.get("_example_for", {}).get(tok.text, ""),
                    })

        scenes: List[Scene] = []
        t = 0.0

        for i, para in enumerate(paragraphs):
            tokens   = para.get("_tokens", [])
            kw_beats = para.get("_kw_beats", {})   # {local_kw_idx: WordBeat (GLOBAL time)}
            duration = float(para.get("_duration", para.get("duration", 4.0)))
            slide    = para.get("slide", f"{i+1}/{len(paragraphs)}")

            main_font = fm.get(60, "zh")
            en_font   = fm.get(60, "en")
            layout    = compute_layout(tokens, content_w, main_font, en_font)

            # Convert kw_beats dict → ordered list, GLOBAL time → SCENE-LOCAL time
            # (FrameRenderer always passes local_t = global_t - scene.start to
            #  render_layer, so beats stored on the Scene must be local too.)
            beats_list: List[WordBeat] = []
            for kidx in sorted(kw_beats.keys()):
                gb = kw_beats[kidx]
                beats_list.append(WordBeat(
                    word=gb.word,
                    start=round(gb.start - t, 4),
                    end=round(gb.end   - t, 4),
                ))

            # Map each paragraph-local kw_idx → index in the GLOBAL keyword list
            # (needed so the bottom panel shows the CURRENT paragraph's keywords,
            #  not whichever ones happen to sit at that index in the global list)
            kw_toks = [tok for tok in tokens if tok.is_keyword]
            kw_global_map = [
                global_idx_of.get(tok.text.lower(), 0) for tok in kw_toks
            ]

            meta = {
                "layout":         layout,
                "all_keywords":   global_kws,
                "total_keywords": len(global_kws),
                "slide_info":     slide,
                "para_tokens":    tokens,
                "kw_global_map":  kw_global_map,   # local idx → global idx
            }

            scenes.append(Scene(
                zh=para.get("text", ""),
                start=round(t, 3),
                duration=round(duration, 3),
                word_beats=beats_list,
                meta=meta,
            ))
            t += duration

        return SceneTimeline(scenes)
