#!/usr/bin/env python3
"""Topic research miner for YouTube, Medium, Substack, and popular blogs.

Outputs (under outputs/):
- latest_news_[YYYY-MM-DD].md
- [theme]_youtube.md
- [theme]_medium.md
- [theme]_substack.md
- [theme]_blogs.md
- [theme]_gold.md

Examples:
  python run_pipeline.py
  python run_pipeline.py --themes "embedded systems,firmware career"
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 "
    "research-miner/1.0"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

DEFAULT_THEMES = ["embedded systems", "firmware jobs", "rtos"]
BLOG_DOMAINS = [
    "embeddedartistry.com",
    "interrupt.memfault.com",
    "embeddedrelated.com",
    "allaboutcircuits.com",
    "hackaday.com",
]


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


def get_text(url: str, timeout: int = 25) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def strip_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_duckduckgo_results(html: str, source: str, query: str, max_items: int) -> List[Item]:
    soup = BeautifulSoup(html, "html.parser")
    items: List[Item] = []

    for result in soup.select("div.result"):
        a = result.select_one("a.result__a")
        snippet_el = result.select_one("a.result__snippet") or result.select_one("div.result__snippet")
        if not a:
            continue

        href = (a.get("href") or "").strip()
        title = strip_whitespace(a.get_text(" ", strip=True))
        snippet = ""
        if snippet_el:
            snippet = strip_whitespace(snippet_el.get_text(" ", strip=True))

        if not href or not title:
            continue

        items.append(Item(source=source, title=title, url=href, snippet=snippet, query=query))
        if len(items) >= max_items:
            break

    return items


def ddg_search(query: str, source: str, max_items: int) -> List[Item]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html = get_text(url)
    return parse_duckduckgo_results(html, source, query, max_items)


def generate_queries(theme: str) -> Dict[str, List[str]]:
    blog_sites = " OR ".join([f"site:{d}" for d in BLOG_DOMAINS])
    return {
        "youtube": [
            f"site:youtube.com {theme} tutorial",
            f"site:youtube.com {theme} best practices",
            f"site:youtube.com {theme} roadmap",
        ],
        "medium": [
            f"site:medium.com {theme}",
            f"site:medium.com {theme} career",
            f"site:medium.com {theme} guide",
        ],
        "substack": [
            f"site:substack.com {theme}",
            f"site:substack.com {theme} newsletter",
            f"site:substack.com {theme} career",
        ],
        "blogs": [
            f"({blog_sites}) {theme}",
            f"({blog_sites}) {theme} tutorial",
        ],
    }


def dedupe_items(items: List[Item], max_items: int) -> List[Item]:
    deduped: List[Item] = []
    seen = set()
    for item in items:
        key = item.url.strip().lower()
        if key in seen:
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

    for kw in ["tutorial", "guide", "career", "roadmap", "best", "deep dive"]:
        if kw in haystack:
            score += 2

    if "youtube.com" in item.url:
        score += 1

    return score


def mine_theme(theme: str, max_per_query: int, max_per_source: int) -> Dict[str, List[Item]]:
    queries = generate_queries(theme)
    mined: Dict[str, List[Item]] = {"youtube": [], "medium": [], "substack": [], "blogs": []}

    for source, source_queries in queries.items():
        aggregate: List[Item] = []
        for q in source_queries:
            try:
                aggregate.extend(ddg_search(q, source, max_per_query))
            except Exception as exc:
                aggregate.append(
                    Item(
                        source=source,
                        title=f"Search failed for query: {q}",
                        url="",
                        snippet=f"Error: {exc}",
                        query=q,
                    )
                )

        cleaned = [x for x in aggregate if x.url]
        cleaned = dedupe_items(cleaned, max_items=max_per_source * 2)
        cleaned.sort(key=lambda x: rank_item(x, theme), reverse=True)
        mined[source] = cleaned[:max_per_source]

    return mined


def write_source_markdown(theme: str, source: str, items: List[Item], out_dir: Path) -> Path:
    file_path = out_dir / f"{slugify(theme)}_{source}.md"
    lines: List[str] = []
    lines.append(f"# {source.title()} Research: {theme}")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    if not items:
        lines.append("No results found.")
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
    parser.add_argument(
        "--themes",
        default=",".join(DEFAULT_THEMES),
        help="Comma-separated topics/themes, e.g. 'embedded systems,firmware jobs'",
    )
    parser.add_argument("--out-dir", default="outputs", help="Output directory")
    parser.add_argument("--max-per-query", type=int, default=8, help="Results per search query")
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
            source_map = mine_theme(theme, max_per_query=max(1, args.max_per_query), max_per_source=max(1, args.max_per_source))
            mined_by_theme[theme] = source_map

            for source, items in source_map.items():
                file_path = write_source_markdown(theme, source, items, out_dir)
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
