"""
pipeline.py
Full end-to-end pipeline orchestrator.

Flow:
  Topic (str)
    ↓ DialogueGenerator      AI → DialogueScript
    ↓ EdgeTTSEngine          TTS → AudioSegments (with word timings)
    ↓ SubtitleBuilder        Build → SceneTimeline
    ↓ FrameRenderer + Template  Render → per-frame np.ndarray
    ↓ VideoExporter          Export → MP4

Modes:
  run_topic(topic)   — full AI pipeline
  run_script(data)   — skip AI, use pre-built JSON script
  run_demo()         — built-in demo (no API key needed)
"""

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent
SRC  = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from config import (
    OUTPUT_DIR, DEFAULT_TEMPLATE,
    TTS_VOICE_MAP,
)
from generator.dialogue_generator import DialogueGenerator, DialogueScript
from tts.edge_tts_engine          import EdgeTTSEngine
from subtitle.subtitle_builder    import SubtitleBuilder, SceneTimeline
from renderer.frame_renderer      import FrameRenderer
from renderer.cache               import cache_stats
from templates                    import get_template, list_templates
from export.video_exporter        import VideoExporter


# ── Pipeline ──────────────────────────────────────────────────────────────────

class Pipeline:
    """
    Orchestrates the full video generation flow.

    Args:
        template_name — one of: english_learning, podcast, tiktok
        voice_key     — TTS voice key from config.TTS_VOICE_MAP
    """

    def __init__(
        self,
        template_name: str = DEFAULT_TEMPLATE,
        voice_key:     str = "en",
    ):
        self.template_name = template_name
        self.voice_key     = voice_key

        self._gen      = DialogueGenerator()
        self._tts      = EdgeTTSEngine(voice_key=voice_key)
        self._exporter = VideoExporter()

    # ── Public entry points ───────────────────────────────────────────────────

    def run_topic(self, topic: str, output_name: str = "") -> str:
        """Full pipeline: topic → MP4."""
        print(f"\n{'═'*54}")
        print(f"  🎬  {topic}")
        print(f"{'═'*54}")
        t0 = time.time()

        # Step 1 — AI dialogue generation
        script = self._gen.generate(topic)
        self._print_script(script)

        # Step 2-5 — TTS, subtitle, render, export
        return self._run_script(script, output_name, t0)

    def run_script(self, data: dict, output_name: str = "") -> str:
        """Skip AI — use pre-built JSON script dict."""
        from generator.dialogue_generator import DialogueLine, KeywordDef
        script = DialogueScript(
            title=data.get("title", "video"),
            topic=data.get("title", ""),
            dialogue=[DialogueLine(**l) for l in data.get("dialogue", [])],
            keywords=[KeywordDef(**k) for k in data.get("keywords", [])],
        )
        self._print_script(script)
        return self._run_script(script, output_name, time.time())

    def run_demo(self, output_name: str = "demo.mp4") -> str:
        """Built-in demo — no API key required."""
        script = self._gen._demo_script("便利店偶遇朋友")
        return self._run_script(script, output_name, time.time())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_script(
        self,
        script:      DialogueScript,
        output_name: str,
        t0:          float,
    ) -> str:
        # Step 2 — TTS
        print(f"\n📢  Synthesising audio ({len(script.dialogue)} lines) …")
        audio_dir = OUTPUT_DIR / "audio" / _safe(script.title)
        audio_segs = self._tts.synthesise(
            script.dialogue,
            out_dir=audio_dir,
        )

        # Step 3 — Build scene timeline
        print(f"\n📋  Building subtitle timeline …")
        timeline = SubtitleBuilder.from_audio_segments(
            dialogue_lines=script.dialogue,
            audio_segments=audio_segs,
            keyword_defs=script.keywords,
        )
        print(f"    {len(timeline)} scenes  |  "
              f"{timeline.total_duration:.1f}s total")

        # Step 4 — Renderer + template
        print(f"\n🎨  Rendering with template '{self.template_name}' …")
        template      = get_template(self.template_name)
        frame_renderer = FrameRenderer(template)
        make_frame, intro = frame_renderer.make_frame_fn(timeline)

        # Step 5 — Export
        if not output_name:
            output_name = _safe(script.title) + ".mp4"
        output_path = str(OUTPUT_DIR / output_name)

        print(f"\n🎞  Exporting → {output_path}")
        audio_paths = [s.audio_path for s in audio_segs]
        self._exporter.export(
            make_frame=make_frame,
            total_duration=timeline.total_duration,
            output_path=output_path,
            audio_paths=audio_paths,
        )

        elapsed  = time.time() - t0
        size_mb  = Path(output_path).stat().st_size / 1024 / 1024
        print(f"\n{'─'*54}")
        print(f"  ✅  Done in {elapsed:.1f}s  |  {size_mb:.1f} MB")
        print(f"  📁  {output_path}")
        print(f"\n{cache_stats()}")
        return output_path

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _print_script(script: DialogueScript):
        print(f"\n  Title   : {script.title}")
        print(f"  Lines   : {len(script.dialogue)}")
        print(f"  Keywords: {', '.join(k.word for k in script.keywords)}")
        print()
        for i, ln in enumerate(script.dialogue, 1):
            print(f"  {ln.speaker}[{i:02d}] {ln.zh}")
            print(f"         {ln.en}")
        print()


def _safe(s: str) -> str:
    """Sanitise string for use as filename."""
    import re
    return re.sub(r"[^\w\-]", "_", s)[:40]


