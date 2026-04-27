#!/usr/bin/env python3
"""Single-file topic research miner (no LLM).

Creates exactly one markdown file per run:
- latest_news_[YYYY-MM-DD].md

Structure:
- Theme section
  - YouTube links
  - Medium links
  - Reddit links
  - Quora links
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
    "research-miner/5.0"
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

MEDIUM_BASE_FEEDS = [
    "https://medium.com/feed/topic/programming",
    "https://medium.com/feed/topic/technology",
]

INTENT_TERMS = [
    "tutorial",
    "career roadmap",
    "interview questions",
    "best practices",
    "real world projects",
    "debugging guide",
]

ROLE_TERMS = [
    "for beginners",
    "for experienced engineers",
    "for job seekers",
    "for career switchers",
]

CONTEXT_TERMS = [
    "2026",
    "remote jobs",
    "portfolio",
    "production systems",
]

FALLBACK_ITEMS: Dict[str, List[Tuple[str, str]]] = {
    "youtube": [
        ("YouTube Search", "https://www.youtube.com/results?search_query=embedded+systems"),
    ],
    "medium": [
        ("Medium Embedded Tag", "https://medium.com/tag/embedded-systems"),
    ],
    "reddit": [
        ("Reddit Embedded Search", "https://www.reddit.com/search/?q=embedded+systems"),
    ],
    "quora": [
        ("Quora Embedded Search", "https://www.quora.com/search?q=embedded%20systems"),
    ],
    "blogs": [
        ("Embedded Artistry", "https://embeddedartistry.com/"),
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


def get_text(url: str, timeout: int = 30) -> str:
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
        link_tag = node.find("link")
        url = (link_tag.get("href") or "").strip() if link_tag else ""
        if not url and link_tag:
            url = strip_whitespace(link_tag.get_text(" ", strip=True))
        desc_node = node.find("summary") or node.find("content")
        desc = strip_html(desc_node.get_text(" ", strip=True)) if desc_node else ""
        if title and url:
            out.append(Item(source=source, title=title, url=url, snippet=desc))
            if len(out) >= max_items:
                return out

    return out


def generate_long_tail_queries(theme: str, max_queries: int) -> List[str]:
    queries: List[str] = [theme]

    for intent in INTENT_TERMS:
        queries.append(f"{theme} {intent}")

    for role in ROLE_TERMS:
        queries.append(f"{theme} {role}")

    for context in CONTEXT_TERMS:
        queries.append(f"{theme} {context}")

    # Combine intent + role for deeper long-tail coverage.
    for intent in INTENT_TERMS:
        for role in ROLE_TERMS[:2]:
            queries.append(f"{theme} {intent} {role}")

    deduped: List[str] = []
    seen = set()
    for q in queries:
        key = q.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
        if len(deduped) >= max_queries:
            break

    return deduped


def matches_theme(item: Item, theme: str) -> bool:
    tokens = [t for t in re.findall(r"[a-z0-9]+", theme.lower()) if len(t) > 2]
    if not tokens:
        return True
    hay = f"{item.title} {item.snippet}".lower()
    return sum(1 for t in tokens if t in hay) > 0


def dedupe_items(items: List[Item], max_items: int) -> List[Item]:
    deduped: List[Item] = []
    seen_url = set()
    seen_title = set()

    for item in items:
        url_key = item.url.strip().lower()
        title_key = re.sub(r"\W+", "", item.title.lower())
        if not url_key or url_key in seen_url or title_key in seen_title:
            continue
        seen_url.add(url_key)
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

    for kw in INTENT_TERMS + ["guide", "career", "interview", "portfolio"]:
        if kw in hay:
            score += 2

    source_bonus = {
        "youtube": 2,
        "medium": 1,
        "reddit": 2,
        "quora": 1,
        "blogs": 1,
    }
    score += source_bonus.get(item.source, 0)
    return score


def google_news_rss(query: str, source: str, max_items: int) -> List[Item]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        xml_text = get_text(url)
        return parse_feed(xml_text, source, max_items=max_items)
    except Exception:
        return []


def fetch_feed_url(url: str, source: str, max_items: int) -> List[Item]:
    try:
        xml_text = get_text(url)
        return parse_feed(xml_text, source, max_items=max_items)
    except Exception:
        return []


def youtube_items(theme: str, queries: List[str], max_items: int) -> List[Item]:
    gathered: List[Item] = []
    for q in queries:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?search_query={quote_plus(q)}"
        gathered.extend(fetch_feed_url(feed_url, "youtube", max_items=6))
    gathered = [i for i in gathered if matches_theme(i, theme)] or gathered
    gathered = dedupe_items(gathered, max_items=max_items * 2)
    gathered.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return gathered[:max_items]


def medium_items(theme: str, queries: List[str], max_items: int) -> List[Item]:
    tag = re.sub(r"[^a-z0-9]+", "-", theme.lower()).strip("-")
    gathered: List[Item] = []

    if tag:
        gathered.extend(fetch_feed_url(f"https://medium.com/feed/tag/{tag}", "medium", max_items=12))

    for feed in MEDIUM_BASE_FEEDS:
        gathered.extend(fetch_feed_url(feed, "medium", max_items=8))

    for q in queries[:8]:
        gathered.extend(google_news_rss(f"site:medium.com {q}", "medium", max_items=5))

    gathered = [i for i in gathered if matches_theme(i, theme)] or gathered
    gathered = dedupe_items(gathered, max_items=max_items * 2)
    gathered.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return gathered[:max_items]


def reddit_items(theme: str, queries: List[str], max_items: int) -> List[Item]:
    gathered: List[Item] = []

    for q in queries[:10]:
        rss_url = f"https://www.reddit.com/search.rss?q={quote_plus(q)}&sort=relevance&t=all"
        gathered.extend(fetch_feed_url(rss_url, "reddit", max_items=7))

    if not gathered:
        for q in queries[:8]:
            gathered.extend(google_news_rss(f"site:reddit.com {q}", "reddit", max_items=5))

    gathered = [i for i in gathered if matches_theme(i, theme)] or gathered
    gathered = dedupe_items(gathered, max_items=max_items * 2)
    gathered.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return gathered[:max_items]


def quora_items(theme: str, queries: List[str], max_items: int) -> List[Item]:
    gathered: List[Item] = []

    for q in queries[:10]:
        gathered.extend(google_news_rss(f"site:quora.com {q}", "quora", max_items=6))

    gathered = [i for i in gathered if matches_theme(i, theme)] or gathered
    gathered = dedupe_items(gathered, max_items=max_items * 2)
    gathered.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return gathered[:max_items]


def blog_items(theme: str, queries: List[str], max_items: int) -> List[Item]:
    gathered: List[Item] = []

    for feed in BLOG_FEEDS:
        gathered.extend(fetch_feed_url(feed, "blogs", max_items=10))

    # Add long-tail blog discovery via Google News RSS as a supplement.
    for q in queries[:6]:
        gathered.extend(
            google_news_rss(
                (
                    "(site:embeddedartistry.com OR site:interrupt.memfault.com OR "
                    "site:embeddedrelated.com OR site:hackaday.com) "
                    f"{q}"
                ),
                "blogs",
                max_items=5,
            )
        )

    gathered = [i for i in gathered if matches_theme(i, theme)] or gathered
    gathered = dedupe_items(gathered, max_items=max_items * 2)
    gathered.sort(key=lambda x: rank_item(x, theme), reverse=True)
    return gathered[:max_items]


def ensure_non_empty(source: str, theme: str, items: List[Item]) -> List[Item]:
    if items:
        return items
    return [
        Item(source=source, title=title, url=url, snippet=f"Fallback reference for theme: {theme}")
        for title, url in FALLBACK_ITEMS.get(source, [])
    ]


def mine_theme(theme: str, max_per_source: int, query_depth: int) -> Dict[str, List[Item]]:
    queries = generate_long_tail_queries(theme, max_queries=query_depth)

    source_map: Dict[str, List[Item]] = {
        "youtube": ensure_non_empty("youtube", theme, youtube_items(theme, queries, max_per_source)),
        "medium": ensure_non_empty("medium", theme, medium_items(theme, queries, max_per_source)),
        "reddit": ensure_non_empty("reddit", theme, reddit_items(theme, queries, max_per_source)),
        "quora": ensure_non_empty("quora", theme, quora_items(theme, queries, max_per_source)),
        "blogs": ensure_non_empty("blogs", theme, blog_items(theme, queries, max_per_source)),
    }
    return source_map


def write_single_report(themes: List[str], mined_by_theme: Dict[str, Dict[str, List[Item]]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_path = out_dir / f"latest_news_{date_str}.md"

    lines: List[str] = [f"# Research Report - {date_str}", ""]

    for theme in themes:
        lines.append(f"## {theme}")
        lines.append("")

        for source in ["youtube", "medium", "reddit", "quora", "blogs"]:
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
    parser = argparse.ArgumentParser(description="Create one deep-research markdown file per run")
    parser.add_argument("--themes", default=",".join(DEFAULT_THEMES), help="Comma-separated topics/themes")
    parser.add_argument("--out-dir", default=".", help="Output directory for the single report file")
    parser.add_argument("--max-per-source", type=int, default=12, help="Links per source per theme")
    parser.add_argument("--query-depth", type=int, default=24, help="Long-tail query count per theme")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    themes = parse_themes(args.themes)
    out_dir = Path(args.out_dir)

    try:
        mined_by_theme: Dict[str, Dict[str, List[Item]]] = {}
        for theme in themes:
            mined_by_theme[theme] = mine_theme(
                theme,
                max_per_source=max(1, args.max_per_source),
                query_depth=max(6, args.query_depth),
            )

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
