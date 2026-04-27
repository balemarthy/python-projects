#!/usr/bin/env python3
"""Single-file topic research miner.

Creates exactly one markdown file per run:
- latest_news_[YYYY-MM-DD].md

Structure:
- Theme section
  - YouTube links
  - Medium links
  - Substack links
  - Blogs links
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 "
    "research-miner/4.0"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

DEFAULT_THEMES = ["embedded systems", "firmware jobs", "rtos"]

BLOG_FEEDS = [
    "https://www.embedded.com/feed/",
    "https://www.embeddedrelated.com/blogs/rss.php",
    "https://embeddedartistry.com/feed",
    "https://interrupt.memfault.com/blog/rss.xml",
    "https://cnx-software.com/feed/",
    "https://hackaday.com/feed/",
]

SUBSTACK_FEEDS = [
    "https://newsletter.pragmaticengineer.com/feed",
    "https://www.exponentialview.co/feed",
    "https://www.notboring.co/feed",
    "https://www.tldr.tech/rss",
]

MEDIUM_BASE_FEEDS = [
    "https://medium.com/feed/topic/programming",
    "https://medium.com/feed/topic/technology",
]

FALLBACK_ITEMS: Dict[str, List[Tuple[str, str]]] = {
    "youtube": [
        ("YouTube Search: embedded systems", "https://www.youtube.com/results?search_query=embedded+systems"),
        ("YouTube Search: firmware career", "https://www.youtube.com/results?search_query=firmware+career"),
    ],
    "medium": [
        ("Medium Tag: embedded-systems", "https://medium.com/tag/embedded-systems"),
        ("Medium Tag: firmware", "https://medium.com/tag/firmware"),
    ],
    "substack": [
        ("Pragmatic Engineer", "https://newsletter.pragmaticengineer.com/"),
        ("Exponential View", "https://www.exponentialview.co/"),
    ],
    "blogs": [
        ("Embedded Artistry", "https://embeddedartistry.com/"),
        ("Memfault Interrupt", "https://interrupt.memfault.com/blog"),
    ],
}


@dataclass
class Item:
    source: str
    title: str
    url: str
    snippet: str


def strip_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text: str) -> str:
    if not text:
        return ""
    return strip_whitespace(BeautifulSoup(text, "html.parser").get_text(" ", strip=True))


def get_text(url: str, timeout: int = 25) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def parse_feed(xml_text: str, source: str, max_items: int) -> List[Item]:
    soup = BeautifulSoup(xml_text, "xml")
    out: List[Item] = []

    for node in soup.find_all("item"):
        title = strip_whitespace(node.title.get_text(" ", strip=True)) if node.title else ""
        url = strip_whitespace(node.link.get_text(" ", strip=True)) if node.link else ""
        desc_node = node.description or node.find("content:encoded")
        desc = strip_html(desc_node.get_text(" ", strip=True)) if desc_node else ""
        if title and url:
            out.append(Item(source=source, title=title, url=url, snippet=desc))
            if len(out) >= max_items:
                return out

    for node in soup.find_all("entry"):
        title = strip_whitespace(node.title.get_text(" ", strip=True)) if node.title else ""
        url = ""
        link_tag = node.find("link")
        if link_tag:
            url = (link_tag.get("href") or "").strip() or strip_whitespace(link_tag.get_text(" ", strip=True))
        desc_node = node.find("summary") or node.find("content")
        desc = strip_html(desc_node.get_text(" ", strip=True)) if desc_node else ""
        if title and url:
            out.append(Item(source=source, title=title, url=url, snippet=desc))
            if len(out) >= max_items:
                return out

    return out


def matches_theme(item: Item, theme: str) -> bool:
    tokens = [t for t in re.findall(r"[a-z0-9]+", theme.lower()) if len(t) > 2]
    if not tokens:
        return True
    hay = f"{item.title} {item.snippet}".lower()
    return sum(1 for t in tokens if t in hay) > 0


def dedupe_items(items: List[Item], max_items: int) -> List[Item]:
    deduped: List[Item] = []
    seen = set()
    seen_title = set()

    for item in items:
        key = item.url.strip().lower()
        title_key = re.sub(r"\W+", "", item.title.lower())
        if not key or key in seen or title_key in seen_title:
            continue
        seen.add(key)
        seen_title.add(title_key)
        deduped.append(item)
        if len(deduped) >= max_items:
            break

    return deduped


def rank_item(item: Item, theme: str) -> int:
    hay = f"{item.title} {item.snippet}".lower()
    score = 0
    for token in re.findall(r"[a-z0-9]+", theme.lower()):
        if token in hay:
            score += 3
    for kw in ["tutorial", "guide", "career", "roadmap", "interview", "best", "news"]:
        if kw in hay:
            score += 2
    if "youtube.com" in item.url:
        score += 2
    return score


def fetch_from_feed_urls(urls: List[str], source: str, max_items: int) -> List[Item]:
    all_items: List[Item] = []
    for url in urls:
        try:
            xml_text = get_text(url)
            all_items.extend(parse_feed(xml_text, source, max_items=max_items))
        except Exception:
            continue
    return all_items


def youtube_items(theme: str, max_items: int) -> List[Item]:
    queries = [theme, f"{theme} tutorial", f"{theme} career", f"{theme} roadmap"]
    urls = [f"https://www.youtube.com/feeds/videos.xml?search_query={quote_plus(q)}" for q in queries]
    items = fetch_from_feed_urls(urls, "youtube", max_items=max_items)
    items = [i for i in items if matches_theme(i, theme)] or items
    items = dedupe_items(items, max_items)
    items.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return items[:max_items]


def medium_items(theme: str, max_items: int) -> List[Item]:
    tag = re.sub(r"[^a-z0-9]+", "-", theme.lower()).strip("-")
    urls = MEDIUM_BASE_FEEDS.copy()
    if tag:
        urls.insert(0, f"https://medium.com/feed/tag/{tag}")
    items = fetch_from_feed_urls(urls, "medium", max_items=max_items)
    items = [i for i in items if matches_theme(i, theme)] or items
    items = dedupe_items(items, max_items)
    items.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return items[:max_items]


def substack_items(theme: str, max_items: int) -> List[Item]:
    items = fetch_from_feed_urls(SUBSTACK_FEEDS, "substack", max_items=max_items)
    items = [i for i in items if matches_theme(i, theme)] or items
    items = dedupe_items(items, max_items)
    items.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return items[:max_items]


def blog_items(theme: str, max_items: int) -> List[Item]:
    items = fetch_from_feed_urls(BLOG_FEEDS, "blogs", max_items=max_items)
    items = [i for i in items if matches_theme(i, theme)] or items
    items = dedupe_items(items, max_items)
    items.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return items[:max_items]


def ensure_non_empty(source: str, theme: str, items: List[Item]) -> List[Item]:
    if items:
        return items
    fallbacks = []
    for title, url in FALLBACK_ITEMS.get(source, []):
        fallbacks.append(Item(source=source, title=title, url=url, snippet=f"Fallback reference for theme: {theme}"))
    return fallbacks


def mine_theme(theme: str, max_per_source: int) -> Dict[str, List[Item]]:
    source_map: Dict[str, List[Item]] = {
        "youtube": ensure_non_empty("youtube", theme, youtube_items(theme, max_per_source)),
        "medium": ensure_non_empty("medium", theme, medium_items(theme, max_per_source)),
        "substack": ensure_non_empty("substack", theme, substack_items(theme, max_per_source)),
        "blogs": ensure_non_empty("blogs", theme, blog_items(theme, max_per_source)),
    }
    return source_map


def write_single_report(themes: List[str], mined_by_theme: Dict[str, Dict[str, List[Item]]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_path = out_dir / f"latest_news_{date_str}.md"

    lines: List[str] = []
    lines.append(f"# Research Report - {date_str}")
    lines.append("")

    for theme in themes:
        lines.append(f"## {theme}")
        lines.append("")

        for source in ["youtube", "medium", "substack", "blogs"]:
            lines.append(f"### {source.title()}")
            lines.append("")
            items = mined_by_theme.get(theme, {}).get(source, [])
            if not items:
                lines.append("- No results")
                lines.append("")
                continue

            for item in items:
                lines.append(f"- [{item.title}]({item.url})")

            lines.append("")

    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def parse_themes(raw: str) -> List[str]:
    if not raw.strip():
        return DEFAULT_THEMES
    return [x.strip() for x in raw.split(",") if x.strip()] or DEFAULT_THEMES


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create one research markdown file per run")
    parser.add_argument("--themes", default=",".join(DEFAULT_THEMES), help="Comma-separated topics/themes")
    parser.add_argument("--out-dir", default=".", help="Output directory for the single report file")
    parser.add_argument("--max-per-source", type=int, default=10, help="Links per source per theme")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    themes = parse_themes(args.themes)
    out_dir = Path(args.out_dir)

    try:
        mined_by_theme: Dict[str, Dict[str, List[Item]]] = {}
        for theme in themes:
            mined_by_theme[theme] = mine_theme(theme, max(1, args.max_per_source))

        report = write_single_report(themes, mined_by_theme, out_dir)
        print(f"Saved {report}")
        return 0
    except requests.RequestException as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
