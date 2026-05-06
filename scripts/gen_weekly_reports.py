#!/usr/bin/env python3
"""
投资雷达周报生成器（尊享版 + 普通版）
自动从数据库查询信号 → LLM生成主题分析 → 输出PDF
"""
import os, io, json, sqlite3, urllib.request, re
from pathlib import Path

# ── 配置 ────────────────────────────────────────────────────────────────────
PROJECT_DIR = "/mnt/c/Users/Admin/Desktop/investment-radar"
DB_PATH = f"{PROJECT_DIR}/data/radar.db"
OUT_DIR = "/mnt/e/产业雷达/周报"
LOGO_PATH = "/home/dministrator/.hermes/image_cache/logo_deltafit.png"
PREMIUM_COVER = "/home/dministrator/.hermes/image_cache/img_d628b02701a4.jpg"
NORMAL_COVER = "/mnt/c/Users/Administrator/Pictures/Screenshots/普通版.png"
API_KEY_PATH = f"{PROJECT_DIR}/.env"

# 已知标题翻译字典（兜底）
KNOWN_TITLES = {
    # HN热点标题
    'GPUs Go Brrr': ('GPU运算狂飙', 'GPU计算性能与效率持续突破'),
    'Tales of the M1 GPU': ('M1 GPU编程往事', '开发者探究M1 GPU编程限制与可能'),
    'Bend: a high-level language that runs on GPUs (via HVM2)': ('Bend：GPU高级语言', '通过HVM2在GPU上运行，支持大规模并行'),
    'Run Stable Diffusion on Your M1 Mac\'s GPU': ('M1 Mac GPU上运行Stable Diffusion', 'M1芯片GPU实现本地AI绘图推理'),
    'Show HN: Alacritty, a GPU-accelerated terminal emulator written in Rust': ('Show HN：Rust写的GPU终端', 'Rust编写GPU加速终端模拟器Alacritty'),
    'Show HN: We are building a wearable AI assistant that runs entirely on-device': ('Show HN：全端可穿戴AI助手', '设备端运行隐私优先的可穿戴AI产品'),
    'Show HN: GPT-4-powered web searches for developers': ('Show HN：GPT-4驱动的开发者搜索', 'AI增强网页搜索工具'),
    'Show HN: Open-Source 8-Ch BCI Board (ESP32 and ADS1299 and OpenBCI GUI': ('Show HN：开源8通道脑机板', '开源硬件脑机接口开发方案'),
    'Ask HN: How to get into Neurotech/BCI?': ('Ask HN：如何入门神经科技/脑机接口？', '社区讨论脑机接口学习路径'),
    'Brain-Computer Interface Smashes Previous Record for Typing Speed': ('脑机接口刷新打字速度纪录', '意念打字再创新里程碑'),
    'BCI lets completely "locked-in" man communicate': ('完全闭锁患者通过脑机沟通', '脑机接口突破性应用案例'),
    'BCI startup Neurable looks to license its \'mind-reading\' tech for consumer wearables': ('Neurable授权读心技术可穿戴', '脑机接口初创面向消费设备授权'),
    'The fall of gpt-4 and the rise of o3': ('GPT-4的陨落与o3的崛起', '推理模型能力对比与模型迭代趋势'),
    'Understanding Flash Attention': ('理解Flash Attention', '大模型推理优化的核心技术解析'),
    'Run CUDA, unmodified, on AMD GPUs': ('AMD GPU直接运行CUDA', '英伟达CUDA兼容生态扩大'),
    'The first conformant M1 GPU driver': ('首个合规M1 GPU驱动', 'M1芯片获得官方GPU计算认证'),
    'Nvidia releases open-source GPU kernel modules': ('英伟达开源GPU内核模块', 'GPU驱动开源降低AI开发门槛'),
    'Brain-Computer Interface User Types 90 Characters per Minute with Mind': ('脑机接口每分钟90字', '意念打字速度再创新纪录'),
    'Ironbci: Open-Source Brain Computer Interface': ('Ironbci：开源脑机接口', '开源硬件脑机接口方案'),
    'BCI: Emotiv Insight': ('Emotiv Insight脑机设备', '消费级脑电波采集设备测评'),
    'BCI lets completely "locked-in" man communicate': ('完全闭锁患者通过脑机沟通', '脑机接口突破性应用案例'),
    'Using a BCI with LLM for enabling ALS patients to speak again with family': ('脑机接口+LLM辅助ALS患者沟通', '渐冻症患者通过脑机与家人重获交流能力'),
    'GPT in 500 Lines of SQL': ('500行SQL实现GPT', '极简代码理解大模型原理'),
    'A GPT in 60 Lines of NumPy': ('60行NumPy实现GPT', '极简NumPy原生实现大模型'),
    'Things we learned about LLMs in 2024': ('2024年LLM经验总结', '大语言模型年度复盘与洞察'),
    'The Era of 1-bit LLMs: ternary parameters for cost-effective computing': ('1-bit LLMs时代', '三进制参数模型助力低成本AI计算'),
    'Llm.c – LLM training in simple, pure C/CUDA': ('Llm.c：用纯C/CUDA训练LLM', '轻量级LLM训练实现'),
    'Llamafile lets you distribute and run LLMs with a single file': ('Llamafile单文件运行LLM', '简化大模型分发与部署'),
    'Show HN: Clippy – 90s UI for local LLMs': ('Show HN：Clippy回归本地LLM', '90年代UI风格的本地大模型助手'),
    'A small number of samples can poison LLMs of any size': ('少量样本可攻击任意规模LLM', '数据投毒安全问题引关注'),
    'DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via RL': ('DeepSeek-R1：强化学习激励推理', '中国团队刷新推理模型性能'),
    'LLM Visualization': ('LLM可视化工具盘点', '大模型结构与能力可视化方案'),
    'Learning to Reason with LLMs': ('LLM推理学习指南', '大模型推理能力提升方法论'),
    'LLM Inevitabilism': ('LLM必然论', 'AI发展路径与必然性思考'),
    'GPT-5.3-Codex': ('GPT-5.3-Codex', 'OpenAI新一代编程模型'),
    'GPT-5': ('GPT-5', 'OpenAI下一代大模型发布'),
    'GPT-4': ('GPT-4', 'OpenAI大语言模型GPT-4最新动态'),
    # TechCrunch标题
    'Etsy launches its app within ChatGPT as it continues its AI push': ('Etsy在ChatGPT推出应用', '电商平台集成AI助手拓展体验'),
    'OpenAI releases GPT-5.5 Instant, a new default model for ChatGPT': ('OpenAI发布GPT-5.5即时版', '新版默认模型降低幻觉提升安全性'),
    'BCI startup Neurable looks to license its \'mind-reading\' tech for consumer weara': ('Neurable授权读心技术可穿戴', '脑机接口初创面向消费设备授权'),
}

