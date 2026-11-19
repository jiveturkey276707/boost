"""Fetch the newest videos for every YouTube handle in channels.json into feed.json.

Uses only the Python standard library. Runs on GitHub Actions every few hours.
A channel that fails to load keeps its previous videos, so one bad handle never
breaks the feed.
"""
import datetime
import json
import pathlib
import re
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": "CONSENT=YES+cb; SOCS=CAI",
}
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
KEEP = 15


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def resolve(handle):
    html = get(f"https://www.youtube.com/@{handle}")
    for pat in (r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"',
                r'"externalId":"(UC[\w-]{22})"',
                r'"channelId":"(UC[\w-]{22})"'):
        m = re.search(pat, html)
        if m:
            return m.group(1)
    raise ValueError("channel id not found")


def videos(channel_id):
    root = ET.fromstring(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"))
    title = root.findtext("a:title", default="", namespaces=NS)
    out = []
    for e in root.findall("a:entry", NS):
        link = e.find("a:link", NS)
        href = link.get("href", "") if link is not None else ""
        out.append({
            "id": e.findtext("yt:videoId", namespaces=NS),
            "title": e.findtext("a:title", default="", namespaces=NS),
            "published": e.findtext("a:published", default="", namespaces=NS),
            "short": "/shorts/" in href,
        })
    return title, out[:KEEP]


def main():
    cfg = json.loads((ROOT / "channels.json").read_text())
    handles = sorted({h.strip().lstrip("@") for k, v in cfg.items()
                      if not k.startswith("_") for h in v if h.strip()}, key=str.lower)
    feed_path = ROOT / "feed.json"
    try:
        old = json.loads(feed_path.read_text()).get("channels", {})
    except Exception:
        old = {}
    new = {}
    for h in handles:
        prev = old.get(h, {})
        try:
            cid = prev.get("id") or resolve(h)
            title, vids = videos(cid)
            new[h] = {"id": cid, "title": title, "videos": vids}
            print(f"ok   @{h}: {len(vids)} videos")
        except Exception as exc:  # keep what we had
            if prev:
                new[h] = prev
            print(f"FAIL @{h}: {exc}")
    feed = {"updated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "channels": new}
    feed_path.write_text(json.dumps(feed, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
