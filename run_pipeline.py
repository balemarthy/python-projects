import feedparser
from datetime import datetime
import os
from newspaper import Article

FEEDS = [
 "https://www.embedded.com/feed/",
 "https://www.embeddedrelated.com/blogs/rss.php",
 "https://embeddedartistry.com/feed",
 "https://interrupt.memfault.com/blog/rss.xml",
 "https://cnx-software.com/feed/",
 "https://hackaday.com/feed/"
]

# UPDATED: Career-focused filtering
KEYWORDS = [
  "hiring","job","career","skills","engineer","salary",
  "debugging","firmware","rtos","driver","linux",
  "embedded systems","bare metal",
  "project","build","implementation","case study",
  "how to","guide",
  "automotive","ev","robotics","industrial",
  "embedded ai","edge computing",
  "gcc","clang","toolchain","ci/cd","testing"
]


def score(title):
    t = title.lower()
    return sum(1 for k in KEYWORDS if k in t)


def get_article_text(url):
    try:
        a = Article(url)
        a.download()
        a.parse()
        return a.text[:2000]
    except Exception as e:
        print(f"Error fetching article: {e}")
        return ""

items = []

try:
    for url in FEEDS:
        d = feedparser.parse(url)
        print(f"Fetched {len(d.entries)} items from {url}")
        for e in d.entries:
            title_lower = e.title.lower()

            # FILTER: remove low-value announcement posts
            if any(x in title_lower for x in ["launch", "announced", "released"]):
                continue

            s = score(e.title)
            if s > 0:
                text = get_article_text(e.link)

                # FILTER: ignore shallow content
                if len(text) < 300:
                    continue

                items.append((s, e.title, e.link, text))
except Exception as e:
    print("Pipeline error:", e)

items = sorted(items, reverse=True)[:20]

today = datetime.now().strftime("%Y-%m-%d")
folder = "outputs"
os.makedirs(folder, exist_ok=True)

fname = f"{folder}/{today}.md"

with open(fname, "w") as f:
    f.write(f"# Research Feed — {today}\n\n")

    if not items:
        f.write("No high-signal items found today.\n")
    else:
        for s, title, link, text in items:
            f.write(f"## {title}\n")
            f.write(f"{link}\n\n")
            if text:
                f.write(f"{text[:500]}\n\n---\n\n")

print(f"Saved {fname}")