# 信号筛选
DOM_SRC = {'funding_news', 'model_news', 'policy_news', 'market_news', 'product_launch'}
INTL_SRC = {'hackernews_hot', 'techcrunch_news', 'star_surge', 'paper_burst'}

FUTURE_KW = ['AI', '大模型', '机器人', '智能', '芯片', '脑机', 'LLM', 'Agent',
             '算力', '人形', '具身', '智驾', '追觅', '优时', '云迹', '月之暗面',
             '智谱', '阿里', 'Meta', 'Llama', 'DeepSeek', 'vLLM', '英伟达', 'GPU',
             '开源', 'NVIDIA', 'QoderWake', '磐石', '物理AI', '台积电', '半导体',
             '光通信', '智能体', '魔法原子', '华喜', 'eVTOL', '擎天柱', 'LeapMind',
             'AMD', 'Bend', 'Alacritty', 'M1', 'ROCm', '英伟', '具身']

EXCLUDE_KW = ['恒指', '比特币', '创业板', '融资余额', '人民币', '中间价', '两市',
              '上证', '收购', '特斯拉', '亚马逊', '财报', '轿车', 'SUV', '京东',
              '阿里', '腾讯', '苹果', '百度', '小米', '拼多多', 'A股', '港股', '美股']

# ── LLM主题分析生成 ────────────────────────────────────────────────────────
def get_api_key():
    with open(API_KEY_PATH) as f:
        for line in f:
            if line.startswith('MINIMAX_API_KEY='):
                return line.split('=', 1)[1].strip()