# ── Convenience shortcuts ─────────────────────────────────────────────────────

def generate(
    topic: str,
    template: str = DEFAULT_TEMPLATE,
    output_name: str = "",
    voice: str = "en",
) -> str:
    """One-line API: generate(topic) → MP4 path."""
    return Pipeline(template, voice).run_topic(topic, output_name)


def batch(jobs: list) -> list:
    """
    Batch generate.
    Each job: {"topic": ..., "template": ..., "output_name": ..., "voice": ...}
    """
    results = []
    for i, job in enumerate(jobs, 1):
        print(f"\n[{i}/{len(jobs)}]", end=" ")
        try:
            path = generate(
                topic=job["topic"],
                template=job.get("template", DEFAULT_TEMPLATE),
                output_name=job.get("output_name", ""),
                voice=job.get("voice", "en"),
            )
            results.append(path)
        except Exception as exc:
            print(f"❌  {exc}")
    return results


# ── Mixed inline pipeline ──────────────────────────────────────────────────────

class MixedPipeline:
    """
    Full pipeline for the mixed_inline template.

    Input JSON formats:

    Single paragraph (simple):
        {
          "text": "fix，如果这次launch再出error，你全年的bonus肯定泡汤！",
          "words": [
            {"word": "fix",    "pos": "v.",    "meaning": "修复"},
            {"word": "launch", "pos": "n./v.", "meaning": "上线"},
            {"word": "bonus",  "pos": "n.",    "meaning": "奖金"}
          ]
        }

    Multi-paragraph:
        {
          "paragraphs": [
            {"text": "...", "words": [...], "slide": "1/2"},
            {"text": "...", "words": [...], "slide": "2/2"}
          ]
        }

    Usage:
        MixedPipeline().run(data, output_name="boss_scene.mp4")
    """

    def __init__(self, zh_voice: str = "zh", en_voice: str = "en"):
        self.zh_voice  = zh_voice
        self.en_voice  = en_voice
        self._exporter = VideoExporter()

    def run(self, data: dict, output_name: str = "") -> str:
        import time
        from subtitle.mixed_parser import parse_mixed_text
        from tts.mixed_tts import MixedTTSEngine
        from subtitle.subtitle_builder import SubtitleBuilder
        from renderer.frame_renderer import FrameRenderer
        from renderer.cache import cache_stats

        t0 = time.time()

        # ── Normalise to paragraph list ────────────────────────────────────
        if "text" in data:
            paragraphs = [{"text": data["text"],
                           "words": data.get("words", []),
                           "slide": "1/1"}]
        else:
            paragraphs = data.get("paragraphs", [])

        total = len(paragraphs)
        for i, p in enumerate(paragraphs):
            p.setdefault("slide", f"{i+1}/{total}")

        print(f"\n{'═'*56}")
        print(f"  🎬  mixed_inline  ·  {total} paragraph(s)")
        print(f"{'═'*56}")

        # ── Parse tokens ────────────────────────────────────────────────────
        for para in paragraphs:
            para["_tokens"] = parse_mixed_text(
                para["text"], para.get("words", [])
            )
            kws = [t.text for t in para["_tokens"] if t.is_keyword]
            print(f"  [{para['slide']}] keywords: {kws}")

        # ── TTS (mixed zh+en) ────────────────────────────────────────────
        print(f"\n📢  Generating mixed TTS …")
        engine   = MixedTTSEngine(zh_voice=self.zh_voice, en_voice=self.en_voice)
        audio_dir = OUTPUT_DIR / "audio" / "mixed"
        engine.synthesise_all(paragraphs, audio_dir)

        # ── Build timeline (content_w auto-detected from template size) ───────
        print(f"\n📋  Building timeline …")
        tpl_tmp = get_template("mixed_inline")
        tw, th  = getattr(tpl_tmp, "output_size", (1080, 1920))
        # mixed_inline layout constants: card margin=46~50px, CPAX=56~64px
        cw_map  = {1920: 1700, 1080: 860}
        content_w = cw_map.get(tw, tw - 220)
        timeline = SubtitleBuilder.from_mixed_paragraphs_with_beats(
            paragraphs, [], content_w=content_w
        )
        total_dur = timeline.total_duration
        print(f"    {len(timeline)} scene(s)  ·  {total_dur:.1f}s  ·  content_w={content_w}px")

        # ── Render ────────────────────────────────────────────────────────
        print(f"\n🎨  Rendering mixed_inline …")
        tpl = tpl_tmp
        fr  = FrameRenderer(tpl)
        make_frame, _ = fr.make_frame_fn(timeline)

        # ── Export ────────────────────────────────────────────────────────
        if not output_name:
            import re
            slug = re.sub(r"[^\w]", "_", paragraphs[0]["text"][:20])
            output_name = f"mixed_{slug}.mp4"

        out_path    = str(OUTPUT_DIR / output_name)
        audio_paths = [p["_audio"] for p in paragraphs if p.get("_audio")]

        print(f"\n🎞  Exporting → {out_path}")
        self._exporter.export(
            make_frame=make_frame,
            total_duration=total_dur,
            output_path=out_path,
            audio_paths=audio_paths,
        )

        elapsed = time.time() - t0
        size_mb = Path(out_path).stat().st_size / 1024 / 1024
        print(f"\n{'─'*56}")
        print(f"  ✅  Done  {elapsed:.1f}s  ·  {size_mb:.1f} MB")
        print(f"  📁  {out_path}")
        print(f"\n{cache_stats()}")
        return out_path
