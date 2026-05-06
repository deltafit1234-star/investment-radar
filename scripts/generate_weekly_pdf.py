#!/usr/bin/env python3
"""
得分洞见周报 PDF 生成器
- 普通版 + 尊享版（金色装饰）
- 国内/国际分栏
- 每赛道独立一份
"""
import os, sys, io, re
from datetime import datetime, timedelta
from pathlib import Path

# 字体路径
FONT = "/mnt/c/Windows/Fonts/NotoSansSC-VF.ttf"
if not os.path.exists(FONT):
    FONT = "/mnt/c/Windows/Fonts/simhei.ttf"

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, Color
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether, Image as RLImage
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage, ImageDraw, ImageFont

pdfmetrics.registerFont(TTFont("NotoSansSC", FONT))

# ── 配色方案 ────────────────────────────────────────────
BRAND_BLUE   = HexColor("#1A3A5C")
BRAND_GOLD   = HexColor("#C9A84C")
BRAND_GRAY   = HexColor("#6B7280")
TEXT_DARK    = HexColor("#1F2937")
WHITE        = HexColor("#FFFFFF")
BORDER_GRAY  = HexColor("#E5E7EB")
LIGHT_BLUE   = HexColor("#E8F4FC")
GOLD_LIGHT   = HexColor("#FDF6E3")

# 尊享版金色渐变（用实色模拟）
GOLD_DARK    = HexColor("#B8860B")
GOLD_BORDER  = HexColor("#D4AF37")

TRACK_COLORS = {
    "AI大模型及应用层": HexColor("#4F46E5"),
    "自动驾驶":         HexColor("#059669"),
    "脑机接口":        HexColor("#7C3AED"),
    "人形机器人":       HexColor("#D97706"),
    "新能源/电池":      HexColor("#16A34A"),
    "半导体/芯片":      HexColor("#DC2626"),
}

# 报头图片路径（由用户提供的原始报头图片，作为背景底图）
ORIGINAL_HEADER_JPG  = "/mnt/c/Users/Admin/Desktop/investment_radar_header.jpg"
# 报头图片尺寸
HEADER_PX_W = 1896
HEADER_PX_H = 364
HEADER_CONTENT_WIDTH_MM = 190 * mm
HEADER_HEIGHT_MM = HEADER_CONTENT_WIDTH_MM / (HEADER_PX_W / HEADER_PX_H)  # ≈ 36.4mm

# FIT Logo
FIT_LOGO_PNG  = "/mnt/e/产业雷达/周报/fit_logo.png"
FIT_LOGO_H_PX = 90   # Logo高度（像素，在原图上）

W, H = A4
TOTAL_PAGES = [0]

# ── 样式工厂 ────────────────────────────────────────────
def sty(name, **kw):
    base = dict(fontName="NotoSansSC", textColor=TEXT_DARK, leading=13)
    base.update(kw)
    return ParagraphStyle(name, **base)

ST = {
    # 题头
    "brand_title":   sty("bt",  fontSize=24, textColor=WHITE,    leading=30, alignment=TA_CENTER, spaceAfter=1*mm),
    "brand_sub":     sty("bs",  fontSize=10, textColor=BRAND_GOLD, leading=14, alignment=TA_CENTER, spaceAfter=1*mm),
    "brand_date":    sty("bd",  fontSize=9,  textColor=WHITE,    leading=12, alignment=TA_CENTER, spaceAfter=1*mm),
    # 栏目标题
    "col_h1":        sty("c1",  fontSize=11, textColor=WHITE,    leading=15, alignment=TA_LEFT),
    "col_h1_premium": sty("c1p",fontSize=11, textColor=GOLD_DARK, leading=15, alignment=TA_LEFT),
    # 小节标题
    "section":       sty("sec", fontSize=10, textColor=BRAND_BLUE, leading=13, fontName="NotoSansSC"),
    # 正文
    "body":          sty("bd",  fontSize=8.5, textColor=TEXT_DARK, leading=12),
    "body_sm":       sty("bsm", fontSize=7.5, textColor=BRAND_GRAY, leading=10),
    "body_gold":     sty("bg",  fontSize=8.5, textColor=GOLD_DARK, leading=12),
    # 数字
    "stat_num":      sty("sn",  fontSize=20, textColor=BRAND_BLUE, leading=24, alignment=TA_CENTER, fontName="NotoSansSC"),
    "stat_label":    sty("sl",  fontSize=7.5, textColor=BRAND_GRAY, leading=10, alignment=TA_CENTER),
    # 信号行
    "sig_title":     sty("st",  fontSize=8.5, textColor=TEXT_DARK, leading=12),
    "sig_body":      sty("sb",  fontSize=7.5, textColor=BRAND_GRAY, leading=10),
    "sig_type":      sty("stp", fontSize=7,   textColor=BRAND_GRAY, leading=9),
    # 页脚
    "footer":        sty("ft",  fontSize=6.5, textColor=BRAND_GRAY, leading=8, alignment=TA_CENTER),
}