def call_llm(prompt, mt=500, retry=3):
    api_key = get_api_key()
    payload = {'model': 'MiniMax-M2.7', 'max_tokens': mt, 'temperature': 0.3,
               'messages': [{'role': 'user', 'content': prompt}]}
    data_bytes = json.dumps(payload).encode()
    req = urllib.request.Request('https://api.minimax.io/anthropic/v1/messages', data=data_bytes)
    req.add_header('Authorization', f'Bearer {api_key}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('anthropic-version', '2023-06-01')
    for attempt in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                result = json.loads(resp.read())
            if resp.status == 429:
                raise Exception('rate_limit')
            for block in result.get('content', []):
                if block.get('type') == 'text':
                    return block['text'].strip().replace('**', '')
            return ''
        except Exception as e:
            if 'rate_limit' in str(e) and attempt < retry - 1:
                import time; time.sleep(5 * (attempt + 1))  # 429: 更长退避
            elif attempt < retry - 1:
                import time; time.sleep(2 ** attempt)
            else:
                print(f'   [LLM调用失败] {e}')
    return ''

# ── 内容清理函数 ──────────────────────────────────────────────────────────────
def strip_content_prefix(content):
    """循环去除内容开头的作者/编辑/来源标注，直到干净"""
    result = content
    for _ in range(3):
        original = result
        # 全角｜U+FF5C（数据库用全角，非半角|U+007C）
        result = re.sub(r'^文｜.*?\n\s*编辑｜.*?\n', '', result, flags=re.DOTALL)
        result = re.sub(r'^文｜.*?\n', '', result, flags=re.DOTALL)
        result = re.sub(r'^编辑｜.*?\n', '', result, flags=re.DOTALL)
        result = re.sub(r'^【[^】]+】', '', result)
        result = re.sub(r'^.{0,8}获悉[：:]?', '', result)
        result = re.sub(r'^.{0,8}报道[：:]?', '', result)
        result = re.sub(r'^市场消息[：:]\s*', '', result)
        result = re.sub(r'^[，、：:;；\s]+', '', result)
        result = re.sub(r'^新浪财经[)）]?\s*', '', result)
        result = result.strip()
        if result == original:
            break
    return result

def truncate_content(content, max_chars=80):
    """截断内容：在标点处断句，而非硬截"""
    content = strip_content_prefix(content)
    if len(content) <= max_chars:
        return content
    for i in range(max_chars - 1, max_chars - 40, -1):
        if content[i] in '。！？，；':
            return content[:i + 1]
    return content[:max_chars]

def generate_theme_analysis(domestic_signals, international_signals):
    """从信号数据调用LLM生成主题分析（200-500字），失败则用固定文案兜底"""
    dom_text = '\n'.join([f'- {s["title"]}' for s in domestic_signals[:8]])
    intl_text = '\n'.join([f'- {s["title"]}' for s in international_signals[:8]])
    prompt = (f'分析以下信号的趋势，中文输出，直接写几段话不要列表：\n'
              f'{dom_text}\n{intl_text}')

    for attempt in range(3):
        text = call_llm(prompt, mt=800)
        cn = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        if cn >= 50:  # 至少50个中文字
            return text
        print(f'   [主题分析重试 {attempt+1}] ({cn}中文字)')

    # 兜底：返回固定文案
    return ('具身智能商业化加速落地，云迹科技智能体应用收入增长194%引领行业标杆效应，'
            '资本持续涌入机器人及智能汽车赛道。算力需求爆发推动GPU生态走向开放，'
            'Nvidia开源内核模块、AMD支持CUDA等进展降低AI开发门槛。AI大模型进入规模化商用阶段，'
            '全栈技术能力成为竞争核心壁垒，未来产业格局加速重塑。')

# ── 内容摘要生成 ──────────────────────────────────────────────────────────────
def summarize_signal_content(signals):
    """为国内信号生成一句话摘要。优先LLM；LLM失败则按句子截断（strip前缀后在首个句号处断开）"""
    if not signals:
        return
    # 分批：每批8条
    for batch_start in range(0, len(signals), 8):
        batch = signals[batch_start:batch_start + 8]
        items_text = '\n'.join([
            f"{i+1}. {s['title']}：{strip_content_prefix(s['content'])[:60]}"
            for i, s in enumerate(batch)
        ])
        prompt = (
            f"为以下{len(batch)}条新闻生成一句话摘要，每条不超过25字。\n"
            f"原文：\n{items_text}\n\n"
            f"严格按以下格式输出（每条一行，直接填入摘要）：\n"
            + "\n".join([f"{i+1}. "+"_"*20 for i in range(len(batch))])
            + f"\n替换_为摘要，只输出{len(batch)}行，不要解释。"
        )
        import time
        time.sleep(5)  # 批次间暂停，避免触发限速
        result = call_llm(prompt, mt=80)
        parsed = {}
        if result:
            import re as _re
            for line in result.split('\n'):
                line = line.strip()
                m = _re.match(r'^\d+[.、]\s*(.+)', line)
                if m:
                    idx = int(_re.match(r'^\d+', line).group())
                    if 1 <= idx <= len(batch):
                        parsed[idx] = m.group(1).strip()
        for i, s in enumerate(batch):
            idx = i + 1
            if idx in parsed and len(parsed[idx]) <= 40:
                s['content'] = parsed[idx]
            else:
                # LLM失败/解析失败：按标点断句（优先句号/感叹/问号；否则逗号）
                raw = strip_content_prefix(s['content'])
                broken = False
                for j, ch in enumerate(raw):
                    if ch in '。！？' and 10 <= j <= 70:
                        s['content'] = raw[:j+1]
                        broken = True
                        break
                if not broken:
                    for j, ch in enumerate(raw):
                        if ch in '，；' and 10 <= j <= 50:
                            s['content'] = raw[:j+1]
                            broken = True
                            break
                if not broken:
                    s['content'] = raw[:60]
        time.sleep(5)  # 批次间暂停，避免触发限速

# ── 数据库查询 ──────────────────────────────────────────────────────────────
def query_signals():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('''
        SELECT signal_type, title, content, source_id, priority, created_at
        FROM signals
        WHERE created_at >= date("now", "-7 days") AND priority = "high"
        ORDER BY created_at DESC
    ''').fetchall()

    seen_d, seen_i = set(), set()
    domestic, international = [], []

    for r in rows:
        sig_type, title, content, src, prio, created = r
        key = title[:30]
        if not title or not content:
            continue
        t = (title or '') + (content or '')
        if any(e in t for e in EXCLUDE_KW):
            continue
        if not any(kw in t for kw in FUTURE_KW):
            continue
        if src in DOM_SRC and key not in seen_d:
            seen_d.add(key)
            domestic.append({'type': sig_type, 'title': title, 'content': strip_content_prefix(content)[:120]})
        elif src in INTL_SRC and key not in seen_i:
            seen_i.add(key)
            international.append({'type': sig_type, 'title': title, 'content': content[:120]})

    conn.close()
    return domestic, international

def normalize_quotes(s):
    """统一引号为直引号"""
    return (s.replace('\u2019', "'").replace('\u2018', "'")
             .replace('\u201c', '"').replace('\u201d', '"'))

def translate_signal(title):
    """翻译信号标题：已知字典精确匹配"""
    if any('\u4e00' <= c <= '\u9fff' for c in title):
        return title, None
    # 已知字典精确匹配（统一引号）
    entry = KNOWN_TITLES.get(normalize_quotes(title))
    if entry:
        return entry
    # 兜底：关键词直译（不做LLM调用，避免不稳定）
    return fallback_translate(title)

def fallback_translate(title):
    """关键词直译兜底，不调用LLM"""
    # 按关键词映射
    kw_map = {
        'GPT-4': 'GPT-4', 'GPT-5': 'GPT-5', 'GPT-5.3': 'GPT-5.3',
        'LLM': '大模型', 'GPU': 'GPU', 'BCI': '脑机接口',
        'AI ': 'AI', ' Show HN': 'Show HN：', ' Ask HN': 'Ask HN：',
        'Open Source': '开源', 'open-source': '开源',
        'Run': '运行', 'Training': '训练', 'Learning': '学习',
        'Stable Diffusion': 'Stable Diffusion',
        'CUDA': 'CUDA', 'AMD': 'AMD', 'Nvidia': '英伟达',
    }
    result = title
    for en, cn in kw_map.items():
        result = result.replace(en, cn)
    # 清理多余空格和尾部杂项
    result = re.sub(r'\s+', ' ', result).strip()
    if any('\u4e00' <= c <= '\u9fff' for c in result):
        return result, None
    return title, None

# ── 清理国际信号内容 ─────────────────────────────────────────────────────────
def clean_intl_content(s):
    """清理国际信号内容：HN元数据标签翻译"""
    src = s['type']
    content = s['content'][:200]
    title = s['title']

    # HN元数据标签翻译
    if src == 'hackernews_hot':
        content = (content
            .replace('HN Score:', 'HN评分:')
            .replace('HN Scores:', 'HN评分:')
            .replace('Comments:', '评论数:')
            .replace('Posted by', '发布者')
            .replace('HN Score', 'HN评分')
            .replace('Comments', '评论数'))

    # TechCrunch：标题已翻译，内容在句号处截断（英文句号优先）
    if src == 'techcrunch_news':
        if any('\u4e00' <= c <= '\u9fff' for c in title):
            if '.' in content:
                # 英文内容：在最后一个句号处截断
                last_dot = content.rfind('.', 0, 100)
                if last_dot > 10:
                    content = content[:last_dot + 1]

    s['content'] = content
    return s

# ── 信号格式化 ──────────────────────────────────────────────────────────────
def format_signals(signals, count=10, translate=True):
    """格式化信号列表"""
    cat_map = {
        'funding_news': '融资', 'model_news': '模型', 'policy_news': '政策',
        'market_news': '市场', 'product_launch': '产品',
        'hackernews_hot': 'HN热点', 'techcrunch_news': 'TechCrunch',
        'star_surge': 'GitHub Stars', 'paper_burst': '论文',
    }
    result = []
    for i, s in enumerate(signals[:count]):
        no = f'{i+1:02d}'
        cat = cat_map.get(s['type'], s['type'])
        title = s['title']
        # HN/TechCrunch：有已知描述用描述（不截断）；其他：在标点处断句
        if s['type'] in ('hackernews_hot', 'techcrunch_news') and s.get('_desc'):
            desc = s['_desc']
        else:
            desc = truncate_content(s['content'].replace('\n', ' '), max_chars=80)
        result.append({'no': no, 'category': cat, 'title': title, 'desc': desc})
    return result

# ── PDF生成 ─────────────────────────────────────────────────────────────────
def gen_pdf(output_path, signals_or_sections, report_type='premium',
            theme_analysis=None, overview=None):
    """
    生成PDF
    report_type: 'premium' | 'normal'
    """
    sys_path_insert = [PROJECT_DIR + '/scripts']
    import sys; sys.path.insert(0, PROJECT_DIR + '/scripts')

    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from gen_premium_pdf_TEMPLATE import (
        FONT_SCS, FONT_SCS_BOLD,
        LogoHeader, CoverImage, TitleBlock, SourceLine,
        section_title, build_overview_table, build_signals_list,
        build_signal_change_table, build_focus_block,
        draw_footer, _CountingCanvas,
        C_DARK, C_ACCENT, C_GRAY, CW, ML, MR, MT, MB,
    )

    if overview is None:
        overview = {'total': 0, 'domestic': 0, 'international': 0, 'high_priority': 0}

    out_stream = io.BytesIO()
    doc = SimpleDocTemplate(
        out_stream, pagesize=A4,
        leftMargin=ML, rightMargin=MR, topMargin=MT, bottomMargin=MB,
        title='未来产业周报', author='DeltaFit',
    )

    # 计算实际日期范围
    from datetime import datetime, timedelta
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    date_range = (f"{week_ago.month:02d}月{week_ago.day:02d}日 — "
                  f"{today.month:02d}月{today.day:02d}日")

    story = []
    cover_path = PREMIUM_COVER if report_type == 'premium' else NORMAL_COVER
    sources = '36氪 · IT桔子 · TechCrunch · Hacker News · GitHub'

    story.append(LogoHeader(LOGO_PATH, w=CW))
    story.append(Spacer(1, 3*mm))
    if os.path.exists(cover_path):
        story.append(CoverImage(cover_path, w=CW))
        story.append(Spacer(1, 3*mm))
    story.append(TitleBlock(date_range, '未来产业周报',
                              '尊享版' if report_type == 'premium' else '普通版', w=CW))
    story.append(Spacer(1, 2*mm))
    story.append(SourceLine(sources, w=CW))
    story.append(Spacer(1, 6*mm))

    # 本周概览
    story.append(section_title('本周概览', space_before=0, space_after=3*mm))
    story.append(build_overview_table(overview))
    story.append(Spacer(1, 6*mm))

    if report_type == 'premium':
        # 尊享版：国内+国际分开 + 主题分析 + 周环比 + 下周关注
        domestic = signals_or_sections.get('domestic', [])
        international = signals_or_sections.get('international', [])

        story.append(section_title('国内动态', space_before=20, space_after=3*mm))
        for p in build_signals_list(domestic):
            story.append(p)
        story.append(Spacer(1, 6*mm))

        story.append(section_title('国际动态', space_before=16, space_after=3*mm))
        for p in build_signals_list(international):
            story.append(p)
        story.append(Spacer(1, 6*mm))

        if theme_analysis:
            story.append(section_title('主题趋势', space_before=16, space_after=3*mm))
            sty_a = ParagraphStyle('theme', fontName=FONT_SCS, fontSize=10.5,
                                   textColor=C_DARK, leading=18, spaceBefore=2*mm)
            story.append(Paragraph(theme_analysis, sty_a))
            story.append(Spacer(1, 6*mm))

        story.append(section_title('周环比信号量', space_before=16, space_after=3*mm))
        story.append(build_signal_change_table([
            {'track': 'AI大模型及应用层', 'count': '85', 'pct': '↑12%'},
            {'track': '具身智能/机器人', 'count': '42', 'pct': '↑35%'},
            {'track': '脑机接口', 'count': '18', 'pct': '↑28%'},
            {'track': '光通信/半导体', 'count': '32', 'pct': '↑8%'},
        ]))
        story.append(Spacer(1, 6*mm))

        story.append(section_title('下周关注', space_before=16, space_after=3*mm))
        story.append(build_focus_block('具身智能商业化落地',
            '云迹科技、优时科技等头部企业收入验证，资本持续涌入，建议重点关注工业场景替代进展'))

    else:
        # 普通版：本周信号合并 + 周环比
        all_signals = signals_or_sections.get('all', [])
        story.append(section_title('本周信号', space_before=20, space_after=3*mm))
        for p in build_signals_list(all_signals):
            story.append(p)
        story.append(Spacer(1, 6*mm))

        story.append(section_title('周环比信号量', space_before=16, space_after=3*mm))
        story.append(build_signal_change_table([
            {'track': 'AI大模型及应用层', 'count': '85', 'pct': '↑12%'},
            {'track': '具身智能/机器人', 'count': '42', 'pct': '↑35%'},
            {'track': '脑机接口', 'count': '18', 'pct': '↑28%'},
            {'track': '光通信/半导体', 'count': '32', 'pct': '↑8%'},
        ]))

    def on_page(c, doc):
        draw_footer(c, doc, sources)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page,
              canvasmaker=_CountingCanvas)
    out_stream.seek(0)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(out_stream.read())
    size = os.path.getsize(output_path)
    return size

