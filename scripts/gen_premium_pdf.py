#!/usr/bin/env python3
"""
投资雷达周报 PDF 生成器（尊享版）
使用 ReportLab 直接绘制，完全自定义布局

布局：
  1. 顶部：Logo + 题图 + 标题区
  2. 内容：本周概览 / 国内动态 / 国际动态 / 主题趋势 / 周环比 / 下周关注
  3. 页脚
"""

import os
import sys
import io
from pathlib import Path

# ── 注册中文字体 ────────────────────────────────────────────────────────────
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

_FONT_PATH = "/mnt/c/Windows/Fonts/NotoSansSC-VF.ttf"
FONT_SCS = "NotoSansSC"
FONT_SCS_BOLD = "NotoSansSC-Bold"

pdfmetrics.registerFont(TTFont(FONT_SCS, _FONT_PATH))
pdfmetrics.registerFont(TTFont(FONT_SCS_BOLD, _FONT_PATH))
registerFontFamily(FONT_SCS, normal=FONT_SCS, bold=FONT_SCS_BOLD)

# ── ReportLab ───────────────────────────────────────────────────────────────
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, KeepTogether, HRFlowable
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus.flowables import Flowable

# ── 颜色 ────────────────────────────────────────────────────────────────────
C_DARK       = HexColor("#1A1A2E")   # 深色主文字
C_ACCENT     = HexColor("#1E5AA8")   # 蓝色强调（标题）
C_GRAY       = HexColor("#6B7280")   # 灰色辅助
C_LIGHT      = HexColor("#F3F4F6")  # 浅灰背景
C_HEADER_BG  = HexColor("#1E5AA8")  # 表头背景
C_ROW_ALT    = HexColor("#F9FAFB")  # 交替行
C_CARD_BG    = HexColor("#EBF4FF")  # 卡片淡蓝背景
C_UP         = HexColor("#16A34A")  # 上升绿
C_DOWN       = HexColor("#DC2626")  # 下降红
C_TAG        = HexColor("#1E5AA8")  # 标签蓝
C_FOCUS_BG   = HexColor("#FFFFE0")  # 下周关注黄背景
C_BORDER     = HexColor("#D1D5DB")  # 边框灰
C_FOOTER     = HexColor("#A0AEC0")  # 页脚灰
C_DESC       = HexColor("#4B5563")   # 描述灰

# ── 样式工厂 ────────────────────────────────────────────────────────────────
def sty(name, size=10, color=C_DARK, align=TA_LEFT, bold=False,
        leading=None, spaceBefore=0, spaceAfter=0, leftIndent=0,
        firstLineIndent=0, backColor=None, borderPad=0, **kw):
    fn = FONT_SCS_BOLD if bold else FONT_SCS
    return ParagraphStyle(
        name,
        fontName=fn,
        fontSize=size,
        textColor=color,
        alignment=align,
        leading=leading or size * 1.45,
        spaceBefore=spaceBefore,
        spaceAfter=spaceAfter,
        leftIndent=leftIndent,
        firstLineIndent=firstLineIndent,
        backColor=backColor,
        borderPad=borderPad,
        **kw
    )

# ── 页面尺寸 ────────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4  # 595.27 x 841.89 pt
ML = 15*mm
MR = 15*mm
MT = 12*mm
MB = 12*mm
CW = PAGE_W - ML - MR  # 内容宽度 ≈ 165mm


# ══════════════════════════════════════════════════════════════════════════════
# 自定义 Flowable：Logo 行
# ══════════════════════════════════════════════════════════════════════════════
class LogoHeader(Flowable):
    H = 16*mm
    def __init__(self, logo_path, text="得分洞见  www.deltafit.com.cn", w=CW):
        super().__init__()
        self.logo_path = logo_path
        self.text = text
        self.width = w
        self.height = self.H
    def draw(self):
        c = self.canv
        y = self.H - 8*mm
        if os.path.exists(self.logo_path):
            lh = 9*mm
            lw = lh * 3
            c.drawImage(self.logo_path, 0, y - lh,
                        width=lw, height=lh,
                        preserveAspectRatio=True, mask='auto')
        c.setFont(FONT_SCS, 8.5)
        c.setFillColor(C_GRAY)
        c.drawString(38*mm, y - 3.5*mm, self.text)


