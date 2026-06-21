#!/usr/bin/env python3
"""
validate_site.py

Lightweight validator for ThePrescottGirls.github.io.

Checks:
- Broken internal links
- Missing images/assets
- Sitemap mismatches
- Missing title/description/canonical
- Unused assets

Expected location:
  src/site validator/validate_site.py

Outputs only a report. Does not modify files.
"""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote
import os
import re
import xml.etree.ElementTree as ET

BASE_URL = "https://www.theprescottgirls.com"
INTERNAL_DOMAINS = {
    "www.theprescottgirls.com",
    "theprescottgirls.com",
}

# These are real site pages, but they should not be checked for sitemap inclusion
# or ordinary page metadata.
EXCLUDE_HTML = {
    "404.html",
    "making-of.html",
}

SCAN_HTML_DIRS = [
    ".",
    "teachers",
    "press",
    "research",
]

ASSET_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".mp4", ".mov",
}

IGNORE_UNUSED_ASSETS = {
    "assets/apple-touch-icon.png",
    "assets/favicon-16.png",
    "assets/favicon-32.png",
}

IGNORE_DIRS = {
    ".git",
    "src",
}

# Keep visible search snippets from getting overly long.
# Google often truncates around 155-160 characters, so 160 is a useful warning threshold.
MAX_META_DESCRIPTION_LENGTH = 160


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.assets = []
        self.title_found = False
        self.description_found = False
        self.description_content = None
        self.canonical_found = False
        self.in_title = False

    def maybe_add_asset(self, value):
        if not value:
            return

        path = strip_url_to_path(value)
        if not path:
            return

        if Path(path).suffix.lower() in ASSET_EXTENSIONS:
            self.assets.append(value)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "title":
            self.in_title = True

        # Ordinary links are checked for breakage. If they point to assets such
        # as PDFs, they are also counted as used assets.
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
            self.maybe_add_asset(attrs["href"])

        # Common embedded asset references.
        for attr in [
            "src",
            "data",
            "poster",
            "data-src",
            "data-full",
            "data-image",
            "data-thumb",
            "data-original",
        ]:
            if attr in attrs:
                self.maybe_add_asset(attrs[attr])

        # srcset can contain multiple references, often with width descriptors.
        if "srcset" in attrs:
            for candidate in attrs["srcset"].split(","):
                url = candidate.strip().split()[0] if candidate.strip() else ""
                self.maybe_add_asset(url)

        if tag == "link":
            href = attrs.get("href")
            rel = attrs.get("rel", "").lower()

            if rel == "canonical":
                self.canonical_found = True

            # Count icons and other asset-like link references, but do not treat
            # canonical page URLs as assets.
            if href and rel != "canonical":
                self.maybe_add_asset(href)

        if tag == "meta":
            name = attrs.get("name", "").lower()
            prop = attrs.get("property", "").lower()
            content = attrs.get("content")

            if name == "description" and content:
                self.description_found = True
                self.description_content = content.strip()

            if prop in {"og:image", "twitter:image"} and content:
                self.maybe_add_asset(content)

    def handle_data(self, data):
        if self.in_title and data.strip():
            self.title_found = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False


def site_root_from_script() -> Path:
    script_dir = Path(__file__).resolve().parent
    return script_dir.parent.parent


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def is_external_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc not in INTERNAL_DOMAINS


def strip_url_to_path(url: str) -> str | None:
    if not url:
        return None

    url = url.strip()

    if url.startswith("#"):
        return None

    if url.startswith("mailto:") or url.startswith("tel:") or url.startswith("javascript:"):
        return None

    parsed = urlparse(url)

    if parsed.scheme in {"http", "https"}:
        if parsed.netloc not in INTERNAL_DOMAINS:
            return None
        path = parsed.path
    else:
        path = parsed.path

    if not path or path == "/":
        path = "index.html"

    path = unquote(path)

    if path.startswith("/"):
        path = path[1:]

    return normalize_path(path)


