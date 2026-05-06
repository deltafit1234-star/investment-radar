#!/usr/bin/env python3
"""
投资雷达 - 每日报告生成 + 推送
Phase 2 ProtoType — 尊享版每日报告（6赛道×6份/天）
个人化「您的关注动态」仅对付费租户显示
"""
import sys, os, json, time
from pathlib import Path
from datetime import datetime, timedelta

# ── 环境变量 ─────────────────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in open(env_path):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.gen_weekly_reports import gen_pdf
from scripts.track_system import (
    get_tenant_subscription, get_personalized_signals,
    list_subscription_packages, match_signal_for_subscriptions,
    get_db
)

OUT_DIR = Path(os.environ.get("REPORT_OUT_DIR", "/mnt/e/产业雷达/日报"))

# ── 赛道配置 ─────────────────────────────────────────────────────────────────
TRACKS = [
    ("AI大模型及应用层", ["AI大模型", "大模型", "LLM", "ChatGPT", "GPT", "AIGC", "文生视频", "文生图", "Agent", "AI Agent"]),
    ("具身智能/机器人", ["具身智能", "机器人", "人形机器人", "自动驾驶", "无人机", "智能驾驶"]),
    ("脑机接口", ["脑机接口", "BCI", "Neuralink", "神经接口", "意念控制"]),
    ("光通信/半导体", ["光通信", "半导体", "芯片", "GPU", "HBM", "IC设计", "封装测试"]),
    ("生物科技/生命科学", ["基因编辑", "mRNA", "合成生物", "AI制药", "蛋白组学", "细胞治疗"]),
    ("新能源/新材料", ["固态电池", "钠离子", "钙钛矿", "光伏", "氢能", "新材料"]),
]

# ── 查询最近N小时信号 ─────────────────────────────────────────────────────────
def query_recent_signals(hours=24, limit=100):
    conn = get_db()
    cur = conn.cursor()
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        SELECT id, title, content, signal_type, source_id, priority, track_id, created_at
        FROM signals
        WHERE created_at >= ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (since, limit))
    rows = cur.fetchall()
    conn.close()
    signals = []
    for r in rows:
        s = {
            "id": r[0], "title": r[1] or "", "content": r[2] or "",
            "signal_type": r[3], "source_id": r[4],
            "priority": r[5], "track_id": r[6], "created_at": r[7]
        }
        # 清理内容
        from scripts.gen_weekly_reports import strip_content_prefix
        s["content"] = strip_content_prefix(s["content"])
        signals.append(s)
    return signals

# ── 信号分配到赛道 ────────────────────────────────────────────────────────────
def assign_to_track(signal):
    title = signal.get("title", "")
    content = signal.get("content", "")
    text = title + " " + content
    for track_name, keywords in TRACKS:
        for kw in keywords:
            if kw in text:
                return track_name
    return "其他"

def group_by_track(signals):
    tracks = {t[0]: [] for t in TRACKS}
    tracks["其他"] = []
    for s in signals:
        t = assign_to_track(s)
        tracks[t].append(s)
    return tracks

# ── 赛道信号格式化 ────────────────────────────────────────────────────────────
def format_track_signals(track_signals, track_name, count_per_track=3):
    """每个赛道最多取count_per_track条，格式：标题 + 一句话摘要"""
    from scripts.gen_weekly_reports import strip_content_prefix, truncate_content
    results = []
    for s in track_signals[:count_per_track]:
        title = s.get("title", "")[:60]
        content = s.get("content", "")
        # 生成简短摘要（内容前80字或句号处截断）
        if content:
            summary = truncate_content(content, max_chars=60)
        else:
            summary = ""
        results.append({"title": title, "summary": summary, "signal_type": s.get("signal_type", "")})
    return results

# ── 生成每日报告 ──────────────────────────────────────────────────────────────
def build_daily_sections(signals_by_track):
    """构建报告sections（用于gen_pdf的normal类型）"""
    sections = []
    for track_name, _ in TRACKS:
        track_sigs = signals_by_track.get(track_name, [])
        if not track_sigs:
            continue
        formatted = format_track_signals(track_sigs, track_name)
        sections.append({
            "track": track_name,
            "signals": formatted,
            "count": len(track_sigs)
        })
    # 其他赛道
    other = signals_by_track.get("其他", [])
    if other:
        formatted = format_track_signals(other, "其他")
        sections.append({"track": "其他", "signals": formatted, "count": len(other)})
    return sections

# ── gen_pdf normal 类型的 sections 格式支持 ───────────────────────────────────
# 现有gen_pdf接受 'all' (list) 或 'domestic'+'international' (dict)
# 为daily report扩展：接受 {'tracks': [...]} 格式