# ══════════════════════════════════════════════════════════════════════════════
# 自定义 Flowable：通栏题图
# ══════════════════════════════════════════════════════════════════════════════
class CoverImage(Flowable):
    H = 42*mm
    def __init__(self, img_path, w=CW, h=None):
        super().__init__()
        self.img_path = img_path
        self.width = w
        self.height = h or self.H
    def draw(self):
        c = self.canv
        if os.path.exists(self.img_path):
            c.drawImage(self.img_path, 0, 0,
                        width=self.width, height=self.height,
                        preserveAspectRatio=True, mask='auto')
        c.setFont(FONT_SCS, 7)
        c.setFillColor(C_GRAY)
        c.drawRightString(self.width, 2*mm, "图 | 豆包AI生成")


# ══════════════════════════════════════════════════════════════════════════════
# 自定义 Flowable：标题区块
# ══════════════════════════════════════════════════════════════════════════════
class TitleBlock(Flowable):
    H = 36*mm
    def __init__(self, date_range, main_title, subtitle, w=CW):
        super().__init__()
        self.date_range = date_range
        self.main_title = main_title
        self.subtitle = subtitle
        self.width = w
        self.height = self.H
    def draw(self):
        c = self.canv
        y = self.H
        c.setFont(FONT_SCS, 9)
        c.setFillColor(C_GRAY)
        c.drawCentredString(self.width / 2, y - 5*mm, self.date_range)
        c.setFont(FONT_SCS_BOLD, 20)
        c.setFillColor(C_DARK)
        c.drawCentredString(self.width / 2, y - 17*mm, self.main_title)
        c.setFont(FONT_SCS, 11)
        c.setFillColor(C_ACCENT)
        c.drawCentredString(self.width / 2, y - 27*mm, self.subtitle)


# ══════════════════════════════════════════════════════════════════════════════
# 自定义 Flowable：数据来源行
# ══════════════════════════════════════════════════════════════════════════════
class SourceLine(Flowable):
    H = 9*mm
    def __init__(self, text, w=CW):
        super().__init__()
        self.text = text
        self.width = w
        self.height = self.H
    def draw(self):
        c = self.canv
        c.setStrokeColor(C_ACCENT)
        c.setLineWidth(0.5)
        c.line(0, self.height - 2*mm, self.width, self.height - 2*mm)
        c.setFont(FONT_SCS, 7.5)
        c.setFillColor(C_GRAY)
        c.drawString(0, self.height - 7*mm, f"数据来源：{self.text}")


# ══════════════════════════════════════════════════════════════════════════════
# 区域标题辅助
# ══════════════════════════════════════════════════════════════════════════════
def section_title(text, space_before=6*mm, space_after=3*mm):
    """深蓝、黑体、14磅、加粗、左对齐"""
    return Paragraph(
        text,
        sty(f"st_{text}", size=14, color=C_ACCENT, bold=True,
            spaceBefore=space_before, spaceAfter=space_after,
            leftIndent=0, leading=17)
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. 本周概览
# ══════════════════════════════════════════════════════════════════════════════
def build_overview_table(data: dict):
    """
    data = {
        "total": 42,
        "domestic": 18,
        "international": 24,
        "high_priority": 5,
    }
    返回 2×4 卡片表格
    """
    total = data.get("total", 0)
    domestic = data.get("domestic", 0)
    international = data.get("international", 0)
    high = data.get("high_priority", 0)

    labels = ["总信号量", "国内", "国际", "高优先级"]
    values = [str(total), str(domestic), str(international), str(high)]

    # 每个卡片：数字大号 + 标签小号，合并在一个 cell
    def card(val, label):
        return Table(
            [[Paragraph(val, sty("cv", size=18, color=white, bold=True,
                                align=TA_CENTER, leading=20))],
             [Paragraph(label, sty("cl", size=8, color=white,
                                align=TA_CENTER, leading=11))]],
            colWidths=[38*mm],
            rowHeights=[11*mm, 6*mm],
        )

    label_style = sty("ov_lab", size=8, color=white, align=TA_CENTER)
    cards = []
    for val, lbl in zip(values, labels):
        cell_tbl = Table(
            [[Paragraph(val, sty("ov_val", size=18, color=white, bold=True,
                                  align=TA_CENTER, leading=20))],
             [Paragraph(lbl, sty("ov_lbl", size=8, color=white,
                                  align=TA_CENTER, leading=11))]],
            colWidths=[38*mm],
            rowHeights=[11*mm, 6*mm],
        )
        cell_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), C_ACCENT),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 1*mm),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1*mm),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        cards.append(cell_tbl)

    # 2行2列
    grid_data = [
        [cards[0], cards[1]],
        [cards[2], cards[3]],
    ]
    tbl = Table(grid_data, colWidths=[CW/2, CW/2])
    tbl.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6*mm),
        ('RIGHTPADDING', (0,0), (-1,-1), 6*mm),
        ('TOPPADDING', (0,0), (-1,-1), 1.5*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5*mm),
    ]))
    return tbl


