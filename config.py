"""
config.py — Central configuration for the English Learning Video Generator.
All tunable parameters live here.  Override with environment variables.
"""
import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
SRC_DIR    = BASE_DIR / "src"
OUTPUT_DIR = BASE_DIR / "output"
FONTS_DIR  = BASE_DIR / "fonts"
CACHE_DIR  = BASE_DIR / "cache"

for _d in (OUTPUT_DIR, FONTS_DIR, CACHE_DIR):
    _d.mkdir(exist_ok=True)

# ── Video ─────────────────────────────────────────────────────────────────────
WIDTH  = 1080
HEIGHT = 1920
FPS    = 30

# ── LLM (OpenAI-compatible) ───────────────────────────────────────────────────
# Supports ZhipuAI GLM-4-Flash (default), OpenAI, DeepSeek, etc.
# Set via env vars or .env file
LLM_API_KEY   = os.getenv("LLM_API_KEY", os.getenv("ZHIPUAI_API_KEY", ""))
LLM_BASE_URL  = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
LLM_MODEL     = os.getenv("LLM_MODEL",    "glm-4-flash")
LLM_TEMP      = float(os.getenv("LLM_TEMPERATURE", "0.75"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))

# Dialogue generation params
DIALOGUE_MIN_TURNS = 8
DIALOGUE_MAX_TURNS = 12
KEYWORD_COUNT      = 8     # keywords to extract per dialogue

# ── TTS (Edge TTS) ────────────────────────────────────────────────────────────
TTS_RATE   = "+0%"
TTS_VOLUME = "+0%"
TTS_VOICE_MAP = {
    "zh": "zh-CN-XiaoxiaoNeural",   # Female, warm
    "zh-m": "zh-CN-YunxiNeural",    # Male
    "en": "en-US-EmmaNeural",       # Female, natural
    "en-m": "en-US-AndrewNeural",   # Male
    "teacher": "en-US-JennyNeural", # Clear teaching voice
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
}
TTS_DEFAULT_VOICE = "en"

# ── ASR (Whisper) ─────────────────────────────────────────────────────────────
# Model sizes: tiny, base, small, medium, large-v3
# tiny/base: fast, less accurate   large-v3: slow, most accurate
ASR_MODEL  = os.getenv("WHISPER_MODEL", "base")
ASR_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")   # "cpu" or "cuda"

# ── Colours (RGB) ─────────────────────────────────────────────────────────────
C_BG          = (7,   7,  11)
C_GRAD_TOP    = (13,  10,  20)
C_TEXT_ZH     = (228, 228, 228)
C_TEXT_EN     = (255, 255, 255)
C_KEYWORD     = (255, 208,  68)
C_KW_GLOW     = (255, 140,  20)
C_SEPARATOR   = ( 55,  55,  70)
C_SPEAKER_A   = (100, 180, 255)   # Speaker A — blue
C_SPEAKER_B   = (255, 140, 100)   # Speaker B — coral
C_HINT_BG     = ( 14,  14,  22)
C_HINT_KW     = (255, 208,  68)
C_HINT_MN     = (148, 148, 168)
C_WAVEFORM    = (100, 180, 255)

# ── Font sizes (px) ───────────────────────────────────────────────────────────
FS_ZH       = 72
FS_EN       = 60
FS_KW       = 96
FS_SPEAKER  = 44
FS_HINT_KW  = 52
FS_HINT_MN  = 40

# ── Layout ────────────────────────────────────────────────────────────────────
LINE_GAP      = 22
SEP_LENGTH    = 64
SEP_H         = 10
HINT_MARGIN_X = 50
HINT_H        = 135
HINT_BOTTOM   = 185

# ── Animation ────────────────────────────────────────────────────────────────
FADE_IN      = 0.35
FADE_OUT     = 0.30
KW_SCALE_DUR = 0.22

# ── Post-processing ───────────────────────────────────────────────────────────
GRAIN_INTENSITY = 18
GRAIN_POOL      = 32
VIGNETTE        = 0.62
CAM_PUSH        = 1.022
GLOW_R          = 24
GLOW_BOOST      = 2.6

# ── Template ─────────────────────────────────────────────────────────────────
DEFAULT_TEMPLATE = os.getenv("DEFAULT_TEMPLATE", "english_learning")
# Available: "english_learning", "podcast", "tiktok"
