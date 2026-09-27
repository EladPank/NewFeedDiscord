#!/usr/bin/env python3
"""
news_digest.py

Pulls headlines from free, publicly available RSS feeds, groups them by
topic, and:
  1. writes public/index.html — a page with a clickable, expandable section
     per topic (meant to be published via GitHub Pages)
  2. optionally posts a short summary + link to that page in Discord

Setup:
    pip install feedparser requests

Usage:
    python news_digest.py                  # writes public/index.html only
    python news_digest.py --discord         # also posts to Discord (see below)
    python news_digest.py --hours 24        # only include stories from last N hours (default 24)

Discord setup (free, no personal account involved):
    1. In Discord: Server Settings > Integrations > Webhooks > New Webhook
    2. Pick the channel it should post to, copy the Webhook URL
    3. Set it as the DISCORD_WEBHOOK_URL environment variable / GitHub secret

GitHub Pages setup (free, gives you the real clickable page):
    1. In the repo: Settings > Pages > Source > "GitHub Actions"
    2. The workflow builds public/index.html and deploys it automatically
    3. Your page lives at https://<your-username>.github.io/<repo-name>/

Scheduling it for free:
    - Fully cloud-based & free: GitHub Actions with a `schedule` trigger
      (cron syntax), so it runs even with your computer off.
"""

import argparse
import os
from datetime import datetime, timedelta, timezone

import feedparser
import requests

# ---------------------------------------------------------------------------
# FEED CONFIG — edit freely. Each feed is (Display Name, RSS URL, Topic).
# Topics are shown in this order, both on the page and in Discord.
# ---------------------------------------------------------------------------
TOPIC_ORDER = ["Israel & Middle East", "International", "Finance", "Technology"]

FEEDS = [
    # --- Israel & Middle East ---
    ("Times of Israel", "https://www.timesofisrael.com/feed/", "Israel & Middle East"),
    ("Jerusalem Post", "https://www.jpost.com/rss/rssfeedsfrontpage.aspx", "Israel & Middle East"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "Israel & Middle East"),

    # --- International ---
    ("BBC News (World)", "http://feeds.bbci.co.uk/news/world/rss.xml", "International"),
    ("Reuters World", "https://www.reutersagency.com/feed/?best-topics=world&post_type=best", "International"),
    ("The Guardian World", "https://www.theguardian.com/world/rss", "International"),

    # --- Finance ---
    ("Reuters Business", "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best", "Finance"),
    ("CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "Finance"),
    ("MarketWatch", "http://feeds.marketwatch.com/marketwatch/topstories/", "Finance"),

    # --- Technology ---
    ("TechCrunch", "https://techcrunch.com/feed/", "Technology"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "Technology"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "Technology"),

    # Add more here as (Name, RSS URL, Topic) — Topic should match one of TOPIC_ORDER
]

# ---------------------------------------------------------------------------
# DISCORD CONFIG — only needed if you run with --discord.
# ---------------------------------------------------------------------------
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Optional: the page's public URL, e.g. https://yourname.github.io/yourrepo/
# Auto-derived from GITHUB_REPOSITORY when run inside GitHub Actions with
# Pages enabled; override manually if you're hosting it elsewhere.
PAGE_URL = os.environ.get("PAGE_URL", "")
if not PAGE_URL and os.environ.get("GITHUB_REPOSITORY"):
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    PAGE_URL = f"https://{owner}.github.io/{repo}/"

TOPIC_COLORS = {
    "Israel & Middle East": 0x0038B8,  # blue
    "International": 0x2ECC71,         # green
    "Finance": 0xF1C40F,               # gold
    "Technology": 0x9B59B6,            # purple
}
DEFAULT_COLOR = 0x95A5A6


def fetch_recent_entries(name, url, topic, cutoff):
    entries = []
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"  [warn] could not fetch {name}: {e}")
        return entries

    for entry in feed.entries:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published:
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
        entries.append({
            "source": name,
            "topic": topic,
            "title": entry.get("title", "(no title)"),
            "link": entry.get("link", ""),
            "summary": entry.get("summary", "")[:220],
        })
    return entries


def build_digest(hours):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_entries = []
    print("Fetching feeds...")
    for name, url, topic in FEEDS:
        print(f"  - {name} ({topic})")
        all_entries.extend(fetch_recent_entries(name, url, topic, cutoff))

    grouped = {topic: [] for topic in TOPIC_ORDER}
    for e in all_entries:
        grouped.setdefault(e["topic"], []).append(e)

    return grouped