# ── 页眉页脚 ────────────────────────────────────────────
def draw_header_footer(c, doc, edition="normal"):
    c.saveState()
    pn = doc.page
    is_premium = (edition == "premium")
    header_bg = BRAND_BLUE if not is_premium else HexColor("#1A2A4A")
    accent    = BRAND_GOLD  if is_premium else BRAND_GOLD

    # 顶栏
    c.setFillColor(header_bg)
    c.rect(0, H - 14*mm, W, 14*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("NotoSansSC", 9)
    c.drawString(10*mm, H - 9*mm, "得 分 洞 察")
    c.setFont("NotoSansSC", 7)
    c.setFillColor(HexColor("#A0AEC0"))
    c.drawString(10*mm, H - 12*mm, "投资雷达 · 产业周报" if not is_premium else "投资雷达 · 产业周报 尊享版")
    c.setFont("NotoSansSC", 7.5)
    c.drawRightString(W - 10*mm, H - 9*mm, f"{pn} / {TOTAL_PAGES[0]}")

    # 金色装饰线（尊享版）
    if is_premium:
        c.setStrokeColor(GOLD_BORDER)
        c.setLineWidth(0.8)
        c.line(0, H - 14*mm, W, H - 14*mm)

    # 底栏
    c.setFillColor(header_bg)
    c.rect(0, 0, W, 9*mm, fill=1, stroke=0)
    if is_premium:
        c.setStrokeColor(GOLD_BORDER)
        c.setLineWidth(0.5)
        c.line(0, 9*mm, W, 9*mm)
    c.setFillColor(HexColor("#A0AEC0"))
    c.setFont("NotoSansSC", 6.5)
    disclaimer = "本报告由 AI 自动生成，仅供参考，不构成任何投资建议。" if not is_premium else "本报告仅供授权机构内部使用，请勿对外传播。"
    c.drawCentredString(W/2, 3*mm, disclaimer)

    c.restoreState()


class PageCounter(pdfcanvas.Canvas):
    def __init__(self, stream, **kw):
        super().__init__(stream, **kw)
        self._n = 0
    def showPage(self):
        self._n += 1
        super().showPage()
    def save(self):
        self._n += 1
        TOTAL_PAGES[0] = self._n
        super().save()


# ── 辅助函数 ────────────────────────────────────────────
def hex_c(c: HexColor) -> str:
    return "#%06x" % int(c.hexval(), 16)


def p(text, style_key="body"):
    return Paragraph(text, ST[style_key])


def sp(h_mm=2):
    return Spacer(1, h_mm*mm)


def hr(color=BORDER_GRAY, thickness=0.4, space_before=2, space_after=2):
    return HRFlowable(width="100%", thickness=thickness, color=color,
                      spaceBefore=space_before*mm, spaceAfter=space_after*mm)


def signal_badge(sig_type: str, is_premium=False) -> Paragraph:
    """信号类型标签"""
    colors = {
        "funding_news":  ("#059669", "融资"),
        "itjuzi_funding":("#059669", "融资"),
        "model_news":    ("#4F46E5", "模型"),
        "star_surge":    ("#D97706", "GitHub"),
        "paper_burst":   ("#7C3AED", "论文"),
        "hackernews":   ("#DC2626", "HN"),
    }
    bg, label = colors.get(sig_type, ("#6B7280", sig_type[:4]))
    txt = f'<font color="{bg}" size="7"><b>{label}</b></font>'
    return Paragraph(txt, ST["sig_type"])


def section_title(text: str, is_premium=False) -> Paragraph:
    """小节标题（带左侧色条）"""
    color = GOLD_DARK if is_premium else BRAND_BLUE
    return Paragraph(
        f'<font color="{hex_c(color)}"><b>▌ {text}</b></font>',
        ST["section"]
    )


def col_header(text: str, color: HexColor, is_premium=False) -> Paragraph:
    """栏目大标题（色块背景）"""
    if is_premium:
        return Paragraph(
            f'<font color="{hex_c(GOLD_DARK)}"><b>　{text}</b></font>',
            ST["col_h1_premium"]
        )
    return Paragraph(
        f'<font color="white"><b>　{text}</b></font>',
        ST["col_h1"]
    )


def sig_row(sig: dict, index: int, is_premium=False) -> list:
    """信号行：[序号, 类型, 标题+摘要, 优先级]"""
    title = (sig.get("title") or sig.get("full_name") or "")[:60]
    summary = (sig.get("summary") or sig.get("content") or sig.get("meaning") or "")[:80]
    sig_type = sig.get("type") or sig.get("signal_type", "")
    priority = sig.get("priority", "")

    badge = signal_badge(sig_type, is_premium)

    title_html = f'<font color="#1F2937">{title}</font>'
    if priority == "high":
        title_html = f'<font color="#DC2626"><b>{title}</b></font>'
    elif priority == "medium":
        title_html = f'<font color="#D97706"><b>{title}</b></font>'

    summary_html = f'<font color="#6B7280" size="7">{summary}</font>'
    content_cell = Paragraph(f"{title_html}<br/>{summary_html}", ST["sig_title"])

    return [
        Paragraph(f'<font color="#9CA3AF">{index:02d}</font>', ST["body_sm"]),
        badge,
        content_cell,
    ]


def stat_box(num: str, label: str, accent=BRAND_BLUE) -> Paragraph:
    """统计数字卡片"""
    return Paragraph(
        f'<font color="{hex_c(accent)}" size="16"><b>{num}</b></font><br/>'
        f'<font color="#6B7280" size="7">{label}</font>',
        sty("sbx", fontSize=16, textColor=accent, leading=20, alignment=TA_CENTER, fontName="NotoSansSC")
    )


def build_overview_table(stats: dict, is_premium=False) -> Table:
    """概览统计表"""
    bg = GOLD_LIGHT if is_premium else LIGHT_BLUE
    accent = GOLD_DARK if is_premium else BRAND_BLUE

    rows = [
        [
            stat_box(str(stats.get("total", 0)), "本周信号", accent),
            stat_box(str(stats.get("domestic", 0)), "国内", accent),
            stat_box(str(stats.get("international", 0)), "国际", accent),
            stat_box(str(stats.get("high", 0)), "高优先级", accent),
        ]
    ]
    t = Table(rows, colWidths=[42*mm, 42*mm, 42*mm, 42*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), bg),
        ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4*mm),
        ("BOTTOMPADDING",(0,0), (-1, -1), 4*mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 2*mm),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2*mm),
        ("ROUNDEDCORNERS", [2*mm]),
    ]))
    return t


