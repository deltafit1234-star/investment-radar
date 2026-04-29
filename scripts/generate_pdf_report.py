#!/usr/bin/env python3
"""
得分洞见 · 投资雷达 — PDF 日报生成器
"""
import os, sys, sqlite3, re, io
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT = "/mnt/c/Windows/Fonts/NotoSansSC-VF.ttf"
if not os.path.exists(FONT):
    FONT = "/mnt/c/Windows/Fonts/simhei.ttf"
pdfmetrics.registerFont(TTFont("NotoSansSC", FONT))

BRAND_BLUE  = HexColor("#1A3A5C")
BRAND_GOLD  = HexColor("#C9A84C")
BRAND_GRAY  = HexColor("#6B7280")
TEXT_DARK   = HexColor("#1F2937")
WHITE       = HexColor("#FFFFFF")
BORDER_GRAY = HexColor("#E5E7EB")

TRACK_COLORS = {
    "AI大模型及应用层": HexColor("#4F46E5"),
    "自动驾驶":         HexColor("#059669"),
    "脑机接口":         HexColor("#7C3AED"),
    "人形机器人":       HexColor("#D97706"),
    "新能源/电池":      HexColor("#16A34A"),
    "半导体/芯片":      HexColor("#DC2626"),
}

TODAY = date.today().strftime("%Y年%m月%d日")
W, H  = A4
TOTAL_PAGES = [0]

def _hex(c):
    return "%06x" % int(c.hexval(), 16)

def _sty(name, **kw):
    b = dict(fontName="NotoSansSC", textColor=TEXT_DARK, leading=12)
    b.update(kw)
    return ParagraphStyle(name, **b)

ST = {
    "brand_title": _sty("bt", fontSize=22, textColor=BRAND_BLUE, leading=28, alignment=TA_CENTER, spaceAfter=1*mm),
    "brand_sub":   _sty("bs", fontSize=10, textColor=BRAND_GOLD, leading=14, alignment=TA_CENTER, spaceAfter=1*mm),
    "date":        _sty("dt", fontSize=9,  textColor=BRAND_GRAY, leading=12, alignment=TA_CENTER, spaceAfter=3*mm),
    "h1":          _sty("h1", fontSize=12, textColor=WHITE, leading=16),
    "overview":    _sty("ov", fontSize=8,  textColor=BRAND_GRAY, leading=10, spaceAfter=1*mm),
    "body":        _sty("bd", fontSize=8,  textColor=TEXT_DARK, leading=11, spaceAfter=1),
    "footer":      _sty("ft", fontSize=6.5, textColor=BRAND_GRAY, leading=8, alignment=TA_CENTER),
    "num":         _sty("nm", fontSize=7.5, textColor=BRAND_GRAY, leading=9),
    "sig":         _sty("sg", fontSize=8,  textColor=TEXT_DARK, leading=11),
}

TOTAL_PAGES = [0]

