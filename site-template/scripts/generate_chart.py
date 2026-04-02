"""
Cost Chart Generator
---------------------
Generates bar chart images from article cost data.
Used by the pipeline to create in-article infographics.

No API key needed — runs entirely locally with matplotlib.

SETUP:
    pip install matplotlib --break-system-packages

Usage:
    python3 generate_chart.py <json_data> <category> <slug>
    
The JSON data should look like:
{
    "title": "Average Roof Replacement Cost by Material",
    "location": "Fort Lauderdale",
    "items": [
        {"label": "3-Tab Asphalt", "low": 8000, "high": 14000},
        {"label": "Architectural Shingle", "low": 10000, "high": 18000},
        {"label": "Metal Standing Seam", "low": 15000, "high": 28000},
        {"label": "Concrete Tile", "low": 18000, "high": 35000}
    ]
}
"""

import sys
import os
import json
from pathlib import Path

# Lazy import — only load matplotlib when actually generating
def generate_cost_chart(data: dict, category: str, slug: str) -> str:
    """
    Generate a horizontal bar chart showing cost ranges.
    Returns the file path of the saved image.
    """
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    
    REPO_PATH = Path.home() / "site-repo"
    IMAGES_DIR = REPO_PATH / "static" / "images" / category
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Color scheme matching the site
    COLOR_ACCENT = "#1B6B4A"
    COLOR_ACCENT_LIGHT = "#8BC4A9"
    COLOR_BG = "#FAFAF8"
    COLOR_TEXT = "#1A1A1A"
    COLOR_TEXT_SECONDARY = "#555555"
    
    items = data["items"]
    labels = [item["label"] for item in items]
    lows = [item["low"] for item in items]
    highs = [item["high"] for item in items]
    ranges = [h - l for h, l in zip(highs, lows)]
    
    # Create figure
    fig_height = max(4, len(items) * 1.1 + 1.5)
    fig, ax = plt.subplots(figsize=(9, fig_height))
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_BG)
    
    y_pos = range(len(labels))
    
    # Draw the range bars
    bars_low = ax.barh(y_pos, lows, color=COLOR_ACCENT_LIGHT, edgecolor='none', height=0.55)
    bars_range = ax.barh(y_pos, ranges, left=lows, color=COLOR_ACCENT, edgecolor='none', height=0.55)
    
    # Add price labels
    for i, (low, high) in enumerate(zip(lows, highs)):
        ax.text(low - max(highs) * 0.02, i, f"${low:,.0f}", 
                ha='right', va='center', fontsize=10, color=COLOR_TEXT,
                fontweight='500')
        ax.text(high + max(highs) * 0.02, i, f"${high:,.0f}", 
                ha='left', va='center', fontsize=10, color=COLOR_TEXT,
                fontweight='500')
    
    # Styling
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=11, color=COLOR_TEXT)
    ax.invert_yaxis()  # Top to bottom
    ax.set_xlim(0, max(highs) * 1.25)
    ax.xaxis.set_visible(False)
    
    # Remove chart chrome
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(left=False, bottom=False)
    
    # Title
    title = data.get("title", "Cost Comparison")
    location = data.get("location", "Florida")
    ax.set_title(f"{title}\n{location} · 2026 Estimates", 
                 fontsize=14, fontweight='bold', color=COLOR_TEXT,
                 loc='left', pad=16)
    
    # Source footnote
    fig.text(0.02, 0.02, "Source: FloridaHomeCosts.com", 
             fontsize=8, color=COLOR_TEXT_SECONDARY, style='italic')
    
    plt.tight_layout()
    
    # Save
    filename = f"{slug}-chart.png"
    filepath = IMAGES_DIR / filename
    fig.savefig(filepath, dpi=150, bbox_inches='tight', 
                facecolor=COLOR_BG, edgecolor='none')
    plt.close(fig)
    
    print(f"✅ Chart saved: {filepath}")
    return f"/images/{category}/{filename}"


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print('Usage: python3 generate_chart.py \'<json>\' <category> <slug>')
        print('Example: python3 generate_chart.py \'{"title":"Roof Cost","location":"Miami","items":[{"label":"Asphalt","low":8000,"high":14000}]}\' roofing cost-to-replace-roof-miami-2026')
        sys.exit(1)
    
    data = json.loads(sys.argv[1])
    category = sys.argv[2]
    slug = sys.argv[3]
    
    path = generate_cost_chart(data, category, slug)
    print(json.dumps({"chart_image": path}))