def build_signal_table(signals: list, is_premium=False, max_rows=15) -> Table:
    """信号列表表格"""
    rows = [sig_row(s, i+1, is_premium) for i, s in enumerate(signals[:max_rows])]
    if not rows:
        rows = [[p("（本周暂无信号）", "body_sm"), "", "", ""]]

    t = Table(rows, colWidths=[8*mm, 14*mm, 138*mm, 18*mm], splitByRow=1)
    style = [
        ("ALIGN",       (0, 0), (1, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",  (0, 0), (-1, -1), 1.5*mm),
        ("BOTTOMPADDING",(0,0), (-1, -1), 1.5*mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 2*mm),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2*mm),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.2, BORDER_GRAY),
    ]
    if is_premium:
        style.append(("BACKGROUND", (0, 0), (-1, 0), GOLD_LIGHT))
    t.setStyle(TableStyle(style))
    return t


def build_ww_comparison(ww: dict) -> Table:
    """周环比对比"""
    rows = []
    for track, data in ww.items():
        curr = data.get("current", 0)
        prev = data.get("previous", 0)
        diff = curr - prev
        pct = (diff / prev * 100) if prev > 0 else 0
        arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        color = "#16A34A" if diff > 0 else "#DC2626" if diff < 0 else "#6B7280"
        rows.append([
            Paragraph(f'<font color="#6B7280">{track}</font>', ST["body_sm"]),
            Paragraph(f'<b>{curr}</b>', ST["body"]),
            Paragraph(f'<font color="{color}">{arrow} {abs(pct):.0f}%</font>', ST["body"]),
        ])
    if not rows:
        return p("（数据不足）", "body_sm")
    t = Table(rows, colWidths=[60*mm, 30*mm, 30*mm])
    t.setStyle(TableStyle([
        ("ALIGN",  (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 1*mm),
        ("BOTTOMPADDING",(0,0), (-1, -1), 1*mm),
        ("LINEBELOW", (0, 0), (-1, -2), 0.2, BORDER_GRAY),
    ]))
    return t


# ── 封面/题头 ───────────────────────────────────────────
def _build_header_composite(edition="normal"):
    """
    在原始报头底图上叠加：
      - 左侧：得分洞见（大字）+ 未来产业周报尊享版
      - 右侧：FIT 几何 Logo + 得分数科 + 官网
    返回 PIL Image（RGBA）。
    """
    from io import BytesIO

    # 加载原始报头底图
    bg = PILImage.open(ORIGINAL_HEADER_JPG).convert("RGBA")
    W_px, H_px = bg.size   # 1896 × 364

    # 绘图层
    overlay = PILImage.new("RGBA", bg.size, (255, 255, 255, 0))
    draw    = ImageDraw.Draw(overlay)

    # 字体（尝试多个）
    def try_font(path, size):
        try:
            return ImageFont.truetype(path, size, layout_engine=ImageFont.LAYOUT_BASIC)
        except Exception:
            try:
                return ImageFont.truetype("/mnt/c/Windows/Fonts/simhei.ttf", size)
            except Exception:
                return ImageFont.load_default()

    f_title  = try_font(FONT, 90)
    f_sub    = try_font(FONT, 32)
    f_brand  = try_font(FONT, 22)
    f_url    = try_font(FONT, 15)

    gold = (212, 175, 55)
    teal = (0, 128, 128)
    black = (0, 0, 0)
    gray  = (102, 102, 102)

    # ── 左侧：文字区 ───────────────────────────────────
    # 主标题「得分洞见」
    main_text  = "得分洞见"
    main_bb    = draw.textbbox((0, 0), main_text, font=f_title)
    main_tw    = main_bb[2] - main_bb[0]
    main_th    = main_bb[3] - main_bb[1]
    main_x     = int(W_px * 0.09)
    main_y     = int(H_px * 0.15)   # 基线

    # 文字颜色：尊享版金色，普通版深青绿
    main_color = gold if edition == "premium" else teal
    draw.text((main_x, main_y - main_th), main_text, font=f_title, fill=main_color)

    # 副标题「未来产业周报尊享版」或「未来产业周报普通版」
    sub_text = "未来产业周报尊享版" if edition == "premium" else "未来产业周报普通版"
    sub_bb   = draw.textbbox((0, 0), sub_text, font=f_sub)
    sub_tw   = sub_bb[2] - sub_bb[0]
    sub_th   = sub_bb[3] - sub_bb[1]
    sub_x    = main_x
    sub_y    = main_y + 6
    draw.text((sub_x, sub_y), sub_text, font=f_sub, fill=black)

    # 左侧版本色装饰竖线
    line_color = gold if edition == "premium" else teal
    draw.line([(main_x - 12, main_y - main_th), (main_x - 12, main_y + 16)],
              fill=line_color, width=5)

    # ── 右侧：FIT Logo + 品牌 ──────────────────────────
    logo_h = FIT_LOGO_H_PX
    logo_w = int(logo_h * 278 / 76)   # 保持 278:76 比例

    # FIT Logo 位置：右上角
    logo_cx = W_px - int(W_px * 0.09) - logo_w // 2
    logo_cy = H_px // 2 - 10

    # 加载 FIT Logo（独立 PNG）
    if os.path.exists(FIT_LOGO_PNG):
        fit_logo = PILImage.open(FIT_LOGO_PNG).convert("RGBA")
        fit_logo = fit_logo.resize((logo_w, logo_h), PILImage.LANCZOS)
        # 贴到 overlay 上
        paste_x = logo_cx - logo_w // 2
        paste_y = logo_cy - logo_h // 2
        bg.paste(fit_logo, (paste_x, paste_y), fit_logo)

    # 「得分数科」
    brand_text  = "得分数科"
    brand_bb    = draw.textbbox((0, 0), brand_text, font=f_brand)
    brand_tw    = brand_bb[2] - brand_bb[0]
    brand_th    = brand_bb[3] - brand_bb[1]
    brand_x     = logo_cx - brand_tw // 2
    brand_y     = logo_cy + logo_h // 2 + 8
    draw.text((brand_x, brand_y), brand_text, font=f_brand, fill=black)

    # 「www.deltafit.com.cn」
    url_text    = "www.deltafit.com.cn"
    url_bb      = draw.textbbox((0, 0), url_text, font=f_url)
    url_tw      = url_bb[2] - url_bb[0]
    url_x       = logo_cx - url_tw // 2
    url_y       = brand_y + brand_th + 4
    draw.text((url_x, url_y), url_text, font=f_url, fill=gray)

    # 合并
    bg = PILImage.alpha_composite(bg, overlay)

    # 保存到 BytesIO
    buf = BytesIO()
    bg.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_cover(track_name: str, week_start: str, week_end: str, edition="normal") -> list:
    """构建封面题头（原始报头图片 + 叠加 FIT Logo + 叠加文字）"""
    story = []

    # 1. 报头图片（全宽，带文字和 Logo 叠加）
    if os.path.exists(ORIGINAL_HEADER_JPG):
        buf = _build_header_composite(edition)
        from reportlab.lib.utils import ImageReader
        from io import BytesIO as IOBuf
        img_bytes = buf.read()
        img_io    = IOBuf(img_bytes)
        img       = RLImage(img_io, width=HEADER_CONTENT_WIDTH_MM, height=HEADER_HEIGHT_MM)
        story.append(img)
    else:
        # Fallback
        bg_color   = HexColor("#1A2A4A") if edition == "premium" else BRAND_BLUE
        title_text = "得分洞见周报 尊享版" if edition == "premium" else "得分洞见周报 普通版"
        cover_data = [[Paragraph(
            f'<font color="white" size="20"><b>　{title_text}</b></font>',
            sty("ct", fontSize=20, textColor=WHITE, leading=28)
        )]]
        t = Table(cover_data, colWidths=[W - 20*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), bg_color),
            ("TOPPADDING",    (0, 0), (-1, -1), 6*mm),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6*mm),
            ("LEFTPADDING",  (0, 0), (-1, -1), 5*mm),
        ]))
        story.append(t)

    # 2. 赛道名 + 日期行
    date_str    = f"{week_start[5:].replace('-','月')}日 — {week_end[5:].replace('-','月')}日"
    track_color = TRACK_COLORS.get(track_name, BRAND_BLUE)
    tc          = hex_c(track_color)

    info_row = Table(
        [
            [
                Paragraph(f'<font color="{tc}" size="13"><b>▌ {track_name}</b></font>',
                         sty("tc2", fontSize=13, textColor=track_color, leading=17, fontName="NotoSansSC")),
                Paragraph(f'<font color="#6B7280" size="9">{date_str}</font>', ST["body_sm"]),
            ],
            [
                Paragraph(f'<font color="#008080" size="8.5">数据来源：36Kr / IT桔子 / GitHub / arXiv / TechCrunch / HackerNews</font>', ST["body_sm"]),
                p("", "body"),
            ],
        ],
        colWidths=[120*mm, 70*mm]
    )
    info_row.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",        (1, 0), (1, -1),  "RIGHT"),
        ("TOPPADDING",   (0, 0), (-1, -1), 1.5*mm),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 1.5*mm),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info_row)
    story.append(sp(3))
    return story


