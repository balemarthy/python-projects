#!/usr/bin/env python3
"""Technical-first research miner v2 (no LLM, single report).

Creates exactly one markdown file per run:
- latest_news_[YYYY-MM-DD].md

Report layout:
- Theme
  - Coverage summary
  - Intent buckets: Debugging, Implementation, Tooling, Interview, Projects, Career/Market

Core required sources: YouTube, Medium, Blogs
Opportunistic sources: Reddit, Quora (included only if quality passes)
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, quote_plus, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 "
    "research-miner/6.0"
)
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

DEFAULT_THEMES = ["embedded systems", "firmware jobs", "rtos"]
CORE_SOURCES = ("youtube", "medium", "blogs")
OPPORTUNISTIC_SOURCES = ("reddit", "quora")
ALL_SOURCES = CORE_SOURCES + OPPORTUNISTIC_SOURCES

INTENT_BUCKETS = (
    "Debugging",
    "Implementation",
    "Tooling",
    "Interview",
    "Projects",
    "Career/Market",
)

# Fixed dictionaries for deterministic long-tail expansion.
TECH_INTENT_TERMS = [
    "debugging",
    "failure analysis",
    "driver development",
    "rtos internals",
    "memory optimization",
    "interrupt handling",
    "firmware architecture",
    "bring-up checklist",
    "embedded testing",
    "code review",
    "profiling",
    "power optimization",
    "bootloader",
    "ipc",
    "scheduler behavior",
    "latency reduction",
]

ROLE_TERMS = [
    "for beginners",
    "for senior engineers",
    "for job seekers",
    "for hiring managers",
    "for career switchers",
]

CONTEXT_TERMS = [
    "2026",
    "production systems",
    "portfolio",
    "interview preparation",
    "real-world examples",
    "tradeoffs",
    "best practices",
    "mistakes to avoid",
    "checklist",
]

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

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "Debugging": [
        "debug",
        "debugging",
        "fault",
        "panic",
        "trace",
        "crash",
        "failure",
        "root cause",
    ],
    "Implementation": [
        "implement",
        "architecture",
        "design",
        "build",
        "driver",
        "firmware",
        "rtos",
        "embedded",
        "scheduler",
        "interrupt",
        "latency",
    ],
    "Tooling": [
        "toolchain",
        "cmake",
        "gcc",
        "clang",
        "gdb",
        "profiler",
        "ci",
        "testing",
        "lint",
    ],
    "Interview": [
        "interview",
        "questions",
        "system design",
        "hiring",
        "assessment",
    ],
    "Projects": [
        "project",
        "portfolio",
        "case study",
        "example",
        "hands-on",
        "walkthrough",
    ],
    "Career/Market": [
        "career",
        "salary",
        "job",
        "market",
        "roadmap",
        "remote",
    ],
}


@dataclass
class Item:
    source: str
    title: str
    url: str
    snippet: str
    query: str
    score: int = 0
    intent: str = "Implementation"


def strip_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text: str) -> str:
    if not text:
        return ""
    return strip_whitespace(BeautifulSoup(text, "html.parser").get_text(" ", strip=True))


def normalize_url(url: str) -> str:
    """Canonicalize URL to improve dedupe across tracking variants."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url.strip()

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")

    # Drop common tracking params.
    query_params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in {"feature", "si", "ref", "ref_src"}
    ]
    query = "&".join(f"{k}={v}" for k, v in query_params)

    return urlunparse((scheme, netloc, path, "", query, ""))


def title_signature(title: str) -> str:
    normalized = re.sub(r"\W+", " ", title.lower())
    tokens = [t for t in normalized.split() if len(t) > 2]
    return " ".join(tokens[:12])


def near_duplicate_signature(title: str) -> str:
    tokens = [t for t in re.findall(r"[a-z0-9]+", title.lower()) if len(t) > 2]
    # Cluster by sorted top tokens; catches minor reorderings.
    return " ".join(sorted(tokens[:8]))


def get_text(url: str, timeout: int = 30) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def parse_feed(xml_text: str, source: str, query: str, max_items: int) -> List[Item]:
    soup = BeautifulSoup(xml_text, "xml")
    out: List[Item] = []

    for node in soup.find_all("item"):
        title = strip_whitespace(node.title.get_text(" ", strip=True)) if node.title else ""
        url = strip_whitespace(node.link.get_text(" ", strip=True)) if node.link else ""
        desc_node = node.description or node.find("content:encoded")
        desc = strip_html(desc_node.get_text(" ", strip=True)) if desc_node else ""
        if title and url:
            out.append(Item(source=source, title=title, url=normalize_url(url), snippet=desc, query=query))
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
            out.append(Item(source=source, title=title, url=normalize_url(url), snippet=desc, query=query))
            if len(out) >= max_items:
                return out

    return out