def resolve_reference(site_root: Path, page_path: Path, ref: str) -> Path | None:
    ref_path = strip_url_to_path(ref)

    if ref_path is None:
        return None

    parsed = urlparse(ref)

    # Absolute internal URL or root-relative path.
    if ref.startswith("/") or parsed.netloc in INTERNAL_DOMAINS:
        return (site_root / ref_path).resolve()

    # Ordinary relative path.
    return (page_path.parent / ref_path).resolve()


def collect_html_pages(site_root: Path) -> list[Path]:
    pages = []

    for directory in SCAN_HTML_DIRS:
        scan_path = site_root / directory
        if not scan_path.exists():
            continue

        for page in sorted(scan_path.glob("*.html")):
            if page.name in EXCLUDE_HTML:
                continue
            pages.append(page.resolve())

    return pages


def collect_asset_reference_pages(site_root: Path, pages: list[Path]) -> list[Path]:
    """Pages to scan for asset references.

    404.html is intentionally excluded from sitemap and metadata checks, but it
    still uses a real image and should be scanned for asset references.
    """
    asset_pages = list(pages)

    for special_name in ["404.html"]:
        special_page = site_root / special_name
        if special_page.exists():
            asset_pages.append(special_page.resolve())

    return asset_pages



def collect_css_files(site_root: Path) -> list[Path]:
    css_files = []

    for root, dirs, files in os.walk(site_root):
        root_path = Path(root)

        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS and not d.startswith(".")
        ]

        for filename in files:
            path = root_path / filename
            if path.suffix.lower() == ".css":
                css_files.append(path.resolve())

    return sorted(css_files)


def css_asset_references(css_file: Path) -> list[str]:
    """Return asset references found in CSS url(...) declarations."""
    text = css_file.read_text(encoding="utf-8", errors="ignore")
    refs = []

    for match in re.finditer(r"url\(\s*(['\"]?)(.*?)\1\s*\)", text):
        ref = match.group(2).strip()
        if not ref or ref.startswith("data:"):
            continue
        refs.append(ref)

    return refs

def collect_all_assets(site_root: Path) -> set[str]:
    assets = set()

    for root, dirs, files in os.walk(site_root):
        root_path = Path(root)

        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS and not d.startswith(".")
        ]

        for filename in files:
            path = root_path / filename
            rel = normalize_path(path.relative_to(site_root).as_posix())

            if path.suffix.lower() in ASSET_EXTENSIONS:
                assets.add(rel)

    return assets


def sitemap_urls(site_root: Path) -> set[str]:
    sitemap_path = site_root / "sitemap.xml"

    if not sitemap_path.exists():
        return set()

    tree = ET.parse(sitemap_path)
    root = tree.getroot()

    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls = set()
    for loc in root.findall(".//sm:loc", namespace):
        if loc.text:
            path = strip_url_to_path(loc.text)
            if path:
                urls.add(path)

    return urls


def expected_sitemap_pages(site_root: Path) -> set[str]:
    expected = set()

    for page in collect_html_pages(site_root):
        rel = normalize_path(page.relative_to(site_root).as_posix())
        expected.add(rel)

    return expected


def parse_page(page: Path) -> PageParser:
    parser = PageParser()
    parser.feed(page.read_text(encoding="utf-8", errors="ignore"))
    return parser