# ══════════════════════════════════════════════════════════════════════════════
# 2. 动态条目（国内/国际共用）
# ══════════════════════════════════════════════════════════════════════════════
def build_signal_item(no: str, category: str, title: str, desc: str):
    """单个动态条目：编号+类别+标题合并一行，描述单独一行"""
    # 编号+类别+标题：合并为一个段落，同一行显示
    title_para = Paragraph(
        f'<font color="#1E5AA8"><b>{no}</b></font> '
        f'<font color="#1E5AA8"><b>{category}</b></font> '
        f'<b>{title}</b>',
        sty(f"title_{no}", size=12, bold=True, leading=15, color=C_DARK,
            leftIndent=5*mm)
    )
    # 描述：左缩进1.0厘米
    desc_para = Paragraph(
        desc,
        sty(f"desc_{no}", size=10.5, color=C_DESC, leading=14,
            leftIndent=10*mm, spaceBefore=0)
    )
    return [title_para, desc_para]


def build_signals_list(items: list):
    """
    items: [{"no":"01","category":"融资","title":"...","desc":"..."}]
    返回段落列表
    """
    paras = []
    for i, item in enumerate(items):
        block = build_signal_item(
            item["no"], item["category"], item["title"], item["desc"]
        )
        for p in block:
            paras.append(p)
        if i < len(items) - 1:
            paras.append(Spacer(1, 6))
    return paras


# ══════════════════════════════════════════════════════════════════════════════
# 3. 主题趋势
# ══════════════════════════════════════════════════════════════════════════════
def build_trend_tags(text: str):
    """tags 行"""
    return Paragraph(
        f'<font color="#1E5AA8">{text}</font>',
        sty("trend", size=10, color=C_TAG, leading=14,
            leftIndent=5*mm, spaceBefore=2*mm)
    )


