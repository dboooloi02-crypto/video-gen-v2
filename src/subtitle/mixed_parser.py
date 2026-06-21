"""
src/subtitle/mixed_parser.py

Parses mixed Chinese-English text into typed tokens,
then computes an inline word-wrap layout for rendering.

Input:
    text  = "fix，如果这次launch再出error，你全年的bonus肯定泡汤！"
    words = [{"word":"fix","pos":"v.","meaning":"修复"}, ...]

Output:
    tokens  = List[TextToken]
    layout  = List[Line]   (list of lines, each line = list of (TextToken, x_offset))
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class TextToken:
    text:       str
    is_keyword: bool   = False
    pos:        str    = ""      # "n." / "v." / "n./v." / "phrase"
    meaning:    str    = ""      # Chinese meaning
    lang:       str    = "zh"   # "zh" or "en"
    kw_idx:     int    = -1     # sequential index among keywords in this paragraph


LineToken  = Tuple[TextToken, int]     # (token, x_offset in px)
Layout     = List[List[LineToken]]     # list of lines


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_mixed_text(text: str, words: list) -> List[TextToken]:
    """
    Split mixed Chinese-English string into ordered TextToken list.

    Longer keyword phrases are matched first so "concrete plan" wins over "plan".
    """
    kw_map = {w["word"].lower(): w for w in words}
    kw_sorted = sorted(kw_map.keys(), key=len, reverse=True)

    tokens: List[TextToken] = []
    remaining = text
    kw_counter = 0

    while remaining:
        # Try to match a keyword at current head (case-insensitive)
        matched = next(
            (kw for kw in kw_sorted if remaining.lower().startswith(kw)),
            None,
        )
        if matched:
            kdef = kw_map[matched]
            tokens.append(TextToken(
                text=remaining[: len(matched)],
                is_keyword=True,
                pos=kdef.get("pos", ""),
                meaning=kdef.get("meaning", ""),
                lang="en",
                kw_idx=kw_counter,
            ))
            remaining = remaining[len(matched):]
            kw_counter += 1
        else:
            # Find the start of the next keyword
            next_pos = len(remaining)
            for kw in kw_sorted:
                idx = remaining.lower().find(kw, 1)   # start at 1 to skip head
                if idx != -1 and idx < next_pos:
                    next_pos = idx
            chunk = remaining[:next_pos]
            if chunk:
                tokens.append(TextToken(text=chunk, is_keyword=False, lang="zh"))
            remaining = remaining[next_pos:]

    return tokens


# ── Layout engine ─────────────────────────────────────────────────────────────

def compute_layout(
    tokens:        List[TextToken],
    content_width: int,
    main_font,                   # PIL font for Chinese main text
    en_font,                     # PIL font for English keywords
    kw_pad_x:      int = 13,     # horizontal padding inside keyword box
    kw_gap:        int = 6,      # extra gap after keyword box
) -> Layout:
    """
    Greedy line-wrap layout.
    Chinese text is split at character level; keywords are atomic.

    Returns: List[Line] where Line = List[(TextToken, x_offset)]
    """
    _dd = ImageDraw.Draw(Image.new("RGBA", (2, 2)))

    def _w(text: str, font) -> int:
        try:
            bb = _dd.textbbox((0, 0), text, font=font)
            return bb[2] - bb[0]
        except AttributeError:
            return _dd.textsize(text, font=font)[0]

    lines: Layout = []
    cur_line: List[LineToken] = []
    cur_x: int = 0

    def _flush():
        nonlocal cur_line, cur_x
        if cur_line:
            lines.append(cur_line)
        cur_line = []
        cur_x = 0

    for token in tokens:
        if token.is_keyword:
            kw_w = _w(token.text, en_font) + kw_pad_x * 2 + kw_gap
            if cur_x + kw_w > content_width and cur_line:
                _flush()
            cur_line.append((token, cur_x))
            cur_x += kw_w
        else:
            # Split CJK text character by character
            for char in token.text:
                cw = _w(char, main_font)
                if cur_x + cw > content_width and cur_line:
                    _flush()
                char_tok = TextToken(text=char, is_keyword=False, lang="zh")
                cur_line.append((char_tok, cur_x))
                cur_x += cw

    _flush()
    return lines


# ── Keyword timing estimator ──────────────────────────────────────────────────

def estimate_keyword_beats(
    tokens:         List[TextToken],
    total_duration: float,
) -> list:
    """
    When no TTS word timing is available, distribute keyword timing
    proportionally across the scene duration.

    Returns list of dicts: [{"start": float, "end": float}, ...]
    indexed by kw_idx.
    """
    kws = [t for t in tokens if t.is_keyword]
    if not kws:
        return []

    slot = total_duration / (len(kws) + 1)
    beats = []
    for i in range(len(kws)):
        start = slot * (i + 0.5)
        beats.append({"start": start, "end": start + slot * 0.8})
    return beats
