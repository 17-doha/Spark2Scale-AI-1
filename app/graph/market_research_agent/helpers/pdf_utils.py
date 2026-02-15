import os
import glob
import pandas as pd
import platform
import arabic_reshaper
from bidi.algorithm import get_display
from fpdf import FPDF

from app.core.config import Config, gemini_client
from app.core.rate_limiter import call_gemini
from app.graph.market_research_agent import prompts
from app.graph.market_research_agent.logger_config import get_logger
from app.graph.market_research_agent.research_config import (
    ResearchConfig, 
    calculate_realistic_opportunity_score,
    get_competition_level
)
import json
import asyncio
import re

logger = get_logger("PDFUtils")

def generate_report(file_path: str, query: str, trend_file=None, finance_file=None):
    """
    Generate executive summary report with realistic opportunity scoring
    """
    logger.info(f"\n📝 [Tool 5] Synthesizing Data & Calculating Realistic Opportunity Score...")
    
    # ========================================
    # 1. LOAD VALIDATION DATA
    # ========================================
    pain_score = 50
    evidence_count = 0
    confidence = "Unknown"
    val_data = ""
    
    if file_path and os.path.exists(file_path):
        with open(file_path, 'r') as f: 
            val_data = f.read()
            try: 
                d = json.loads(val_data)
                pain_score = d.get('pain_score', 50)  # This is now the adjusted score
                evidence_count = d.get('evidence_quality', {}).get('total_count', 0)
                confidence = d.get('confidence', 'Unknown')
                
                logger.info(f"   📊 Pain Score: {pain_score}/100 (Confidence: {confidence}, Evidence: {evidence_count} sources)")
            except Exception as e:
                logger.warning(f"   ⚠️ Error parsing validation data: {e}")

    # ========================================
    # 2. LOAD TREND DATA
    # ========================================
    growth_pct = 0
    trend_summary = "No trend data."
    
    if trend_file and os.path.exists(trend_file):
        try:
            stats = pd.read_csv("data_output/market_stats.csv")
            growth_row = stats[stats['metric'] == 'growth_pct']
            if not growth_row.empty:
                growth_pct = float(growth_row.iloc[0]['value'])
                trend_summary = f"12-Month Growth: {growth_pct:.1f}%"
                logger.info(f"   📈 Market Growth: {growth_pct:.1f}%")
        except Exception as e:
            logger.warning(f"   ⚠️ Error reading trend data: {e}")

    # ========================================
    # 3. LOAD FINANCIAL DATA
    # ========================================
    finance_summary = "No financial projections available."
    startup_cost = 0
    monthly_profit = 0
    break_even = 99
    
    if finance_file and os.path.exists(finance_file):
        try:
            df_fin = pd.read_csv(finance_file)
            finance_summary = df_fin.to_string(index=False)
            
            # Extract key metrics
            for _, row in df_fin.iterrows():
                metric = row.get('Metric', '')
                if metric == 'Total Startup':
                    startup_cost = row.get('Value', 0)
                elif metric == 'Net Profit':
                    monthly_profit = row.get('Value', 0)
                elif metric == 'Break-Even Month':
                    break_even = row.get('Value', 99)
            
            logger.info(f"   💰 Startup Cost: {startup_cost}, Break-Even: Month {break_even}")
        except Exception as e:
            logger.warning(f"   ⚠️ Error reading finance data: {e}")

    # ========================================
    # 4. LOAD COMPETITOR DATA
    # ========================================
    competitor_count = 0
    competitors_file = glob.glob(f"data_output/{query.replace(' ', '_')}_competitors.csv")
    
    if competitors_file:
        try:
            df_comp = pd.read_csv(competitors_file[0])
            competitor_count = len(df_comp)
            logger.info(f"   🏢 Competitors Found: {competitor_count}")
        except Exception as e:
            logger.warning(f"   ⚠️ Error reading competitor data: {e}")

    # ========================================
    # 5. LOAD MARKET SIZING DATA
    # ========================================
    market_size_score = 50  # Default middle score
    tam_value = "Unknown"
    sam_value = "Unknown"
    som_value = "Unknown"
    
    if os.path.exists("data_output/market_sizing.json"):
        try:
            with open("data_output/market_sizing.json", "r") as f:
                sizing_data = json.load(f)
                tam_value = sizing_data.get('tam_value', 'Unknown')
                sam_value = sizing_data.get('sam_value', 'Unknown')
                som_value = sizing_data.get('som_value', 'Unknown')
                
                # Score based on market size (simple heuristic)
                # Extract numeric value from strings like "$5 Billion"
                def extract_value(size_str):
                    try:
                        # Remove $, commas, and extract number
                        clean = re.sub(r'[^\d.]', '', size_str.split()[0])
                        num = float(clean)
                        
                        # Adjust for unit (Million vs Billion)
                        if 'Billion' in size_str or 'billion' in size_str:
                            num *= 1000
                        elif 'Trillion' in size_str or 'trillion' in size_str:
                            num *= 1000000
                        
                        return num
                    except:
                        return 0
                
                sam_numeric = extract_value(sam_value)
                
                # Score: <$10M = 20, $10-100M = 50, $100M-1B = 70, >$1B = 90
                if sam_numeric < 10:
                    market_size_score = 20
                elif sam_numeric < 100:
                    market_size_score = 50
                elif sam_numeric < 1000:
                    market_size_score = 70
                else:
                    market_size_score = 90
                
                logger.info(f"   📐 Market Size Score: {market_size_score}/100 (SAM: {sam_value})")
        except Exception as e:
            logger.warning(f"   ⚠️ Error reading market sizing: {e}")

    # ========================================
    # 6. CALCULATE REALISTIC OPPORTUNITY SCORE
    # ========================================
    logger.info(f"\n   🧮 Calculating Opportunity Score with Realistic Weights...")
    
    opportunity_analysis = calculate_realistic_opportunity_score(
        pain_score=pain_score,
        growth_pct=growth_pct,
        market_size_score=market_size_score,
        competitor_count=competitor_count,
        evidence_count=evidence_count
    )
    
    opp_score = opportunity_analysis['opportunity_score']
    grade = opportunity_analysis['grade']
    warnings = opportunity_analysis['warnings']
    recommendation = opportunity_analysis['recommendation']
    breakdown = opportunity_analysis['breakdown']
    
    logger.info(f"\n   ✅ FINAL OPPORTUNITY SCORE: {opp_score}/100")
    logger.info(f"   🏆 GRADE: {grade}")
    logger.info(f"   💡 RECOMMENDATION: {recommendation}")
    
    if warnings:
        logger.warning(f"\n   ⚠️  WARNINGS:")
        for warning in warnings:
            logger.warning(f"      {warning}")

    # ========================================
    # 7. GENERATE EXECUTIVE SUMMARY
    # ========================================
    if not val_data:
        val_data = "Validation data was not generated."

    # Create enhanced prompt with breakdown
    prompt = prompts.investment_memo_prompt_enhanced(
        query=query,
        pain_score=pain_score,
        growth_pct=growth_pct,
        grade=grade,
        opp_score=opp_score,
        finance_summary=finance_summary,
        val_data=val_data,
        breakdown=breakdown,
        warnings=warnings,
        recommendation=recommendation,
        evidence_count=evidence_count,
        competitor_count=competitor_count
    )
    
    try:
        # Gemini Call
        res = call_gemini(prompt)
        content = res.text
        
        # Add opportunity analysis section to report
        analysis_section = f"""

---

## Opportunity Analysis Breakdown

**Overall Score:** {opp_score}/100 - **{grade}**

### Component Scores:
- **Pain Score:** {breakdown['pain_score_adjusted']:.1f}/100 (Raw: {breakdown['pain_score_raw']}, Evidence: {breakdown['evidence_count']} sources, Quality: {breakdown['evidence_quality']})
- **Market Growth:** {breakdown['growth_score']:.1f}/100 (YoY: {breakdown['growth_pct']:.1f}%)
- **Market Size:** {market_size_score}/100 (SAM: {sam_value})
- **Competition:** {breakdown['competition_score']:.1f}/100 (Level: {breakdown['competition_level']}, Count: {breakdown['competitor_count']})

### Methodology:
- Pain Weight: {ResearchConfig.PAIN_WEIGHT * 100:.0f}%
- Growth Weight: {ResearchConfig.GROWTH_WEIGHT * 100:.0f}%
- Market Size Weight: {ResearchConfig.MARKET_SIZE_WEIGHT * 100:.0f}%
- Competition Weight: {ResearchConfig.COMPETITION_WEIGHT * 100:.0f}%

### Recommendation:
{recommendation}

"""
        
        if warnings:
            analysis_section += "\n### ⚠️ Warnings:\n"
            for warning in warnings:
                analysis_section += f"- {warning}\n"
        
        content += analysis_section
        
        # Save comprehensive report
        with open("data_output/FINAL_MARKET_REPORT.md", "w", encoding="utf-8") as f:
            f.write(content)
        
        # Also save opportunity analysis as JSON for programmatic access
        with open("data_output/opportunity_analysis.json", "w", encoding="utf-8") as f:
            json.dump(opportunity_analysis, f, indent=4)
        
        logger.info(f"✅ Final Report Saved with Realistic Opportunity Scoring.")
        
    except Exception as e:
        logger.error(f"⚠️ Report Error: {e}")