def generate_long_tail_queries(theme: str, max_queries: int) -> List[str]:
    """query_expansion(theme): deterministic 60-90 long-tail variants."""
    queries: List[str] = [theme]

    for intent in TECH_INTENT_TERMS:
        queries.append(f"{theme} {intent}")

    for role in ROLE_TERMS:
        queries.append(f"{theme} {role}")

    for ctx in CONTEXT_TERMS:
        queries.append(f"{theme} {ctx}")

    for intent in TECH_INTENT_TERMS:
        for role in ROLE_TERMS[:4]:
            queries.append(f"{theme} {intent} {role}")

    for intent in TECH_INTENT_TERMS[:10]:
        for ctx in CONTEXT_TERMS[:6]:
            queries.append(f"{theme} {intent} {ctx}")

    deduped: List[str] = []
    seen: Set[str] = set()
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


def assign_intent(item: Item) -> str:
    hay = f"{item.title} {item.snippet} {item.query}".lower()
    best_intent = "Implementation"
    best_score = -1

    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in hay)
        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent


def score_item(item: Item, theme: str) -> int:
    hay = f"{item.title} {item.snippet} {item.query}".lower()
    score = 0

    for token in re.findall(r"[a-z0-9]+", theme.lower()):
        if token in hay:
            score += 3

    # Technical-first weighting.
    for kw in [
        "debug",
        "driver",
        "rtos",
        "toolchain",
        "firmware",
        "latency",
        "interrupt",
        "architecture",
        "profiling",
    ]:
        if kw in hay:
            score += 4

    for kw in ["project", "portfolio", "interview", "career", "market"]:
        if kw in hay:
            score += 2

    source_bonus = {
        "youtube": 3,
        "medium": 2,
        "blogs": 2,
        "reddit": 1,
        "quora": 1,
    }
    score += source_bonus.get(item.source, 0)
    return score


def dedupe_items(items: Iterable[Item], max_items: int) -> List[Item]:
    deduped: List[Item] = []
    seen_url: Set[str] = set()
    seen_title: Set[str] = set()
    seen_cluster: Set[str] = set()

    for item in items:
        u = normalize_url(item.url)
        t = title_signature(item.title)
        c = near_duplicate_signature(item.title)

        if not u or u in seen_url or t in seen_title or c in seen_cluster:
            continue

        seen_url.add(u)
        seen_title.add(t)
        seen_cluster.add(c)
        item.url = u
        deduped.append(item)

        if len(deduped) >= max_items:
            break

    return deduped


def fetch_feed_url(url: str, source: str, query: str, max_items: int) -> List[Item]:
    try:
        xml_text = get_text(url)
        return parse_feed(xml_text, source, query=query, max_items=max_items)
    except Exception:
        return []


def google_news_rss(query: str, source: str, max_items: int) -> List[Item]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    return fetch_feed_url(url, source, query=query, max_items=max_items)


def collect_candidates(theme: str, queries: List[str], source: str, sample_depth: int) -> List[Item]:
    candidates: List[Item] = []

    if source == "youtube":
        for q in queries[:sample_depth]:
            feed_url = f"https://www.youtube.com/feeds/videos.xml?search_query={quote_plus(q)}"
            candidates.extend(fetch_feed_url(feed_url, "youtube", q, max_items=6))

    elif source == "medium":
        tag = re.sub(r"[^a-z0-9]+", "-", theme.lower()).strip("-")
        if tag:
            candidates.extend(fetch_feed_url(f"https://medium.com/feed/tag/{tag}", "medium", f"tag:{tag}", max_items=14))

        for feed in MEDIUM_BASE_FEEDS:
            candidates.extend(fetch_feed_url(feed, "medium", f"feed:{feed}", max_items=10))

        for q in queries[: min(sample_depth, 20)]:
            candidates.extend(google_news_rss(f"site:medium.com {q}", "medium", max_items=4))

    elif source == "blogs":
        for feed in BLOG_FEEDS:
            candidates.extend(fetch_feed_url(feed, "blogs", f"feed:{feed}", max_items=10))

        for q in queries[: min(sample_depth, 20)]:
            candidates.extend(
                google_news_rss(
                    "(site:embeddedartistry.com OR site:interrupt.memfault.com OR "
                    "site:embeddedrelated.com OR site:hackaday.com OR site:embedded.com) "
                    f"{q}",
                    "blogs",
                    max_items=4,
                )
            )

    elif source == "reddit":
        for q in queries[: min(sample_depth, 24)]:
            rss_url = f"https://www.reddit.com/search.rss?q={quote_plus(q)}&sort=relevance&t=all"
            candidates.extend(fetch_feed_url(rss_url, "reddit", q, max_items=6))

        if not candidates:
            for q in queries[: min(sample_depth, 16)]:
                candidates.extend(google_news_rss(f"site:reddit.com {q}", "reddit", max_items=4))

    elif source == "quora":
        for q in queries[: min(sample_depth, 24)]:
            candidates.extend(google_news_rss(f"site:quora.com {q}", "quora", max_items=5))

    return [c for c in candidates if matches_theme(c, theme)] or candidates