# ── 国内/国际栏目 ────────────────────────────────────────
def build_domestic_section(domestic_signals: list, is_premium=False) -> list:
    """国内动态栏目"""
    items = []
    items.append(col_header("📍 国内动态", BRAND_BLUE, is_premium))
    items.append(sp(2))
    if domestic_signals:
        items.append(build_signal_table(domestic_signals, is_premium))
    else:
        items.append(p("（本周暂无国内信号）", "body_sm"))
    items.append(sp(5))
    return items


def build_international_section(intl_signals: list, is_premium=False) -> list:
    """国际动态栏目"""
    items = []
    items.append(col_header("🌐 国际动态", HexColor("#2E6DA4"), is_premium))
    items.append(sp(2))
    if intl_signals:
        items.append(build_signal_table(intl_signals, is_premium))
    else:
        items.append(p("（本周暂无国际信号）", "body_sm"))
    items.append(sp(5))
    return items


# ── 趋势洞察 ────────────────────────────────────────────
def build_trends_section(themes: list, ww: dict, is_premium=False) -> list:
    """主题趋势 + 周环比"""
    items = []
    items.append(section_title("主题趋势", is_premium))
    items.append(sp(2))
    if themes:
        theme_tags = "  ".join([f'<font color="{hex_c(GOLD_DARK if is_premium else BRAND_BLUE)}">#{t}</font>' for t in themes[:6]])
        items.append(p(theme_tags, "body"))
    else:
        items.append(p("本周趋势不明显，持续观察中。", "body_sm"))
    items.append(sp(3))
    items.append(hr())
    items.append(sp(3))
    items.append(section_title("周环比信号量", is_premium))
    items.append(sp(2))
    items.append(build_ww_comparison(ww))
    items.append(sp(5))
    return items


