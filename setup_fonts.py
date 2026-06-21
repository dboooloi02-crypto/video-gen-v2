"""
setup_fonts.py — Download required fonts and verify environment.

Run once after cloning:
    python setup_fonts.py

Downloads:
    BebasNeue-Regular.ttf  → cinematic English display font
    Montserrat-Bold.ttf    → fallback English bold font

Chinese font: manual download required (see instructions printed below).
"""

import os
import sys
import urllib.request
from pathlib import Path

FONTS_DIR = Path(__file__).parent / "fonts"
FONTS_DIR.mkdir(exist_ok=True)

AUTO_FONTS = {
    "BebasNeue-Regular.ttf": (
        "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf"
    ),
    "Montserrat-Bold.ttf": (
        "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf"
    ),
}

CJK_PATHS = [
    "/System/Library/Fonts/PingFang.ttc",           # macOS
    "C:/Windows/Fonts/msyhbd.ttc",                  # Windows
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]

CJK_MANUAL = """
╔══════════════════════════════════════════════════════╗
║          Chinese (CJK) Font — Manual Setup           ║
╠══════════════════════════════════════════════════════╣
║  Option A — Google Fonts                             ║
║    1. https://fonts.google.com/noto/specimen/        ║
║       Noto+Sans+SC                                   ║
║    2. Download → unzip                               ║
║    3. Copy NotoSansSC-Bold.ttf → fonts/              ║
║                                                      ║
║  Option B — Linux one-liner                          ║
║    sudo apt install fonts-noto-cjk                   ║
║    (auto-detected, no copy needed)                   ║
║                                                      ║
║  Option C — macOS / Windows                          ║
║    System font auto-detected (no action needed)      ║
╚══════════════════════════════════════════════════════╝
"""


def download(name: str, url: str) -> bool:
    dest = FONTS_DIR / name
    if dest.exists():
        print(f"  ✓  {name}  (already present)")
        return True
    print(f"  ↓  {name} … ", end="", flush=True)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        dest.write_bytes(data)
        print(f"✓  ({len(data) // 1024} KB)")
        return True
    except Exception as exc:
        print(f"✗  ({exc})")
        return False


def check_cjk() -> str | None:
    # Check local fonts/ first
    for name in ("NotoSansSC-Bold.ttf", "NotoSansSCBold.ttf",
                 "NotoSansCJK-Bold.ttc"):
        p = FONTS_DIR / name
        if p.exists():
            return str(p)
    # Check system paths
    for p in CJK_PATHS:
        if os.path.exists(p):
            return p
    return None


def check_deps():
    required = {
        "moviepy":   "pip install moviepy",
        "PIL":       "pip install Pillow",
        "numpy":     "pip install numpy",
        "edge_tts":  "pip install edge-tts",
        "openai":    "pip install openai",
    }
    print("\nDependency check:")
    all_ok = True
    for mod, install_cmd in required.items():
        try:
            __import__(mod)
            print(f"  ✓  {mod}")
        except ImportError:
            print(f"  ✗  {mod}  →  {install_cmd}")
            all_ok = False
    return all_ok


if __name__ == "__main__":
    print("=" * 56)
    print("  English Learning Video Generator — Setup")
    print("=" * 56)
    print(f"\nFonts directory: {FONTS_DIR}\n")

    # 1. Auto-download English fonts
    print("English fonts:")
    for name, url in AUTO_FONTS.items():
        download(name, url)

    # 2. CJK font check
    print("\nChinese font:")
    cjk_path = check_cjk()
    if cjk_path:
        print(f"  ✓  Found: {cjk_path}")
    else:
        print("  ✗  Not found")
        print(CJK_MANUAL)

    # 3. Python dependency check
    check_deps()

    print("\n" + "─" * 56)
    if cjk_path:
        print("  ✅  Ready!  Run: python main.py --mode demo")
    else:
        print("  ⚠   Ready (English only). Add CJK font for Chinese text.")
        print("      Then run: python main.py --mode demo")
    print("─" * 56 + "\n")
