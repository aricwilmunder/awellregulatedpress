#!/usr/bin/env python3
"""
build_sitemap.py

Generates sitemap.xml in the website root.

Expected layout:

website/
├── sitemap.xml            <-- generated here
├── index.html
├── author.html
├── teachers/
├── press/
└── src/
    └── build_sitemap.py
"""

from pathlib import Path
from urllib.parse import quote
from datetime import datetime

BASE_URL = "https://www.theprescottgirls.com"

# Pages to exclude
EXCLUDE_FILES = {
    "404.html",
    "making-of.html",
}

# Directories to scan
SCAN_DIRS = [
    ".",            # root html files
    "teachers",
    "press",
    "research",
]


def make_url(relative_path: str) -> str:
    parts = relative_path.replace("\\", "/").split("/")
    return f"{BASE_URL}/{'/'.join(quote(p) for p in parts)}"


def collect_pages(site_root: Path):
    pages = []

    for directory in SCAN_DIRS:
        scan_path = site_root / directory

        if not scan_path.exists():
            continue

        for html_file in sorted(scan_path.glob("*.html")):
            if html_file.name in EXCLUDE_FILES:
                continue

            rel_path = html_file.relative_to(site_root).as_posix()

            # index.html becomes root URL
            if rel_path == "index.html":
                loc = f"{BASE_URL}/"
            else:
                loc = make_url(rel_path)

            lastmod = datetime.fromtimestamp(
                html_file.stat().st_mtime
            ).strftime("%Y-%m-%d")

            pages.append((loc, lastmod))

    return sorted(pages)


def build_sitemap(site_root: Path):
    pages = collect_pages(site_root)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "",
    ]

    for loc, lastmod in pages:
        lines.extend([
            "  <url>",
            f"    <loc>{loc}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            "  </url>",
            "",
        ])

    lines.append("</urlset>")

    sitemap_path = site_root / "sitemap.xml"
    sitemap_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {len(pages)} URLs to {sitemap_path}")


def main():
    script_dir = Path(__file__).resolve().parent
    site_root = script_dir.parent.parent

    build_sitemap(site_root)


if __name__ == "__main__":
    main()

