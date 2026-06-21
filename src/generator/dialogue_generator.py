"""
src/generator/dialogue_generator.py
AI dialogue generator and keyword extractor.

Uses any OpenAI-compatible API (ZhipuAI GLM-4, OpenAI, DeepSeek, etc.)
Falls back to built-in demo data when API key is not configured.
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ── path bootstrap (allow running from any working directory) ─────────────────
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
    LLM_TEMP, LLM_MAX_TOKENS,
    DIALOGUE_MIN_TURNS, DIALOGUE_MAX_TURNS, KEYWORD_COUNT,
)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class KeywordDef:
    word:    str
    meaning: str
    level:   str = "B1"    # CEFR level


@dataclass
class DialogueLine:
    speaker:  str            # "A" or "B"
    zh:       str
    en:       str
    keywords: List[str] = field(default_factory=list)   # words from KeywordDef


@dataclass
class DialogueScript:
    title:    str
    topic:    str
    dialogue: List[DialogueLine]
    keywords: List[KeywordDef]


# ── Prompts ───────────────────────────────────────────────────────────────────

_DIALOGUE_SYSTEM = """\
你是一个英语教学内容创作者，擅长写自然的日常生活对话。
你的对话生活化、口语化，英文地道，适合A2-B2学习者。
"""

_DIALOGUE_USER_TMPL = """\
请生成一段关于"{topic}"的日常生活对话场景。

要求：
1. {min_t}~{max_t}轮对话，A和B两人交替
2. 话题真实自然，贴近日常生活
3. 每句中文控制在15字以内
4. 英文保持口语化、地道，难度A2-B2
5. 对话要有起承转合，不要只是问答

只返回JSON，不要Markdown代码块：
{{
  "title": "对话标题（中文）",
  "dialogue": [
    {{"speaker":"A","zh":"中文句子","en":"English sentence"}},
    ...
  ]
}}
"""

_KEYWORD_SYSTEM = """\
你是英语词汇教学专家，擅长从对话中筛选高价值学习词汇。
"""

_KEYWORD_USER_TMPL = """\
请从以下英语对话中提取{count}个最值得学习的词汇或短语。

对话：
{dialogue}

筛选标准：
1. CEFR A2-B2难度
2. 生活高频，实用性强
3. 优先动词短语、形容词、固定搭配
4. 排除过于简单的词（go、have、be）

只返回JSON数组，不要Markdown代码块：
[
  {{"word":"coincidence","meaning":"巧合","level":"B1"}},
  ...
]
"""


# ── Generator ─────────────────────────────────────────────────────────────────

class DialogueGenerator:
    """
    Generates English learning dialogue scripts using an LLM.

    Usage:
        gen = DialogueGenerator()
        script = gen.generate("在便利店偶遇朋友")
    """

    def __init__(self):
        self._client = None
        if LLM_API_KEY:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=LLM_API_KEY,
                    base_url=LLM_BASE_URL,
                )
            except ImportError:
                print("⚠  openai package not found. Run: pip install openai")

    # ── Public ────────────────────────────────────────────────────────────────

    def generate(self, topic: str) -> DialogueScript:
        """Generate a full dialogue script for the given topic."""
        if not self._client:
            print(f"ℹ  No LLM API key — using built-in demo for '{topic}'")
            return self._demo_script(topic)

        print(f"🤖  Generating dialogue: {topic} …")
        dialogue_lines = self._gen_dialogue(topic)
        keywords = self._extract_keywords(dialogue_lines)

        # Tag which lines contain keywords
        kw_words = {k.word.lower() for k in keywords}
        for line in dialogue_lines:
            line.keywords = [k.word for k in keywords if k.word.lower() in line.en.lower()]

        title = topic   # fallback; overwritten below if LLM returns one
        return DialogueScript(
            title=title,
            topic=topic,
            dialogue=dialogue_lines,
            keywords=keywords,
        )

    # ── LLM calls ─────────────────────────────────────────────────────────────

    def _gen_dialogue(self, topic: str) -> List[DialogueLine]:
        prompt = _DIALOGUE_USER_TMPL.format(
            topic=topic,
            min_t=DIALOGUE_MIN_TURNS,
            max_t=DIALOGUE_MAX_TURNS,
        )
        raw = self._call_llm(_DIALOGUE_SYSTEM, prompt)
        data = self._parse_json(raw)

        lines = []
        for item in data.get("dialogue", []):
            lines.append(DialogueLine(
                speaker=item.get("speaker", "A"),
                zh=item.get("zh", "").strip(),
                en=item.get("en", "").strip(),
            ))
        return lines

    def _extract_keywords(self, lines: List[DialogueLine]) -> List[KeywordDef]:
        dialogue_text = "\n".join(f"{l.speaker}: {l.en}" for l in lines)
        prompt = _KEYWORD_USER_TMPL.format(
            count=KEYWORD_COUNT,
            dialogue=dialogue_text,
        )
        raw = self._call_llm(_KEYWORD_SYSTEM, prompt)
        data = self._parse_json(raw)

        keywords = []
        for item in (data if isinstance(data, list) else []):
            keywords.append(KeywordDef(
                word=item.get("word", "").strip(),
                meaning=item.get("meaning", "").strip(),
                level=item.get("level", "B1"),
            ))
        return keywords

    def _call_llm(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=LLM_TEMP,
            max_tokens=LLM_MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> any:
        """Parse JSON, stripping markdown code fences if present."""
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as exc:
            print(f"⚠  JSON parse error: {exc}\n  Raw: {text[:200]}")
            return {}

    # ── Demo fallback ─────────────────────────────────────────────────────────

    @staticmethod
    def _demo_script(topic: str) -> DialogueScript:
        """Built-in demo when no API key is configured."""
        return DialogueScript(
            title="便利店偶遇朋友",
            topic=topic,
            dialogue=[
                DialogueLine("A", "好巧啊，你怎么也在这里？",
                             "What a coincidence! What are you doing here?",
                             ["coincidence"]),
                DialogueLine("B", "我来买点饮料，顺便逛逛。",
                             "I'm here to grab some drinks. Just browsing around.",
                             ["browsing"]),
                DialogueLine("A", "最近工作怎么样？",
                             "How's work going recently?",
                             ["recently"]),
                DialogueLine("B", "还行，就是有点忙。",
                             "Not bad, just a little hectic lately.",
                             ["hectic"]),
                DialogueLine("A", "我也是，项目快截止了。",
                             "Same here. My project deadline is coming up.",
                             ["deadline"]),
                DialogueLine("B", "加油，你肯定能搞定的。",
                             "Hang in there. I'm sure you can pull it off.",
                             ["pull it off"]),
                DialogueLine("A", "谢谢！改天约着出来喝咖啡？",
                             "Thanks! We should grab coffee sometime.",
                             ["grab coffee"]),
                DialogueLine("B", "当然，这周末怎么样？",
                             "Absolutely. How about this weekend?",
                             ["absolutely"]),
            ],
            keywords=[
                KeywordDef("coincidence", "巧合",       "B1"),
                KeywordDef("hectic",      "忙乱的",      "B2"),
                KeywordDef("deadline",    "截止日期",    "B1"),
                KeywordDef("pull it off", "成功做到",    "B2"),
                KeywordDef("grab coffee", "一起喝咖啡",  "A2"),
                KeywordDef("absolutely",  "当然，完全地", "A2"),
                KeywordDef("browsing",    "随便逛逛",    "A2"),
                KeywordDef("recently",    "最近",        "A2"),
            ],
        )
