"""Check a built site before it is published. Exit 1 (and publish nothing) if anything is off.

  python3 -m auditline.guard [_site]

Checks: enough recommendations; every recommendation has its page, and that page shows the
publisher's exact status, the date the publisher's file was read, a link to the publisher and the
notice that a status is the publisher's claim; the search index and the data files list every
record; every count page carries a source and a read date; every internal link resolves; and,
while the site is staged, every page is noindex and no sitemap exists.
"""
import csv
import io
import json
import os
import re
import sys
from html import escape as E
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import refresh, sources
from .common import ROOT, indexable, load_config, site_url

MUST = ["index.html", "404.html", "robots.txt", "urls.txt", "feed.xml", "build.json", "static/style.css", "static/app.js",
        "static/favicon.svg", "open/index.html", "search/index.html", "assets/search.json", "changes/index.html",
        "coverage/index.html", "method/index.html", "about/index.html", "data/index.html", "data/recommendations.csv",
        "data/recommendations.json", "og/default.png"]
CLAIM = "It does not check whether a recommendation was carried out"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src"):
            if a.get(k):
                self.links.append(a[k])


def check(site_dir):
    cfg = load_config()
    errors = []
    base_path = urlparse(site_url(cfg)).path.rstrip("/")
    staged = not indexable(cfg)
    for f in MUST + [f"publisher/{s['id']}/index.html" for s in sources.COVERED] + [f"data/{s['id']}.{ext}" for s in sources.COVERED for ext in ("csv", "json")]:
        if not os.path.exists(os.path.join(site_dir, f)):
            errors.append(f"missing {f}")
    recs = [r for s in sources.COVERED for r in refresh.load_records(s["id"])]
    counts = {"pages": 0, "recommendations": len(recs)}
    if len(recs) < cfg["min_recommendations_to_publish"]:
        errors.append(f"only {len(recs)} recommendations (minimum {cfg['min_recommendations_to_publish']})")
    if len({r["id"] for r in recs}) != len(recs):
        errors.append("two recommendations share an id")
    for r in recs:
        page = os.path.join(site_dir, "rec", r["id"], "index.html")
        try:
            with open(page, encoding="utf-8") as f:
                html = f.read()
        except OSError:
            errors.append(f"{r['id']}: page missing")
            continue
        src = sources.BY_ID[r["publisher"]]
        status = E(r["status"] or "No status given")
        if f'<span class="status {r["state"]}">{status}</span>' not in html:
            errors.append(f"{r['id']}: page does not show the publisher's status exactly")
        if "<time datetime=" not in html or E(src["tracker"]) not in html or CLAIM not in html:
            errors.append(f"{r['id']}: page lacks its read date, its publisher link or the status notice")
        if r["text"] and E(r["text"]) not in html:
            errors.append(f"{r['id']}: page does not carry the publisher's wording")
        if len(errors) > 200:
            return errors, counts
    try:
        with open(os.path.join(site_dir, "assets", "search.json"), encoding="utf-8") as f:
            idx = json.load(f)
        live = [r for r in recs if r.get("in_export", True)]
        if len(idx["records"]) != len(live):
            errors.append(f"search index lists {len(idx['records'])} records for {len(live)} recommendations")
        known = {r["id"] for r in recs}
        for row in idx["records"]:
            if f"{idx['publishers'][row[0]]['id']}/{row[1]}" not in known:
                errors.append(f"search index row {row[1]} points at no recommendation")
                break
    except (OSError, ValueError, KeyError, IndexError):
        errors.append("assets/search.json unreadable")
    try:
        with open(os.path.join(site_dir, "data", "recommendations.csv"), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(io.StringIO(f.read())))
        if len(rows) != len(recs):
            errors.append(f"recommendations.csv has {len(rows)} rows for {len(recs)} recommendations")
        if rows and not all(rows[0].get(k) for k in ("id", "publisher", "number", "page", "source")):
            errors.append("recommendations.csv is missing its key columns")
    except OSError:
        errors.append("data/recommendations.csv unreadable")
    if staged:
        if os.path.exists(os.path.join(site_dir, "sitemap.xml")):
            errors.append("staged site must not publish a sitemap")
        with open(os.path.join(site_dir, "robots.txt"), encoding="utf-8") as f:
            if "Disallow: /" not in f.read():
                errors.append("staged site must disallow crawling in robots.txt")
    elif not os.path.exists(os.path.join(site_dir, "sitemap.xml")):
        errors.append("missing sitemap.xml")

    exists = {}

    def there(full):
        if full not in exists:
            exists[full] = os.path.exists(full)
        return exists[full]

    for dirpath, _, files in os.walk(site_dir):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            counts["pages"] += 1
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, site_dir).replace(os.sep, "/")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "<title>" not in text or 'name="description"' not in text or 'rel="canonical"' not in text:
                errors.append(f"{rel}: missing title, description or canonical")
            if staged and '<meta name="robots" content="noindex' not in text:
                errors.append(f"{rel}: staged page is missing noindex")
            if len(re.findall(r"<h1[ >]", text)) != 1:
                errors.append(f"{rel}: expected exactly one h1")
            if rel.startswith(("agency/", "publisher/", "open/")) and not re.search(r'class="asof">Source: <a href="https://[^"]+"[^>]*>[^<]+</a>, official export read\s+<time datetime=', text):
                errors.append(f"{rel}: counts without a source and a read date")
            if rel == "404.html":
                continue
            p = Links()
            p.feed(text)
            for link in set(p.links):
                u = urlparse(link)
                if u.scheme or link.startswith(("#", "mailto:", "data:", "//")):
                    continue
                target = u.path
                if target.startswith("/"):
                    if base_path and not target.startswith(base_path + "/"):
                        errors.append(f"{rel}: link {link} ignores the site base path")
                        continue
                    target = target[len(base_path):]
                else:
                    target = urlparse(urljoin("file:///" + rel, target)).path
                full = os.path.join(site_dir, target.lstrip("/"))
                if target.endswith("/"):
                    full = os.path.join(full, "index.html")
                if not there(full) and not there(os.path.join(full, "index.html")):
                    errors.append(f"{rel}: broken link {link}")
            if len(errors) > 200:
                return errors, counts
    return errors, counts


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site_dir = argv[0] if argv else os.path.join(ROOT, "_site")
    errors, counts = check(site_dir)
    for e in errors[:50]:
        print("GUARD", e)
    print(f"guard: {counts['pages']} pages, {counts['recommendations']} recommendations, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