# ── 下周关注 ────────────────────────────────────────────
def build_outlook_section(high_priority: list, is_premium=False) -> list:
    """下周关注"""
    items = []
    items.append(section_title("下周关注", is_premium))
    items.append(sp(2))
    if high_priority:
        for sig in high_priority[:5]:
            title = sig.get("title") or sig.get("full_name", "")
            meaning = sig.get("meaning", "")[:80]
            items.append(p(f'<font color="#DC2626">●</font> <b>{title}</b>  {meaning}', "body"))
            items.append(sp(1.5))
    else:
        items.append(p("暂无高优先级关注事项。", "body_sm"))
    items.append(sp(5))
    return items


# ── 拼装完整故事 ────────────────────────────────────────
def make_story(report_data: dict, edition="normal") -> list:
    is_premium = (edition == "premium")
    s = []

    track_name  = report_data.get("track_name", "")
    week_start  = report_data.get("week_start", "")
    week_end    = report_data.get("week_end", "")
    stats       = report_data.get("stats", {})
    themes      = report_data.get("themes", [])
    domestic    = report_data.get("domestic_signals", [])
    international = report_data.get("international_signals", [])
    ww          = report_data.get("week_over_week", {})
    high_prio   = report_data.get("high_priority_signals", [])

    # 封面
    s.extend(build_cover(track_name, week_start, week_end, edition))
    s.append(hr(space_before=3, space_after=3))

    # 概览
    s.append(section_title("本周概览", is_premium))
    s.append(sp(2))
    s.append(build_overview_table(stats, is_premium))
    s.append(sp(5))

    # 国内/国际双栏
    s.append(col_header("📍 国内动态", TRACK_COLORS.get(track_name, BRAND_BLUE), is_premium))
    s.append(sp(2))
    if domestic:
        s.append(build_signal_table(domestic, is_premium, max_rows=12))
    else:
        s.append(p("（本周暂无国内信号）", "body_sm"))
    s.append(sp(4))

    s.append(col_header("🌐 国际动态", HexColor("#2E6DA4"), is_premium))
    s.append(sp(2))
    if international:
        s.append(build_signal_table(international, is_premium, max_rows=12))
    else:
        s.append(p("（本周暂无国际信号）", "body_sm"))
    s.append(sp(5))

    # 趋势 + 周环比
    s.append(KeepTogether(build_trends_section(themes, ww, is_premium)))

    # 下周关注（尊享版特有）
    if is_premium:
        s.append(hr(space_before=3, space_after=3))
        s.extend(build_outlook_section(high_prio, is_premium))

    # 免责声明
    s.append(hr(space_before=4, space_after=2))
    s.append(p(
        "本报告由 AI 自动生成，仅供参考，不构成任何投资建议。投资有风险，决策需谨慎。" if not is_premium
        else "本报告仅供授权机构内部使用。数据来源：36Kr / IT桔子 / GitHub / arXiv / TechCrunch / HackerNews。",
        "footer"
    ))
    return s