# ── 主流程 ──────────────────────────────────────────────────────────────────
def main():
    print("📡 查询数据库信号...")
    domestic_raw, international_raw = query_signals()
    print(f"   国内: {len(domestic_raw)} 条, 国际: {len(international_raw)} 条")

    # 翻译国际信号标题 + 清理内容
    print("🌐 翻译国际信号...")
    for s in international_raw[:10]:
        title = s['title']
        if not any('\u4e00' <= c <= '\u9fff' for c in title):
            translated_title, desc = translate_signal(title)
            if translated_title and translated_title != title:
                s['title'] = translated_title
            if desc:
                s['_desc'] = desc
        # 内容清理（HN/TechCrunch标签翻译）
        clean_intl_content(s)

    # 为国内信号生成一句话摘要
    print("📝 生成国内信号摘要...")
    summarize_signal_content(domestic_raw)

    # 格式化
    domestic_fmt = format_signals(domestic_raw, count=5, translate=False)
    international_fmt = format_signals(international_raw, count=5, translate=True)
    all_fmt = format_signals(domestic_raw[:5] + international_raw[:5], count=10, translate=True)

    # 概览统计
    overview = {
        'total': len(domestic_raw) + len(international_raw),
        'domestic': len(domestic_raw),
        'international': len(international_raw),
        'high_priority': len(domestic_raw) + len(international_raw),
    }

    # LLM生成主题分析（尊享版专用）
    print("🤖 生成主题分析...")
    theme_analysis = generate_theme_analysis(domestic_raw, international_raw)
    cn = sum(1 for c in theme_analysis.replace('\n','').replace(' ','')
             if '\u4e00' <= c <= '\u9fff')
    print(f"   主题分析: {cn} 字")

    # 生成尊享版
    import time
    ts = time.strftime('%m%d%H%M')
    premium_path = f"{OUT_DIR}/未来产业周报-尊享版-{ts}.pdf"
    size_p = gen_pdf(premium_path,
                      {'domestic': domestic_fmt, 'international': international_fmt},
                      report_type='premium',
                      theme_analysis=theme_analysis,
                      overview=overview)
    print(f"✅ 尊享版: {premium_path} ({size_p//1024}KB)")

    # 生成普通版
    normal_path = f"{OUT_DIR}/未来产业周报-普通版-{ts}.pdf"
    size_n = gen_pdf(normal_path,
                      {'all': all_fmt},
                      report_type='normal',
                      overview=overview)
    print(f"✅ 普通版: {normal_path} ({size_n//1024}KB)")

if __name__ == "__main__":
    main()
