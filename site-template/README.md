# Florida Home Costs — Hugo Site Setup

## Quick Start (10 minutes)

### Step 1: Create GitHub Repo
```bash
# Create a new repo on GitHub called "florida-home-costs" (or whatever you want)
# Then locally:
cd ~/site-repo
git init
git remote add origin git@github.com:YOUR_USERNAME/florida-home-costs.git
```

### Step 2: Copy These Files Into the Repo
```
site-repo/
├── .github/
│   └── workflows/
│       └── deploy.yml          ← Auto-deploy on push
├── layouts/
│   ├── _default/
│   │   ├── baseof.html         ← Base template (ads, header, footer)
│   │   ├── single.html         ← Article page template
│   │   └── list.html           ← Category listing template
│   └── index.html              ← Homepage template
├── content/
│   ├── roofing/
│   │   └── _index.md
│   ├── hurricane-protection/
│   │   └── _index.md
│   ├── exterior/
│   │   └── _index.md
│   ├── interior/
│   │   └── _index.md
│   ├── plumbing/
│   │   └── _index.md
│   ├── electrical/
│   │   └── _index.md
│   ├── hvac/
│   │   └── _index.md
│   ├── major-systems/
│   │   └── _index.md
│   └── pool/
│       └── _index.md
├── static/
│   └── images/               ← Article images go here
├── scripts/
│   ├── fetch_image.py        ← Unsplash image fetcher
│   └── generate_chart.py     ← Cost chart generator
├── hugo.yaml                 ← Site configuration
└── README.md
```

### Step 3: Enable GitHub Pages
1. Go to repo Settings → Pages
2. Source: **GitHub Actions**
3. That's it — the deploy.yml handles everything

### Step 4: Update hugo.yaml
Change `baseURL` to your actual URL:
- GitHub Pages: `https://YOUR_USERNAME.github.io/florida-home-costs/`
- Custom domain: `https://floridahomecosts.com/`

### Step 5: Push and Verify
```bash
git add .
git commit -m "Initial site setup"
git push -u origin main
```
Wait 2-3 minutes. Check GitHub Actions tab to see the build. Visit your URL.

---

## Custom Domain (Optional, Recommended)

1. Buy a domain ($10/yr on Namecheap or Cloudflare)
2. In repo root, create a file called `static/CNAME` containing just:
   ```
   floridahomecosts.com
   ```
3. Set DNS:
   - A record: `185.199.108.153`
   - A record: `185.199.109.153`
   - A record: `185.199.110.153`
   - A record: `185.199.111.153`
   - CNAME: `www` → `YOUR_USERNAME.github.io`
4. In GitHub repo Settings → Pages → Custom domain: enter your domain

---

## How Rivet Publishes Articles

Rivet's only interaction with this site is:

```bash
# 1. Write article markdown to the correct category folder
#    File goes in: content/[category]/[slug].md

# 2. Optionally fetch an image
python3 scripts/fetch_image.py "roof replacement florida" "roofing" "cost-to-replace-roof-florida-2026"

# 3. Git commit and push
cd ~/site-repo
git add .
git commit -m "Add: cost to replace roof in Florida 2026"
git push origin main

# 4. GitHub Actions auto-builds and deploys. Done.
```

---

## Article Front Matter Format

Every article markdown file needs this YAML front matter:

```yaml
---
title: "How Much Does It Cost to Replace a Roof in Florida? (2026 Guide)"
description: "Average roof replacement cost in Florida ranges from $8,000 to $25,000. Full breakdown of materials, labor, and permits."
date: 2026-04-02
last_updated: 2026-04-02
category: roofing
location: Florida
service: roof replacement
hero_image: "/images/roofing/cost-to-replace-roof-florida-2026.jpg"
hero_image_alt: "Roof replacement in progress on a Florida home"
hero_image_credit: "John Doe / Unsplash"
cost_low: 8000
cost_high: 25000
---

# Article content here...
```

The `cost_low` and `cost_high` fields power the sidebar "Quick Estimate" widget.

---

## AdSense Setup (After 20-30 Articles Are Live)

1. Apply at https://adsense.google.com
2. Once approved, you'll get a script tag and ad unit codes
3. In `layouts/_default/baseof.html`:
   - Uncomment the AdSense script tag in `<head>`
   - Replace `ca-pub-XXXXXXXXXXXXXXXX` with your publisher ID
4. In each ad slot div, replace the placeholder with your ad unit code:
   ```html
   <div class="ad-slot" id="ad-header">
     <ins class="adsbygoogle"
          style="display:block"
          data-ad-client="ca-pub-XXXXXXXXXXXXXXXX"
          data-ad-slot="XXXXXXXXXX"
          data-ad-format="auto"
          data-full-width-responsive="true"></ins>
     <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
   </div>
   ```
5. Push the change. Every page on the site now has ads.

### Ad Slot Locations (5 total)
- **ad-header**: Horizontal banner below site header (every page)
- **ad-above-content**: Between hero image and article body
- **ad-below-content**: After article ends
- **ad-sidebar-top**: Top of sidebar (sticky)
- **ad-sidebar-bottom**: Below popular guides widget

---

## Image Pipeline Setup

### Unsplash (Hero Photos)
1. Create free account at https://unsplash.com/developers
2. Create an app to get an Access Key
3. Set env variable: `export UNSPLASH_ACCESS_KEY=your_key_here`
4. Pipeline calls fetch_image.py automatically per article

### Cost Charts (matplotlib)
```bash
pip install matplotlib --break-system-packages
```
Pipeline calls generate_chart.py with cost data extracted from article.

### If No Image API Key
Articles work fine without images. The template gracefully hides the 
hero image section if no `hero_image` is set in front matter.
Images are nice-to-have, not required for launch.
Test
Test 2
Test Cloudflare token update
Token update test
New token test