# ── 生成 PDF ────────────────────────────────────────────
class _CountingCanvas:
    """同时计数的 Canvas wrapper（避免两 Pass）"""
    def __init__(self, canvas_class, stream, **kw):
        self._c = canvas_class(stream, **kw)
        self._n = 0
    def __getattr__(self, name):
        return getattr(self._c, name)
    def showPage(self):
        self._n += 1
        self._c.showPage()
    def save(self):
        self._n += 1
        TOTAL_PAGES[0] = self._n
        self._c.save()


def generate(report_data: dict, out_path: str, edition="normal"):
    story = make_story(report_data, edition)

    # 单 Pass：边生成边计数
    TOTAL_PAGES[0] = 0
    out_stream = io.BytesIO()
    counting_canvas = _CountingCanvas(pdfcanvas.Canvas, out_stream, pagesize=A4)
    doc = SimpleDocTemplate(out_stream, pagesize=A4,
                            leftMargin=10*mm, rightMargin=10*mm,
                            topMargin=20*mm, bottomMargin=14*mm,
                            title=f"得分洞见周报 {report_data.get('track_name','')} {report_data.get('week_start','')}",
                            author="得分洞察·投资雷达")
    def hf(c, doc):
        draw_header_footer(c, doc, edition)
    doc.build(story, onFirstPage=hf, onLaterPages=hf,
              canvasmaker=lambda *a, **kw: counting_canvas)

    total = TOTAL_PAGES[0]
    out_stream.seek(0)
    with open(out_path, 'wb') as f:
        f.write(out_stream.read())

    sz = os.path.getsize(out_path)
    print(f"✅ {out_path} ({total}页, {sz//1024}KB)")
    return out_path


