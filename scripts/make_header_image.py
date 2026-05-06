#!/usr/bin/env python3
"""生成 FIT 几何 Logo（三角 + FIT 字母，纯扁平金色）"""
from PIL import Image, ImageDraw, ImageFont
import math

LOGO_SIZE = 180   # 高度 px
OUT_PATH  = "/mnt/e/产业雷达/周报/fit_logo.png"

def make_fit_logo(out_path=OUT_PATH, size=LOGO_SIZE):
    """生成极简几何 FIT Logo PNG"""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    gold     = "#D4AF37"
    gold_rgb = (212, 175, 55)

    # ── 正三角形参数 ───────────────────────────────────
    # 顶角朝上，底边水平
    # 外三角形：顶点在顶部中心
    tri_margin = size * 0.10   # 边距
    tri_top_y  = tri_margin
    tri_bot_y  = size - tri_margin
    tri_h      = tri_bot_y - tri_top_y
    tri_w      = tri_h / math.sqrt(3) * 2   # 正三角形：边长 = 高×2/√3
    tri_cx     = size / 2
    tri_top_x  = tri_cx
    tri_bl_x   = tri_cx - tri_w / 2
    tri_br_x   = tri_cx + tri_w / 2

    # 画外三角形（描边，不填充）
    outer_pts = [
        (tri_top_x, tri_top_y),
        (tri_br_x,  tri_bot_y),
        (tri_bl_x,  tri_bot_y),
    ]
    draw.polygon(outer_pts, outline=gold_rgb)

    # ── FIT 字母 ────────────────────────────────────────
    # 三角形内区域（留一点 padding）
    pad = tri_h * 0.12
    inner_top_y = tri_top_y + pad
    inner_bot_y = tri_bot_y - pad
    inner_h     = inner_bot_y - inner_top_y

    # 计算 FIT 三个字母的宽度
    # 用默认字体测量（后续可用实际字体替换）
    try:
        font = ImageFont.truetype("/mnt/c/Windows/Fonts/NotoSansSC-VF.ttf", int(inner_h * 0.45))
    except Exception:
        font = ImageFont.load_default()

    # "FIT" 总宽度估算
    letter_spacing = inner_h * 0.20
    letter_h_est   = inner_h * 0.42
    total_text_w   = letter_spacing * 2 + letter_h_est * 2.5  # 粗估

    # 内切椭圆高度（用于确定字母基线）
    inner_cx = tri_cx
    inner_cy = (inner_top_y + inner_bot_y) / 2

    # F I T 三个字母，用矩形笔画模拟几何风格
    lw = max(3, int(inner_h * 0.08))   # 笔画粗细
    letter_w = int(inner_h * 0.30)     # 每个字母宽
    gap      = int(inner_h * 0.12)     # 字母间距

    f_x = inner_cx - (letter_w * 3 + gap * 2) / 2
    i_x = f_x + letter_w + gap
    t_x = i_x + letter_w + gap

    # 字母基线（底部对齐）
    baseline = inner_bot_y - inner_h * 0.05

    # F：两横 + 一竖
    # 上横
    draw.rectangle([f_x, baseline - letter_h_est, f_x + letter_w, baseline - letter_h_est + lw], fill=gold_rgb)
    # 中横
    mid_y = baseline - letter_h_est * 0.55
    draw.rectangle([f_x, mid_y, f_x + letter_w, mid_y + lw], fill=gold_rgb)
    # 竖
    draw.rectangle([f_x, baseline - letter_h_est, f_x + lw, baseline], fill=gold_rgb)

    # I：一竖
    draw.rectangle([i_x, baseline - letter_h_est, i_x + lw, baseline], fill=gold_rgb)

    # T：一横 + 一竖（居中）
    t_mid_x = t_x + letter_w / 2
    draw.rectangle([t_x, baseline - letter_h_est, t_x + letter_w, baseline - letter_h_est + lw], fill=gold_rgb)  # 上横
    draw.rectangle([t_mid_x - lw//2, baseline - letter_h_est, t_mid_x + lw//2, baseline], fill=gold_rgb)  # 竖

    img.save(out_path, "PNG")
    print(f"✅ {out_path} ({size}×{size})")
    return out_path


if __name__ == "__main__":
    make_fit_logo()