def gen_daily_pdf(output_path, signals_by_track, personalized=None,
                  report_date=None, theme=None):
    """
    生成每日PDF
    signals_by_track: dict[track_name] -> list[signal_dict]
    personalized: personalied signals dict
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import ParagraphStyle
    from scripts.gen_premium_pdf_TEMPLATE import (
        FONT_SCS, FONT_SCS_BOLD, C_DARK, C_LIGHT, C_ACCENT,
        section_title, sty
    )
    import reportlab.platypus as platypus

    OUT_PATH = Path(output_path)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(OUT_PATH),
        pagesize=A4,
        rightMargin=18*mm, leftMargin=18*mm,
        topMargin=15*mm, bottomMargin=15*mm
    )

    story = []

    # 标题区
    date_str = report_date or datetime.now().strftime("%Y年%m月%d日")
    title_style = ParagraphStyle('dtitle', fontName=FONT_SCS_BOLD, fontSize=16,
                                   textColor=C_DARK, spaceAfter=4*mm)
    story.append(Paragraph(f"未来产业情报 {date_str}", title_style))

    sub_style = ParagraphStyle('dsub', fontName=FONT_SCS, fontSize=9,
                                 textColor=C_DARK, spaceAfter=6*mm)
    total = sum(len(v) for v in signals_by_track.values())
    story.append(Paragraph(f"共 {total} 条信号 · 6大赛道覆盖", sub_style))
    story.append(Spacer(1, 4*mm))

    # 赛道章节
    for track_name, _ in TRACKS:
        track_sigs = signals_by_track.get(track_name, [])
        if not track_sigs:
            continue
        formatted = format_track_signals(track_sigs, track_name)
        count = len(track_sigs)

        # 赛道标题
        track_style = ParagraphStyle('track', fontName=FONT_SCS_BOLD, fontSize=12,
                                      textColor=C_ACCENT, spaceBefore=6*mm, spaceAfter=2*mm)
        story.append(Paragraph(f"{track_name}（{count}条）", track_style))

        for item in formatted:
            sig_type_style = ParagraphStyle('st', fontName=FONT_SCS_BOLD, fontSize=8.5,
                                              textColor=C_ACCENT, spaceBefore=1.5*mm, spaceAfter=0)
            story.append(Paragraph(f"[{item['signal_type']}] {item['title']}", sig_type_style))
            if item['summary']:
                sum_style = ParagraphStyle('sum', fontName=FONT_SCS, fontSize=8,
                                             textColor=C_DARK, leading=12, spaceAfter=0.5*mm)
                story.append(Paragraph(f"  {item['summary']}", sum_style))

    # 个人化章节
    if personalized:
        co = personalized.get('company_signals', [])
        kw = personalized.get('keyword_signals', [])
        if co or kw:
            story.append(Spacer(1, 6*mm))
            story.append(section_title('您的关注动态', space_before=6*mm, space_after=3*mm))
            if co:
                from collections import defaultdict
                by_co = defaultdict(list)
                for s in co:
                    by_co[s.get('matched_company', '未知')].append(s)
                for company, sigs in by_co.items():
                    co_style = ParagraphStyle('co', fontName=FONT_SCS_BOLD, fontSize=9,
                                               textColor=C_ACCENT, spaceBefore=2*mm, spaceAfter=0.5*mm)
                    story.append(Paragraph(f"🏢 {company}（{len(sigs)}条）", co_style))
                    for s in sigs[:5]:
                        t = s.get('title', '')[:50]
                        sty_t = ParagraphStyle('cod', fontName=FONT_SCS, fontSize=8.5,
                                               textColor=C_DARK, leading=12)
                        story.append(Paragraph(f"  · {t}", sty_t))
            if kw:
                kw_style = ParagraphStyle('kw', fontName=FONT_SCS_BOLD, fontSize=9,
                                           textColor=C_ACCENT, spaceBefore=3*mm, spaceAfter=0.5*mm)
                story.append(Paragraph(f"🔍 关键词订阅（{len(kw)}条）", kw_style))
                for s in kw[:5]:
                    t = s.get('title', '')[:50]
                    sty_t = ParagraphStyle('kd', fontName=FONT_SCS, fontSize=8.5,
                                            textColor=C_DARK, leading=12)
                    story.append(Paragraph(f"  · {t}", sty_t))

    # 页脚
    footer_style = ParagraphStyle('foot', fontName=FONT_SCS, fontSize=7, textColor=C_DARK,
                                    alignment=1, spaceBefore=8*mm)
    story.append(Paragraph("投资雷达 · DeltaFit · 每日更新", footer_style))

    doc.build(story)
    return OUT_PATH.stat().st_size

# ── 主流程 ────────────────────────────────────────────────────────────────────
def main(tenant_id=None, hours=24):
    tenant_id = tenant_id or os.environ.get("SYSTEM_TENANT_ID", "o9cq801RJ2JWK_pnZsCG4ATRP_t8@im.wechat")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[日报] 开始生成 {datetime.now().strftime('%Y-%m-%d %H:%M')} (过去{hours}h)", flush=True)

    # 1. 查询信号
    signals = query_recent_signals(hours=hours)
    print(f"   信号: {len(signals)} 条", flush=True)
    if not signals:
        print("   无新信号，跳过", flush=True)
        return

    # 2. 分配赛道
    by_track = group_by_track(signals)
    total = len(signals)
    print(f"   赛道分布: " + " / ".join(f"{k}({len(v)})" for k, v in by_track.items() if v), flush=True)

    # 3. 个人化
    personalized = None
    sub = get_tenant_subscription(tenant_id)
    if sub and sub.get('has_personalized_report'):
        personalized = get_personalized_signals(tenant_id, days=1, limit=20)
        co = len(personalized.get('company_signals', []))
        kw = len(personalized.get('keyword_signals', []))
        if co or kw:
            print(f"   📌 个人化: 公司{co}条 + 关键词{kw}条", flush=True)

    # 4. 生成PDF
    date_str = datetime.now().strftime("%m%d")
    pdf_path = OUT_DIR / f"未来产业日报-{date_str}.pdf"
    size = gen_daily_pdf(pdf_path, by_track, personalized=personalized,
                         report_date=datetime.now().strftime("%Y年%m月%d日"))
    print(f"   ✅ 日报: {pdf_path} ({size//1024}KB)", flush=True)
    return str(pdf_path)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default=None)
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()
    result = main(tenant_id=args.tenant, hours=args.hours)
    if result:
        print(f"OUTPUT:{result}")
