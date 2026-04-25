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

# Expanded keywords for trends + authority
KEYWORDS = [
 "embedded","firmware","rtos","driver","kernel","linux",
 "tinyml","machine learning","ai","edge ai",
 "automotive","ev","autonomous","adas",
 "semiconductor","chip","soc","microcontroller",
 "release","launch","new","announcement",
 "trend","future","next-gen"
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
    except:
        return ""

items = []
for url in FEEDS:
    d = feedparser.parse(url)
    for e in d.entries:
        s = score(e.title)
        if s > 0:
            text = get_article_text(e.link)
            items.append((s, e.title, e.link, text))

items = sorted(items, reverse=True)[:20]

today = datetime.now().strftime("%Y-%m-%d")
folder = "outputs"
os.makedirs(folder, exist_ok=True)

fname = f"{folder}/{today}.md"

with open(fname, "w") as f:
    f.write(f"# Research Feed — {today}\n\n")
    for s, title, link, text in items:
        f.write(f"## {title}\n")
        f.write(f"{link}\n\n")
        if text:
            f.write(f"{text}\n\n---\n\n")

print(f"Saved {fname}")