def _draw_hf(c, doc):
    c.saveState()
    pn = doc.page
    # 顶栏
    c.setFillColor(BRAND_BLUE)
    c.rect(0, H - 12*mm, W, 12*mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("NotoSansSC", 9)
    c.drawString(10*mm, H - 8*mm, "得 分 洞 察")
    c.setFont("NotoSansSC", 7)
    c.setFillColor(HexColor("#A0AEC0"))
    c.drawString(10*mm, H - 11*mm, "投资雷达 · 每日产业情报")
    c.setFont("NotoSansSC", 7.5)
    c.drawRightString(W - 10*mm, H - 8*mm, f"{pn} / {TOTAL_PAGES[0]}")
    # 底栏
    c.setFillColor(BRAND_BLUE)
    c.rect(0, 0, W, 8*mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#A0AEC0"))
    c.setFont("NotoSansSC", 6.5)
    c.drawCentredString(W/2, 2.5*mm, f"投资雷达 · {TODAY} · 机密 — 仅供授权机构内部使用")
    c.restoreState()

def fetch(db):
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "SELECT track_name, report_text, signal_count FROM daily_reports "
        "WHERE report_date='2026-04-29' ORDER BY signal_count DESC"
    )
    return [(r[0], r[1], r[2]) for r in cur.fetchall()]

def parse(text):
    if not text:
        return []
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("◆"):
            continue
        rest = line[1:].strip()
        title, body = rest, ""
        if ":" in rest:
            parts = rest.split(":", 1)
            title = re.sub(r"\[.*?\]", "", parts[0]).strip()
            body  = parts[1].strip()
        else:
            title = re.sub(r"\[.*?\]", "", title).strip()
        if title:
            out.append({"title": title, "body": body[:55]})
    return out

def sig_table(signals):
    rows = []
    for i, s in enumerate(signals[:8]):
        rows.append([
            Paragraph(f'<font color="#6B7280">{i+1:02d}</font>', ST["num"]),
            Paragraph(
                f'<font color="#1F2937">{s["title"]}</font>'
                f'<br/><font color="#6B7280" size="7">{s["body"]}</font>',
                ST["sig"]),
        ])
    if not rows:
        return Paragraph("（暂无信号数据）", ST["body"])
    t = Table(rows, colWidths=[10*mm, 172*mm], splitByRow=1)
    t.setStyle(TableStyle([
        ("ALIGN",       (0, 0), (0, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",  (0, 0), (-1, -1), 2.2*mm),
        ("BOTTOMPADDING",(0,0), (-1, -1), 2.2*mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 2*mm),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2*mm),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.2, BORDER_GRAY),
    ]))
    return t

def track_hdr(name, color):
    hex_c = "#%06x" % int(color.hexval(), 16)
    return Paragraph(
        f'<font color="white"><b>{name}</b></font>',
        _sty("th", fontName="NotoSansSC", fontSize=9, textColor=HexColor(hex_c),
             backColor=HexColor(hex_c), leading=13,
             leftIndent=5*mm, rightIndent=5*mm,
             spaceBefore=1*mm, spaceAfter=1*mm))

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

def make_story(reports):
    s = []
    # 封面
    s.append(Spacer(1, 5*mm))
    s.append(Paragraph("得 分 洞 察", ST["brand_title"]))
    s.append(Paragraph("投资雷达 · 每日产业情报", ST["brand_sub"]))
    s.append(Paragraph(f"报告日期：{TODAY}", ST["date"]))
    s.append(HRFlowable(width="100%", thickness=1.2, color=BRAND_GOLD, spaceAfter=2*mm, spaceBefore=1*mm))
    s.append(HRFlowable(width="100%", thickness=0.4, color=BORDER_GRAY, spaceAfter=3*mm))
    # 各赛道
    for track_name, raw_text, _ in reports:
        tc = TRACK_COLORS.get(track_name, BRAND_BLUE)
        signals = parse(raw_text)
        s.append(track_hdr(track_name, tc))
        s.append(Spacer(1, 1.5*mm))
        s.append(Paragraph(f'<font color="#6B7280"><b>信号</b> 共 {len(signals)} 条</font>', ST["overview"]))
        s.append(Spacer(1, 2*mm))
        s.append(sig_table(signals) if signals else Paragraph("（报告生成中…）", ST["body"]))
        s.append(Spacer(1, 5*mm))
    # 免责声明
    s.append(HRFlowable(width="100%", thickness=0.4, color=BORDER_GRAY, spaceBefore=2*mm, spaceAfter=2*mm))
    s.append(Paragraph("本报告由 AI 自动生成，仅供参考，不构成任何投资建议。投资有风险，决策需谨慎。", ST["footer"]))
    s.append(Paragraph("得分洞察 投资雷达  ·  数据来源：arXiv / TechCrunch / 36Kr / IT桔子  ·  请勿对外传播", ST["footer"]))
    return s

def generate(reports, out_path):
    story = make_story(reports)

    # Pass 1: 用 PageCounter 统计页数
    buf = io.BytesIO()
    counter = PageCounter(buf, pagesize=A4)
    SimpleDocTemplate(buf, pagesize=A4,
                     leftMargin=10*mm, rightMargin=10*mm,
                     topMargin=18*mm, bottomMargin=14*mm
    ).build(story[:], canvasmaker=lambda *a, **kw: counter)
    total = TOTAL_PAGES[0]
    buf.close()
    print(f"  页数统计: {total}", file=sys.stderr)

    # Pass 2: 正式写入文件
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                           leftMargin=10*mm, rightMargin=10*mm,
                           topMargin=18*mm, bottomMargin=14*mm,
                           title=f"投资雷达日报 {TODAY}",
                           author="得分洞察 · 投资雷达")
    # 用 _hf_with_total 显示页码
    def hf(c, doc):
        TOTAL_PAGES[0] = total  # 固定总数
        _draw_hf(c, doc)

    doc.build(story, onFirstPage=hf, onLaterPages=hf)
    sz = os.path.getsize(out_path)
    print(f"✅ {out_path}  ({total}页, {sz//1024}KB)")

if __name__ == "__main__":
    db = "/mnt/c/Users/Admin/Desktop/investment-radar/data/radar.db"
    out = "/mnt/e/dailyReports/daily_report_2026-04-29.pdf"
    os.makedirs("/mnt/e/dailyReports", exist_ok=True)
    reports = fetch(db)
    print(f"读取 {len(reports)} 份报告")
    generate(reports, out)
