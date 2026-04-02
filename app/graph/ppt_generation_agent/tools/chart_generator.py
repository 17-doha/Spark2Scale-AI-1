import os
import uuid
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from app.core.logger import get_logger

logger = get_logger(__name__)

# Professional color palette
COLORS = {
    'primary': '#2E86AB',
    'secondary': '#A23B72', 
    'accent': '#F18F01',
    'success': '#C73E1D',
    'dark': '#1B1B3A',
    'palette': ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#3BCEAC', '#6B2D5C', '#0EAD69', '#FF6B6B']
}

def generate_chart(data: dict, output_dir: str, theme_colors: list = None, font_name: str = 'Arial') -> str:
    """
    Generates various chart types from structured data with premium styling.
    """
    try:
        chart_type = data.get("type", "bar").lower()
        title = data.get("title", "Chart")
        labels = data.get("labels", [])
        values = data.get("values", [])
        x_label = data.get("x_label", "")
        y_label = data.get("y_label", "")
        
        # Use theme colors if provided, else fallback to professional palette
        if theme_colors:
            colors = theme_colors[:len(labels)] if len(theme_colors) >= len(labels) else (theme_colors * (len(labels)//len(theme_colors) + 1))[:len(labels)]
        else:
            colors = data.get("colors", COLORS['palette'][:len(labels)])

        plt.rcParams['font.family'] = font_name
        plt.style.use('seaborn-v0_8-whitegrid')
        
        # Match background to a clean off-white or dark if needed (default to very light)
        bg_color = '#FAFAFA'
        
        fig, ax = plt.subplots(figsize=(12, 7))
        fig.patch.set_facecolor(bg_color)
        ax.set_facecolor(bg_color)

        if chart_type == "bar":
            bars = ax.bar(labels, values, color=colors, edgecolor=bg_color, linewidth=2)
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02, 
                       f'{val:,.0f}' if isinstance(val, (int, float)) else str(val),
                       ha='center', va='bottom', fontsize=12, fontweight='bold', color='#333333')
            ax.set_xlabel(x_label, fontsize=14, color='#555555')
            ax.set_ylabel(y_label, fontsize=14, color='#555555')

        elif chart_type == "horizontal_bar":
            y_pos = np.arange(len(labels))
            bars = ax.barh(y_pos, values, color=colors, edgecolor=bg_color, linewidth=2)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, fontsize=12)
            for bar, val in zip(bars, values):
                ax.text(val + max(values)*0.02, bar.get_y() + bar.get_height()/2,
                       f'{val:,.0f}' if isinstance(val, (int, float)) else str(val),
                       va='center', fontsize=12, fontweight='bold', color='#333333')
            ax.set_xlabel(y_label, fontsize=14, color='#555555')

        elif chart_type == "line":
            line_color = colors[0] if colors else COLORS['primary']
            ax.plot(labels, values, marker='o', markersize=12, linewidth=4, color=line_color)
            ax.fill_between(labels, values, alpha=0.15, color=line_color)
            for i, val in enumerate(values):
                ax.annotate(f'{val:,.0f}' if isinstance(val, (int, float)) else str(val),
                           (labels[i], val), textcoords="offset points", xytext=(0,15),
                           ha='center', fontsize=12, fontweight='bold', color='#333333')
            ax.set_xlabel(x_label, fontsize=14)
            ax.set_ylabel(y_label, fontsize=14)

        elif chart_type == "pie" or chart_type == "donut":
            inner_pct = 0.6 if chart_type == "donut" else 0
            
            if sum(values) == 0:
                plot_values = [1]
                plot_labels = ["No Data"]
                plot_colors = ['#cccccc']
            else:
                plot_values = values
                plot_labels = labels
                plot_colors = colors

            wedges, texts, autotexts = ax.pie(plot_values, labels=plot_labels, autopct='%1.1f%%',
                                               colors=plot_colors, wedgeprops=dict(width=1-inner_pct, edgecolor=bg_color, linewidth=2),
                                               startangle=140, pctdistance=0.85 if chart_type == "donut" else 0.75)
            plt.setp(autotexts, size=12, weight="bold")
            if chart_type == "donut":
                total = sum(values)
                ax.text(0, 0, f'Total\n{total:,.0f}', ha='center', va='center', fontsize=18, fontweight='bold', color='#333333')

        elif chart_type == "funnel":
            widths = np.array(values) / max(values)
            y_positions = np.arange(len(labels))[::-1]
            for i, (label, width, val) in enumerate(zip(labels, widths, values)):
                left = (1 - width) / 2
                ax.barh(y_positions[i], width, left=left, height=0.7, 
                       color=colors[i % len(colors)], edgecolor=bg_color, linewidth=3)
                ax.text(0.5, y_positions[i], f'{label}\n{val:,.1%}' if val < 1 else f'{label}\n{val:,.0f}', 
                       ha='center', va='center', fontsize=12, fontweight='bold', color='white')
            ax.set_xlim(0, 1)
            ax.axis('off')

        else:
            # Fallback
            ax.bar(labels, values, color=colors)

        # Final Polishing: Hide Spines
        for spine in ax.spines.values():
            spine.set_visible(False)
            
        ax.set_title(title.upper(), fontsize=20, fontweight='bold', pad=30, color='#222222')
        plt.tight_layout()

        filename = f"{uuid.uuid4()}.png"
        filepath = os.path.join(output_dir, filename)
        plt.savefig(filepath, dpi=200, bbox_inches='tight', facecolor=bg_color)
        plt.close()
        
        logger.info(f"Premium chart saved to {filepath}")
        return filepath

    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        import traceback
        traceback.print_exc()
        return None