def main():
    site_root = site_root_from_script()
    pages = collect_html_pages(site_root)
    asset_pages = collect_asset_reference_pages(site_root, pages)

    broken_links = []
    missing_assets = []
    used_assets = set()
    metadata_warnings = []

    # Check ordinary pages for metadata and broken links. This intentionally
    # excludes 404.html and other non-indexed pages.
    for page in pages:
        rel_page = normalize_path(page.relative_to(site_root).as_posix())
        parser = parse_page(page)

        if not parser.title_found:
            metadata_warnings.append((rel_page, "missing <title>"))

        if not parser.description_found:
            metadata_warnings.append((rel_page, "missing meta description"))
        elif len(parser.description_content) > MAX_META_DESCRIPTION_LENGTH:
            metadata_warnings.append((
                rel_page,
                f"meta description too long ({len(parser.description_content)} chars, max {MAX_META_DESCRIPTION_LENGTH})"
            ))

        if not parser.canonical_found:
            metadata_warnings.append((rel_page, "missing canonical link"))

        for href in parser.links:
            if is_external_url(href):
                continue

            target = resolve_reference(site_root, page, href)

            if target is None:
                continue

            if not target.exists():
                broken_links.append((rel_page, href))

    # Check all asset references, including special pages like 404.html.
    for page in asset_pages:
        rel_page = normalize_path(page.relative_to(site_root).as_posix())
        parser = parse_page(page)

        for asset_ref in parser.assets:
            if is_external_url(asset_ref):
                continue

            target = resolve_reference(site_root, page, asset_ref)

            if target is None:
                continue

            if target.exists():
                try:
                    used_assets.add(normalize_path(target.relative_to(site_root).as_posix()))
                except ValueError:
                    pass
            else:
                missing_assets.append((rel_page, asset_ref))

    # Check CSS url(...) references, such as background images.
    for css_file in collect_css_files(site_root):
        rel_css = normalize_path(css_file.relative_to(site_root).as_posix())

        for asset_ref in css_asset_references(css_file):
            if is_external_url(asset_ref):
                continue

            target = resolve_reference(site_root, css_file, asset_ref)

            if target is None:
                continue

            if target.exists():
                try:
                    used_assets.add(normalize_path(target.relative_to(site_root).as_posix()))
                except ValueError:
                    pass
            else:
                missing_assets.append((rel_css, asset_ref))

    sitemap_found = sitemap_urls(site_root)
    sitemap_expected = expected_sitemap_pages(site_root)

    missing_from_sitemap = sorted(sitemap_expected - sitemap_found)
    extra_in_sitemap = sorted(sitemap_found - sitemap_expected)

    all_assets = collect_all_assets(site_root)
    unused_assets = sorted(all_assets - used_assets - IGNORE_UNUSED_ASSETS)

    print()
    print("Site validation report")
    print("======================")
    print(f"Site root: {site_root}")
    print(f"HTML pages scanned: {len(pages)}")
    print()

    if broken_links:
        print(f"Broken internal links: {len(broken_links)}")
        for page, href in broken_links:
            print(f"  {page}")
            print(f"    -> {href}")
    else:
        print("Broken internal links: 0")

    print()

    if missing_assets:
        print(f"Missing assets/images: {len(missing_assets)}")
        for page, asset in missing_assets:
            print(f"  {page}")
            print(f"    -> {asset}")
    else:
        print("Missing assets/images: 0")

    print()

    if missing_from_sitemap or extra_in_sitemap:
        print("Sitemap mismatches:")
        for path in missing_from_sitemap:
            print(f"  Missing from sitemap: {path}")
        for path in extra_in_sitemap:
            print(f"  Extra in sitemap: {path}")
    else:
        print("Sitemap mismatches: 0")

    print()

    if metadata_warnings:
        print(f"Metadata warnings: {len(metadata_warnings)}")
        for page, warning in metadata_warnings:
            print(f"  {page}: {warning}")
    else:
        print("Metadata warnings: 0")

    print()

    if unused_assets:
        total_bytes = sum((site_root / path).stat().st_size for path in unused_assets)
        total_mb = total_bytes / (1024 * 1024)

        print(f"Unused assets: {len(unused_assets)} ({total_mb:.1f} MB)")
        for path in unused_assets:
            print(f"  {path}")
    else:
        print("Unused assets: 0")

    print()

    error_count = len(broken_links) + len(missing_assets) + len(missing_from_sitemap) + len(extra_in_sitemap)

    if error_count == 0:
        print("PASS")
    else:
        print("FAIL")


if __name__ == "__main__":
    main()
