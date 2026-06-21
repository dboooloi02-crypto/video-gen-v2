"""
main.py — CLI entry point for the English Learning Video Generator v2.

Usage examples
──────────────
  # Full AI pipeline (requires LLM_API_KEY env var)
  python main.py --topic "在便利店偶遇朋友"

  # Choose template
  python main.py --topic "职场英语" --template tiktok
  python main.py --topic "日常对话" --template podcast

  # No API key? Use built-in demo
  python main.py --mode demo

  # Load pre-written JSON script
  python main.py --mode script --input my_script.json --template english

  # Batch generate from JSON list
  python main.py --mode batch --input batch_jobs.json

  # List available templates
  python main.py --list-templates

Environment variables
─────────────────────
  LLM_API_KEY    ZhipuAI / OpenAI key
  LLM_BASE_URL   API base URL  (default: ZhipuAI)
  LLM_MODEL      Model name    (default: glm-4-flash)
  WHISPER_MODEL  tiny/base/small/medium/large-v3  (default: base)

Batch JSON format
─────────────────
  [
    {"topic": "便利店偶遇", "template": "english_learning", "voice": "en"},
    {"topic": "职场沟通",   "template": "tiktok",           "voice": "en-m"},
    ...
  ]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC  = ROOT / "src"
for p in (str(ROOT), str(SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from config import DEFAULT_TEMPLATE
from pipeline import Pipeline, generate, batch
from templates import list_templates


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="English Learning Video Generator v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    p.add_argument(
        "--topic", "-t",
        type=str,
        help="Dialogue topic for AI generation (e.g. '在便利店偶遇朋友')",
    )
    p.add_argument(
        "--template", "-T",
        type=str,
        default=DEFAULT_TEMPLATE,
        help="Template name: english_learning | podcast | tiktok  (default: %(default)s)",
    )
    p.add_argument(
        "--voice", "-v",
        type=str,
        default="en",
        help="TTS voice key: en | en-m | teacher | zh | zh-m  (default: %(default)s)",
    )
    p.add_argument(
        "--output", "-o",
        type=str,
        default="",
        help="Output filename (saved in output/).  Auto-generated if omitted.",
    )
    p.add_argument(
        "--mode", "-m",
        choices=["ai","demo","script","batch","mixed","mixed-demo","mixed-multi"],
        default="ai",
        help="Generation mode (default: ai)",
    )
    p.add_argument(
        "--input", "-i",
        type=str,
        default="",
        help="Input JSON file (required for mode=script / mode=batch)",
    )
    p.add_argument(
        "--list-templates",
        action="store_true",
        help="Print available template names and exit",
    )
    return p


def main():
    parser = build_parser()
    args   = parser.parse_args()

    # ─ List templates ─────────────────────────────────────────────────────────
    # ── Mixed inline modes ────────────────────────────────────────────────────
    if args.mode == "mixed-demo":
        from pipeline import MixedPipeline
        MixedPipeline().run(MIXED_DEMO_SINGLE, "mixed_demo_single.mp4")
        return

    if args.mode == "mixed-multi":
        from pipeline import MixedPipeline
        MixedPipeline().run(MIXED_DEMO_MULTI, "mixed_demo_multi.mp4")
        return

    if args.mode == "mixed":
        if not args.input:
            build_parser().error("--input <json file> required for mode=mixed")
        import json
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        from pipeline import MixedPipeline
        MixedPipeline(
            zh_voice=args.voice if args.voice in ("zh","zh-m") else "zh",
            en_voice=args.voice if args.voice in ("en","en-m","teacher") else "en",
        ).run(data, args.output)
        return

    if args.list_templates:
        print("\nAvailable templates:")
        for name in list_templates():
            print(f"  {name}")
        return

    # ─ Mode: demo ─────────────────────────────────────────────────────────────
    if args.mode == "demo":
        out = args.output or "demo.mp4"
        Pipeline(args.template, args.voice).run_demo(out)
        return

    # ─ Mode: script (pre-written JSON) ────────────────────────────────────────
    if args.mode == "script":
        if not args.input:
            parser.error("--input <json file> is required for mode=script")
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        Pipeline(args.template, args.voice).run_script(data, args.output)
        return

    # ─ Mode: batch ────────────────────────────────────────────────────────────
    if args.mode == "batch":
        if not args.input:
            parser.error("--input <json file> is required for mode=batch")
        jobs = json.loads(Path(args.input).read_text(encoding="utf-8"))
        results = batch(jobs)
        print(f"\n✅  {len(results)}/{len(jobs)} videos generated")
        return

    # ─ Mode: ai (default) ─────────────────────────────────────────────────────
    if not args.topic:
        # Interactive prompt if --topic not given
        args.topic = input("\n📌  Enter topic (e.g. 在便利店偶遇朋友): ").strip()
    if not args.topic:
        parser.error("--topic is required for mode=ai")

    generate(
        topic=args.topic,
        template=args.template,
        output_name=args.output,
        voice=args.voice,
    )


if __name__ == "__main__":
    main()


# ── Mixed demo data ────────────────────────────────────────────────────────────

MIXED_DEMO_SINGLE = {
    "text": "fix，如果这次launch再出error，你全年的bonus肯定泡汤！",
    "words": [
        {"word": "fix",    "pos": "v.",    "meaning": "修复"},
        {"word": "launch", "pos": "n./v.", "meaning": "上线"},
        {"word": "error",  "pos": "n.",    "meaning": "错误"},
        {"word": "bonus",  "pos": "n.",    "meaning": "奖金"},
    ],
}

MIXED_DEMO_MULTI = {
    "paragraphs": [
        {
            "text":  "fix，如果这次launch再出error，你全年的bonus肯定泡汤！",
            "slide": "1/2",
            "words": [
                {"word": "fix",    "pos": "v.",    "meaning": "修复"},
                {"word": "launch", "pos": "n./v.", "meaning": "上线"},
                {"word": "error",  "pos": "n.",    "meaning": "错误"},
                {"word": "bonus",  "pos": "n.",    "meaning": "奖金"},
            ],
        },
        {
            "text":  "我要看到一个concrete plan，否则你自己跟board解释，"
                     "这里没人欠你opportunity！",
            "slide": "2/2",
            "words": [
                {"word": "concrete plan", "pos": "phrase", "meaning": "具体方案"},
                {"word": "board",         "pos": "n.",     "meaning": "董事会"},
                {"word": "opportunity",   "pos": "n.",     "meaning": "机会"},
            ],
        },
    ],
}
