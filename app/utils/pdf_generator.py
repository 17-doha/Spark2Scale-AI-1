import os
import io
import json
import re
import numpy as np
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from datetime import datetime

# --- BRANDING ---
COLOR_PRIMARY = colors.HexColor("#576238")  # Olive
COLOR_ACCENT = colors.HexColor("#ffd95d")   # Mustard
COLOR_BG = colors.HexColor("#F0EADC")       # Cream
COLOR_TEXT = colors.HexColor("#2c3e50")     # Dark Slate

def draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(COLOR_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=True, stroke=False)
    canvas.restoreState()

def find_value(data: dict, possible_keys: list, default="N/A"):
    if not isinstance(data, dict): return default
    # Flatten
    search_data = data.copy()
    if "Content" in data and isinstance(data["Content"], dict): search_data.update(data["Content"])
    if "content" in data and isinstance(data["content"], dict): search_data.update(data["content"])
    
    # Normalize
    norm = {k.lower().replace("_", "").replace(" ", ""): v for k, v in search_data.items()}
    
    for key in possible_keys:
        sk = key.lower().replace("_", "").replace(" ", "")
        if sk in norm: return norm[sk]
    return default

def clean_score(val):
    if isinstance(val, (int, float)): return val
    if not val: return 0
    try:
        match = re.search(r"(\d+(\.\d+)?)", str(val))
        return float(match.group(1)) if match else 0
    except: return 0

def create_radar_chart(scores):
    labels = list(scores.keys())
    stats = [clean_score(v) for v in scores.values()]
    if not stats or sum(stats) == 0: return None
    
    angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
    stats += stats[:1]
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor('#F0EADC')
    ax.set_facecolor('#F0EADC')
    ax.plot(angles, stats, color='#576238', linewidth=2.5)
    ax.fill(angles, stats, color='#ffd95d', alpha=0.5)
    ax.set_ylim(0, 5)
    ax.set_yticklabels(['1', '2', '3', '4', '5'], color="#576238", size=8)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([l.upper() for l in labels], size=9, weight='bold', color="#576238")
    ax.spines['polar'].set_visible(False)
    ax.grid(color='#576238', alpha=0.2)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#F0EADC')
    plt.close()
    buf.seek(0)
    return buf

# =========================================================
# 1. FOUNDER REPORT
# =========================================================
def generate_founder_report(report_data: dict, filename: str):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    s_title = ParagraphStyle('T', parent=styles['Heading1'], fontSize=24, textColor=COLOR_PRIMARY, alignment=TA_CENTER)
    s_head = ParagraphStyle('H', parent=styles['Heading2'], fontSize=18, textColor=COLOR_PRIMARY, spaceBefore=15)
    s_body = ParagraphStyle('B', parent=styles['BodyText'], fontSize=11, textColor=COLOR_TEXT, leading=14)
    
    story = []
    final = find_value(report_data, ["final_report"], {})
    founder = find_value(final, ["founder_output"], {})
    
    # Metadata
    user_json = find_value(report_data.get("team_report", {}), ["user_json_data"], "{}")
    if isinstance(user_json, str): user_json = json.loads(user_json)
    company_name = find_value(find_value(user_json, ["company_snapshot"], {}), ["company_name"], "Startup")

    story.append(Paragraph(f"EVALUATION REPORT: {company_name.upper()}", s_title))
    story.append(Spacer(1, 20))

    # --- SCORECARD ---
    verdict = find_value(founder, ["verdict", "verdict_band"], "Pending")
    score = clean_score(find_value(founder, ["weighted_score", "score"], 0))
    
    t_data = [
        ["VERDICT", "SCORE", "STAGE"],
        [str(verdict).upper(), f"{score:.1f} / 45", "Pre-Seed"]
    ]
    t = Table(t_data, colWidths=[2.3*inch]*3)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('BOX', (0,0), (-1,-1), 1.5, COLOR_PRIMARY),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TEXTCOLOR', (0,0), (-1,-1), COLOR_PRIMARY),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('PADDING', (0,0), (-1,-1), 12)
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    # --- EXEC SUMMARY ---
    story.append(Paragraph("Executive Summary", s_head))
    story.append(Paragraph(str(find_value(founder, ["executive_summary"], "")), s_body))
    story.append(Spacer(1, 15))

    # --- CHART ---
    grid = find_value(founder, ["scorecard_grid"], {})
    img = create_radar_chart(grid)
    if img: story.append(Image(img, width=5*inch, height=5*inch))
    story.append(PageBreak())

    # --- DETAILED ANALYSIS ---
    story.append(Paragraph("Detailed Analysis", s_head))
    dims = find_value(founder, ["dimension_analysis"], [])
    if isinstance(dims, dict): dims = [{"dimension": k, **v} for k,v in dims.items()]

    for d in dims:
        name = find_value(d, ["dimension"], "Area").upper()
        sc = clean_score(find_value(d, ["score"], 0))
        just = find_value(d, ["justification", "reasoning"], "No data")
        conf = find_value(d, ["confidence_level", "confidence"], "Medium")
        imp = find_value(d, ["improvements", "improvement_path", "tactical_fix"], "")
        
        # Header
        story.append(Paragraph(f"<b>{name}</b> ({sc}/5) | <font color='grey' size=9>Confidence: {conf}</font>", s_head))
        # Justification
        story.append(Paragraph(f"<b>Analysis:</b> {just}", s_body))
        
        # Red Flags
        flags = find_value(d, ["red_flags", "risks"], [])
        if flags:
            story.append(Spacer(1, 3))
            if isinstance(flags, list):
                for f in flags: story.append(Paragraph(f"<font color='firebrick'>• {f}</font>", s_body))
            else:
                story.append(Paragraph(f"<font color='firebrick'>• {flags}</font>", s_body))

        # Improvement
        if imp:
            story.append(Spacer(1, 5))
            i_text = imp if isinstance(imp, str) else "; ".join(imp)
            story.append(Paragraph(f"<b>[LAUNCH] Fix:</b> {i_text}", ParagraphStyle('fix', parent=s_body, textColor=colors.darkgreen)))
            
        story.append(Spacer(1, 10))
        story.append(Paragraph("_"*50, ParagraphStyle('l', parent=s_body, textColor=COLOR_PRIMARY)))

    story.append(PageBreak())

    # --- PRIORITIES ---
    story.append(Paragraph("Top 3 Execution Priorities", s_head))
    # Broader search for keys
    pris = find_value(founder, ["top_3_priorities", "priorities", "execution_priorities", "top_3_execution_priorities"], [])
    
    if pris and isinstance(pris, list):
        for i, p in enumerate(pris):
            story.append(Paragraph(f"<b>{i+1}.</b> {p}", s_body))
            story.append(Spacer(1, 8))
    else:
        story.append(Paragraph("No specific priorities listed.", s_body))

    doc.build(story, onFirstPage=draw_background, onLaterPages=draw_background)

