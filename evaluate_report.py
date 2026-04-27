#!/usr/bin/env python3
"""Evaluate research report quality.

Computes an objective score for latest_news_*.md using:
- coverage status per theme
- source diversity
- intent bucket coverage
- duplicate-link penalty

Exit code is non-zero if score is below --min-score.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

INTENT_BUCKETS = [
    "Debugging",
    "Implementation",
    "Tooling",
    "Interview",
    "Projects",
    "Career/Market",
]

THEME_RE = re.compile(r"^##\s+(.+?)\s*$")
BUCKET_RE = re.compile(r"^###\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<url>https?://[^)]+)\)\s*\((?P<source>[^)]+)\)")
COVERAGE_RE = re.compile(r"^Coverage:\s+\*\*(GOOD|INSUFFICIENT)\*\*\s*\((.+)\)")


def parse_report(path: Path) -> Dict:
    themes: Dict[str, Dict] = {}
    current_theme = None
    current_bucket = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue

        m_theme = THEME_RE.match(line)
        if m_theme:
            current_theme = m_theme.group(1)
            themes[current_theme] = {
                "coverage": "INSUFFICIENT",
                "buckets": {b: [] for b in INTENT_BUCKETS},
                "sources": set(),
                "urls": [],
            }
            current_bucket = None
            continue

        if current_theme is None:
            continue

        m_cov = COVERAGE_RE.match(line)
        if m_cov:
            themes[current_theme]["coverage"] = m_cov.group(1)
            continue

        m_bucket = BUCKET_RE.match(line)
        if m_bucket:
            b = m_bucket.group(1)
            current_bucket = b if b in themes[current_theme]["buckets"] else None
            continue

        if line.startswith("- ") and current_bucket:
            m_link = LINK_RE.search(line)
            if not m_link:
                continue
            url = m_link.group("url").strip().lower()
            source = m_link.group("source").strip().lower()
            themes[current_theme]["buckets"][current_bucket].append(url)
            themes[current_theme]["sources"].add(source)
            themes[current_theme]["urls"].append(url)

    return themes


def score_theme(theme_data: Dict) -> Dict:
    urls: List[str] = theme_data["urls"]
    unique_urls: Set[str] = set(urls)
    dup_rate = 0.0
    if urls:
        dup_rate = 1.0 - (len(unique_urls) / float(len(urls)))

    non_empty_buckets = sum(1 for _, vals in theme_data["buckets"].items() if vals)
    source_count = len(theme_data["sources"])

    score = 0.0

    # Coverage quality
    if theme_data["coverage"] == "GOOD":
        score += 35
    else:
        score += 10

    # Source diversity (cap at 5)
    score += min(source_count, 5) * 8

    # Bucket fill (0-6)
    score += (non_empty_buckets / 6.0) * 25.0

    # Duplicate penalty
    score += max(0.0, 20.0 * (1.0 - dup_rate * 2.0))

    return {
        "score": round(score, 2),
        "links": len(urls),
        "unique_links": len(unique_urls),
        "duplicate_rate": round(dup_rate, 3),
        "sources": source_count,
        "non_empty_buckets": non_empty_buckets,
        "coverage": theme_data["coverage"],
    }


def evaluate(path: Path) -> Dict:
    themes = parse_report(path)
    if not themes:
        return {"overall": 0.0, "themes": {}, "errors": ["No themes parsed"]}

    per_theme = {name: score_theme(data) for name, data in themes.items()}
    overall = sum(t["score"] for t in per_theme.values()) / float(len(per_theme))
    return {"overall": round(overall, 2), "themes": per_theme, "errors": []}


def find_latest_report(out_dir: Path) -> Path:
    files = sorted(out_dir.glob("latest_news_*.md"))
    if not files:
        raise FileNotFoundError("No latest_news_*.md found")
    return files[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate research report quality")
    parser.add_argument("--report", default="", help="Path to report markdown")
    parser.add_argument("--out-dir", default=".", help="Directory containing latest_news_*.md")
    parser.add_argument("--min-score", type=float, default=55.0, help="Minimum acceptable overall score")
    args = parser.parse_args()

    try:
        report = Path(args.report) if args.report else find_latest_report(Path(args.out_dir))
        result = evaluate(report)

        print(f"Report: {report}")
        print(f"Overall Score: {result['overall']}")
        for name, stats in result["themes"].items():
            print(
                f"- {name}: score={stats['score']} coverage={stats['coverage']} "
                f"links={stats['links']} unique={stats['unique_links']} "
                f"sources={stats['sources']} buckets={stats['non_empty_buckets']} "
                f"dup_rate={stats['duplicate_rate']}"
            )

        if result["errors"]:
            for err in result["errors"]:
                print(f"ERROR: {err}", file=sys.stderr)
            return 2

        if result["overall"] < args.min_score:
            print(
                f"Quality score below threshold: {result['overall']} < {args.min_score}",
                file=sys.stderr,
            )
            return 1

        return 0
    except Exception as exc:
        print(f"Evaluation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