# Note: The PDFReport class and other PDF generation functions remain the same
# Only the generate_report function needed updating for realistic scoring

class PDFReport(FPDF):
    # Brand Colors
    COLOR_MOSS = (87, 98, 56)      # #576238
    COLOR_MUSTARD = (255, 217, 93) # #FFD95D
    COLOR_EGGSHELL = (240, 234, 220) # #F0EADC
    COLOR_DARK_TEXT = (40, 40, 40)

    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        
        # Load Calibri Fonts (Windows) - "Neater & Smoother"
        self.font_family = 'Arial' # Default fallback
        try:
            # Check for Calibri files
            font_dir = r"C:\Windows\Fonts"
            if os.path.exists(os.path.join(font_dir, "calibri.ttf")):
                self.add_font("Calibri", style="", fname=os.path.join(font_dir, "calibri.ttf"), uni=True)
                self.add_font("Calibri", style="B", fname=os.path.join(font_dir, "calibrib.ttf"), uni=True)
                self.add_font("Calibri", style="I", fname=os.path.join(font_dir, "calibrii.ttf"), uni=True)
                self.add_font("Calibri", style="BI", fname=os.path.join(font_dir, "calibriz.ttf"), uni=True)
                self.font_family = 'Calibri'
            else:
                 # Fallback
                self.add_font("ArialUnicode", style="", fname=os.path.join(font_dir, "arial.ttf"), uni=True)
                self.add_font("ArialUnicode", style="B", fname=os.path.join(font_dir, "arialbd.ttf"), uni=True)
                self.font_family = 'ArialUnicode'
        except Exception as e:
            print(f"Font Warning: {e}")

    def header(self):
        # 1. Background Color (Eggshell) - Covers entire page
        # Save current state
        self.set_fill_color(*self.COLOR_EGGSHELL)
        self.rect(0, 0, 210, 297, 'F')
        
        # 2. Header Content
        self.set_font_for_content('B', 14)
        # Moss Color for Header Text
        self.set_text_color(*self.COLOR_MOSS)
        self.cell(0, 10, 'Spark2Scale AI - Market Research Report', 0, 1, 'R')
        
        # Decorative Line in Mustard
        self.set_draw_color(*self.COLOR_MUSTARD)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        
        # --- NEW: PAGE BORDER (CONTAINED LOOK) ---
        self.set_draw_color(*self.COLOR_MOSS)
        self.set_line_width(0.5)
        self.rect(5, 5, 200, 287)
        
        self.ln(5)

    def write_markdown(self, text, line_height=6):
        """
        Parses `**bold**` markdown and writes text with mixed styles.
        """
        if not text: return
        
        # Split by newlines to handle paragraphs
        lines = text.split('\n')
        for line in lines:
            if not line.strip():
                self.ln(line_height)
                continue
            
            clean_line = line.strip()
            is_header = False
            header_level = 0
            
            # Detect Header
            if clean_line.startswith('### '):
                header_level = 3
                line = clean_line[4:]
                is_header = True
            elif clean_line.startswith('## '):
                header_level = 2
                line = clean_line[3:]
                is_header = True
            elif clean_line.startswith('# '):
                header_level = 1
                line = clean_line[2:]
                is_header = True
            
            # Set Font for Line
            if is_header:
                self.set_font_for_content('B', 14 - (header_level * 1))
                self.set_text_color(*self.COLOR_MOSS)
            else:
                self.set_font_for_content('', 12)
                self.set_text_color(*self.COLOR_DARK_TEXT)
            
            parts = line.split('**')
            for i, part in enumerate(parts):
                processed_text = fix_arabic(part)
                
                if i % 2 == 1: # BOLD
                    if not is_header:
                        self.set_font_for_content('B', 12)
                    self.write(line_height, processed_text)
                    if not is_header:
                        self.set_font_for_content('', 12) 
                else: # Regular
                    self.write(line_height, processed_text)
            
            self.ln(line_height)

    def draw_score_bar(self, label, score, max_score=100):
        """Draws a visual progress bar for a score."""
        self.ln(5)
        self.set_font_for_content('B', 14)
        self.set_text_color(*self.COLOR_MOSS)
        self.cell(0, 10, f"{label}: {score}/{max_score}", 0, 1, 'L')
        
        # Bar dimensions
        bar_width = 160
        bar_height = 8
        start_x = 15
        
        # Background Bar
        self.set_fill_color(255, 255, 255)
        self.rect(start_x, self.get_y(), bar_width, bar_height, 'F')
        
        # Foreground Bar
        self.set_fill_color(*self.COLOR_MUSTARD)
        
        fill_width = (score / max_score) * bar_width
        self.rect(start_x, self.get_y(), fill_width, bar_height, 'F')
        
        self.ln(bar_height + 5)

    def footer(self):
        self.set_y(-15)
        # Decorative Line in Mustard above footer
        self.set_draw_color(*self.COLOR_MUSTARD)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        
        self.set_font("Arial", 'I', 8)
        # Moss Color for Footer Text
        self.set_text_color(*self.COLOR_MOSS)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, label):
        self.set_font_for_content('B', 18)
        # Moss Color for Title
        self.set_text_color(*self.COLOR_MOSS)
        
        # Add a left accent bar in Mustard
        self.set_fill_color(*self.COLOR_MUSTARD)
        self.rect(8, self.get_y() + 2, 1, 6, 'F')
        
        self.set_x(12)
        self.cell(0, 10, label.upper(), 0, 1, 'L')
        self.ln(2)
        
        # Underline in Moss
        self.set_draw_color(*self.COLOR_MOSS)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def chapter_body(self, text):
        self.write_markdown(text)
        self.ln()

    def add_image_centered(self, image_path, height=80):
        if os.path.exists(image_path):
            try:
                self.image(image_path, x=15, w=180)
                self.ln(5)
            except: pass
        else:
            self.set_font("Arial", 'I', 10)
            self.set_text_color(255, 0, 0)
            self.cell(0, 10, f'[Image Missing: {os.path.basename(image_path)}]', 0, 1)

    def set_font_for_content(self, style, size):
        try:
            self.set_font(self.font_family, style, size)
        except:
            self.set_font('Arial', style, size)

def remove_emojis(text):
    if not isinstance(text, str): return text
    return re.sub(r'[^\w\s,.\-\(\)\[\]/\%\$\:\'\"\+\&\?\!\@\#\*\;\<\>\=\u0600-\u06FF]', '', text)

def fix_arabic(text):
    """
    Fixes Arabic text rendering in PDFs
    """
    if pd.isna(text): return "N/A"
    text = str(text)
    
    # Remove emojis first
    text = remove_emojis(text)
    
    try:
        # Check if text contains Arabic characters
        if any('\u0600' <= char <= '\u06FF' for char in text):
            reshaped_text = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        return text
    except:
        return text