# ══════════════════════════════════════════════════════════════════════════════
# 4. 周环比信号量
# ══════════════════════════════════════════════════════════════════════════════
def build_signal_change_table(data: list):
    """
    data: [
        {"track":"AI大模型及应用层","count":"42","pct":"↑35%"},
        {"track":"自动驾驶","count":"28","pct":"↓15%"},
    ]
    """
    def up_pct(txt):
        return Paragraph(
            f'<font color="#16A34A"><b>{txt}</b></font>',
            sty(f"up_{txt}", size=10, bold=True, leading=14,
                align=TA_CENTER, color=C_UP)
        )
    def dn_pct(txt):
        return Paragraph(
            f'<font color="#DC2626"><b>{txt}</b></font>',
            sty(f"dn_{txt}", size=10, bold=True, leading=14,
                align=TA_CENTER, color=C_DOWN)
        )

    def make_pct(pct_str):
        if pct_str.startswith("↑"):
            return up_pct(pct_str)
        elif pct_str.startswith("↓"):
            return dn_pct(pct_str)
        return Paragraph(pct_str, sty("pct", size=10, leading=14, align=TA_CENTER))

    # 表头
    header = [
        Paragraph("赛道", sty("ch0", size=9, bold=True, color=white, align=TA_CENTER, leading=12)),
        Paragraph("信号量", sty("ch1", size=9, bold=True, color=white, align=TA_CENTER, leading=12)),
        Paragraph("环比", sty("ch2", size=9, bold=True, color=white, align=TA_CENTER, leading=12)),
    ]

    rows = [header]
    for item in data:
        row = [
            Paragraph(item["track"], sty(f"tr_{item['track']}", size=10,
                                          color=C_DARK, leading=14)),
            Paragraph(item["count"], sty(f"cnt_{item['count']}", size=11,
                                          color=C_DARK, bold=True,
                                          align=TA_CENTER, leading=14)),
            make_pct(item["pct"]),
        ]
        rows.append(row)

    tbl = Table(rows, colWidths=[CW*0.5, CW*0.25, CW*0.25])
    tbl.setStyle(TableStyle([
        # 表头
        ('BACKGROUND', (0,0), (-1,0), C_ACCENT),
        ('TEXTCOLOR', (0,0), (-1,0), white),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6*mm),
        ('TOPPADDING', (0,0), (-1,-1), 2*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2*mm),
        # 数据行
        ('BACKGROUND', (0,1), (-1,1), white),
        ('BACKGROUND', (0,2), (-1,2), C_LIGHT),
        ('ALIGN', (1,1), (-1,-1), 'CENTER'),
        # 网格
        ('GRID', (0,0), (-1,-1), 0.3, C_BORDER),
        ('LINEBELOW', (0,0), (-1,0), 1, C_ACCENT),
    ]))
    return tbl


# ══════════════════════════════════════════════════════════════════════════════
# 5. 下周关注
# ══════════════════════════════════════════════════════════════════════════════
def build_focus_block(title: str, text: str):
    """黄色背景 + 灰色边框的关注区"""
    # 首行缩进2字符 ≈ 21pt（10.5pt/字符 × 2）
    p = Paragraph(
        f'<b>{title}</b> {text}',
        sty("focus", size=11, color=C_DARK, leading=16,
            leftIndent=5*mm, firstLineIndent=21,
            spaceBefore=2*mm, spaceAfter=2*mm)
    )
    tbl = Table([[p]], colWidths=[CW])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_FOCUS_BG),
        ('BOX', (0,0), (-1,-1), 0.5, C_BORDER),
        ('LEFTPADDING', (0,0), (-1,-1), 5*mm),
        ('RIGHTPADDING', (0,0), (-1,-1), 5*mm),
        ('TOPPADDING', (0,0), (-1,-1), 3*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3*mm),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    return tbl


# ══════════════════════════════════════════════════════════════════════════════
# 页脚
# ══════════════════════════════════════════════════════════════════════════════
TOTAL_PAGES = [0]

class _CountingCanvas(pdfcanvas.Canvas):
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

def draw_footer(c, doc, sources):
    pn = doc.page
    W, H = A4
    c.saveState()
    c.setFont(FONT_SCS, 7)
    c.setFillColor(C_FOOTER)
    msg = (f"本报告仅供授权机构内部使用。数据来源：{sources}。")
    # 距离页面底部 2cm = 20mm
    c.drawCentredString(W / 2, 20*mm, msg)
    c.restoreState()


