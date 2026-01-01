#!/usr/bin/env python3
"""
Render HTML slides to PNG using Playwright.
Supports theme injection and batch rendering.
"""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# Predefined themes
THEMES = {
    "orchestrate": {
        "bg-primary": "#0A0A0F",
        "bg-surface": "#141419",
        "bg-card": "#1A1A22",
        "accent-primary": "#F97316",
        "accent-secondary": "#FB923C",
        "accent-success": "#22C55E",
        "accent-warning": "#EAB308",
        "accent-error": "#EF4444",
        "accent-info": "#3B82F6",
        "text-primary": "#FFFFFF",
        "text-secondary": "#A1A1AA",
        "text-muted": "#71717A",
        "border-default": "#27272A"
    },
    "corporate-blue": {
        "bg-primary": "#0F172A",
        "bg-surface": "#1E293B",
        "bg-card": "#334155",
        "accent-primary": "#3B82F6",
        "accent-secondary": "#60A5FA",
        "accent-success": "#22C55E",
        "accent-warning": "#EAB308",
        "accent-error": "#EF4444",
        "accent-info": "#06B6D4",
        "text-primary": "#F8FAFC",
        "text-secondary": "#94A3B8",
        "text-muted": "#64748B",
        "border-default": "#475569"
    },
    "minimal-light": {
        "bg-primary": "#FFFFFF",
        "bg-surface": "#F8FAFC",
        "bg-card": "#F1F5F9",
        "accent-primary": "#0F172A",
        "accent-secondary": "#334155",
        "accent-success": "#16A34A",
        "accent-warning": "#CA8A04",
        "accent-error": "#DC2626",
        "accent-info": "#2563EB",
        "text-primary": "#0F172A",
        "text-secondary": "#475569",
        "text-muted": "#94A3B8",
        "border-default": "#E2E8F0"
    },
    "startup-gradient": {
        "bg-primary": "#0D0D12",
        "bg-surface": "#18181F",
        "bg-card": "#1F1F28",
        "accent-primary": "#8B5CF6",
        "accent-secondary": "#A78BFA",
        "accent-success": "#10B981",
        "accent-warning": "#F59E0B",
        "accent-error": "#EF4444",
        "accent-info": "#06B6D4",
        "text-primary": "#FFFFFF",
        "text-secondary": "#A1A1AA",
        "text-muted": "#71717A",
        "border-default": "#27272A"
    }
}

def theme_to_css(theme_dict):
    """Convert theme dictionary to CSS variables."""
    return '\n  '.join(f'--{k}: {v};' for k, v in theme_dict.items())


def inject_theme(html_content, theme_name="orchestrate", custom_theme=None):
    """Inject theme CSS variables into HTML."""
    if custom_theme:
        theme = custom_theme
    else:
        theme = THEMES.get(theme_name, THEMES["orchestrate"])
    
    css_vars = theme_to_css(theme)
    theme_style = f"<style>:root {{ {css_vars} }}</style>"
    
    # Inject after <head> tag
    if "<head>" in html_content:
        html_content = html_content.replace("<head>", f"<head>\n{theme_style}")
    else:
        html_content = f"{theme_style}\n{html_content}"
    
    return html_content


async def render_html_to_png(html_content, output_path, width=None, height=None):
    """Render HTML content to PNG using Playwright.
    
    If width/height not provided, auto-detects from HTML content.
    """
    # Auto-detect dimensions from HTML if not provided
    if width is None or height is None:
        import re
        # Look for common dimension patterns in CSS
        # ig-square = 1080x1080, ig-story = 1080x1920, twitter-card = 1200x675
        if 'ig-square' in html_content or '1080px' in html_content and 'height: 1080px' in html_content:
            width, height = 1080, 1080
        elif 'ig-story' in html_content or 'height: 1920px' in html_content:
            width, height = 1080, 1920
        elif 'ig-portrait' in html_content or 'height: 1350px' in html_content:
            width, height = 1080, 1350
        elif 'twitter-card' in html_content or 'width: 1200px' in html_content:
            width, height = 1200, 675
        elif 'twitter-header' in html_content:
            width, height = 1500, 500
        else:
            # Default to slide dimensions
            width, height = 1920, 1080
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height})
        
        await page.set_content(html_content, wait_until="networkidle")
        
        # Wait for fonts to load
        await page.wait_for_timeout(500)
        
        await page.screenshot(path=output_path, type="png")
        await browser.close()
        
    return output_path


async def render_file(html_path, output_path, theme="orchestrate", custom_theme=None):
    """Render an HTML file to PNG with theme injection."""
    with open(html_path, 'r') as f:
        html_content = f.read()
    
    html_content = inject_theme(html_content, theme, custom_theme)
    await render_html_to_png(html_content, output_path)
    return output_path


async def render_deck(deck_json_path, output_dir, theme="orchestrate"):
    """
    Render a full deck from JSON definition.
    
    Expected JSON structure:
    {
        "theme": "orchestrate",
        "custom_theme": {...},  // Optional
        "slides": [
            {"html": "<div>...</div>"},
            {"file": "slide1.html"}
        ]
    }
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(deck_json_path, 'r') as f:
        deck = json.load(f)
    
    deck_theme = deck.get("theme", theme)
    custom_theme = deck.get("custom_theme")
    slides = deck.get("slides", [])
    
    outputs = []
    for i, slide in enumerate(slides):
        output_path = output_dir / f"slide_{i+1:02d}.png"
        
        if "html" in slide:
            html_content = inject_theme(slide["html"], deck_theme, custom_theme)
            await render_html_to_png(html_content, str(output_path))
        elif "file" in slide:
            await render_file(slide["file"], str(output_path), deck_theme, custom_theme)
        
        outputs.append(str(output_path))
        print(f"Rendered: {output_path}")
    
    return outputs


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  render_slide.py <input.html> <output.png> [theme]")
        print("  render_slide.py --deck <deck.json> <output_dir> [theme]")
        print("")
        print("Available themes: orchestrate, corporate-blue, minimal-light, startup-gradient")
        sys.exit(1)
    
    if sys.argv[1] == "--deck":
        deck_path = sys.argv[2]
        output_dir = sys.argv[3]
        theme = sys.argv[4] if len(sys.argv) > 4 else "orchestrate"
        asyncio.run(render_deck(deck_path, output_dir, theme))
    else:
        html_path = sys.argv[1]
        output_path = sys.argv[2]
        theme = sys.argv[3] if len(sys.argv) > 3 else "orchestrate"
        asyncio.run(render_file(html_path, output_path, theme))
        print(f"Rendered: {output_path}")


if __name__ == "__main__":
    main()
