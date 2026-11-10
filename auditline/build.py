"""Build the static site from data/.

  python3 -m auditline.build [--site _site]

Environment (all optional):
  SITE_URL          public base URL: the one setting to change at cutover
  SITE_INDEXABLE    "true" to allow indexing (the staged copy is noindex by default)
  GOATCOUNTER_URL   privacy-friendly page counts
  WATCHLIST_URL     link for the one marked "private watchlists" slot
"""
import argparse
import csv
import io
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from html import escape as E
from urllib.parse import urlsplit

from . import refresh, sources
from .common import ROOT, clip, human_date, indexable, iso, load_config, now_utc, parse_iso, read_json, short_date, site_url, slugify

OPEN_NOTE = ("“Open” and “closed” are the publisher's words. AuditLine repeats them with the date it read them. "
             "It does not check whether a recommendation was carried out, and a closed recommendation is not proof that a problem was fixed.")


def dollars(v):
    """The publisher's figure, exactly: $275,327,274 (cents only when the publisher gives them)."""
    return f"${v:,.2f}" if abs(v - round(v)) > 0.004 else f"${v:,.0f}"


def when(ts):
    if not ts:
        return "not yet read"
    return f'<time datetime="{E(ts)}">{human_date(parse_iso(ts))}</time>'


def chip(rec):
    return f'<span class="status {rec["state"]}">{E(rec["status"] or "No status given")}</span>'


def years_open(issued, today):
    if not issued:
        return None
    d = parse_iso(issued + "T00:00:00Z")
    return (today - d).days / 365.25


class Site:
    def __init__(self, out, now=None):
        self.cfg = load_config()
        self.url = site_url(self.cfg)
        self.base = urlsplit(self.url).path.rstrip("/")
        self.out = out
        self.now = now or now_utc()
        self.indexable = indexable(self.cfg)
        self.name = self.cfg["name"]
        self.repo_url = f"https://github.com/{self.cfg['repo']}"
        self.urls, self.og_jobs = [], []
        self.asof = ""

    def href(self, path):
        return self.base + path

    def write(self, rel, text):
        path = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def page(self, path, title, description, body, *, crumbs=None, jsonld=None, nav="", listed=True, og=None, lastmod=None, extra_head=""):
        canonical = self.url + path
        full = title if self.name in title else f"{title} | {self.name}"
        robots = "" if (self.indexable and listed) else '<meta name="robots" content="noindex, nofollow">\n'
        ld = ""
        for block in jsonld or []:
            safe = json.dumps(block, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            ld += f'<script type="application/ld+json">{safe}</script>\n'
        gc = os.environ.get("GOATCOUNTER_URL", "").strip()
        analytics = f'<script data-goatcounter="{E(gc)}" async src="https://gc.zgo.at/count.js"></script>\n' if gc else ""
        og_file = "default.png"
        if og:
            og_file = og[0] + ".png"
            self.og_jobs.append(og)
        crumb_html = ""
        if crumbs:
            crumb_html = '<p class="crumbs">' + " › ".join(f'<a href="{self.href(p)}">{E(t)}</a>' for t, p in crumbs) + "</p>"

        def nav_link(key, label, p):
            cur = ' aria-current="page"' if nav == key else ""
            return f'<a href="{self.href(p)}"{cur}>{label}</a>'

        html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(full)}</title>
<meta name="description" content="{E(description)}">
{robots}<link rel="canonical" href="{E(canonical)}">
<meta name="site-base" content="{E(self.base)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{E(self.name)}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(description)}">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:image" content="{E(self.url)}/og/{og_file}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{self.href('/static/favicon.svg')}" type="image/svg+xml">
<link rel="alternate" type="application/atom+xml" title="{E(self.name)}: status changes" href="{self.href('/feed.xml')}">
{extra_head}<link rel="stylesheet" href="{self.href('/static/style.css')}">
{ld}{analytics}</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site"><div class="wrap">
<a class="brand" href="{self.href('/')}"><small>★ America V2</small><b>Audit<em>Line</em></b></a>
<span class="alpha">ALPHA</span>
<nav class="main" aria-label="Main">
{nav_link('open', 'Open by agency', '/open/')}
{nav_link('search', 'Search', '/search/')}
{nav_link('changes', 'Changes', '/changes/')}
{nav_link('coverage', 'Coverage', '/coverage/')}
{nav_link('method', 'Evidence rules', '/method/')}
{nav_link('data', 'Data', '/data/')}
</nav>
</div></header>
<main id="main"><div class="wrap">
{crumb_html}
{body}
</div></main>
<footer class="site"><div class="wrap"><div class="cols">
<div><strong>AuditLine</strong><p>Every official warning, and what the publisher says happened next. Publisher status is labelled.
No inferred fraud or waste. Every change becomes a dated event.</p></div>
<div><strong>Publishers mirrored</strong><ul>
{''.join(f'<li><a href="{E(s["tracker"])}" rel="noopener">{E(s["tracker_name"])}</a></li>' for s in sources.COVERED)}
<li><a href="{self.href('/coverage/')}">What is and is not covered</a></li></ul></div>
<div><strong>This site</strong><ul>
<li><a href="{self.href('/method/')}">Evidence rules</a></li>
<li><a href="{self.href('/data/')}">Open CSV and JSON</a></li>
<li><a href="{self.href('/about/')}">About and corrections</a></li>
<li><a href="{E(self.repo_url)}" rel="noopener">Source code</a></li></ul></div>
</div>
<p>Static edition, rebuilt by an automated job. Publisher files last read {when(self.asof)}. A status shown here is the
publisher's claim on the date shown, not an independent finding. Not affiliated with any inspector general or agency.</p>
</div></footer>
<script src="{self.href('/static/app.js')}" defer></script>
</body>
</html>
"""
        rel = path.lstrip("/")
        if rel.endswith("/") or rel == "":
            rel += "index.html"
        self.write(rel, html)
        if listed and self.indexable:
            self.urls.append((canonical, lastmod or self.asof[:10]))

    def slot(self):
        url = os.environ.get("WATCHLIST_URL", "").strip()
        if not url.startswith("https://"):
            return ""
        return (f'<aside class="slot" aria-label="Paid service"><small>Paid service</small>'
                f'<a href="{E(url)}" rel="noopener">Private watchlists and alerts for organizations</a></aside>')


FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#126e61"/>'
           '<path d="M8 22h16M10 22V12m4 10V12m4 10V12m4 10V12M7 12l9-5 9 5z" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>')


def rec_row(site, r, show_agency=True):
    bits = [f"{E(sources.BY_ID[r['publisher']]['short'])} {E(r['number'])}"]
    if show_agency and r.get("agency"):
        bits.append(E(r["agency"]))
    if r.get("issued"):
        bits.append("issued " + short_date(r["issued"]))
    if r["state"] == "closed" and r.get("closed"):
        bits.append("closed " + short_date(r["closed"]))
    return (f'<li><span><a href="{site.href("/rec/" + r["id"] + "/")}">{E(clip(r["text"], 190) or "Recommendation " + r["number"])}</a>'
            f'<small>{" · ".join(bits)}</small></span>{chip(r)}</li>')


def tiles(site, items):
    return '<ul class="grid">' + "".join(
        f'<li><a class="tile" href="{site.href(p)}"><small>{E(a)}</small><b>{E(b)}</b><span>{E(c)}</span></a></li>' for a, b, c, p in items) + "</ul>"


def describe_event(e, rec):
    """One plain sentence for a recorded change. States only that the publisher's file changed."""
    f, old, new = e["field"], e.get("old"), e.get("new")
    if f == "added":
        return f"First appeared in the publisher's file, with status “{new or 'none given'}”."
    if f == "in_export":
        return "Returned to the publisher's file." if new else "No longer in the publisher's file."
    if f == "status":
        return f"Status changed from “{old or 'none'}” to “{new or 'none'}”."
    if f == "amounts":
        def fmt(d):
            return ", ".join(f"{sources.AMOUNT_LABEL.get(k, k)} {dollars(v)}" for k, v in (d or {}).items()) or "none"
        return f"Dollar figures changed from {fmt(old)} to {fmt(new)}."
    if f == "text":
        return "The publisher changed the recommendation's wording."
    label = sources.FIELD_LABEL.get(f, f)
    if f in ("closed", "next_update", "last_update"):
        old, new = human_date(old) or "none", human_date(new) or "none"
    return f"{label} changed from “{old or 'none'}” to “{new or 'none'}”."