# =========================================================
# 2. INVESTOR MEMO
# =========================================================
def generate_investor_report(report_data: dict, filename: str):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    s_title = ParagraphStyle('T', parent=styles['Heading1'], fontSize=24, textColor=COLOR_PRIMARY, alignment=TA_CENTER)
    s_head = ParagraphStyle('H', parent=styles['Heading2'], fontSize=18, textColor=COLOR_PRIMARY, spaceBefore=15)
    s_body = ParagraphStyle('B', parent=styles['BodyText'], fontSize=11, textColor=COLOR_TEXT)
    
    final = find_value(report_data, ["final_report"], {})
    investor = find_value(final, ["investor_output"], {})
    founder = find_value(final, ["founder_output"], {}) # Fallback source

    story = []
    story.append(Paragraph("INVESTMENT MEMO (CONFIDENTIAL)", s_title))
    story.append(Spacer(1, 20))

    # Summary
    verdict = find_value(investor, ["verdict"], "Review")
    score = clean_score(find_value(investor, ["weighted_score"], 0))
    
    t_data = [["VERDICT", "SCORE"], [str(verdict).upper(), f"{score:.1f} / 45"]]
    t = Table(t_data, colWidths=[3.5*inch, 3.5*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), COLOR_ACCENT),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 15)
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    # Text Sections
    story.append(Paragraph("Executive Summary", s_head))
    story.append(Paragraph(find_value(investor, ["executive_summary"], ""), s_body))
    
    story.append(Paragraph("🚩 Deal Breakers", s_head))
    flags = find_value(investor, ["deal_breakers"], [])
    if isinstance(flags, list):
        for f in flags: story.append(Paragraph(f"• {f}", ParagraphStyle('r', parent=s_body, textColor=colors.firebrick)))
    else:
        story.append(Paragraph(str(flags), s_body))

    # --- SCORECARD GRID ---
    story.append(Paragraph("Scorecard", s_head))
    grid = find_value(investor, ["scorecard_grid"], {})
    if grid:
        t_rows = [["Category", "Score"]]
        for k, v in grid.items():
            t_rows.append([k.upper(), f"{clean_score(v)}/5"])
        
        t_s = Table(t_rows, colWidths=[4*inch, 2*inch])
        t_s.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, COLOR_PRIMARY),
            ('BACKGROUND', (0,0), (0,-1), colors.white)
        ]))
        story.append(t_s)

    # --- DIMENSION RATIONALES (The Fix) ---
    story.append(Paragraph("Dimension Rationales", s_head))
    
    # 1. Try Investor Output first
    rationales = find_value(investor, ["dimension_rationales"], [])
    
    # 2. Robust Fallback: Build from Founder Output if missing
    if not rationales or rationales == "N/A":
        # Extract from founder details
        f_dims = find_value(founder, ["dimension_analysis"], [])
        if isinstance(f_dims, dict): f_dims = list(f_dims.values())
        
        rationales = []
        for d in f_dims:
            dim_name = find_value(d, ["dimension"], "Unknown")
            # Prefer "justification", fall back to "reasoning"
            reason = find_value(d, ["justification", "reasoning"], "No data")
            rationales.append({"dimension": dim_name, "rationale": reason})

    # Render
    if isinstance(rationales, list):
        for r in rationales:
            # Handle if r is dict or tuple
            if isinstance(r, dict):
                d = find_value(r, ["dimension"], "Dim")
                t = find_value(r, ["rationale", "reasoning", "bottom_line"], "")
            else: continue
            
            story.append(Paragraph(f"<b>{str(d).upper()}:</b> {t}", s_body))
            story.append(Spacer(1, 6))

    doc.build(story, onFirstPage=draw_background, onLaterPages=draw_background)