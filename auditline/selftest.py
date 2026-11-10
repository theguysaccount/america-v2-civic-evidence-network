"""Self-test of the live site. Exit 1 if anything a visitor would notice is broken or stale.

  python3 -m auditline.selftest [--site-url URL] [--max-age-hours 200]

Reads only this project's own site. Checks the key pages, a spread of recommendation pages taken
from the live search index, that each publisher's file was read recently enough, that the build is
recent, and that the staged or indexed state on the live site is the one this repository is
configured for. Prints `stale=true` on its own line when the build or a publisher's file is older
than the limit, so the workflow can start a refresh.
"""
import argparse
import concurrent.futures
import json
import sys
import urllib.error
import urllib.request
from datetime import timedelta

from . import sources
from .common import indexable, load_config, now_utc, parse_iso, site_url


def fetch(url, ua):
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return e.code, b""
        except Exception:
            pass
    return 0, b""


def main(argv=None):
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default=site_url(cfg))
    ap.add_argument("--max-age-hours", type=float, default=200)
    ap.add_argument("--sample", type=int, default=40)
    a = ap.parse_args(argv)
    base, ua = a.site_url.rstrip("/"), cfg["user_agent"]
    problems, stale = [], False
    now = now_utc()

    code, home = fetch(base + "/", ua)
    if code != 200:
        print(f"FAIL home page answered {code}")
        return 1
    want_index = indexable(cfg)
    has_noindex = b'<meta name="robots" content="noindex' in home
    if want_index and has_noindex:
        problems.append("the site is configured as indexable but the live home page is noindex")
    if not want_index and not has_noindex:
        problems.append("the site is configured as staged but the live home page is missing noindex")
    code, body = fetch(base + "/build.json", ua)
    try:
        build = json.loads(body)
        built = parse_iso(build["built_at"])
    except Exception:
        build, built = {}, None
        problems.append(f"build.json did not load (status {code})")
    if built is not None and now - built > timedelta(hours=a.max_age_hours):
        stale = True
        problems.append(f"the live build is from {build.get('built_at')} (limit {a.max_age_hours:g} hours)")
    if build and build.get("recommendations", 0) < cfg["min_recommendations_to_publish"]:
        problems.append(f"only {build.get('recommendations')} recommendations on the live site")
    for s in sources.COVERED:
        st = (build.get("publishers") or {}).get(s["id"], {})
        read = parse_iso(st.get("retrieved_at"))
        if build and (read is None or now - read > timedelta(days=cfg["stale_after_days"])):
            stale = True
            problems.append(f"{s['short']}: the live site's copy was read {st.get('retrieved_at') or 'never'} (limit {cfg['stale_after_days']} days)")
    code, body = fetch(base + "/assets/search.json", ua)
    try:
        idx = json.loads(body)
        rows = idx["records"]
    except Exception:
        idx, rows = {}, []
        problems.append(f"search index did not load (status {code})")
    step = max(1, len(rows) // max(1, a.sample))
    sample = rows[::step][: a.sample]
    pages = [(base + p, None) for p in ("/open/", "/search/", "/changes/", "/coverage/", "/method/", "/data/", "/about/", "/feed.xml",
                                        "/data/recommendations.csv", "/static/style.css", "/static/app.js", "/og/default.png", "/robots.txt")]
    pages += [(f"{base}/publisher/{s['id']}/", None) for s in sources.COVERED]
    pages += [(f"{base}/rec/{idx['publishers'][r[0]]['id']}/{r[1]}/", idx["statuses"][r[4]]) for r in sample]

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda p: (p, fetch(p[0], ua)), pages))
    for (u, status), (c, body) in results:
        if c != 200:
            problems.append(f"{u} answered {c}")
        elif status is not None:
            text = body.decode("utf-8", "replace")
            if "<time datetime=" not in text:
                problems.append(f"{u} carries no read date")
            if 'class="status ' not in text or status.replace("&", "&amp;") not in text:
                problems.append(f"{u} does not show the status the search index lists ({status})")
    if not want_index:
        code, robots = fetch(base + "/robots.txt", ua)
        if b"Disallow: /" not in robots:
            problems.append("staged site's robots.txt does not disallow crawling")
    for p in problems[:40]:
        print("FAIL", p)
    print(f"selftest: {len(results)} URLs checked ({len(sample)} recommendation pages), {len(problems)} problems")
    print(f"stale={'true' if stale else 'false'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
