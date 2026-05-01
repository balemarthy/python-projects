#!/usr/bin/env python3
"""Fetch a selected URL and export readable content for downstream use.

Usage examples:
  python fetch_content.py --url "https://example.com/post" --format md
  python fetch_content.py --url "https://example.com/post" --format txt --out-dir captures
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 "
    "content-fetcher/1.0"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}


@dataclass
class CapturedContent:
    title: str
    url: str
    byline: str
    content: str
    captured_at: str


def strip_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip().lower())
    return slug.strip("-") or "capture"


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=40)
    resp.raise_for_status()
    return resp.text


def extract_title(soup: BeautifulSoup) -> str:
    for selector in [
        "meta[property='og:title']",
        "meta[name='twitter:title']",
        "h1",
        "title",
    ]:
        node = soup.select_one(selector)
        if not node:
            continue
        if node.name == "meta":
            content = strip_ws(node.get("content", ""))
        else:
            content = strip_ws(node.get_text(" ", strip=True))
        if content:
            return content
    return "Untitled"


def extract_byline(soup: BeautifulSoup) -> str:
    for selector in [
        "meta[name='author']",
        "meta[property='article:author']",
        "[rel='author']",
        ".author",
        ".byline",
    ]:
        node = soup.select_one(selector)
        if not node:
            continue
        if node.name == "meta":
            content = strip_ws(node.get("content", ""))
        else:
            content = strip_ws(node.get_text(" ", strip=True))
        if content:
            return content
    return ""


def extract_main_text(soup: BeautifulSoup) -> str:
    # Remove obvious noise before collecting text.
    for tag in soup.select("script, style, nav, footer, header, aside, form, noscript"):
        tag.decompose()

    candidates = []
    for selector in ["article", "main", "[role='main']"]:
        for node in soup.select(selector):
            text = strip_ws(node.get_text("\n", strip=True))
            if len(text) > 600:
                candidates.append(text)

    if candidates:
        return max(candidates, key=len)

    paragraphs = []
    for p in soup.find_all(["p", "li"]):
        text = strip_ws(p.get_text(" ", strip=True))
        if len(text) >= 60:
            paragraphs.append(text)

    return "\n\n".join(paragraphs[:120])


def capture_url(url: str) -> CapturedContent:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    title = extract_title(soup)
    byline = extract_byline(soup)
    content = extract_main_text(soup)
    return CapturedContent(
        title=title,
        url=url,
        byline=byline,
        content=content,
        captured_at=datetime.now().isoformat(timespec="seconds"),
    )


def to_markdown(doc: CapturedContent) -> str:
    lines = [f"# {doc.title}", ""]
    lines.append(f"Source: {doc.url}")
    lines.append(f"Captured: {doc.captured_at}")
    if doc.byline:
        lines.append(f"Author: {doc.byline}")
    lines.append("")
    lines.append(doc.content or "No readable content extracted.")
    lines.append("")
    return "\n".join(lines)


def to_text(doc: CapturedContent) -> str:
    lines = [doc.title, "", f"Source: {doc.url}", f"Captured: {doc.captured_at}"]
    if doc.byline:
        lines.append(f"Author: {doc.byline}")
    lines.append("")
    lines.append(doc.content or "No readable content extracted.")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch selected URL content into md or txt")
    parser.add_argument("--url", required=True, help="URL to capture")
    parser.add_argument("--format", choices=("md", "txt"), default="md", help="Output format")
    parser.add_argument("--out-dir", default="captures", help="Output directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = capture_url(args.url)
        ext = "md" if args.format == "md" else "txt"
        host = urlparse(args.url).netloc.replace("www.", "") or "source"
        filename = f"{datetime.now().strftime('%Y-%m-%d')}_{slugify(host)}_{slugify(doc.title)[:80]}.{ext}"
        output_path = out_dir / filename
        payload = to_markdown(doc) if args.format == "md" else to_text(doc)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Saved {output_path}")
        return 0
    except requests.RequestException as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Capture error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