def build(out, now=None):
    site = Site(out, now)
    cfg = site.cfg
    status = read_json(refresh.status_path(), {}) or {}
    pubs = status.get("publishers", {})
    recs, events_by_id, all_events = [], defaultdict(list), []
    for s in sources.COVERED:
        recs += refresh.load_records(s["id"])
        for e in refresh.load_events(s["id"]):
            events_by_id[e["id"]].append(e)
            all_events.append(e)
    by_id = {r["id"]: r for r in recs}
    site.asof = max((pubs.get(s["id"], {}).get("retrieved_at", "") for s in sources.COVERED), default="") or iso(site.now)
    today = parse_iso(site.asof)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(out, "static"))
    site.write("static/favicon.svg", FAVICON)

    live = [r for r in recs if r.get("in_export", True)]
    open_recs = [r for r in live if r["state"] == "open"]
    by_pub = defaultdict(list)
    by_agency = defaultdict(list)      # (publisher, agency) -> records
    by_report = defaultdict(list)
    for r in recs:
        by_pub[r["publisher"]].append(r)
        by_agency[(r["publisher"], r["agency"] or "Agency not stated")].append(r)
        by_report[(r["publisher"], r["report_number"])].append(r)

    def agency_path(pid, agency):
        return f"/agency/{pid}/{slugify(agency) or 'not-stated'}/"

    def report_link(r):
        """The per-report link, unless the weekly link check found that this publisher's report links stopped working."""
        state = pubs.get(r["publisher"], {}).get("links", {}).get("report_link", "ok")
        broken = state.startswith(("HTTP 4", "opened, but"))
        return r["report_url"] if r.get("report_url") and not broken else sources.BY_ID[r["publisher"]]["tracker"]

    def read_line(pid):
        st = pubs.get(pid, {})
        s = sources.BY_ID[pid]
        stale = ""
        if st.get("outcome") and st.get("outcome") != "ok":
            stale = (f' <b>The latest attempt, on {human_date(st.get("checked_at"))}, did not succeed ({E(st.get("outcome"))}: {E(st.get("note", ""))}); '
                     f"the records below are from the last good file.</b>")
        return (f'<p class="asof">Source: <a href="{E(s["tracker"])}" rel="noopener">{E(s["tracker_name"])}</a>, official export read '
                f'{when(st.get("retrieved_at", ""))}.{stale}</p>')

    home = [("AuditLine", "/")]

    # ------------------------------------------------------------------------------------ recommendation pages
    for r in recs:
        s = sources.BY_ID[r["publisher"]]
        st = pubs.get(r["publisher"], {})
        agency = r["agency"] or "Agency not stated"
        facts = [("Responsible agency", f'<a href="{site.href(agency_path(r["publisher"], agency))}">{E(agency)}</a>'),
                 ("Issued", E(human_date(r["issued"]) or "Not stated"))]
        report = E(r["report_title"] or "Title not stated") + (f' <span class="asof">({E(r["report_number"])})</span>' if r["report_number"] else "")
        report += f' · <a href="{E(report_link(r))}" rel="noopener">find it at {E(s["short"])}</a>'
        facts.append(("Report", report))
        if r.get("report_type"):
            facts.append(("Kind of report", E(r["report_type"])))
        if r.get("response"):
            facts.append(("Agency response", E(r["response"]) + " <span class=\"asof\">(as recorded by the publisher)</span>"))
        if r.get("closed"):
            facts.append(("Closed", E(human_date(r["closed"])) + " <span class=\"asof\">(publisher's date)</span>"))
        if r.get("last_update"):
            facts.append(("Last update received", E(human_date(r["last_update"]))))
        if r.get("next_update"):
            facts.append(("Next update expected", E(human_date(r["next_update"])) + " <span class=\"asof\">(publisher's date)</span>"))
        for k, v in (r.get("amounts") or {}).items():
            facts.append((sources.AMOUNT_LABEL.get(k, k), E(dollars(v)) + " <span class=\"asof\">(the publisher's figure; not realised savings)</span>"))
        if r.get("flags"):
            facts.append(("Publisher flags", E(", ".join(r["flags"]))))
        if r.get("topics"):
            facts.append(("Publisher topics", E(", ".join(r["topics"]))))
        facts_html = '<dl class="facts">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts) + "</dl>"

        timeline = []
        if r.get("issued"):
            timeline.append((r["issued"], f"Issued by {E(s['short'])}.", "publisher's date"))
        for e in events_by_id.get(r["id"], []):
            timeline.append((e["at"], E(describe_event(e, r)), "observed by AuditLine in the publisher's file"))
        if r.get("closed"):
            timeline.append((r["closed"], f"Closed, with status “{E(r['status'])}”.", "publisher's date"))
        timeline.append((r.get("first_seen", ""), "First recorded by AuditLine.", "start of AuditLine's own history for this record"))
        timeline.sort(key=lambda t: t[0][:10])
        timeline_html = '<ol class="timeline">' + "".join(
            f'<li><time datetime="{E(d)}">{E(human_date(d))}</time>{text} <small>({E(src)})</small></li>' for d, text, src in timeline if d) + "</ol>"

        siblings = sorted((x for x in by_report[(r["publisher"], r["report_number"])] if x["id"] != r["id"]), key=lambda x: x["number"]) if r["report_number"] else []
        sib_html = ""
        if siblings:
            n_open = sum(1 for x in siblings if x["state"] == "open")
            sib_html = (f'<h2>Other recommendations from this report</h2><p>{len(siblings)} more, of which {n_open} '
                        f'{"is" if n_open == 1 else "are"} open in the publisher\'s file.</p><ul class="recs">'
                        + "".join(rec_row(site, x, show_agency=False) for x in siblings[:40]) + "</ul>"
                        + (f"<p>And {len(siblings) - 40} more in the <a href=\"{site.href('/data/')}\">data files</a>.</p>" if len(siblings) > 40 else ""))
        gone = ""
        if not r.get("in_export", True):
            gone = (f'<p class="note warn"><b>No longer in the publisher\'s file.</b> This recommendation was in {E(s["short"])}\'s export until '
                    f'{E(human_date(r.get("gone_since")))}. The status below is the last one the publisher reported.</p>')
        age = years_open(r["issued"], today) if r["state"] == "open" else None
        age_html = f' <span class="says">Open for {age:.1f} years since it was issued.</span>' if age is not None and age >= 0 else ""
        past = ""
        if r["state"] == "open" and r.get("next_update") and r["next_update"] < site.asof[:10]:
            past = (f'<p class="note">The publisher\'s file lists {E(human_date(r["next_update"]))} as the date the next update was expected. '
                    f"That date has passed. This is the publisher's own date field, not a finding that anyone missed a deadline.</p>")
        cut = ""
        if s.get("text_limit") and len(r["text"]) >= s["text_limit"]:
            cut = (f'<p class="note">{E(s["short"])}\'s export stops at {s["text_limit"]:,} characters, so this text is cut short. '
                   f'The full wording is in <a href="{E(report_link(r))}" rel="noopener">the publisher\'s tracker</a>.</p>')
        title_text = clip(r["text"], 150) or f"Recommendation {r['number']}"
        desc = (f"{s['short']} recommendation {r['number']} to {agency}. Publisher status: {r['status'] or 'none given'}, as of {human_date(st.get('retrieved_at', ''))}. "
                f"Issued {human_date(r['issued']) or 'date not stated'}.")
        body = f"""<p class="eyebrow">{E(s['short'])} recommendation {E(r['number'])}</p>
<h1 class="long">{E(title_text)}</h1>
{gone}
<div class="panel status-panel">{chip(r)}<span class="says">The publisher's status, as reported by {E(s['name'])} in the file read {when(st.get('retrieved_at', ''))}.</span>{age_html}</div>
{past}
<h2>The recommendation, in the publisher's words</h2>
<blockquote class="rec">{E(r['text']) or 'The publisher gives no text.'}</blockquote>
{cut}
{facts_html}
<p class="note">{E(OPEN_NOTE)}</p>
<h2>Dated history</h2>
{timeline_html}
<p class="asof">Dates marked "publisher's date" come from the publisher's file. AuditLine's own observations begin {E(human_date(r.get('first_seen')))} and are added each time the publisher's file changes.</p>
{site.slot()}
{sib_html}
<h2>Source</h2>
<p><a class="btn primary" href="{E(report_link(r))}" rel="noopener">Open this report in {E(s['short'])}'s tracker</a>
<a class="btn" href="{site.href('/data/' + r['publisher'] + '.csv')}">This publisher's records (CSV)</a></p>
<p class="asof">Official export: <code>{E(s['url'])}</code>. File read {when(st.get('retrieved_at', ''))}, {st.get('rows', 0):,} rows,
SHA-256 <code>{E((st.get('sha256') or '')[:16])}…</code>. {E(s['note'])}</p>"""
        site.page(f"/rec/{r['id']}/", f"{s['short']} {r['number']}: {clip(r['text'], 80)}", desc, body,
                  crumbs=home + [(s["short"], f"/publisher/{s['id']}/"), (agency, agency_path(r["publisher"], agency))],
                  lastmod=(max([e["at"] for e in events_by_id.get(r["id"], [])] + [r.get("first_seen", "")]) or site.asof)[:10])

    # ------------------------------------------------------------------------------------ agency pages
    agency_tiles = []
    for (pid, agency), items in sorted(by_agency.items()):
        s = sources.BY_ID[pid]
        cur = [r for r in items if r.get("in_export", True)]
        opened = sorted((r for r in cur if r["state"] == "open"), key=lambda r: r["issued"] or "9999")
        closed = sorted((r for r in cur if r["state"] == "closed"), key=lambda r: r.get("closed") or r["issued"], reverse=True)
        unstated = [r for r in cur if r["state"] == "other"]
        statuses = Counter(r["status"] or "No status given" for r in cur)
        oldest = opened[0] if opened else None
        over5 = sum(1 for r in opened if (years_open(r["issued"], today) or 0) >= 5)
        status_rows = "".join(f"<tr><td>{E(k)}</td><td class=\"num\">{v:,}</td></tr>" for k, v in statuses.most_common())
        path = agency_path(pid, agency)
        aslug = path.rstrip("/").rsplit("/", 1)[1]
        body = f"""<p class="eyebrow">{E(s['short'])} recommendations · {E(s['department'])}</p>
<h1>{E(agency)}</h1>
<p class="lede">{len(opened):,} open and {len(closed):,} closed recommendations from {E(s['name'])} name this office as responsible, in the publisher's own file.</p>
{read_line(pid)}
<div class="stats">
<div class="stat"><b>{len(opened):,}</b><span>open</span><small>publisher's status</small></div>
<div class="stat"><b>{len(closed):,}</b><span>closed</span><small>all closed statuses</small></div>
<div class="stat"><b>{over5:,}</b><span>open five years or more</span><small>counted from the issue date</small></div>
<div class="stat"><b>{E(short_date(oldest['issued'])) if oldest else '—'}</b><span>oldest open, issued</span></div>
</div>
<div class="tablewrap"><table><thead><tr><th>Publisher's status</th><th class="num">Recommendations</th></tr></thead><tbody>{status_rows}</tbody></table></div>
<p class="note">{E(OPEN_NOTE)}</p>
<h2 id="open">Open recommendations, oldest first</h2>
{'<ul class="recs">' + ''.join(rec_row(site, r, show_agency=False) for r in opened) + '</ul>' if opened else '<p>None in the publisher&#x27;s file.</p>'}
<h2 id="closed">Closed recommendations, most recently closed first</h2>
{'<ul class="recs">' + ''.join(rec_row(site, r, show_agency=False) for r in closed[:150]) + '</ul>' if closed else '<p>None in the publisher&#x27;s file.</p>'}
{f'<p><a class="btn" href="{site.href(path + "closed/")}">All {len(closed):,} closed recommendations</a></p>' if len(closed) > 150 else ''}
<h2 id="follow">Follow or embed this office</h2>
<p>Every change the publisher makes to one of this office's recommendations is added to a feed:
<a href="{site.href(path + 'feed.xml')}">{E(agency)} changes (Atom)</a>.</p>
<details class="embed"><summary>Embed the open count on your site</summary>
<p>Paste this where the count should appear. It shows the publisher's count and the date its file was read, and links back here.</p>
<pre><code>{E(f'<iframe src="{site.url}/embed/{pid}/{aslug}/" title="Open {s["short"]} recommendations: {agency}" width="340" height="150" style="border:0;max-width:100%" loading="lazy"></iframe>')}</code></pre></details>
{'<h2 id="unstated">Neither open nor closed in the publisher&#x27;s file</h2><ul class="recs">' + ''.join(rec_row(site, r, show_agency=False) for r in unstated) + '</ul>' if unstated else ''}"""
        site.page(path, f"{agency}: open {s['short']} recommendations",
                  f"{len(opened):,} open and {len(closed):,} closed {s['short']} recommendations for {agency}, with the publisher's status, dates and a link to each one. File read {human_date(pubs.get(pid, {}).get('retrieved_at', ''))}.",
                  body, crumbs=home + [(s["short"], f"/publisher/{pid}/")], nav="open",
                  og=(f"agency-{pid}-{slugify(agency)}", agency, f"{len(opened):,} open {s['short']} recommendations"),
                  extra_head=f'<link rel="alternate" type="application/atom+xml" title="{E(agency)}: changes" href="{site.href(path + "feed.xml")}">\n')
        if len(closed) > 150:
            site.page(path + "closed/", f"{agency}: closed {s['short']} recommendations",
                      f"All {len(closed):,} closed {s['short']} recommendations for {agency}, most recently closed first.",
                      f"""<p class="eyebrow">{E(s['short'])} recommendations</p><h1>{E(agency)}: closed recommendations</h1>
{read_line(pid)}<p class="note">{E(OPEN_NOTE)}</p>
<ul class="recs">{''.join(rec_row(site, r, show_agency=False) for r in closed)}</ul>""",
                      crumbs=home + [(s["short"], f"/publisher/{pid}/"), (agency, path)], nav="open")
        agency_tiles.append((pid, agency, len(opened), len(closed), oldest["issued"] if oldest else "", path))
        # the agency's own feed of observed changes
        ids = {r["id"] for r in items}
        mine = sorted((e for e in all_events if e["id"] in ids), key=lambda e: e["at"], reverse=True)[:60]
        feed_entries = "".join(
            f"<entry><title>{E(sources.BY_ID[pid]['short'])} {E(by_id[e['id']]['number'])}: {E(describe_event(e, by_id[e['id']]))}</title>"
            f"<id>{E(site.url)}/rec/{E(e['id'])}/#{E(e['field'])}-{E(e['at'])}</id><link href=\"{E(site.url)}/rec/{E(e['id'])}/\"/>"
            f"<updated>{E(e['at'])}</updated><summary>{E(clip(by_id[e['id']]['text'], 240))}</summary></entry>" for e in mine)
        site.write(path.lstrip("/") + "feed.xml",
                   f'<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"><title>AuditLine: {E(agency)} ({E(s["short"])})</title>'
                   f'<id>{E(site.url)}{E(path)}</id><link href="{E(site.url)}{E(path)}"/><link rel="self" href="{E(site.url)}{E(path)}feed.xml"/>'
                   f"<updated>{E(mine[0]['at'] if mine else pubs.get(pid, {}).get('retrieved_at') or site.asof)}</updated><author><name>AuditLine</name></author>{feed_entries}</feed>\n")
        # the embeddable count: a tiny page of its own, never indexed
        site.write(f"embed/{pid}/{aslug}/index.html", f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Open {E(s['short'])} recommendations: {E(agency)} | AuditLine</title>
<meta name="description" content="{len(opened):,} open {E(s['short'])} recommendations name {E(agency)} as responsible, by the publisher's own status.">
<meta name="robots" content="noindex, nofollow"><link rel="canonical" href="{E(site.url)}{E(path)}">
<style>html,body{{margin:0}}body{{font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#132524;background:#fbfaf5}}
a{{display:block;padding:14px 16px;border:1px solid #cfdcd6;border-radius:12px;text-decoration:none;color:inherit;background:#fff}}
h1{{font-size:13px;font-weight:600;margin:0;color:#126e61}}b{{display:block;font-size:34px;line-height:1.1;margin:4px 0 2px}}small{{color:#52605d;display:block}}
@media (prefers-color-scheme:dark){{body{{background:#0f1c1b;color:#eef5f2}}a{{background:#152827;border-color:#2b4541}}h1{{color:#7fd6c2}}small{{color:#a9bab5}}}}</style></head>
<body><a href="{E(site.url)}{E(path)}" target="_blank" rel="noopener"><h1>{E(agency)}</h1><b>{len(opened):,}</b>
<small>open {E(s['short'])} recommendations, by the publisher's status</small>
<small>File read {E(human_date(pubs.get(pid, {}).get('retrieved_at', '')))} · AuditLine</small></a></body></html>
""")

    # ------------------------------------------------------------------------------------ publisher pages
    for s in sources.COVERED:
        pid = s["id"]
        cur = [r for r in by_pub[pid] if r.get("in_export", True)]
        statuses = Counter(r["status"] or "No status given" for r in cur)
        rows = "".join(f'<tr><td><a href="{site.href(p)}">{E(a)}</a></td><td class="num">{o:,}</td><td class="num">{c:,}</td><td>{E(short_date(old))}</td></tr>'
                       for pp, a, o, c, old, p in sorted(agency_tiles, key=lambda t: -t[2]) if pp == pid)
        st = pubs.get(pid, {})
        body = f"""<p class="eyebrow">Publisher</p><h1>{E(s['name'])}</h1>
<p class="lede">{len(cur):,} recommendations in the publisher's official export: {sum(1 for r in cur if r['state'] == 'open'):,} open and {sum(1 for r in cur if r['state'] == 'closed'):,} closed, by the publisher's own status.</p>
{read_line(pid)}
<div class="tablewrap"><table><thead><tr><th>Publisher's status, exactly as written</th><th class="num">Recommendations</th></tr></thead><tbody>
{''.join(f'<tr><td>{E(k)}</td><td class="num">{v:,}</td></tr>' for k, v in statuses.most_common())}</tbody></table></div>
<p class="note">{E(s['note'])} {E(s['cadence'])}</p>
<h2>By responsible agency</h2>
<div class="tablewrap"><table><thead><tr><th>Agency</th><th class="num">Open</th><th class="num">Closed</th><th>Oldest open, issued</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Source file</h2>
<p class="asof">Official export: <code>{E(s['url'])}</code><br>Read {when(st.get('retrieved_at', ''))} · {st.get('rows', 0):,} rows · {st.get('bytes', 0):,} bytes · SHA-256 <code>{E(st.get('sha256', ''))}</code></p>
<p><a class="btn primary" href="{E(s['tracker'])}" rel="noopener">{E(s['tracker_name'])}</a> <a class="btn" href="{site.href('/data/' + pid + '.csv')}">Mirror (CSV)</a>
<a class="btn" href="{site.href('/data/' + pid + '.json')}">Mirror (JSON)</a></p>"""
        site.page(f"/publisher/{pid}/", f"{s['name']}: recommendations and their status",
                  f"All {len(cur):,} recommendations in {s['short']}'s official export, by status and responsible agency, as read on {human_date(st.get('retrieved_at', ''))}.",
                  body, crumbs=home, og=(f"publisher-{pid}", s["name"], f"{len(cur):,} recommendations mirrored"))

    # ------------------------------------------------------------------------------------ open by agency
    rows = "".join(
        f'<tr><td><a href="{site.href(p)}">{E(a)}</a></td><td>{E(sources.BY_ID[pp]["short"])}</td><td class="num">{o:,}</td><td class="num">{c:,}</td><td>{E(short_date(old))}</td></tr>'
        for pp, a, o, c, old, p in sorted(agency_tiles, key=lambda t: -t[2]))
    past = sorted((r for r in open_recs if r.get("next_update") and r["next_update"] < site.asof[:10]), key=lambda r: r["next_update"])
    site.page("/open/", "Open inspector-general recommendations by agency",
              f"How many recommendations each agency still has open, according to the inspectors general who made them: {len(open_recs):,} open across {len(agency_tiles)} offices.",
              f"""<p class="eyebrow">Open recommendations</p><h1>Who still has an open recommendation?</h1>
<p class="lede">{len(open_recs):,} recommendations are open in the publishers' own files, across {len(agency_tiles)} responsible offices.</p>
{''.join(read_line(s['id']) for s in sources.COVERED)}
<div class="tablewrap"><table><thead><tr><th>Responsible agency</th><th>Publisher</th><th class="num">Open</th><th class="num">Closed</th><th>Oldest open, issued</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="note">{E(OPEN_NOTE)}</p>
{f'<h2>Past the publisher&#x27;s expected-update date</h2><p>{len(past):,} open recommendations list a “next update expected” date that has passed. That field is HHS OIG&#x27;s own. A passed date does not mean anyone missed a legal deadline.</p><p><a class="btn" href="{site.href("/open/past-expected-update/")}">See the list</a></p>' if past else ''}""",
              crumbs=home, nav="open")
    if past:
        site.page("/open/past-expected-update/", "Open recommendations past the publisher's expected-update date",
                  f"{len(past):,} open HHS OIG recommendations whose “next update expected” date, a field in the publisher's own file, has passed.",
                  f"""<p class="eyebrow">Open recommendations</p><h1>Past the publisher's expected-update date</h1>
<p class="lede">{len(past):,} open recommendations carry a “next update expected” date earlier than the day the file was read.</p>
{read_line('hhs-oig')}
<p class="note">This list is date arithmetic on one field of the publisher's file. It is not a finding that an agency is late, non-compliant or at fault. Publishers update these dates on their own schedule.</p>
<ul class="recs">{''.join(f'<li><span><a href="{site.href("/rec/" + r["id"] + "/")}">{E(clip(r["text"], 190))}</a><small>{E(sources.BY_ID[r["publisher"]]["short"])} {E(r["number"])} · {E(r["agency"])} · update expected {short_date(r["next_update"])}</small></span>{chip(r)}</li>' for r in past)}</ul>""",
                  crumbs=home + [("Open by agency", "/open/")], nav="open")

    # ------------------------------------------------------------------------------------ changes + feed
    all_events.sort(key=lambda e: e["at"], reverse=True)
    groups = defaultdict(list)
    for e in all_events[:3000]:
        groups[e["at"]].append(e)
    blocks, entries = [], []
    for at in sorted(groups, reverse=True)[:30]:
        evs = groups[at]
        counts = Counter(e["field"] for e in evs)
        summary = ", ".join(f"{n} {sources.FIELD_LABEL.get(k, {'added': 'new', 'in_export': 'listing'}.get(k, k)).lower()} change{'s' if n != 1 else ''}"
                            for k, n in counts.most_common())
        items = "".join(
            f'<li><span><a href="{site.href("/rec/" + e["id"] + "/")}">{E(sources.BY_ID[e["id"].split("/")[0]]["short"])} {E(by_id[e["id"]]["number"] if e["id"] in by_id else e["id"])}</a>'
            f'<small>{E(by_id[e["id"]]["agency"] if e["id"] in by_id else "")} · {E(describe_event(e, by_id.get(e["id"])))}</small></span></li>'
            for e in evs[:250])
        blocks.append(f'<h2 id="{at[:10]}">{when(at)}</h2><p>{len(evs):,} changes in the publishers\' files: {E(summary)}.</p><ul class="recs">{items}</ul>'
                      + (f"<p>And {len(evs) - 250:,} more in the data files.</p>" if len(evs) > 250 else ""))
        entries.append(f"<entry><title>{E(human_date(at))}: {len(evs):,} changes in publisher files</title><id>{E(site.url)}/changes/#{at[:10]}</id>"
                       f'<link href="{E(site.url)}/changes/#{at[:10]}"/><updated>{E(at)}</updated><summary>{E(summary)}</summary></entry>')
    first_read = min((r.get("first_seen", "") for r in recs if r.get("first_seen")), default="")
    site.page("/changes/", "What changed in the publishers' files",
              "Every status, date and wording change AuditLine has observed in inspectors general's recommendation files, newest first.",
              f"""<p class="eyebrow">Change history</p><h1>What changed</h1>
<p class="lede">Each time a publisher's file is read, it is compared with the previous one. Every difference becomes a dated event here and on the recommendation's own page.</p>
<p class="asof">AuditLine's history begins {E(human_date(first_read))}, the day the files were first read. Files last read {when(site.asof)}.</p>
{''.join(blocks) or '<p class="note">No changes have been observed yet. The first comparison happens the next time a publisher updates its file.</p>'}""",
              crumbs=home, nav="changes")
    site.write("feed.xml", f'<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"><title>AuditLine: changes in publisher files</title>'
               f'<id>{E(site.url)}/</id><link href="{E(site.url)}/changes/"/><link rel="self" href="{E(site.url)}/feed.xml"/>'
               f"<updated>{E(site.asof)}</updated><author><name>AuditLine</name></author>{''.join(entries[:20])}</feed>\n")

    # ------------------------------------------------------------------------------------ search
    agencies = sorted({r["agency"] or "Agency not stated" for r in live})
    statuses = sorted({r["status"] or "No status given" for r in live})
    a_idx, s_idx = {a: i for i, a in enumerate(agencies)}, {s: i for i, s in enumerate(statuses)}
    p_idx = {s["id"]: i for i, s in enumerate(sources.COVERED)}
    ordered = sorted(live, key=lambda r: (r["state"] != "open", r["issued"] or ""), reverse=False)
    ordered.sort(key=lambda r: r["issued"] or "", reverse=True)
    site.write("assets/search.json", json.dumps({
        "asof": site.asof, "publishers": [{"id": s["id"], "short": s["short"]} for s in sources.COVERED], "agencies": agencies, "statuses": statuses,
        "records": [[p_idx[r["publisher"]], r["slug"], r["number"], a_idx[r["agency"] or "Agency not stated"], s_idx[r["status"] or "No status given"],
                     r["issued"], clip(r["text"], 170)] for r in ordered]}, ensure_ascii=False, separators=(",", ":")))
    site.page("/search/", "Search inspector-general recommendations",
              f"Search {len(live):,} recommendations from {', '.join(s['short'] for s in sources.COVERED)} by words, agency and status.",
              f"""<p class="eyebrow">Search</p><h1>Search the recommendations</h1>
<div class="finder" id="search" hidden>
<label class="f q">Words or a recommendation number<input type="search" name="q" autocomplete="off" placeholder="For example: hospice, cybersecurity, A-07-14-02800"></label>
<label class="f">Publisher<select name="p"><option value="">All</option></select></label>
<label class="f">Responsible agency<select name="a"><option value="">All</option></select></label>
<label class="f">Publisher's status<select name="s"><option value="">Any</option><option value="open">Open</option><option value="closed">Closed</option></select></label>
</div>
<p class="count" id="count" role="status" aria-live="polite"></p>
<ul class="recs" id="results"></ul>
<p><button class="btn" type="button" id="more" hidden>Show more</button></p>
<noscript><p class="note">Search needs JavaScript. Every recommendation is also listed on its <a href="{site.href('/open/')}">agency's page</a>.</p></noscript>
<p class="asof">Files last read {when(site.asof)}. Newest recommendations first.</p>""", crumbs=home, nav="search")

    # ------------------------------------------------------------------------------------ home
    top = sorted(agency_tiles, key=lambda t: -t[2])[:9]
    newest = sorted(live, key=lambda r: r["issued"] or "", reverse=True)[:8]
    oldest_open = sorted(open_recs, key=lambda r: r["issued"] or "9999")[:6]
    recent_events = all_events[:8]
    pub_stats = "".join(
        f'<div class="stat"><b>{sum(1 for r in by_pub[s["id"]] if r.get("in_export", True) and r["state"] == "open"):,}</b><span>open at {E(s["short"])}</span>'
        f'<small>of {sum(1 for r in by_pub[s["id"]] if r.get("in_export", True)):,}; file read {E(short_date(pubs.get(s["id"], {}).get("retrieved_at", "")))}</small></div>'
        for s in sources.COVERED)
    body = f"""<p class="eyebrow">America V2 public tools · alpha</p>
<h1>Every official warning. <em>What happened next?</em></h1>
<p class="lede">AuditLine mirrors the recommendations federal inspectors general make to agencies: the exact recommendation, the responsible
office, the publisher's own status, and a dated history of every change. One page each. No verdicts.</p>
<div class="stats">
<div class="stat"><b>{len(live):,}</b><span>recommendations mirrored</span><small>{len(sources.COVERED)} publishers</small></div>
<div class="stat"><b>{len(open_recs):,}</b><span>open, by publisher status</span><small>{len(agency_tiles)} responsible offices</small></div>
{pub_stats}
</div>
<p class="asof">Every number on this page is a count of rows in the publishers' official files, read {when(site.asof)}.</p>
<form class="finder" role="search" action="{site.href('/search/')}" method="get">
<label class="f q">Search recommendations<input type="search" name="q" placeholder="Words, an agency or a recommendation number" autocomplete="off"></label>
<label class="f">Publisher's status<select name="s"><option value="">Any</option><option value="open">Open</option><option value="closed">Closed</option></select></label>
<span></span><button class="btn primary" type="submit" style="align-self:end">Search</button>
</form>
<h2>Agencies with the most open recommendations</h2>
{tiles(site, [(sources.BY_ID[pp]["short"], a, f"{o:,} open · {c:,} closed", p) for pp, a, o, c, old, p in top])}
<p><a class="btn" href="{site.href('/open/')}">All {len(agency_tiles)} offices</a></p>
<h2>Longest open</h2>
<ul class="recs">{''.join(rec_row(site, r) for r in oldest_open)}</ul>
<h2>Newest recommendations</h2>
<ul class="recs">{''.join(rec_row(site, r) for r in newest)}</ul>
{('<h2>Latest observed changes</h2><ul class="recs">' + ''.join(f'<li><span><a href="{site.href("/rec/" + e["id"] + "/")}">{E(by_id[e["id"]]["number"] if e["id"] in by_id else e["id"])}</a><small>{E(human_date(e["at"]))} · {E(describe_event(e, by_id.get(e["id"])))}</small></span></li>' for e in recent_events) + f'</ul><p><a class="btn" href="{site.href("/changes/")}">All changes</a></p>') if recent_events else ''}
<h2>The evidence rules</h2>
{tiles(site, [("Rule 1", "Primary sources open in one click", "Every page links the publisher's own tracker and names the exact file it was read from.", "/method/#sources"),
              ("Rule 2", "Publisher status is labelled", "“Open” and “closed” are the inspector general's words, shown with the date they were read.", "/method/#status"),
              ("Rule 3", "No inferred fraud or waste", "Dollar figures are the publisher's labels. Nothing is scored, ranked for blame or judged.", "/method/#no-verdicts"),
              ("Rule 4", "Every change becomes an event", "When a publisher's file changes, the difference is recorded with its date and kept.", "/method/#history")])}
<p class="note"><b>Coverage is partial.</b> AuditLine mirrors publishers that offer an official export and accept automated readers.
GAO, Oversight.gov and some inspectors general do not, so they are not here. <a href="{site.href('/coverage/')}">See what is covered</a>.</p>"""
    site.page("/", "AuditLine: federal oversight recommendations and what the publisher says happened next", cfg["tagline"], body,
              og=("home", "Every official warning. What happened next?", f"{len(live):,} inspector-general recommendations, mirrored with their official status"),
              jsonld=[{"@context": "https://schema.org", "@type": "WebSite", "name": site.name, "url": site.url + "/", "description": cfg["tagline"],
                       "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint", "urlTemplate": site.url + "/search/?q={search_term_string}"},
                                           "query-input": "required name=search_term_string"}}])

    # ------------------------------------------------------------------------------------ coverage, method, about, data
    unc = status.get("uncovered", {})

    def links_cell(links):
        if not links:
            return "not yet checked"
        return (f'tracker: {E(links.get("tracker", ""))}; report link: {E(links.get("report_link", ""))} '
                f'<span class="asof">({E(short_date(links.get("checked_at", "")))})</span>')
    cov_rows = "".join(
        f'<tr><td><a href="{site.href("/publisher/" + s["id"] + "/")}">{E(s["name"])}</a></td><td>{pubs.get(s["id"], {}).get("rows", 0):,}</td>'
        f'<td>{when(pubs.get(s["id"], {}).get("retrieved_at", ""))}</td><td>{E(pubs.get(s["id"], {}).get("outcome", "not yet read"))}: {E(pubs.get(s["id"], {}).get("note", ""))}</td>'
        f'<td>{links_cell(pubs.get(s["id"], {}).get("links"))}</td></tr>'
        for s in sources.COVERED)
    unc_rows = "".join(
        f'<tr><td>{E(s["name"])}</td><td>{E(s["why"])}</td><td>{E(unc.get("answers", {}).get(s["short"], "not yet checked"))}</td>'
        f'<td><a href="{E(s["tracker"])}" rel="noopener">{E(s["tracker_name"])}</a></td></tr>' for s in sources.NOT_COVERED)
    site.page("/coverage/", "What AuditLine covers, and what it does not",
              "Which oversight publishers AuditLine mirrors, when each file was last read, and which publishers refuse automated readers and are therefore missing.",
              f"""<article><p class="eyebrow">Coverage</p><h1>What is covered, and what is not</h1>
<p class="lede">AuditLine mirrors a publisher only when it offers an official export of its recommendations and answers an honest automated request. It does not disguise its reader or work around a refusal.</p>
<h2>Mirrored</h2>
<div class="tablewrap"><table><thead><tr><th>Publisher</th><th>Recommendations</th><th>File last read</th><th>Latest attempt</th><th>Source links</th></tr></thead><tbody>{cov_rows}</tbody></table></div>
<p class="asof">“Source links” is a weekly check that the publisher's tracker and a per-report link built the way these pages build them still open.</p>
<h2>Not mirrored</h2>
<p>These publishers hold a large share of federal oversight recommendations. They are missing here because their websites refuse automated readers. Use their own trackers.</p>
<div class="tablewrap"><table><thead><tr><th>Publisher</th><th>Why it is missing</th><th>How it answered on {E(human_date(unc.get("checked_at", "")) or "the last check")}</th><th>Its own tracker</th></tr></thead><tbody>{unc_rows}</tbody></table></div>
<p class="note">A weekly job asks each of these sites for its robots.txt, once, and records the answer above. If one starts accepting automated readers, it can be added.</p>
<h2>What a missing publisher means for an agency page</h2>
<p>An agency page lists only the recommendations from the publishers mirrored here. An agency with nothing open on AuditLine may still have open recommendations from GAO or from an inspector general that is not covered.</p></article>""",
              crumbs=home, nav="coverage")
    site.page("/method/", "Evidence rules: how AuditLine works",
              "The four rules AuditLine follows, where every field comes from, how history is recorded, and what the site refuses to say.",
              f"""<article class="prose"><p class="eyebrow">Evidence rules</p><h1>How AuditLine works</h1>
<p class="lede">Source before summary. Event before status. Missing evidence stays visible.</p>
<h2 id="sources">1. Primary sources open in one click</h2>
<p>Every record comes from a publisher's official export file. Each page links the publisher's own tracker and shows the address of the file,
the date it was read, its size and its SHA-256, so anyone can fetch the same file and compare.</p>
<h2 id="status">2. Publisher status is labelled</h2>
<p>A status such as “Open Unimplemented” or “Closed Implemented” is the inspector general's wording, copied exactly. AuditLine sorts records into
open and closed only by whether that wording begins with “Open” or “Closed”. It does not check whether anything was actually done.</p>
<h2 id="no-verdicts">3. No inferred fraud or waste</h2>
<p>Dollar figures (“potential savings”, “questioned costs”, “funds put to better use”) are the publisher's labels for its own estimates. They are not
money lost, stolen or saved. AuditLine does not rank agencies for blame, does not score them, and does not say any person or office failed.
Lists such as “longest open” are date arithmetic on the publisher's issue date.</p>
<h2 id="history">4. Every change becomes an event</h2>
<p>Each week the publishers' files are read again and compared with the previous copy. A change of status, date, response, responsible office,
wording or dollar figure is recorded as an event with the date it was observed. Events are never edited or removed. A recommendation that
disappears from a publisher's file stays here, marked as no longer in the file.</p>
<p>AuditLine's own observations start on the day a publisher was first read. Earlier dates on a page (“issued”, “closed”) are the publisher's.</p>
<h2 id="freshness">When a publisher cannot be read</h2>
<p>If a publisher's site is down, refuses the request, or sends a file that fails basic checks (missing numbers, statuses or dates, or far fewer
rows than last time), the previous records are kept unchanged and every page keeps showing the date of the last good file.</p>
<h2 id="limits">Limits</h2>
<ul><li>Coverage is partial. See <a href="{site.href('/coverage/')}">what is and is not covered</a>.</li>
<li>Publishers correct and re-date their own records. AuditLine shows what the file said on the day it was read.</li>
<li>Recommendations a publisher marks sensitive appear without their text, as the publisher lists them.</li>
<li>No AI reads, summarises or classifies anything here.</li></ul>
<h2 id="corrections">Corrections</h2>
<p>If a page misstates what a publisher's file says, <a href="{E(site.repo_url)}/issues/new/choose" rel="noopener">open an issue</a> with the recommendation number.
If the publisher's own record is wrong, the publisher has to correct it; AuditLine will show the change the next time the file is read.</p></article>""",
              crumbs=home, nav="method")
    site.page("/about/", "About AuditLine", "What AuditLine is for, who is behind it, how it treats privacy, and how to send a correction.",
              f"""<article class="prose"><p class="eyebrow">About</p><h1>A public ledger of official warnings</h1>
<p class="lede">Inspectors general tell agencies what to fix. Whether anything happened next is recorded in tracker files few people read. AuditLine gives each recommendation a permanent page.</p>
<p>It is for reporters, watchdogs, oversight staff and researchers who need to cite a specific recommendation, see how long it has been open, and be told when its status changes.</p>
<p>AuditLine is one of the America V2 public tools. This is its static edition: no accounts, no reviewer queue, no AI. It mirrors publishers and records changes, and nothing more.</p>
<h2>Nonpartisan by construction</h2>
<p>Every recommendation in a publisher's file is listed, with the same fields and the same rules, whichever administration it was issued under.</p>
<h2>Privacy</h2>
<p>No accounts, no cookies, no sign-up. Searches run in your browser. {'Page views are counted with GoatCounter, which stores no personal data.' if os.environ.get('GOATCOUNTER_URL') else 'The site runs no analytics.'}
Publisher files name organizations and, occasionally, companies or public officials. AuditLine adds no personal data of its own.</p>
<h2>Not an official site</h2>
<p>AuditLine is not affiliated with any inspector general, GAO or any agency. The official record is always the publisher's.</p>
<h2>Corrections and contact</h2>
<p><a href="{E(site.repo_url)}/issues" rel="noopener">Open an issue on GitHub</a>. The code that builds this site is public in the same place.</p></article>""",
              crumbs=home)

    fields = ["id", "publisher", "number", "status", "state", "agency", "issued", "closed", "response", "last_update", "next_update",
              "report_number", "report_title", "report_type", "amounts", "flags", "topics", "text", "in_export", "first_seen", "page", "source"]

    def public(r):
        s = sources.BY_ID[r["publisher"]]
        return {"id": r["id"], "publisher": s["short"], "number": r["number"], "status": r["status"], "state": r["state"], "agency": r["agency"],
                "issued": r["issued"], "closed": r.get("closed", ""), "response": r.get("response", ""), "last_update": r.get("last_update", ""),
                "next_update": r.get("next_update", ""), "report_number": r["report_number"], "report_title": r["report_title"],
                "report_type": r.get("report_type", ""), "amounts": r.get("amounts", {}), "flags": r.get("flags", []), "topics": r.get("topics", []),
                "text": r["text"], "in_export": r.get("in_export", True), "first_seen": r.get("first_seen", ""),
                "page": site.url + f"/rec/{r['id']}/", "source": s["tracker"]}

    def write_set(name, items, pid=None):
        rows_ = [public(r) for r in items]
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(fields)
        for row in rows_:
            w.writerow([json.dumps(row[k], ensure_ascii=False) if isinstance(row[k], (dict, list)) else row[k] for k in fields])
        site.write(f"data/{name}.csv", buf.getvalue())
        meta = {"as_of": pubs.get(pid, {}).get("retrieved_at", site.asof) if pid else site.asof, "license": "CC0-1.0", "source": site.url + "/",
                "count": len(rows_), "recommendations": rows_}
        if pid:
            meta["publisher_file"] = {k: pubs.get(pid, {}).get(k, "") for k in ("retrieved_at", "rows", "bytes", "sha256")}
            meta["publisher_file"]["url"] = sources.BY_ID[pid]["url"]
            meta["events"] = refresh.load_events(pid)
        site.write(f"data/{name}.json", json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + "\n")

    write_set("recommendations", recs)
    for s in sources.COVERED:
        write_set(s["id"], by_pub[s["id"]], s["id"])
    site.page("/data/", "Open data: recommendations as CSV and JSON",
              "Download every mirrored recommendation, with its publisher status and AuditLine's recorded history, as CSV or JSON under CC0.",
              f"""<article class="prose"><p class="eyebrow">Open data</p><h1>Download the records</h1>
<p class="lede">Everything on this site, as files. The publishers' records are federal public records; this compilation is released under CC0.</p>
<p><a class="btn primary" href="{site.href('/data/recommendations.csv')}">recommendations.csv</a> <a class="btn" href="{site.href('/data/recommendations.json')}">recommendations.json</a></p>
<p>Per publisher (the JSON includes the recorded change events and the publisher file's date, size and SHA-256):</p>
<p>{' '.join(f'<a class="btn" href="{site.href("/data/" + s["id"] + ".csv")}">{E(s["short"])} CSV</a> <a class="btn" href="{site.href("/data/" + s["id"] + ".json")}">{E(s["short"])} JSON</a>' for s in sources.COVERED)}</p>
<p class="asof">{len(recs):,} recommendations. Publisher files last read {when(site.asof)}. Rebuilt after every weekly read.</p>
<h2>Columns</h2>
<div class="tablewrap"><table><thead><tr><th>Column</th><th>Meaning</th></tr></thead><tbody>
<tr><td><code>publisher</code>, <code>number</code>, <code>id</code></td><td>Who made the recommendation, its number in the publisher's file, and AuditLine's stable identifier.</td></tr>
<tr><td><code>status</code>, <code>state</code></td><td>The publisher's status, exactly as written, and whether that wording starts with “Open” or “Closed”.</td></tr>
<tr><td><code>agency</code>, <code>response</code></td><td>The office the publisher names as responsible, and the response the publisher recorded.</td></tr>
<tr><td><code>issued</code>, <code>closed</code>, <code>last_update</code>, <code>next_update</code></td><td>Dates from the publisher's file.</td></tr>
<tr><td><code>report_number</code>, <code>report_title</code>, <code>report_type</code></td><td>The report the recommendation comes from.</td></tr>
<tr><td><code>amounts</code>, <code>flags</code>, <code>topics</code></td><td>The publisher's dollar labels, flags and topic labels. Dollar figures are estimates, not realised savings.</td></tr>
<tr><td><code>text</code></td><td>The recommendation in the publisher's words.</td></tr>
<tr><td><code>in_export</code>, <code>first_seen</code></td><td>Whether the record is in the publisher's latest file, and the day AuditLine first recorded it.</td></tr>
<tr><td><code>page</code>, <code>source</code></td><td>The record's page here, and the publisher's tracker.</td></tr></tbody></table></div>
<h2>Feed</h2><p><a href="{site.href('/feed.xml')}">Changes in publisher files</a> (Atom).</p>
<p>When you reuse a record, cite the publisher and the date its file was read, and link the record's page so readers can see later changes.</p></article>""",
              crumbs=home, nav="data", jsonld=[{
                  "@context": "https://schema.org", "@type": "Dataset", "name": "AuditLine: federal inspector-general recommendations and their status",
                  "description": "Recommendations from federal inspectors general with the publisher's status, dates and a recorded history of changes.",
                  "url": site.url + "/data/", "license": "https://creativecommons.org/publicdomain/zero/1.0/", "dateModified": site.asof,
                  "creator": {"@type": "Organization", "name": "AuditLine", "url": site.url + "/"},
                  "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": site.url + "/data/recommendations.csv"},
                                   {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": site.url + "/data/recommendations.json"}]}])
    site.page("/404.html", "Page not found", "That page does not exist.",
              f'<h1>Page not found</h1><p class="lede">That address is not in the ledger.</p><p><a class="btn primary" href="{site.href("/search/")}">Search the recommendations</a></p>',
              listed=False)

    with open(os.path.join(ROOT, "config", "indexnow-key.txt"), encoding="utf-8") as f:
        key = f.read().strip()
    site.write(f"{key}.txt", key + "\n")
    if site.indexable:
        site.write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
            f"<url><loc>{E(u)}</loc><lastmod>{E(d)}</lastmod></url>\n" for u, d in site.urls) + "</urlset>\n")
        site.write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {site.url}/sitemap.xml\n")
    else:
        site.write("robots.txt", "User-agent: *\nDisallow: /\n")
    site.write("urls.txt", "\n".join(u for u, _ in site.urls) + ("\n" if site.urls else ""))
    site.write("og-jobs.json", json.dumps(site.og_jobs))
    site.write("build.json", json.dumps({
        "built_at": iso(site.now), "recommendations": len(recs), "open": len(open_recs), "indexable": site.indexable, "base_url": site.url,
        "publishers": {s["id"]: {"retrieved_at": pubs.get(s["id"], {}).get("retrieved_at", ""), "rows": pubs.get(s["id"], {}).get("rows", 0),
                                 "outcome": pubs.get(s["id"], {}).get("outcome", "")} for s in sources.COVERED}}, indent=1) + "\n")
    site.write(".nojekyll", "")
    return {"recommendations": len(recs), "open": len(open_recs), "agencies": len(agency_tiles), "events": len(all_events),
            "indexable": site.indexable, "og": len(site.og_jobs)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.join(ROOT, "_site"))
    a = ap.parse_args(argv)
    print(json.dumps(build(a.site)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
