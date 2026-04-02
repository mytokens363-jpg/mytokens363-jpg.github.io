"""
Image Fetcher for Article Pipeline
-----------------------------------
Fetches relevant hero images from Unsplash for each article.
Runs as part of the night shift pipeline after an article is approved.

SETUP:
1. Get a free Unsplash API key at https://unsplash.com/developers
2. Set UNSPLASH_ACCESS_KEY environment variable or paste below
3. Images are downloaded to site-repo/static/images/[category]/

Usage:
    python3 fetch_image.py "roof replacement florida" "roofing" "cost-to-replace-roof-florida-2026"
    
Arguments:
    1. Search query (descriptive, based on article topic)
    2. Category folder name
    3. Article slug (used as filename)
"""

import sys
import os
import json
import requests
from pathlib import Path

# ===== CONFIGURATION =====
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "YOUR_KEY_HERE")
REPO_PATH = Path.home() / "site-repo"
IMAGES_DIR = REPO_PATH / "static" / "images"

# Search query mappings — override generic queries with better ones
CATEGORY_SEARCH_HINTS = {
    "roofing": "house roof construction florida",
    "hurricane-protection": "hurricane impact windows home florida",
    "exterior": "house exterior renovation",
    "interior": "home interior renovation modern",
    "plumbing": "plumbing repair home",
    "electrical": "electrical panel home",
    "hvac": "air conditioning unit home florida",
    "major-systems": "home construction systems",
    "pool": "swimming pool home florida backyard",
}


def fetch_unsplash_image(query: str, category: str, slug: str) -> dict:
    """
    Search Unsplash for a relevant image and download it.
    
    Returns dict with image metadata for Hugo front matter:
    {
        "hero_image": "/images/roofing/cost-to-replace-roof-florida-2026.jpg",
        "hero_image_alt": "Roof replacement on a Florida home",
        "hero_image_credit": "Photo by John Doe on Unsplash"
    }
    """
    
    if UNSPLASH_ACCESS_KEY == "YOUR_KEY_HERE":
        print("⚠️  No Unsplash API key set. Skipping image fetch.")
        print("   Get a free key at https://unsplash.com/developers")
        print("   Set UNSPLASH_ACCESS_KEY environment variable")
        return None
    
    # Enhance query with category hints
    enhanced_query = query
    if category in CATEGORY_SEARCH_HINTS:
        enhanced_query = f"{query} {CATEGORY_SEARCH_HINTS[category]}"
    
    # Search Unsplash
    try:
        response = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": enhanced_query,
                "per_page": 5,
                "orientation": "landscape",
                "content_filter": "high",  # Only safe images
            },
            headers={
                "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"
            },
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"❌ Unsplash API error: {e}")
        return None
    
    if not data.get("results"):
        print(f"⚠️  No images found for query: {enhanced_query}")
        # Try simpler query
        simple_query = query.split()[0:2]
        print(f"   Retrying with: {' '.join(simple_query)}")
        try:
            response = requests.get(
                "https://api.unsplash.com/search/photos",
                params={
                    "query": " ".join(simple_query),
                    "per_page": 3,
                    "orientation": "landscape",
                },
                headers={
                    "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"
                },
                timeout=15
            )
            data = response.json()
        except Exception:
            return None
        
        if not data.get("results"):
            return None
    
    # Pick the first result
    photo = data["results"][0]
    
    # Download the image (regular size — good balance of quality and file size)
    image_url = photo["urls"]["regular"]  # 1080px wide
    photographer = photo["user"]["name"]
    alt_text = photo.get("alt_description", f"{query}")
    
    # Create directory
    category_dir = IMAGES_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)
    
    # Download
    filename = f"{slug}.jpg"
    filepath = category_dir / filename
    
    try:
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        filepath.write_bytes(img_response.content)
        print(f"✅ Image saved: {filepath}")
    except Exception as e:
        print(f"❌ Image download failed: {e}")
        return None
    
    # Trigger Unsplash download tracking (required by API terms)
    try:
        requests.get(
            photo["links"]["download_location"],
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10
        )
    except Exception:
        pass  # Non-critical
    
    # Return metadata for Hugo front matter
    return {
        "hero_image": f"/images/{category}/{filename}",
        "hero_image_alt": alt_text[:120] if alt_text else f"{query} - Florida home improvement",
        "hero_image_credit": f"{photographer} / Unsplash"
    }


def generate_search_query(keyword: str, category: str) -> str:
    """
    Convert a keyword like 'cost to replace roof in Fort Lauderdale 2026'
    into a good image search query like 'roof replacement florida home'
    """
    # Strip cost/price language and year
    noise_words = [
        "cost to", "cost of", "how much does", "how much do",
        "cost", "price", "pricing", "in", "the", "a", "an",
        "2024", "2025", "2026", "2027", "florida",
    ]
    
    query = keyword.lower()
    for word in noise_words:
        query = query.replace(word, "")
    
    # Clean up whitespace
    query = " ".join(query.split())
    
    # Add context
    query = f"{query} home florida"
    
    return query


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 fetch_image.py <search_query> <category> <slug>")
        print('Example: python3 fetch_image.py "roof replacement florida" "roofing" "cost-to-replace-roof-florida-2026"')
        sys.exit(1)
    
    query = sys.argv[1]
    category = sys.argv[2]
    slug = sys.argv[3]
    
    result = fetch_image(query, category, slug)
    
    if result:
        # Output as JSON so the pipeline can parse it
        print(json.dumps(result))
    else:
        print(json.dumps({"error": "No image fetched"}))