def render_html(grouped):
    today = datetime.now().strftime("%A, %B %d, %Y")
    html = [
        "<html><head><meta charset='utf-8'>",
        f"<title>News Digest - {today}</title>",
        "<style>",
        "body{font-family:Georgia,serif;max-width:720px;margin:40px auto;line-height:1.5;padding:0 16px;}",
        "h1{font-size:24px;margin-bottom:4px;}",
        ".dateline{color:#666;font-size:14px;margin-bottom:24px;}",
        "details{border:1px solid #ddd;border-radius:8px;margin-bottom:12px;padding:0;}",
        "summary{cursor:pointer;font-size:18px;font-weight:bold;padding:14px 18px;list-style:none;}",
        "summary::-webkit-details-marker{display:none;}",
        "summary:before{content:'▶ ';font-size:14px;color:#666;}",
        "details[open] summary:before{content:'▼ ';}",
        "ul{list-style:none;padding:0 18px 14px 18px;margin:0;}",
        "li{margin-bottom:14px;}",
        "a{color:#0645ad;text-decoration:none;font-size:16px;}",
        "a:hover{text-decoration:underline;}",
        ".src{color:#666;font-size:12px;}",
        ".count{font-weight:normal;color:#888;font-size:14px;}",
        "</style></head><body>",
        f"<h1>Your News Digest</h1><div class='dateline'>{today}</div>",
    ]

    for topic in TOPIC_ORDER:
        items = grouped.get(topic, [])
        html.append(f"<details><summary>{topic} <span class='count'>({len(items)})</span></summary><ul>")
        if not items:
            html.append("<li>No new stories in this window.</li>")
        for item in items:
            html.append(
                f"<li><a href='{item['link']}'>{item['title']}</a><br>"
                f"<span class='src'>{item['source']}</span></li>"
            )
        html.append("</ul></details>")

    html.append("</body></html>")
    return "\n".join(html)


MAX_ITEMS_PER_TOPIC = 5      # headlines shown per topic in Discord
MAX_TITLE_CHARS = 100        # truncate very long headlines
MAX_TOTAL_EMBED_CHARS = 5500 # stay safely under Discord's 6000-char total limit


def build_discord_embeds(grouped):
    """
    Discord webhooks cap the combined size of title+description across every
    embed in one message at 6000 characters total, so we cap items per topic,
    truncate long titles, and trim whole embeds off the end if still too big.
    """
    embeds = []
    for topic in TOPIC_ORDER:
        items = grouped.get(topic, [])
        lines = []
        for item in items[:MAX_ITEMS_PER_TOPIC]:
            title = item["title"].replace("[", "(").replace("]", ")")
            if len(title) > MAX_TITLE_CHARS:
                title = title[:MAX_TITLE_CHARS - 1] + "…"
            lines.append(f"[{title}]({item['link']})  —  *{item['source']}*")
        description = "\n\n".join(lines) if lines else "No stories in this window."
        if len(items) > MAX_ITEMS_PER_TOPIC:
            description += f"\n\n*+{len(items) - MAX_ITEMS_PER_TOPIC} more — see the full page*"
        embeds.append({
            "title": topic,
            "description": description[:1800],
            "color": TOPIC_COLORS.get(topic, DEFAULT_COLOR),
        })

    def total_size(embed_list):
        return sum(len(e.get("title", "")) + len(e.get("description", "")) for e in embed_list)

    embeds = embeds[:10]
    while embeds and total_size(embeds) > MAX_TOTAL_EMBED_CHARS:
        embeds.pop()

    return embeds


def send_discord(grouped):
    if not DISCORD_WEBHOOK_URL:
        raise SystemExit(
            "Missing DISCORD_WEBHOOK_URL environment variable. "
            "Set it as a GitHub repo secret, or export it locally before running."
        )

    today = datetime.now().strftime("%A, %B %d, %Y")
    content = f"**Your News Digest — {today}**"
    if PAGE_URL:
        content += f"\nFull clickable digest: {PAGE_URL}"

    payload = {
        "content": content,
        "embeds": build_discord_embeds(grouped),
    }

    resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=15)
    if resp.status_code >= 300:
        raise SystemExit(f"Discord webhook failed ({resp.status_code}): {resp.text}")
    print("Posted to Discord.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24, help="How many hours back to include")
    parser.add_argument("--discord", action="store_true", help="Post the digest to Discord")
    parser.add_argument("--out", default="public/index.html", help="Output HTML file path")
    args = parser.parse_args()

    grouped = build_digest(args.hours)
    html = render_html(grouped)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Digest written to {args.out}")

    if args.discord:
        send_discord(grouped)


if __name__ == "__main__":
    main()
