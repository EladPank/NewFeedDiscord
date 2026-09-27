#!/usr/bin/env python3
"""
news_digest.py

Pulls headlines from free, publicly available RSS feeds spanning different
political leanings, groups them, and posts a daily digest to a Discord
channel via webhook (and always writes a local digest.html too).

Setup:
    pip install feedparser requests

Usage:
    python news_digest.py                  # writes digest.html only
    python news_digest.py --discord         # also posts to Discord (see below)
    python news_digest.py --hours 24        # only include stories from last N hours (default 24)

Discord setup (free, no personal account involved):
    1. In Discord: Server Settings > Integrations > Webhooks > New Webhook
    2. Pick the channel it should post to, copy the Webhook URL
    3. Set it as the DISCORD_WEBHOOK_URL environment variable / GitHub secret

Scheduling it for free:
    - macOS/Linux: cron, e.g. `0 7 * * * /usr/bin/python3 /path/news_digest.py --discord`
    - Windows: Task Scheduler
    - Fully cloud-based & free: GitHub Actions with a `schedule` trigger
      (cron syntax) + a repo secret for the webhook URL, so it runs even
      with your computer off.
"""

import argparse
import os
from datetime import datetime, timedelta, timezone

import feedparser
import requests

# ---------------------------------------------------------------------------
# FEED CONFIG — edit freely. "lean" is a rough, widely-cited label, not a
# precise measurement. Swap in/out any feeds you prefer.
# ---------------------------------------------------------------------------
FEEDS = [
    # Wire services / attempt-at-neutral
    ("BBC News (World)", "http://feeds.bbci.co.uk/news/world/rss.xml", "Center"),
    ("NPR News", "https://feeds.npr.org/1001/rss.xml", "Center-Left"),
    ("Reuters World", "https://www.reutersagency.com/feed/?best-topics=world&post_type=best", "Center"),
    # Left-leaning
    ("The Guardian World", "https://www.theguardian.com/world/rss", "Left"),
    # Right-leaning
    ("Fox News Latest", "https://moxie.foxnews.com/google-publisher/latest.xml", "Right"),
    ("Reason", "https://reason.com/feed/", "Right-Libertarian"),
    # Add more here as (Name, RSS URL, Lean)
]

# ---------------------------------------------------------------------------
# DISCORD CONFIG — only needed if you run with --discord.
# Comes from an environment variable so nothing sensitive is ever written
# into this file or committed to the repo. Set as a GitHub repo secret:
#   DISCORD_WEBHOOK_URL
# ---------------------------------------------------------------------------
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Discord embed colors per lean group (decimal, not hex)
LEAN_COLORS = {
    "Center": 0x95A5A6,
    "Center-Left": 0x3498DB,
    "Left": 0xE74C3C,
    "Right": 0xE67E22,
    "Right-Libertarian": 0xF1C40F,
}
DEFAULT_COLOR = 0x2ECC71


def fetch_recent_entries(name, url, lean, cutoff):
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
            "lean": lean,
            "title": entry.get("title", "(no title)"),
            "link": entry.get("link", ""),
            "summary": entry.get("summary", "")[:220],
        })
    return entries


def build_digest(hours):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_entries = []
    print("Fetching feeds...")
    for name, url, lean in FEEDS:
        print(f"  - {name}")
        all_entries.extend(fetch_recent_entries(name, url, lean, cutoff))

    grouped = {}
    for e in all_entries:
        grouped.setdefault(e["lean"], []).append(e)

    return grouped


def render_html(grouped):
    today = datetime.now().strftime("%A, %B %d, %Y")
    html = [f"<html><head><meta charset='utf-8'><title>News Digest - {today}</title>",
            "<style>body{font-family:Georgia,serif;max-width:700px;margin:40px auto;line-height:1.5;}",
            "h1{font-size:22px;} h2{font-size:16px;border-bottom:1px solid #ccc;padding-bottom:4px;margin-top:30px;}",
            "a{color:#0645ad;text-decoration:none;} .src{color:#666;font-size:12px;}",
            "li{margin-bottom:14px;}</style></head><body>",
            f"<h1>Your News Digest — {today}</h1>"]

    if not grouped:
        html.append("<p>No new stories found in the given time window. Try increasing --hours.</p>")

    for lean, items in grouped.items():
        html.append(f"<h2>{lean}</h2><ul>")
        for item in items:
            html.append(
                f"<li><a href='{item['link']}'>{item['title']}</a><br>"
                f"<span class='src'>{item['source']}</span></li>"
            )
        html.append("</ul>")

    html.append("</body></html>")
    return "\n".join(html)


def build_discord_embeds(grouped):
    """
    Discord webhooks accept up to 10 embeds per message and each embed
    field value must be <= 1024 chars, so headlines are truncated defensively.
    """
    embeds = []
    for lean, items in grouped.items():
        lines = []
        for item in items[:10]:  # cap per group so we don't blow the char limit
            title = item["title"].replace("[", "(").replace("]", ")")
            lines.append(f"[{title}]({item['link']})  —  *{item['source']}*")
        description = "\n\n".join(lines) if lines else "No stories in this window."
        embeds.append({
            "title": lean,
            "description": description[:4000],
            "color": LEAN_COLORS.get(lean, DEFAULT_COLOR),
        })
    return embeds[:10]  # Discord hard limit


def send_discord(grouped):
    if not DISCORD_WEBHOOK_URL:
        raise SystemExit(
            "Missing DISCORD_WEBHOOK_URL environment variable. "
            "Set it as a GitHub repo secret, or export it locally before running."
        )

    today = datetime.now().strftime("%A, %B %d, %Y")
    payload = {
        "content": f"**Your News Digest — {today}**",
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
    parser.add_argument("--out", default="digest.html", help="Output HTML file path")
    args = parser.parse_args()

    grouped = build_digest(args.hours)
    html = render_html(grouped)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Digest written to {args.out}")

    if args.discord:
        send_discord(grouped)


if __name__ == "__main__":
    main()
