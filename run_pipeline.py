import feedparser
from datetime import datetime
import os

FEEDS = [
 "https://www.embedded.com/feed/",
 "https://www.embeddedrelated.com/blogs/rss.php",
 "https://embeddedartistry.com/feed",
 "https://interrupt.memfault.com/blog/rss.xml",
 "https://cnx-software.com/feed/",
 "https://hackaday.com/feed/"
]

KEYWORDS = ["embedded","firmware","rtos","driver","kernel","linux"]

def score(title):
    t = title.lower()
    return sum(1 for k in KEYWORDS if k in t)

items = []
for url in FEEDS:
    d = feedparser.parse(url)
    for e in d.entries:
        s = score(e.title)
        if s > 0:
            items.append((s, e.title, e.link))

items = sorted(items, reverse=True)[:20]

today = datetime.now().strftime("%Y-%m-%d")
folder = "outputs"
os.makedirs(folder, exist_ok=True)

fname = f"{folder}/{today}.md"

with open(fname, "w") as f:
    f.write(f"# Research Feed — {today}\n\n")
    for s, title, link in items:
        f.write(f"- {title}\n  {link}\n\n")

print(f"Saved {fname}")