def source_quality_pass(items: List[Item], min_items: int = 3, min_avg_score: float = 8.0) -> bool:
    if len(items) < min_items:
        return False
    avg = sum(i.score for i in items) / float(len(items))
    return avg >= min_avg_score


def curate_items(
    theme: str,
    candidates_by_source: Dict[str, List[Item]],
    target_total_links: int,
    strict_diversity: bool,
) -> Tuple[List[Item], Dict[str, str]]:
    """collect_and_curate(theme): score, bucket, dedupe, diversity constraints."""
    source_notes: Dict[str, str] = {}

    # Score + annotate.
    for source_items in candidates_by_source.values():
        for item in source_items:
            item.intent = assign_intent(item)
            item.score = score_item(item, theme)

    # Opportunistic sources only if quality passes.
    for src in OPPORTUNISTIC_SOURCES:
        source_items = sorted(candidates_by_source.get(src, []), key=lambda i: i.score, reverse=True)
        if not source_quality_pass(source_items):
            candidates_by_source[src] = []
            source_notes[src] = "Insufficient quality; excluded from curated output."

    per_source_cap = max(3, target_total_links // len(ALL_SOURCES))
    per_intent_cap = max(2, target_total_links // len(INTENT_BUCKETS))

    selected: List[Item] = []
    used_url: Set[str] = set()
    used_cluster: Set[str] = set()
    source_count: Dict[str, int] = {s: 0 for s in ALL_SOURCES}
    intent_count: Dict[str, int] = {i: 0 for i in INTENT_BUCKETS}

    # Global ranking list.
    all_candidates: List[Item] = []
    for src, items in candidates_by_source.items():
        source_deduped = dedupe_items(sorted(items, key=lambda i: i.score, reverse=True), max_items=300)
        candidates_by_source[src] = source_deduped
        all_candidates.extend(source_deduped)

    all_candidates.sort(key=lambda i: i.score, reverse=True)

    for item in all_candidates:
        if len(selected) >= target_total_links:
            break

        cluster = near_duplicate_signature(item.title)
        if item.url in used_url or cluster in used_cluster:
            continue

        if source_count[item.source] >= per_source_cap:
            continue

        if strict_diversity and intent_count[item.intent] >= per_intent_cap:
            continue

        used_url.add(item.url)
        used_cluster.add(cluster)
        source_count[item.source] += 1
        intent_count[item.intent] += 1
        selected.append(item)

    # Make sure core sources are represented where possible.
    present_sources = {i.source for i in selected}
    for src in CORE_SOURCES:
        if src in present_sources:
            continue
        fallback_candidates = candidates_by_source.get(src, [])
        for item in fallback_candidates:
            if item.url in used_url:
                continue
            if source_count[src] >= per_source_cap:
                break
            if strict_diversity and intent_count[item.intent] >= per_intent_cap:
                continue
            selected.append(item)
            used_url.add(item.url)
            used_cluster.add(near_duplicate_signature(item.title))
            source_count[src] += 1
            intent_count[item.intent] += 1
            present_sources.add(src)
            break

    # Final dedupe + ranking for stable output.
    selected = dedupe_items(sorted(selected, key=lambda i: i.score, reverse=True), max_items=target_total_links)
    return selected, source_notes


def mine_theme(
    theme: str,
    query_depth: int,
    target_total_links: int,
    strict_diversity: bool,
) -> Tuple[List[Item], Dict[str, str]]:
    queries = generate_long_tail_queries(theme, max_queries=query_depth)
    # Scale query sampling with depth but keep runtime bounded for daily jobs.
    sample_depth = min(max(18, query_depth), 72)

    candidates_by_source: Dict[str, List[Item]] = {}
    for source in ALL_SOURCES:
        candidates_by_source[source] = collect_candidates(theme, queries, source, sample_depth=sample_depth)

    curated, source_notes = curate_items(
        theme=theme,
        candidates_by_source=candidates_by_source,
        target_total_links=target_total_links,
        strict_diversity=strict_diversity,
    )
    return curated, source_notes


def bucketize(items: List[Item]) -> Dict[str, List[Item]]:
    buckets: Dict[str, List[Item]] = {name: [] for name in INTENT_BUCKETS}
    for item in items:
        buckets[item.intent].append(item)
    return buckets


def coverage_status(items: List[Item], min_links_per_theme: int) -> Tuple[str, str]:
    sources = {i.source for i in items}
    if len(items) >= min_links_per_theme and len(sources) >= 2:
        return "GOOD", f"{len(items)} links across {len(sources)} sources"
    return "INSUFFICIENT", f"{len(items)} links across {len(sources)} sources"


def is_theme_good(items: List[Item], min_links_per_theme: int) -> bool:
    sources = {i.source for i in items}
    return len(items) >= min_links_per_theme and len(sources) >= 2


def write_single_report(
    themes: List[str],
    results: Dict[str, List[Item]],
    source_notes_by_theme: Dict[str, Dict[str, str]],
    out_dir: Path,
    min_links_per_theme: int,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_path = out_dir / f"latest_news_{date_str}.md"

    lines: List[str] = [f"# Research Report - {date_str}", ""]

    for theme in themes:
        items = results.get(theme, [])
        buckets = bucketize(items)
        status, coverage = coverage_status(items, min_links_per_theme)

        lines.append(f"## {theme}")
        lines.append("")
        lines.append(f"Coverage: **{status}** ({coverage})")
        lines.append("")

        for intent in INTENT_BUCKETS:
            lines.append(f"### {intent}")
            lines.append("")
            bucket_items = buckets.get(intent, [])
            if not bucket_items:
                lines.append("- Insufficient quality for this intent bucket in this run.")
                lines.append("")
                continue

            for item in bucket_items:
                snippet = item.snippet[:180].strip()
                if snippet:
                    lines.append(f"- [{item.title}]({item.url}) ({item.source}) - {snippet}")
                else:
                    lines.append(f"- [{item.title}]({item.url}) ({item.source})")
            lines.append("")

        notes = source_notes_by_theme.get(theme, {})
        missing_core = [s for s in CORE_SOURCES if not any(i.source == s for i in items)]
        if notes or missing_core:
            lines.append("### Source Notes")
            lines.append("")
            for src in missing_core:
                lines.append(f"- {src}: Insufficient quality or unavailable in this run (core source).")
            for src, note in notes.items():
                lines.append(f"- {src}: {note}")
            lines.append("")

    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def parse_themes(raw: str) -> List[str]:
    if not raw.strip():
        return DEFAULT_THEMES
    themes = [x.strip() for x in raw.split(",") if x.strip()]
    return themes or DEFAULT_THEMES


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Technical-first research miner (single report)")
    parser.add_argument("--themes", default=",".join(DEFAULT_THEMES), help="Comma-separated topics/themes")
    parser.add_argument("--out-dir", default=".", help="Output directory for report")
    parser.add_argument("--query-depth", type=int, default=72, help="Long-tail query count per theme")
    parser.add_argument("--target-total-links", type=int, default=120, help="Total curated links budget per theme")
    parser.add_argument("--min-links-per-theme", type=int, default=12, help="Minimum links threshold for GOOD status")
    parser.add_argument(
        "--strict-diversity",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enforce strict per-source/per-intent diversity caps",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    themes = parse_themes(args.themes)
    out_dir = Path(args.out_dir)

    try:
        results: Dict[str, List[Item]] = {}
        source_notes_by_theme: Dict[str, Dict[str, str]] = {}

        for theme in themes:
            curated, source_notes = mine_theme(
                theme=theme,
                query_depth=max(12, args.query_depth),
                target_total_links=max(20, args.target_total_links),
                strict_diversity=bool(args.strict_diversity),
            )

            # Adaptive hardening pass:
            # If a theme is still weak, run a broader second pass with relaxed diversity
            # so tomorrow's report is more usable for manual content selection.
            if not is_theme_good(curated, max(1, args.min_links_per_theme)):
                recovery_curated, recovery_notes = mine_theme(
                    theme=theme,
                    query_depth=min(96, max(18, args.query_depth + 16)),
                    target_total_links=max(30, int(args.target_total_links * 1.35)),
                    strict_diversity=False,
                )
                if len(recovery_curated) > len(curated):
                    curated = recovery_curated
                    source_notes.update(recovery_notes)
                    source_notes["recovery"] = (
                        "Adaptive recovery pass enabled: expanded query depth and "
                        "relaxed diversity constraints for better coverage."
                    )

            results[theme] = curated
            source_notes_by_theme[theme] = source_notes

        report = write_single_report(
            themes=themes,
            results=results,
            source_notes_by_theme=source_notes_by_theme,
            out_dir=out_dir,
            min_links_per_theme=max(1, args.min_links_per_theme),
        )
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
