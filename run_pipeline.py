#!/usr/bin/env python3
"""Topic research miner for YouTube, Medium, Substack, and popular blogs.

Outputs (under outputs/):
- latest_news_[YYYY-MM-DD].md
- [theme]_youtube.md
- [theme]_medium.md
- [theme]_substack.md
- [theme]_blogs.md
- [theme]_gold.md
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
    "research-miner/3.0"
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
    query: str


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip().lower())
    return slug.strip("_") or "theme"


def strip_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text: str) -> str:
    if not text:
        return ""
    plain = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return strip_whitespace(plain)


def get_text(url: str, timeout: int = 25) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def parse_feed(xml_text: str, source: str, query: str, max_items: int) -> List[Item]:
    soup = BeautifulSoup(xml_text, "xml")
    out: List[Item] = []

    # RSS items
    for node in soup.find_all("item"):
        title = strip_whitespace(node.title.get_text(" ", strip=True)) if node.title else ""
        url = strip_whitespace(node.link.get_text(" ", strip=True)) if node.link else ""
        desc_node = node.description or node.find("content:encoded")
        desc = strip_html(desc_node.get_text(" ", strip=True)) if desc_node else ""

        if title and url:
            out.append(Item(source=source, title=title, url=url, snippet=desc, query=query))
            if len(out) >= max_items:
                return out

    # Atom entries (used by YouTube)
    for node in soup.find_all("entry"):
        title = strip_whitespace(node.title.get_text(" ", strip=True)) if node.title else ""

        url = ""
        link_tag = node.find("link")
        if link_tag:
            url = (link_tag.get("href") or "").strip() or strip_whitespace(link_tag.get_text(" ", strip=True))

        desc_node = node.find("summary") or node.find("content")
        desc = strip_html(desc_node.get_text(" ", strip=True)) if desc_node else ""

        if title and url:
            out.append(Item(source=source, title=title, url=url, snippet=desc, query=query))
            if len(out) >= max_items:
                return out

    return out


def matches_theme(item: Item, theme: str) -> bool:
    tokens = [t for t in re.findall(r"[a-z0-9]+", theme.lower()) if len(t) > 2]
    if not tokens:
        return True

    hay = f"{item.title} {item.snippet}".lower()
    return any(tok in hay for tok in tokens)


def dedupe_items(items: List[Item], max_items: int) -> List[Item]:
    deduped: List[Item] = []
    seen = set()

    for item in items:
        key = item.url.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_items:
            break

    return deduped


def rank_item(item: Item, theme: str) -> int:
    haystack = f"{item.title} {item.snippet}".lower()
    score = 0

    for token in re.findall(r"[a-z0-9]+", theme.lower()):
        if token in haystack:
            score += 3

    for kw in ["tutorial", "guide", "career", "roadmap", "interview", "best", "news"]:
        if kw in haystack:
            score += 2

    if "youtube.com" in item.url:
        score += 2
    if "medium.com" in item.url:
        score += 1
    if "substack" in item.url:
        score += 1

    return score


def fetch_from_feed_urls(urls: List[str], source: str, query: str, max_items: int) -> Tuple[List[Item], List[str]]:
    all_items: List[Item] = []
    errors: List[str] = []

    for url in urls:
        try:
            xml_text = get_text(url)
            all_items.extend(parse_feed(xml_text, source, query, max_items=max_items))
        except Exception as exc:
            errors.append(f"{url} -> {exc}")

    return all_items, errors


def youtube_items(theme: str, max_items: int) -> Tuple[List[Item], List[str]]:
    queries = [theme, f"{theme} tutorial", f"{theme} career", f"{theme} roadmap"]
    urls = [f"https://www.youtube.com/feeds/videos.xml?search_query={quote_plus(q)}" for q in queries]
    items, errors = fetch_from_feed_urls(urls, "youtube", query=theme, max_items=max_items)

    filtered = [i for i in items if matches_theme(i, theme)]
    items = filtered or items
    items = dedupe_items(items, max_items=max_items)
    items.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return items[:max_items], errors


def medium_items(theme: str, max_items: int) -> Tuple[List[Item], List[str]]:
    tag = re.sub(r"[^a-z0-9]+", "-", theme.lower()).strip("-")
    urls = MEDIUM_BASE_FEEDS.copy()
    if tag:
        urls.insert(0, f"https://medium.com/feed/tag/{tag}")

    items, errors = fetch_from_feed_urls(urls, "medium", query=theme, max_items=max_items)
    filtered = [i for i in items if matches_theme(i, theme)]
    items = filtered or items
    items = dedupe_items(items, max_items=max_items)
    items.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return items[:max_items], errors


def substack_items(theme: str, max_items: int) -> Tuple[List[Item], List[str]]:
    items, errors = fetch_from_feed_urls(SUBSTACK_FEEDS, "substack", query=theme, max_items=max_items)
    filtered = [i for i in items if matches_theme(i, theme)]
    items = filtered or items
    items = dedupe_items(items, max_items=max_items)
    items.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return items[:max_items], errors


def blog_items(theme: str, max_items: int) -> Tuple[List[Item], List[str]]:
    items, errors = fetch_from_feed_urls(BLOG_FEEDS, "blogs", query=theme, max_items=max_items)
    filtered = [i for i in items if matches_theme(i, theme)]
    items = filtered or items
    items = dedupe_items(items, max_items=max_items)
    items.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return items[:max_items], errors


def ensure_non_empty(source: str, theme: str, items: List[Item]) -> List[Item]:
    if items:
        return items

    fallback = []
    for title, url in FALLBACK_ITEMS.get(source, []):
        fallback.append(
            Item(
                source=source,
                title=title,
                url=url,
                snippet=f"Fallback reference for theme: {theme}",
                query="fallback",
            )
        )

    return fallback


def mine_theme(theme: str, max_per_source: int) -> Tuple[Dict[str, List[Item]], Dict[str, List[str]]]:
    mined: Dict[str, List[Item]] = {"youtube": [], "medium": [], "substack": [], "blogs": []}
    errors: Dict[str, List[str]] = {"youtube": [], "medium": [], "substack": [], "blogs": []}

    yt, yt_err = youtube_items(theme, max_per_source)
    md, md_err = medium_items(theme, max_per_source)
    ss, ss_err = substack_items(theme, max_per_source)
    bl, bl_err = blog_items(theme, max_per_source)

    mined["youtube"] = ensure_non_empty("youtube", theme, yt)
    mined["medium"] = ensure_non_empty("medium", theme, md)
    mined["substack"] = ensure_non_empty("substack", theme, ss)
    mined["blogs"] = ensure_non_empty("blogs", theme, bl)

    errors["youtube"] = yt_err
    errors["medium"] = md_err
    errors["substack"] = ss_err
    errors["blogs"] = bl_err

    return mined, errors


def write_source_markdown(theme: str, source: str, items: List[Item], out_dir: Path, errors: List[str]) -> Path:
    file_path = out_dir / f"{slugify(theme)}_{source}.md"
    lines: List[str] = []
    lines.append(f"# {source.title()} Research: {theme}")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    if not items:
        lines.append("No results found.")
        lines.append("")
    else:
        for idx, item in enumerate(items, start=1):
            lines.append(f"## {idx}. {item.title}")
            lines.append("")
            lines.append(f"URL: {item.url}")
            lines.append("")
            if item.snippet:
                lines.append(item.snippet)
                lines.append("")
            lines.append(f"Query: `{item.query}`")
            lines.append("")
            lines.append("---")
            lines.append("")

    if errors:
        lines.append("## Source Notes")
        lines.append("")
        lines.append("Some feeds failed during this run:")
        lines.append("")
        for err in errors[:10]:
            lines.append(f"- {err}")

    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def write_gold_markdown(theme: str, source_map: Dict[str, List[Item]], out_dir: Path, max_items: int) -> Path:
    file_path = out_dir / f"{slugify(theme)}_gold.md"
    merged: List[Item] = []
    for items in source_map.values():
        merged.extend(items)

    merged = dedupe_items(merged, max_items=max_items * 3)
    merged.sort(key=lambda x: rank_item(x, theme), reverse=True)
    merged = merged[:max_items]

    lines: List[str] = []
    lines.append(f"# Gold Research: {theme}")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    if not merged:
        lines.append("No results found.")
    else:
        for idx, item in enumerate(merged, start=1):
            lines.append(f"## {idx}. [{item.source}] {item.title}")
            lines.append("")
            lines.append(f"URL: {item.url}")
            lines.append("")
            if item.snippet:
                lines.append(item.snippet)
                lines.append("")

    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def write_latest_news(themes: List[str], mined_by_theme: Dict[str, Dict[str, List[Item]]], out_dir: Path) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_path = out_dir / f"latest_news_{date_str}.md"

    lines: List[str] = []
    lines.append(f"# Latest News - {date_str}")
    lines.append("")
    lines.append("Curated links mined from YouTube, Medium, Substack, and popular blogs.")
    lines.append("")

    for theme in themes:
        lines.append(f"## {theme}")
        lines.append("")

        merged: List[Item] = []
        for source_items in mined_by_theme[theme].values():
            merged.extend(source_items)

        merged = dedupe_items(merged, 20)
        merged.sort(key=lambda x: rank_item(x, theme), reverse=True)

        if not merged:
            lines.append("No items found.")
            lines.append("")
            continue

        for item in merged[:10]:
            lines.append(f"- [{item.title}]({item.url}) ({item.source})")

        lines.append("")

    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def parse_themes(raw: str) -> List[str]:
    if not raw.strip():
        return DEFAULT_THEMES
    values = [x.strip() for x in raw.split(",") if x.strip()]
    return values or DEFAULT_THEMES


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine topic research across high-signal sources")
    parser.add_argument("--themes", default=",".join(DEFAULT_THEMES), help="Comma-separated topics/themes")
    parser.add_argument("--out-dir", default="outputs", help="Output directory")
    parser.add_argument("--max-per-source", type=int, default=12, help="Saved results per source per theme")
    parser.add_argument("--max-gold", type=int, default=20, help="Items in [theme]_gold.md")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    themes = parse_themes(args.themes)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mined_by_theme: Dict[str, Dict[str, List[Item]]] = {}

    try:
        for theme in themes:
            source_map, error_map = mine_theme(theme, max_per_source=max(1, args.max_per_source))
            mined_by_theme[theme] = source_map

            for source, items in source_map.items():
                print(f"{theme} -> {source}: {len(items)} items")
                file_path = write_source_markdown(theme, source, items, out_dir, errors=error_map.get(source, []))
                print(f"Saved {file_path}")

            gold_path = write_gold_markdown(theme, source_map, out_dir, max_items=max(1, args.max_gold))
            print(f"Saved {gold_path}")

        latest_path = write_latest_news(themes, mined_by_theme, out_dir)
        print(f"Saved {latest_path}")
        return 0

    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
