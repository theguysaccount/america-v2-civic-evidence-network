"""The built site: every record has a page that repeats the publisher's status with its read date,
nothing is judged, and the staged copy cannot be indexed. Built from made-up exports, so these
checks hold whatever the real publishers' files say on a given day."""
import csv
import io
import json
import os
import re
import unittest

from auditline import build, guard, net, refresh, sources
from tests import fixtures

OWN_WORDS = re.compile(r"\b(fraud|wasted?|failed|failure|overdue|delinquent|negligen\w+|scandal\w*|corrupt\w*|blame\w*|guilty)\b", re.I)


def page(site, rel):
    with open(os.path.join(site, rel), encoding="utf-8") as f:
        return f.read()


def main_of(html):
    return html.split("<main", 1)[1].split("</main>", 1)[0]


class Built(fixtures.TempData, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.feed(1, hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv())

    def feed(self, day, **files):
        with fixtures.quiet():
            refresh.run(now=fixtures.when(day), fetch=fixtures.Feed(**files), probe=False, pause=0)

    def build(self, day=2, **env):
        os.environ.update(env)
        try:
            return build.build(self.site, now=fixtures.when(day))
        finally:
            for k in env:
                os.environ.pop(k, None)

    def records(self):
        return [r for s in sources.COVERED for r in refresh.load_records(s["id"])]

    def test_every_recommendation_has_a_page_with_the_publishers_exact_status_and_read_date(self):
        self.build()
        for r in self.records():
            html = page(self.site, f"rec/{r['id']}/index.html")
            self.assertIn(f'<span class="status {r["state"]}">{r["status"]}</span>', html)
            self.assertIn('<time datetime="2031-03-01T06:00:00Z">March 1, 2031</time>', html, "the date the publisher's file was read")
            self.assertIn(sources.BY_ID[r["publisher"]]["tracker"], html)
            self.assertIn("It does not check whether a recommendation was carried out", html)
            self.assertIn(r["number"], html)

    def test_publisher_text_is_shown_whole_and_escaped(self):
        self.build()
        r = self.records()[0]
        html = page(self.site, f"rec/{r['id']}/index.html")
        self.assertNotIn("<of the plan>", html)
        self.assertIn("&lt;of the plan&gt;", html)
        home = page(self.site, "index.html")
        self.assertNotIn("<of the plan>", home)
        idx = json.loads(page(self.site, "assets/search.json"))
        self.assertTrue(any("<of the plan>" in row[6] for row in idx["records"]), "the index holds raw text; the page script escapes it")
        self.assertIn("function esc", page(self.site, "static/app.js"))

    def test_counts_match_the_records_and_carry_a_source_and_a_date(self):
        self.build()
        recs = self.records()
        open_n = sum(1 for r in recs if r["state"] == "open")
        home = page(self.site, "index.html")
        self.assertIn(f"<b>{len(recs):,}</b><span>recommendations mirrored</span>", home)
        self.assertIn(f"<b>{open_n:,}</b><span>open, by publisher status</span>", home)
        self.assertRegex(home, r'count of rows in the publishers\' official files, read <time datetime="2031-03-01T06:00:00Z">')
        for rel in ("open/index.html", "publisher/hhs-oig/index.html", "agency/hhs-oig/example-health-agency/index.html"):
            self.assertRegex(page(self.site, rel), r'class="asof">Source: <a href="https://[^"]+"[^>]*>[^<]+</a>, official export read\s+<time datetime=')
        agency = page(self.site, "agency/hhs-oig/example-health-agency/index.html")
        mine = [r for r in recs if r["agency"] == "Example Health Agency"]
        self.assertIn(f"<b>{sum(1 for r in mine if r['state'] == 'open'):,}</b><span>open</span>", agency)
        self.assertIn(f"<b>{sum(1 for r in mine if r['state'] == 'closed'):,}</b><span>closed</span>", agency)
        for r in mine:
            self.assertIn(f'/rec/{r["id"]}/"', agency)

    def test_dollar_figures_are_labelled_as_the_publishers(self):
        self.build()
        r = next(r for r in self.records() if r["amounts"])
        html = page(self.site, f"rec/{r['id']}/index.html")
        self.assertIn("<dt>Potential savings</dt>", html)
        self.assertIn("$1,250,000", html, "the publisher's figure is shown exactly, not rounded")
        self.assertIn("the publisher's figure; not realised savings", html)

    def test_the_sites_own_words_pass_no_verdict(self):
        self.build()
        recs = self.records()
        pages = [f"rec/{r['id']}/index.html" for r in recs] + ["open/index.html", "open/past-expected-update/index.html",
                                                              "publisher/hhs-oig/index.html", "publisher/dot-oig/index.html",
                                                              "agency/hhs-oig/example-health-agency/index.html", "search/index.html", "changes/index.html"]
        for rel in pages:
            found = OWN_WORDS.findall(main_of(page(self.site, rel)))
            self.assertEqual(found, [], rel)

    def test_past_expected_update_list_is_date_arithmetic_and_says_so(self):
        self.build()
        html = page(self.site, "open/past-expected-update/index.html")
        self.assertIn("not a finding that an agency is late", html)
        r = next(r for r in self.records() if r["next_update"])
        self.assertIn(f'/rec/{r["id"]}/"', html)
        self.assertIn("not a finding that anyone missed a deadline", page(self.site, f"rec/{r['id']}/index.html"))

    def test_a_status_change_shows_on_the_record_the_changes_page_and_the_feed(self):
        self.feed(8, hhs_oig=fixtures.hhs_csv(status_of={1: "Closed Implemented"}), dot_oig=fixtures.dot_csv())
        self.build(9)
        rid = sources.parse_hhs(fixtures.hhs_csv())[0]["id"]
        html = page(self.site, f"rec/{rid}/index.html")
        self.assertIn("Status changed from “Open Unimplemented” to “Closed Implemented”.", html)
        self.assertIn("observed by AuditLine in the publisher", html)
        self.assertIn('<span class="status closed">Closed Implemented</span>', html)
        changes = page(self.site, "changes/index.html")
        self.assertIn(f'/rec/{rid}/"', changes)
        self.assertIn('id="2031-03-08"', changes)
        feed = page(self.site, "feed.xml")
        self.assertIn("<entry>", feed)
        self.assertIn("2031-03-08T06:00:00Z", feed)

    def test_a_publisher_that_stops_answering_keeps_its_pages_and_its_old_read_date(self):
        self.feed(8, hhs_oig=fixtures.hhs_csv(), dot_oig=net.Refused("HTTP 403"))
        self.build(9)
        html = page(self.site, "publisher/dot-oig/index.html")
        self.assertIn("did not succeed", html)
        self.assertIn("refused", html)
        self.assertIn('<time datetime="2031-03-01T06:00:00Z">', html, "DOT's pages still show the day its file was last read")
        self.assertIn('<time datetime="2031-03-08T06:00:00Z">', page(self.site, "publisher/hhs-oig/index.html"))
        self.assertTrue(os.path.exists(os.path.join(self.site, "rec", "dot-oig", "ex2021002-1", "index.html")))
        cov = page(self.site, "coverage/index.html")
        self.assertIn("refused", cov)

    def test_a_record_dropped_by_the_publisher_keeps_its_page_and_says_so(self):
        self.feed(8, hhs_oig=fixtures.hhs_csv(drop={4}), dot_oig=fixtures.dot_csv())
        self.build(9)
        gone = next(r for r in self.records() if not r["in_export"])
        html = page(self.site, f"rec/{gone['id']}/index.html")
        self.assertIn("No longer in the publisher's file.", html)
        idx = json.loads(page(self.site, "assets/search.json"))
        self.assertNotIn(gone["slug"], [row[1] for row in idx["records"]])
        rows = list(csv.DictReader(io.StringIO(page(self.site, "data/recommendations.csv"))))
        self.assertEqual({row["in_export"] for row in rows}, {"True", "False"})

    def test_each_office_has_a_feed_and_an_embeddable_count(self):
        self.feed(8, hhs_oig=fixtures.hhs_csv(status_of={1: "Closed Implemented"}), dot_oig=fixtures.dot_csv())
        self.build(9)
        base = "agency/hhs-oig/example-health-agency/"
        feed = page(self.site, base + "feed.xml")
        self.assertIn("Status changed from “Open Unimplemented” to “Closed Implemented”.", feed)
        other = page(self.site, "agency/hhs-oig/example-services-programs-office/feed.xml")
        self.assertNotIn("<entry>", other, "an office's feed carries only its own recommendations")
        html = page(self.site, base + "index.html")
        self.assertIn("/embed/hhs-oig/example-health-agency/", html)
        self.assertIn(base + "feed.xml", html)
        embed = page(self.site, "embed/hhs-oig/example-health-agency/index.html")
        recs = [r for r in self.records() if r["agency"] == "Example Health Agency" and r["state"] == "open"]
        self.assertIn(f"<b>{len(recs):,}</b>", embed)
        self.assertIn("File read March 8, 2031", embed)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', embed)
        self.assertIn("/agency/hhs-oig/example-health-agency/", embed)

    def test_embeds_stay_out_of_search_engines_after_cutover(self):
        self.build(SITE_URL="https://auditline.example.org", SITE_INDEXABLE="true")
        embed = page(self.site, "embed/hhs-oig/example-health-agency/index.html")
        self.assertIn('<meta name="robots" content="noindex, nofollow">', embed)
        self.assertIn('<link rel="canonical" href="https://auditline.example.org/agency/hhs-oig/example-health-agency/">', embed)
        self.assertNotIn("/embed/", page(self.site, "sitemap.xml"))

    def test_report_links_fall_back_to_the_tracker_when_the_link_check_says_they_broke(self):
        r = self.records()[0]
        self.build()
        self.assertIn(r["report_url"].replace("&", "&amp;"), page(self.site, f"rec/{r['id']}/index.html"))
        status = refresh.read_json(refresh.status_path())
        status["publishers"]["hhs-oig"]["links"] = {"tracker": "ok", "report_link": "opened, but the report was not on the page", "checked_at": "2031-03-01T06:00:00Z"}
        refresh.write_json(refresh.status_path(), status)
        self.build()
        html = page(self.site, f"rec/{r['id']}/index.html")
        self.assertNotIn("?search=", html)
        self.assertIn(sources.BY_ID["hhs-oig"]["tracker"], html)
        self.assertIn("opened, but the report was not on the page", page(self.site, "coverage/index.html"))

    def test_staged_copy_cannot_be_indexed(self):
        out = self.build()
        self.assertFalse(out["indexable"])
        self.assertFalse(os.path.exists(os.path.join(self.site, "sitemap.xml")))
        self.assertEqual(page(self.site, "robots.txt"), "User-agent: *\nDisallow: /\n")
        self.assertEqual(page(self.site, "urls.txt"), "")
        for dirpath, _, files in os.walk(self.site):
            for fn in files:
                if fn.endswith(".html"):
                    self.assertIn('<meta name="robots" content="noindex, nofollow">', page(dirpath, fn), fn)

    def test_cutover_is_two_settings(self):
        out = self.build(SITE_URL="https://auditline.example.org", SITE_INDEXABLE="true")
        self.assertTrue(out["indexable"])
        home = page(self.site, "index.html")
        self.assertNotIn("noindex", home)
        self.assertIn('<link rel="canonical" href="https://auditline.example.org/">', home)
        self.assertIn('href="/static/style.css"', home)
        self.assertNotIn("github.io", home)
        sitemap = page(self.site, "sitemap.xml")
        recs = self.records()
        for r in recs:
            self.assertIn(f"<loc>https://auditline.example.org/rec/{r['id']}/</loc>", sitemap)
        self.assertNotIn("404", sitemap)
        self.assertIn("Sitemap: https://auditline.example.org/sitemap.xml", page(self.site, "robots.txt"))
        self.assertEqual(len(page(self.site, "urls.txt").split()), sitemap.count("<loc>"))
        self.assertIn('"@type": "Dataset"', page(self.site, "data/index.html").replace('"@type":"Dataset"', '"@type": "Dataset"'))

    def test_data_files_list_every_record_with_its_page_and_source(self):
        self.build()
        recs = self.records()
        rows = list(csv.DictReader(io.StringIO(page(self.site, "data/recommendations.csv"))))
        self.assertEqual(len(rows), len(recs))
        self.assertTrue(all(row["page"].endswith(f"/rec/{row['id']}/") and row["source"].startswith("https://") for row in rows))
        doc = json.loads(page(self.site, "data/hhs-oig.json"))
        self.assertEqual(doc["count"], sum(1 for r in recs if r["publisher"] == "hhs-oig"))
        self.assertEqual(doc["as_of"], "2031-03-01T06:00:00Z")
        self.assertEqual(doc["publisher_file"]["url"], sources.BY_ID["hhs-oig"]["url"])
        self.assertEqual(len(doc["publisher_file"]["sha256"]), 64)
        self.assertEqual(doc["license"], "CC0-1.0")

    def test_guard_accepts_the_build_and_catches_damage(self):
        self.build()
        old = guard.load_config
        cfg = dict(old(), min_recommendations_to_publish=1)
        guard.load_config = lambda: cfg
        try:
            os.makedirs(os.path.join(self.site, "og"), exist_ok=True)
            with open(os.path.join(self.site, "og", "default.png"), "wb") as f:
                f.write(b"png")
            errors, counts = guard.check(self.site)
            self.assertEqual(errors, [])
            self.assertEqual(counts["recommendations"], len(self.records()))
            r = self.records()[0]
            path = os.path.join(self.site, "rec", r["id"], "index.html")
            html = page(self.site, f"rec/{r['id']}/index.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html.replace(f'">{r["status"]}</span>', '">Closed Implemented</span>'))
            errors, _ = guard.check(self.site)
            self.assertTrue(any("publisher's status" in e for e in errors), errors[:3])
            with open(path, "w", encoding="utf-8") as f:
                f.write(html.replace('<meta name="robots" content="noindex, nofollow">', ""))
            errors, _ = guard.check(self.site)
            self.assertTrue(any("noindex" in e for e in errors))
            os.remove(path)
            errors, _ = guard.check(self.site)
            self.assertTrue(any("page missing" in e for e in errors))
            self.assertTrue(any("broken link" in e for e in errors))
        finally:
            guard.load_config = old

    def test_no_contact_address_or_tracker_is_published(self):
        self.build()
        for rel in ("index.html", "about/index.html", "method/index.html", "coverage/index.html", "data/index.html"):
            html = page(self.site, rel)
            self.assertNotRegex(html, r"[\w.+-]+@[\w-]+\.[a-z]{2,}", rel)
            self.assertNotIn("googletagmanager", html)
            self.assertNotIn("gc.zgo.at", html)
        self.assertIn("github.com/", page(self.site, "about/index.html"))


if __name__ == "__main__":
    unittest.main()
