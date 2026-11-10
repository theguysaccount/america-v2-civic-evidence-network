"""Load the built site in headless Chrome and check the part that needs a browser: search.

  python3 -m auditline.e2e [_site]

Serves the build at the same path it has on the web, then checks that the search page loads its
index, that the publisher and status filters count what the data says, and that searching for one
recommendation's number finds that recommendation and links to its page.
Skips (exit 0, with a warning) when no Chrome is installed; GitHub's runners have Chrome.
"""
import functools
import http.server
import os
import re
import subprocess
import sys
import tempfile
import threading
from urllib.parse import quote, urlsplit

from . import refresh, sources
from .common import ROOT, load_config, site_url
from .og import find_chrome


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def dump(chrome, url, profile):
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--mute-audio", f"--user-data-dir={profile}",
           "--virtual-time-budget=9000", "--dump-dom", url]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout


def shown(html):
    m = re.search(r'id="count"[^>]*>([\d,]+) recommendations?', html)
    return int(m.group(1).replace(",", "")) if m else None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site_dir = os.path.abspath(argv[0] if argv else os.path.join(ROOT, "_site"))
    chrome = find_chrome()
    if not chrome:
        print("::warning::e2e skipped: no Chrome found")
        return 0
    base = urlsplit(site_url(load_config())).path.strip("/")
    live = [r for s in sources.COVERED for r in refresh.load_records(s["id"]) if r.get("in_export", True)]
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        web = os.path.join(tmp, "web")
        os.makedirs(web)
        if base:
            os.makedirs(os.path.dirname(os.path.join(web, base)), exist_ok=True)
            os.symlink(site_dir, os.path.join(web, base))
        else:
            os.rmdir(web)
            os.symlink(site_dir, web)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=web))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        root = f"http://127.0.0.1:{srv.server_address[1]}/{base + '/' if base else ''}"
        try:
            n = 0

            def page(path):
                nonlocal n
                n += 1
                return dump(chrome, root + path, os.path.join(tmp, f"profile{n}"))

            html = page("search/")
            if shown(html) != len(live):
                problems.append(f"search: shows {shown(html)} recommendations with no filter, expected {len(live)}")
            want = sum(1 for r in live if r["state"] == "open")
            html = page("search/?s=open")
            if shown(html) != want:
                problems.append(f"search: status filter shows {shown(html)} open, expected {want}")
            for i, s in enumerate(sources.COVERED):
                want = sum(1 for r in live if r["publisher"] == s["id"])
                html = page(f"search/?p={i}")
                if shown(html) != want:
                    problems.append(f"search: publisher filter shows {shown(html)} for {s['short']}, expected {want}")
            rec = live[len(live) // 3]
            html = page("search/?q=" + quote(rec["number"]))
            got = shown(html)
            if not got or got > 12 or f'/rec/{rec["id"]}/"' not in html:
                problems.append(f"search: looking up {rec['number']} gave {got} rows and no link to its page")
        finally:
            srv.shutdown()
    for p in problems:
        print("E2E", p)
    print(f"e2e: search index, status filter, publisher filter and number lookup checked in Chrome; {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
