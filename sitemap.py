#!/usr/bin/env python3
"""
sitemap.py — Génère sitemap.xml depuis articles.json
Usage : python sitemap.py [--base-url https://monblog.fr]
Soumettre ensuite à Google Search Console.
"""
import json, os, sys, argparse
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:8000", help="URL de base du site")
args = parser.parse_args()

BASE = args.base_url.rstrip("/")

with open(os.path.join(os.path.dirname(__file__), "articles.json"), encoding="utf-8") as f:
    articles = json.load(f).get("articles", [])

today = datetime.now().strftime("%Y-%m-%d")

urls = [
    f"""  <url>
    <loc>{BASE}/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>""",
    f"""  <url>
    <loc>{BASE}/#/programme</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>""",
]

for a in articles:
    urls.append(f"""  <url>
    <loc>{BASE}/#/article/{a['id']}</loc>
    <lastmod>{a.get('date', today)}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>""")

sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

out = os.path.join(os.path.dirname(__file__), "sitemap.xml")
with open(out, "w", encoding="utf-8") as f:
    f.write(sitemap)

print(f"sitemap.xml genere : {len(urls)} URLs")
print(f"Base URL : {BASE}")
print(f"A soumettre sur : https://search.google.com/search-console")
