"""
src/templates/mixed_inline.py  ——  v4  (16:9 landscape)

Layout : 1920 × 1080  (横版)
State  : future=灰色ghost  →  active=黄色+光晕  →  past=黄色
         读到哪个变黄，没读到保持灰色
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from renderer.animation import pulse
from templates.base import BaseTemplate

# ── 16:9 输出尺寸 ──────────────────────────────────────────────────────────────
_W = 1920
_H = 1080

# ── 颜色 ──────────────────────────────────────────────────────────────────────
_C_APP       = (10,  10,  18)       # 深色背景
_C_CARD      = (255, 255, 255)      # 白卡片
_C_SHADOW    = (0,   0,   10)

_C_TEXT      = (20,  20,  32)       # 正常中文颜色
_C_TEXT_GRAY = (170, 170, 185)      # 未读中文（同行有未读词时变灰）

# 关键词 — 三态
_C_KW_FUTURE = (212, 212, 226)      # 灰色框（未读）
_C_TXT_FUT   = (155, 155, 172)      # 灰色文字
_C_KW_PAST   = (255, 214,  10)      # 黄色框（已读/不发光）
_C_KW_ACT    = (255, 214,  10)      # 黄色框（正读 + 光晕）
_C_KW_TXT    = (22,  22,  32)       # 关键词黑色文字
_C_KW_GLOW   = (255, 170,   0)      # 光晕颜色

_C_ANN_PAST  = (95,  95, 115)       # 注释（已读）
_C_ANN_FUT   = (185, 185, 200)      # 注释（未读）

# 底部词卡
_C_PANEL     = (16,  16,  28)
_C_PKW       = (255, 214,  10)
_C_PMN       = (195, 195, 215)
_C_PEX       = (120, 120, 145)
_C_BRD_ON    = (218,  96,  36)      # 橙色边框（当前词）
_C_BRD_OFF   = ( 48,  48,  70)

_C_PROG      = (155, 155, 178)

# ── 16:9 布局常量 ──────────────────────────────────────────────────────────────
_CARD_X  = 46
_CARD_W  = _W - 92        # 1828
_CARD_RX = 22

_CPAX    = 64             # 内容左右padding
_CPAY    = 46             # 内容上下padding
_CW      = _CARD_W - _CPAX * 2   # 1700 px 可用宽度

_FS      = 66             # 正文字号
_FS_ANN  = 20             # 注释字号
_FS_PROG = 24

_KW_PX   = 12             # 关键词框水平padding
_KW_PY   = 6              # 关键词框垂直padding
_KW_GAP  = 5              # 框后间距

_LINE_H  = 126            # 统一行高

# 卡片高度随文字行数自适应（避免文字少时卡片留白过多）
_CARD_H_MIN = 320         # 最少撑住1-2行
_CARD_H_MAX = 760         # 最多六行左右，留出底部词卡空间

# 底部词卡 — 固定高度，紧跟卡片底部
_PANEL_X = 46
_PANEL_W = _W - 92
_PANEL_H = 250
_PANEL_RX= 14
_BLOCK_GAP = 16            # 卡片与底部词卡之间的间距

_ANN_OFF = 5              # 框底到注释的间距


class MixedInlineTemplate(BaseTemplate):

    @property
    def name(self):         return "mixed_inline"
    @property
    def description(self):  return "16:9 白卡片 · 内嵌关键词框 · 灰→黄渐显动画"
    @property
    def output_size(self):  return (_W, _H)   # ← 16:9
    @property
    def use_vignette(self): return False
    @property
    def use_grain(self):    return False

    # ── 主渲染 ────────────────────────────────────────────────────────────────

    def render_layer(self, scene, local_t, alpha, fm, tc, gc) -> Image.Image:
        layer = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
        draw  = ImageDraw.Draw(layer)

        # 深色背景
        draw.rectangle([0, 0, _W, _H], fill=(*_C_APP, 255))

        meta          = getattr(scene, "meta", {}) or {}
        layout        = meta.get("layout", [])
        all_kws       = meta.get("all_keywords", [])
        slide_info    = meta.get("slide_info", "")
        kw_global_map = meta.get("kw_global_map", [])   # local idx -> global idx
        word_beats    = getattr(scene, "word_beats", []) or []

        # ── 卡片高度按实际行数自适应 ──────────────────────────────────────────
        n_lines = max(1, len(layout))
        card_h  = n_lines * _LINE_H + _CPAY * 2
        card_h  = max(_CARD_H_MIN, min(_CARD_H_MAX, card_h))

        # 整体（卡片+间距+底部词卡）在屏幕上垂直居中
        block_h = card_h + _BLOCK_GAP + _PANEL_H
        card_y  = max(20, (_H - block_h) // 2)
        panel_y = card_y + card_h + _BLOCK_GAP

        # 卡片阴影
        sa = int(26 * alpha)
        for off in (7, 5, 3):
            try:
                draw.rounded_rectangle(
                    [_CARD_X+off, card_y+off,
                     _CARD_X+_CARD_W+off-1, card_y+card_h+off-1],
                    radius=_CARD_RX, fill=(*_C_SHADOW, sa))
            except Exception:
                pass

        # 白卡片
        ca = int(255 * min(1.0, alpha * 3))
        self._rrect(draw, _CARD_X, card_y, _CARD_W, card_h,
                    _CARD_RX, (*_C_CARD, ca))

        active_idx = self._active_kw(local_t, word_beats)   # LOCAL to this scene

        # 进度标记
        if slide_info:
            pf = fm.get(_FS_PROG, "en")
            draw.text((_CARD_X + _CARD_W - 66, card_y + 18), slide_info,
                      font=pf, fill=(*_C_PROG, int(200 * alpha)))

        # 文字内容 — uses LOCAL active_idx (tok.kw_idx is also paragraph-local)
        if layout:
            self._render_lines(draw, layer, fm, layout, card_y, card_h,
                               active_idx, local_t, alpha, word_beats)

        # 底部词卡 — must use GLOBAL index since all_kws spans all paragraphs
        if all_kws and alpha > 0.1:
            pa = min(1.0, (alpha - 0.1) / 0.25)
            if active_idx >= 0 and active_idx < len(kw_global_map):
                global_active = kw_global_map[active_idx]
            elif kw_global_map:
                # Before this scene's first beat fires — anchor panel to this
                # scene's own first keyword (not the video's global first one)
                global_active = kw_global_map[0]
            else:
                global_active = -1
            self._draw_panel(draw, fm, all_kws, global_active, panel_y, pa)

        return layer

    # ── 行渲染 ────────────────────────────────────────────────────────────────

    def _render_lines(self, draw, layer, fm, layout, card_y, card_h,
                      active_idx, local_t, alpha, word_beats):
        mf = fm.get(_FS,     "zh")
        ef = fm.get(_FS,     "en")
        af = fm.get(_FS_ANN, "zh")

        # 测量真实文字高度
        dd = ImageDraw.Draw(Image.new("RGBA", (2, 2)))
        try:
            bb = dd.textbbox((0, 0), "测Ag", mf)
            th = bb[3] - bb[1]
        except Exception:
            th = int(_FS * 1.10)

        a_int = int(255 * alpha)
        cx0   = _CARD_X + _CPAX
        # 垂直居中文字块
        n     = len(layout)
        blk_h = n * _LINE_H
        avail = card_h - _CPAY * 2
        y0    = card_y + _CPAY + max(0, (avail - blk_h) // 2)
        y     = y0

        for line in layout:
            # 判断该行第一个关键词的状态，决定中文颜色
            line_kw_idxs = [t.kw_idx for t, _ in line if t.is_keyword]
            first_kw = line_kw_idxs[0] if line_kw_idxs else None
            # 行内中文颜色：若该行有未读词，中文稍微变灰
            zh_col = _C_TEXT
            if first_kw is not None:
                st = self._kw_state(first_kw, active_idx)
                if st == "future":
                    zh_col = _C_TEXT_GRAY

            for tok, x_off in line:
                px = cx0 + x_off
                if tok.is_keyword:
                    state = self._kw_state(tok.kw_idx, active_idx)
                    self._draw_keyword(draw, layer, fm, ef, af,
                                       tok, px, y, th, state,
                                       local_t, alpha)
                else:
                    draw.text((px, y), tok.text, font=mf,
                              fill=(*zh_col, a_int))
            y += _LINE_H

    # ── 关键词 ────────────────────────────────────────────────────────────────

    def _draw_keyword(self, draw, layer, fm, ef, af,
                      tok, x, y, th, state, local_t, alpha):
        a = int(255 * alpha)
        dd = ImageDraw.Draw(Image.new("RGBA", (2, 2)))
        try:
            bb = dd.textbbox((0, 0), tok.text, ef)
            tw = bb[2] - bb[0]
        except Exception:
            tw = int(len(tok.text) * _FS * 0.62)

        bx = x
        by = y - _KW_PY
        bw = tw + _KW_PX * 2
        bh = th + _KW_PY * 2

        if state == "future":
            # ── 灰色 ghost 框（未读）────────────────────────────────────────
            self._rrect(draw, bx, by, bw, bh, 8,
                        (*_C_KW_FUTURE, int(230 * alpha)))
            draw.text((bx + _KW_PX, y), tok.text, font=ef,
                      fill=(*_C_TXT_FUT, int(200 * alpha)))
            ann_str = (f"{tok.pos} {tok.meaning}".strip()
                       if tok.pos else tok.meaning)
            if ann_str:
                draw.text((bx, by + bh + _ANN_OFF), ann_str,
                          font=af, fill=(*_C_ANN_FUT, int(150 * alpha)))

        elif state == "active":
            # ── 黄色 + 脉冲光晕（正在读）────────────────────────────────────
            p   = pulse(local_t, freq=1.6)
            exp = int(3 + 3 * p)
            gw, gh = bw + exp * 4, bh + exp * 4
            gs  = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
            gd  = ImageDraw.Draw(gs)
            gd.rounded_rectangle([exp, exp, gw-exp-1, gh-exp-1],
                                  radius=10+exp,
                                  fill=(*_C_KW_GLOW, int(130 * alpha * p)))
            layer.paste(gs.filter(ImageFilter.GaussianBlur(7)),
                        (bx - exp*2, by - exp*2),
                        gs.filter(ImageFilter.GaussianBlur(7)))
            self._rrect(draw, bx, by, bw, bh, 8, (*_C_KW_ACT, a))
            draw.text((bx + _KW_PX, y), tok.text, font=ef,
                      fill=(*_C_KW_TXT, a))
            ann_str = (f"{tok.pos} {tok.meaning}".strip()
                       if tok.pos else tok.meaning)
            if ann_str:
                draw.text((bx, by + bh + _ANN_OFF), ann_str,
                          font=af, fill=(*_C_ANN_PAST, int(220 * alpha)))

        else:  # past
            # ── 黄色（已读，无光晕）─────────────────────────────────────────
            self._rrect(draw, bx, by, bw, bh, 8, (*_C_KW_PAST, a))
            draw.text((bx + _KW_PX, y), tok.text, font=ef,
                      fill=(*_C_KW_TXT, a))
            ann_str = (f"{tok.pos} {tok.meaning}".strip()
                       if tok.pos else tok.meaning)
            if ann_str:
                draw.text((bx, by + bh + _ANN_OFF), ann_str,
                          font=af, fill=(*_C_ANN_PAST, int(220 * alpha)))

    # ── 底部词卡 ──────────────────────────────────────────────────────────────

    def _draw_panel(self, draw, fm, all_kws, active_idx, panel_y, alpha):
        a = int(240 * alpha)
        self._rrect(draw, _PANEL_X, panel_y, _PANEL_W, _PANEL_H,
                    _PANEL_RX, (*_C_PANEL, a))

        if active_idx < 0:
            show = all_kws[:2]; cur = -1
        else:
            s    = max(0, active_idx - 1)
            show = all_kws[s: s + 2]
            cur  = active_idx - s

        kf  = fm.get(42, "en")
        mf2 = fm.get(28, "zh")
        exf = fm.get(23, "zh")
        cw  = (_PANEL_W - 20) // 2

        for i, kw in enumerate(show):
            cx  = _PANEL_X + 10 + i * (cw + 10)
            cy  = panel_y + 12
            ch  = _PANEL_H - 24
            on  = (i == cur)
            brd = _C_BRD_ON if on else _C_BRD_OFF
            ta  = int(255 * alpha)

            self._rrect(draw, cx, cy, cw, ch, 12,
                        (26, 26, 42, int(200 * alpha)))
            try:
                draw.rounded_rectangle(
                    [cx, cy, cx+cw-1, cy+ch-1],
                    radius=12, outline=(*brd, ta), width=2 if on else 1)
            except Exception:
                pass

            draw.text((cx+14, cy+12),  kw.get("word",""),
                      font=kf,  fill=(*_C_PKW, ta))
            draw.text((cx+14, cy+60),  kw.get("meaning",""),
                      font=mf2, fill=(*_C_PMN, ta))
            ex = kw.get("example","")
            if ex:
                ex_s = ex[:20] + "…" if len(ex) > 20 else ex
                draw.text((cx+14, cy+94), ex_s,
                          font=exf, fill=(*_C_PEX, int(180*alpha)))

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _rrect(draw, x, y, w, h, r, fill):
        try:
            draw.rounded_rectangle([x, y, x+w-1, y+h-1], radius=r, fill=fill)
        except Exception:
            draw.rectangle([x, y, x+w, y+h], fill=fill)

    @staticmethod
    def _active_kw(local_t, word_beats):
        """返回当前正在朗读的关键词序号，-1表示无"""
        if not word_beats:
            return -1
        for i, b in enumerate(word_beats):
            s = b.start if hasattr(b,"start") else b.get("start",0)
            e = b.end   if hasattr(b,"end")   else b.get("end",  0)
            if s <= local_t < e + 0.3:
                return i
        # 全部读完后停在最后一个
        last = word_beats[-1]
        e = last.end if hasattr(last,"end") else last.get("end",0)
        return len(word_beats)-1 if local_t >= e else -1

    @staticmethod
    def _kw_state(kw_idx, active_idx):
        """
        past   = 已读（黄色）
        active = 正在读（黄色+光晕）
        future = 未读（灰色）
        """
        if active_idx < 0:
            return "future"           # 还没开始读，全部灰色
        if kw_idx < active_idx:
            return "past"
        if kw_idx == active_idx:
            return "active"
        return "future"