if __name__ == "__main__":
    # 演示数据
    demo_data = {
        "track_name": "AI大模型及应用层",
        "week_start": "2026-04-21",
        "week_end":   "2026-04-27",
        "stats": {"total": 42, "domestic": 18, "international": 24, "high": 5},
        "themes": ["大模型推理优化", "Agent框架", "多模态", "开源模型"],
        "domestic_signals": [
            {"title": "月之暗面完成新一轮融资，估值超20亿美元", "type": "funding_news", "priority": "high", "summary": "Kimi 开发商获红杉等机构投资"},
            {"title": "智谱AI发布GLM-4开源版本", "type": "model_news", "priority": "high", "summary": "支持128K上下文"},
            {"title": "上海发布大模型产业扶持政策", "type": "funding_news", "priority": "medium", "summary": "最高补贴1000万元"},
        ],
        "international_signals": [
            {"title": "Llama 3 发布，Meta 开源最强开源大模型", "type": "model_news", "priority": "high", "summary": "400B参数，支持多模态"},
            {"title": "GitHub Stars 激增：vLLM 项目周增长 300%", "type": "star_surge", "priority": "medium", "summary": "推理优化框架持续火热"},
            {"title": "arXiv 论文爆发：Agent 相关论文周增 45%", "type": "paper_burst", "priority": "medium", "summary": "自主Agent成为研究热点"},
        ],
        "week_over_week": {
            "AI大模型及应用层": {"current": 42, "previous": 31},
            "自动驾驶": {"current": 28, "previous": 33},
        },
        "high_priority_signals": [
            {"title": "月之暗面融资事件", "meaning": "头部项目获资本认可，行业马太效应加剧"},
        ],
    }

    out_dir = Path("/mnt/e/产业雷达/周报")
    out_dir.mkdir(parents=True, exist_ok=True)

    generate(demo_data, str(out_dir / "demo_normal_v3.pdf"), edition="normal")
    generate(demo_data, str(out_dir / "demo_premium_v3.pdf"), edition="premium")