# ══════════════════════════════════════════════════════════════════════════════
# 主函数
# ══════════════════════════════════════════════════════════════════════════════
def generate_premium_report(
    output_path: str,
    # 基础信息
    date_range: str = "04月21日 — 04月27日",
    main_title: str = "未来产业周报 尊享版",
    subtitle: str = "得分洞见",
    sources: str = "36Kr / IT桔子 / GitHub / arXiv / TechCrunch / HackerNews",
    # 题图
    logo_path: str = "/home/dministrator/.hermes/image_cache/logo_deltafit.png",
    cover_path: str = "/home/dministrator/.hermes/image_cache/img_d628b02701a4.jpg",
    # 本周概览
    overview: dict = None,
    # 国内动态
    domestic_signals: list = None,
    # 国际动态
    international_signals: list = None,
    # 主题趋势
    trend_tags: str = "#大模型推理优化 #Agent框架 #多模态 #开源模型",
    # 周环比
    signal_changes: list = None,
    # 下周关注
    focus_title: str = "月之暗面融资事件",
    focus_text: str = "头部项目获资本认可，行业马太效应加剧",
):
    if overview is None:
        overview = {"total": 42, "domestic": 18, "international": 24, "high_priority": 5}
    if domestic_signals is None:
        domestic_signals = [
            {"no": "01", "category": "融资", "title": "月之暗面完成新一轮融资，估值超20亿美元",
             "desc": "Kimi开发商获红杉等机构投资"},
            {"no": "02", "category": "模型", "title": "智谱AI发布GLM-4开源版本",
             "desc": "支持128K上下文"},
            {"no": "03", "category": "融资", "title": "上海发布大模型产业扶持政策",
             "desc": "最高补贴1000万元"},
        ]
    if international_signals is None:
        international_signals = [
            {"no": "01", "category": "模型", "title": "Llama 3 发布，Meta开源最强开源大模型",
             "desc": "400B参数，支持多模态"},
            {"no": "02", "category": "GitHub", "title": "GitHub Stars 激增：vLLM项目周增长300%",
             "desc": "推理优化框架持续火热"},
            {"no": "03", "category": "论文", "title": "arXiv 论文爆发：Agent相关论文周增45%",
             "desc": "自主Agent成为研究热点"},
        ]
    if signal_changes is None:
        signal_changes = [
            {"track": "AI大模型及应用层", "count": "42", "pct": "↑35%"},
            {"track": "自动驾驶", "count": "28", "pct": "↓15%"},
        ]

    out_stream = io.BytesIO()
    doc = SimpleDocTemplate(
        out_stream,
        pagesize=A4,
        leftMargin=ML, rightMargin=MR,
        topMargin=MT, bottomMargin=MB,
        title=main_title,
        author="DeltaFit",
    )

    story = []

    # ── 顶部 ─────────────────────────────────────────────────────────────────
    story.append(LogoHeader(logo_path, w=CW))
    story.append(Spacer(1, 3*mm))

    if os.path.exists(cover_path):
        story.append(CoverImage(cover_path, w=CW))
        story.append(Spacer(1, 3*mm))

    story.append(TitleBlock(date_range, main_title, subtitle, w=CW))
    story.append(Spacer(1, 2*mm))
    story.append(SourceLine(sources, w=CW))
    story.append(Spacer(1, 6*mm))

    # ── 本周概览 ──────────────────────────────────────────────────────────────
    story.append(section_title("本周概览", space_before=0, space_after=3*mm))
    story.append(build_overview_table(overview))
    story.append(Spacer(1, 6*mm))

    # ── 国内动态 ─────────────────────────────────────────────────────────────
    story.append(section_title("国内动态", space_before=20, space_after=3*mm))
    for p in build_signals_list(domestic_signals):
        story.append(p)
    story.append(Spacer(1, 0))

    # ── 国际动态 ─────────────────────────────────────────────────────────────
    story.append(section_title("国际动态", space_before=16, space_after=3*mm))
    for p in build_signals_list(international_signals):
        story.append(p)
    story.append(Spacer(1, 0))

    # ── 主题趋势 ─────────────────────────────────────────────────────────────
    story.append(section_title("主题趋势", space_before=16, space_after=3*mm))
    story.append(build_trend_tags(trend_tags))
    story.append(Spacer(1, 0))

    # ── 周环比信号量 ─────────────────────────────────────────────────────────
    story.append(section_title("周环比信号量", space_before=16, space_after=3*mm))
    story.append(build_signal_change_table(signal_changes))
    story.append(Spacer(1, 0))

    # ── 下周关注 ─────────────────────────────────────────────────────────────
    story.append(section_title("下周关注", space_before=16, space_after=3*mm))
    story.append(build_focus_block(focus_title, focus_text))

    # ── 页脚 ─────────────────────────────────────────────────────────────────
    def on_page(c, doc):
        draw_footer(c, doc, sources)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page,
              canvasmaker=_CountingCanvas)

    out_stream.seek(0)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(out_stream.read())

    size = os.path.getsize(output_path)
    print(f"✅ PDF 生成完成：{output_path} ({size//1024}KB)")


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    output = "/mnt/e/产业雷达/周报/未来产业周报-尊享版-ReportLab.pdf"
    generate_premium_report(output)
