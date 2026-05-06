#!/usr/bin/env python3
"""
投资雷达 - DOCX 模板渲染工具
纯 stdlib XML + PyMuPDF (fitz)，无外部依赖（python-docx/lxml 都不要）

流程:
  1. 解压 DOCX (zip)
  2. 用 xml.etree 操作 XML，替换 {{变量}} 和处理 SIGNAL_ROW 表格循环
  3. 重新打包 DOCX
  4. PyMuPDF 渲染 DOCX → PDF

用法:
  from render_report import render_report, signals_to_template_data
  pdf_path = render_report("template.docx", data, "output.pdf")
"""

import sys
import os
import re
import shutil
import zipfile
import tempfile
import json
import copy
from pathlib import Path
from typing import Dict, List, Any, Optional
from xml.etree import ElementTree as ET

# ─── Constants ────────────────────────────────────────────────────────────────
SIGNAL_ROW_MARKER = "{{ SIGNAL_ROW }}"
VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# Word XML namespace
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing")
ET.register_namespace("a", "http://schemas.openxmlformats.org/drawingml/2006/main")
ET.register_namespace("pic", "http://schemas.openxmlformats.org/drawingml/2006/picture")
ET.register_namespace("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
ET.register_namespace("w15", "http://schemas.microsoft.com/office/word/2012/wordml")

W = f"{{{W_NS}}}"

# Pre-compile XPath-friendly tag names
TAG_R = f"{W}r"
TAG_T = f"{W}t"
TAG_P = f"{W}p"
TAG_PPR = f"{W}pPr"
TAG_RPR = f"{W}rPr"
TAG_TR = f"{W}tr"
TAG_TBL = f"{W}tbl"
TAG_TC = f"{W}tc"


# ══════════════════════════════════════════════════════════════════════════════
# XML manipulation helpers (stdlib only)
# ══════════════════════════════════════════════════════════════════════════════

def _get_para_full_text(para) -> str:
    """Get all text from a paragraph element."""
    texts = []
    for t in para.iter(TAG_T):
        if t.text:
            texts.append(t.text)
    return "".join(texts)


def _clear_para_runs(para):
    """Remove all <w:r> children from a paragraph element."""
    for r in list(para.findall(TAG_R)):
        para.remove(r)


def _make_run(para, text: str, font: str = "微软雅黑", color: str = "000000",
              size: str = "24", bold: bool = False) -> None:
    """Add a <w:r> run with text to a paragraph."""
    r = ET.SubElement(para, TAG_R)

    if bold or font or color or size:
        rPr = ET.SubElement(r, TAG_RPR)

        if font:
            rFonts = ET.SubElement(rPr, f"{W}rFonts")
            rFonts.set(f"{W}ascii", font)
            rFonts.set(f"{W}hAnsi", font)
            rFonts.set(f"{W}eastAsia", font)
            rFonts.set(f"{W}cs", font)

        if color:
            c = ET.SubElement(rPr, f"{W}color")
            c.set(f"{W}val", color)

        if size:
            sz = ET.SubElement(rPr, f"{W}sz")
            sz.set(f"{W}val", size)
            szCs = ET.SubElement(rPr, f"{W}szCs")
            szCs.set(f"{W}val", size)

        if bold:
            b = ET.SubElement(rPr, f"{W}b")

    t = ET.SubElement(r, TAG_T)
    t.set(f"{W}xml:space", "preserve")
    t.text = text


def _get_run_formatting(r) -> Dict[str, str]:
    """Extract formatting from a run element."""
    rpr = r.find(TAG_RPR)
    if rpr is None:
        return {"font": "微软雅黑", "color": "000000", "size": "24"}
    result = {"font": "微软雅黑", "color": "000000", "size": "24"}
    rf = rpr.find(f"{W}rFonts")
    if rf is not None:
        result["font"] = rf.get(f"{W}eastAsia", "微软雅黑")
    rc = rpr.find(f"{W}color")
    if rc is not None:
        result["color"] = rc.get(f"{W}val", "000000")
    sz = rpr.find(f"{W}sz")
    if sz is not None:
        result["size"] = sz.get(f"{W}val", "24")
    return result


def _is_signal_placeholder_row(tr) -> bool:
    """Check if a table row contains SIGNAL_ROW_MARKER in any cell."""
    for tc in tr.findall(TAG_TC):
        for p in tc.findall(TAG_P):
            if SIGNAL_ROW_MARKER in _get_para_full_text(p):
                return True
    return False


def _get_signal_list_name(tr) -> Optional[str]:
    """Get the signal list variable name from a SIGNAL_ROW placeholder row."""
    for tc in tr.findall(TAG_TC):
        for p in tc.findall(TAG_P):
            text = _get_para_full_text(p)
            m = VAR_RE.search(text)
            if m:
                return m.group(1)
    return None


def _copy_row(tr, tbl) -> None:
    """Deep-copy a table row and append it to the table."""
    import copy
    new_tr = copy.deepcopy(tr)
    tbl.append(new_tr)


def _fill_table_signal_row(tr, signal: Dict[str, Any]) -> None:
    """Fill field placeholders in a signal row."""
    for tc in tr.findall(TAG_TC):
        for p in tc.findall(TAG_P):
            full_text = _get_para_full_text(p)
            if "{{" not in full_text:
                continue

            # Get formatting from first run
            fmt = {"font": "微软雅黑", "color": "000000", "size": "24"}
            first_r = p.find(TAG_R)
            if first_r is not None:
                fmt = _get_run_formatting(first_r)

            def replacer(m):
                key = m.group(1)
                val = signal.get(key, "")
                return str(val) if val is not None else ""

            new_text = VAR_RE.sub(replacer, full_text)
            if new_text == full_text:
                continue

            _clear_para_runs(p)
            _make_run(p, new_text, **fmt)


# ══════════════════════════════════════════════════════════════════════════════
# Main render function
# ══════════════════════════════════════════════════════════════════════════════

def render_report(
    template_path: str,
    data: Dict[str, Any],
    output_path: str,
    docx_only: bool = False,
) -> str:
    """
    Fill DOCX template with data and convert to PDF.

    Uses stdlib xml.etree + PyMuPDF (fitz) — no python-docx, no lxml needed.
    """
    import fitz  # PyMuPDF

    template_path = Path(template_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmpdir = Path(tempfile.mkdtemp(prefix="render_docx_"))
    try:
        # ── Step 1: Extract DOCX ───────────────────────────────────────────────
        with zipfile.ZipFile(template_path, "r") as z:
            z.extractall(tmpdir)

        doc_xml_path = tmpdir / "word" / "document.xml"

        # ── Step 2: Parse XML ─────────────────────────────────────────────────
        # Register all namespaces found in the document to avoid ns0: prefixes
        with open(doc_xml_path, "rb") as f:
            raw = f.read()

        # Collect namespace declarations from the XML
        ns_pattern = re.compile(r'xmlns(?::(\w+))?="([^"]+)"')
        for prefix, uri in ns_pattern.findall(raw.decode("utf-8")):
            ET.register_namespace(prefix or "w", uri)

        # Re-read with namespace awareness
        tree = ET.parse(doc_xml_path)
        root = tree.getroot()

        # Build a map of namespace prefixes → URIs for SubElement compatibility
        nsmap_raw = copy.copy(root.attrib)
        for k, v in nsmap_raw.items():
            if k.startswith("{"):
                prefix = k[1:].split("}")[0] if "}" in k else ""
                # Already registered
                pass

        changed = False

        # ── Step 2a: Replace {{ variables }} in paragraphs ──────────────────
        # Supports two modes:
        #   - str value: replaces with single text run (existing behavior)
        #   - list value: replaces placeholder paragraph with N paragraphs (one per item)
        for para in root.iter(TAG_P):
            full_text = _get_para_full_text(para)
            if "{{" not in full_text:
                continue

            # Collect formatting from first run
            fmt = {"font": "微软雅黑", "color": "000000", "size": "24"}
            first_r = para.find(TAG_R)
            if first_r is not None:
                rpr = first_r.find(TAG_RPR)
                if rpr is not None:
                    rf = rpr.find(f"{W}rFonts")
                    if rf is not None:
                        fmt["font"] = rf.get(f"{W}eastAsia", "微软雅黑")
                    rc = rpr.find(f"{W}color")
                    if rc is not None:
                        fmt["color"] = rc.get(f"{W}val", "000000")
                    sz = rpr.find(f"{W}sz")
                    if sz is not None:
                        fmt["size"] = sz.get(f"{W}val", "24")

            # Determine replacement value
            m_var = VAR_RE.search(full_text)
            if not m_var:
                continue
            key = m_var.group(1)
            val = data.get(key, "")

            # Get parent body to insert new paragraphs (if list mode)
            body = root.find(f".//{TAG_P}/..")
            if body is None:
                body = root  # fallback

            def _make_para_with_text(text: str) -> "ET.Element":
                """Create a new w:p element with one run containing text."""
                new_p = ET.Element(TAG_P)
                # Copy paragraph properties (pPr) if present
                pPr = para.find(TAG_PPR)
                if pPr is not None:
                    new_ppr = copy.deepcopy(pPr)
                    new_p.append(new_ppr)
                _make_run(new_p, text, **fmt)
                return new_p

            if isinstance(val, list):
                # List mode: replace placeholder paragraph with N paragraphs
                items = [str(v) for v in val if str(v).strip()]
                if not items:
                    continue

                # Recursive parent finder
                def find_parent_of(target, node, parent=None):
                    """Find parent of target element by DFS. Returns (parent, index_in_parent)."""
                    for child in list(node):
                        if child is target:
                            return node, list(node).index(child)
                        result = find_parent_of(target, child, node)
                        if result[0] is not None:
                            return result
                    return None, None

                parent, idx = find_parent_of(para, root)
                if parent is None:
                    continue

                # Remove original runs from placeholder (keep paragraph structure)
                for r in para.findall(TAG_R):
                    para.remove(r)

                # First item goes into the existing placeholder paragraph
                _make_run(para, items[0], **fmt)

                # Remaining items are inserted as new paragraphs after
                insert_idx = idx + 1
                for item in items[1:]:
                    new_p = _make_para_with_text(item)
                    parent.insert(insert_idx, new_p)
                    insert_idx += 1

                changed = True

            else:
                # String mode: existing behavior
                new_text = str(val)
                if not new_text.strip():
                    continue

                def replacer(m2):
                    k = m2.group(1)
                    v = data.get(k, "")
                    return str(v) if v is not None else ""

                new_text = VAR_RE.sub(replacer, full_text)
                if new_text == full_text:
                    continue

                # Remove all runs
                for r in para.findall(TAG_R):
                    para.remove(r)
                _make_run(para, new_text, **fmt)
                changed = True

        # ── Step 2b: Handle SIGNAL_ROW table rows ─────────────────────────────
        for tbl in root.iter(TAG_TBL):
            tbl_children = list(tbl)
            rows_to_remove = []
            rows_to_insert = {}  # {insert_position: [(row_xml, signal_data)]}

            for i, tr in enumerate(tbl_children):
                if tr.tag != TAG_TR:
                    continue
                if not _is_signal_placeholder_row(tr):
                    continue

                list_name = _get_signal_list_name(tr)
                signals: List[Dict] = data.get(list_name, [])

                rows_to_remove.append(i)

                if not signals:
                    changed = True
                    continue

                # Clone rows for each signal
                for si, sig in enumerate(signals):
                    new_tr = copy.deepcopy(tr)
                    _fill_table_signal_row(new_tr, sig)
                    rows_to_insert[(i + si, new_tr)] = None

                changed = True

            # Remove placeholder rows (in reverse to maintain indices)
            for i in reversed(rows_to_remove):
                tbl.remove(list(tbl_children)[i])

            # Insert new rows at correct positions
            for insert_pos, new_tr in sorted(rows_to_insert.keys(), key=lambda x: x[0]):
                tbl.insert(insert_pos, new_tr)

        # ── Step 3: Write modified XML ────────────────────────────────────────
        if changed:
            # Serialize back preserving declaration
            xml_bytes = ET.tostring(root, encoding="unicode").encode("utf-8")
            with open(doc_xml_path, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n')
                f.write(xml_bytes)

        # ── Step 4: Repack DOCX ───────────────────────────────────────────────
        tmp_docx = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp_docx.close()

        with zipfile.ZipFile(tmp_docx.name, "w", zipfile.ZIP_DEFLATED) as zout:
            for file_path in tmpdir.rglob("*"):
                if file_path.is_file():
                    arcname = str(file_path.relative_to(tmpdir))
                    zout.write(file_path, arcname)

        if docx_only:
            # Rename to .docx
            docx_output = output_path.with_suffix(".docx")
            shutil.copy(tmp_docx.name, str(docx_output))
            os.unlink(tmp_docx.name)
            return str(docx_output)

        # ── Step 5: PyMuPDF DOCX → PDF via image rendering ───────────────────
        # PyMuPDF's native save() doesn't work reliably for DOCX→PDF.
        # Use image rendering approach: render each page to PNG at high DPI, then combine.
        doc = fitz.open(tmp_docx.name)
        pdf_doc = fitz.open()

        # 3x scale for print-quality rendering (3 * 72 = 216 DPI)
        scale = 3.0
        mat = fitz.Matrix(scale, scale)

        for i in range(doc.page_count):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat)
            img_path = tmpdir / f"page_{i}.png"
            pix.save(str(img_path))

            # Create PDF page matching the image dimensions
            pdf_page = pdf_doc.new_page(width=pix.width, height=pix.height)
            pdf_page.insert_image(pdf_page.rect, filename=str(img_path))

        doc.close()
        os.unlink(tmp_docx.name)

        pdf_path = output_path.with_suffix(".pdf")
        pdf_doc.save(str(pdf_path), deflate=True)
        pdf_doc.close()

        return str(pdf_path)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# Data helpers
# ══════════════════════════════════════════════════════════════════════════════

TYPE_EMOJI = {
    "funding_news": "💰 融资",
    "model_news": "🤖 模型",
    "policy_news": "📰 政策",
    "tech_breakthrough": "🔬 技术",
    "market_news": "📈 市场",
    "hackathon": "🏆 赛事",
    "product_launch": "🚀 产品",
    "hackernot_hot": "🔥 HackerNews",
    "arxiv_new": "📚 论文",
    "github_trending": "⭐ GitHub",
    "techcrunch": "🌐 TechCrunch",
    "default": "📌",
}


def _is_domestic(sig) -> bool:
    """Determine if a signal is domestic (China-related) based on signal_type."""
    sig_type = sig.get("signal_type", "").lower()
    # signal_type IS the source category here (funding_news=domestic, hackernews_hot=intl, etc.)
    domestic_types = {"funding_news", "model_news", "policy_news", "market_news", "product_launch"}
    return sig_type in domestic_types


def format_signal(s: Dict) -> Dict[str, str]:
    sig_type = s.get("signal_type", "default")
    emoji = TYPE_EMOJI.get(sig_type, TYPE_EMOJI["default"])

    created = s.get("created_at", "")
    if created:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(created.replace("Z", "+00:00").split("+")[0])
            date_str = dt.strftime("%m月%d日")
        except Exception:
            date_str = created[:10]
    else:
        date_str = ""

    return {
        "type": emoji,
        "title": (s.get("title") or "")[:80],
        "org": (s.get("content") or "")[:40],
        "date": date_str,
        "source": s.get("source_id", ""),
        "priority": s.get("priority", ""),
    }


def _format_signal_text(s: Dict) -> str:
    """Format a signal as a single-line text string for template rendering."""
    emoji = TYPE_EMOJI.get(s.get("signal_type", "default"), TYPE_EMOJI["default"])
    title = (s.get("title") or "")[:80]
    source = s.get("source_id", "")
    created = s.get("created_at", "")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00").split("+")[0])
            date_str = dt.strftime("%m月%d日")
        except Exception:
            date_str = created[:10]
    else:
        date_str = ""
    return f"{emoji} {title} | {source} | {date_str}"


def signals_to_template_data(
    signals: List[Dict],
    track_name: str,
    week_start: str,
    week_end: str,
    edition: str = "尊享版",
) -> Dict[str, Any]:
    domestic = [s for s in signals if _is_domestic(s)]
    international = [s for s in signals if not _is_domestic(s)]
    high_prio = [s for s in signals if s.get("priority") == "high"]

    # Format as plain text strings for docxtpl template
    domestic_contents = [_format_signal_text(s) for s in domestic]
    international_contents = [_format_signal_text(s) for s in international]

    main_trends = [
        f"• {s.get('title', '')[:60]}"
        for s in sorted(high_prio, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
    ] or ["本周暂无高优先级信号"]

    return {
        "week_range": f"{week_start} — {week_end}",
        "total_signals": str(len(signals)),
        "domestic_count": str(len(domestic)),
        "international_count": str(len(international)),
        "high_priority_count": str(len(high_prio)),
        "main_trends": main_trends,
        "signal_change_trends": "↑ 信号量较上周上升",
        # Template variable names (domestic/foreign NOT domestic_signals)
        "domestic_contents": domestic_contents,
        "international_contents": international_contents,
        "theme_analysis": "本周赛道活跃，AI应用层持续火热",
        "next_week_focus": "持续关注政策动态及大模型融资",
        "edition": edition,
        "track_name": track_name,
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Render DOCX template → PDF")
    parser.add_argument("template", help="DOCX template path")
    parser.add_argument("data_json", help="JSON file with template data")
    parser.add_argument("output", help="Output file path (without extension)")
    parser.add_argument("--docx-only", action="store_true", help="Only output DOCX")
    args = parser.parse_args()

    with open(args.data_json) as f:
        data = json.load(f)

    result = render_report(args.template, data, args.output, docx_only=args.docx_only)
    print(f"✅ Output: {result}")
