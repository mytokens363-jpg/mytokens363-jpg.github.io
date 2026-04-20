#!/usr/bin/env python3
"""
Cost Comparison Chart Generator

Takes article metadata and generates a cost comparison bar chart
as a PNG image. Called by the night shift pipeline after each
article is approved.

Usage:
    python3 generate_chart.py \
        --title "Roof Replacement Cost in Fort Lauderdale" \
        --items "3-Tab Asphalt:4.00-5.50,Architectural:5.50-7.50,Concrete Tile:9.00-14.00,Clay Tile:12.00-20.00,Metal:12.00-18.00" \
        --unit "per sq ft" \
        --output "/path/to/static/images/charts/cost-to-replace-roof-fort-lauderdale-2026.png"
"""

import argparse
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server/headless use
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os


def generate_chart(title, items_str, unit, output_path):
    """Generate a horizontal bar chart comparing costs."""
    
    # Parse items: "Name:low-high,Name:low-high"
    items = []
    for item in items_str.split(","):
        parts = item.strip().split(":")
        name = parts[0].strip()
        costs = parts[1].strip().split("-")
        low = float(costs[0].replace("$", "").replace(",", ""))
        high = float(costs[1].replace("$", "").replace(",", ""))
        items.append((name, low, high))
    
    # Sort by midpoint (lowest first, so cheapest is at top)
    items.sort(key=lambda x: (x[1] + x[2]) / 2)
    
    names = [item[0] for item in items]
    lows = [item[1] for item in items]
    highs = [item[2] for item in items]
    ranges = [h - l for l, h in zip(lows, highs)]
    
    # Chart styling
    fig, ax = plt.subplots(figsize=(8, max(3.5, len(items) * 0.8)))
    
    # Colors — gradient from green (budget) to orange (expensive)
    colors = []
    for i in range(len(items)):
        ratio = i / max(len(items) - 1, 1)
        r = 0.15 + ratio * 0.7
        g = 0.65 - ratio * 0.35
        b = 0.35 - ratio * 0.15
        colors.append((r, g, b, 0.85))
    
    # Draw bars
    bars = ax.barh(
        names, ranges, left=lows,
        color=colors,
        edgecolor='white',
        linewidth=1.5,
        height=0.6
    )
    
    # Add price labels on each bar
    for i, (name, low, high) in enumerate(items):
        mid = (low + high) / 2
        if high >= 1000:
            label = f"${low:,.0f} – ${high:,.0f}"
        else:
            label = f"${low:.2f} – ${high:.2f}"
        
        ax.text(
            mid, i, label,
            ha='center', va='center',
            fontsize=10, fontweight='bold',
            color='white',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.3)
        )
    
    # Title and labels
    ax.set_title(title, fontsize=13, fontweight='bold', pad=15, color='#1a1a1a')
    
    if unit:
        ax.set_xlabel(f"Cost ({unit})", fontsize=10, color='#666')
    else:
        ax.set_xlabel("Cost ($)", fontsize=10, color='#666')
    
    # Format x-axis
    if max(highs) >= 1000:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    else:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:.2f}"))
    
    # Styling
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#ddd')
    ax.tick_params(left=False, colors='#333')
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, linestyle='--', alpha=0.3)
    
    # Watermark
    fig.text(
        0.98, 0.02, 'FloridaHomeCosts.com',
        ha='right', va='bottom',
        fontsize=8, color='#aaa', style='italic'
    )
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"Chart saved: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate cost comparison chart")
    parser.add_argument("--title", required=True, help="Chart title")
    parser.add_argument("--items", required=True, help="Comma-separated Name:low-high pairs")
    parser.add_argument("--unit", default="", help="Unit label (e.g., 'per sq ft')")
    parser.add_argument("--output", required=True, help="Output PNG path")
    
    args = parser.parse_args()
    generate_chart(args.title, args.items, args.unit, args.output)
