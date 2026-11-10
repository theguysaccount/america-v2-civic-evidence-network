"""The refresh: history is append-only, and a publisher that fails keeps its last good records."""
import json
import unittest
from datetime import timedelta

from auditline import net, refresh, sources
from tests import fixtures


def parsed(**kw):
    return sources.parse_hhs(fixtures.hhs_csv(**kw))


class Merge(unittest.TestCase):
    def test_first_file_records_no_events(self):
        recs, events = refresh.merge([], parsed(), fixtures.when(1))
        self.assertEqual(events, [])
        self.assertTrue(all(r["in_export"] and r["first_seen"] == "2031-03-01" for r in recs))

    def test_identical_file_changes_nothing(self):
        first, _ = refresh.merge([], parsed(), fixtures.when(1))
        again, events = refresh.merge(first, parsed(), fixtures.when(8))
        self.assertEqual(events, [])
        self.assertEqual(again, first, "first_seen survives and nothing else moves")

    def test_a_status_change_becomes_a_dated_event(self):
        first, _ = refresh.merge([], parsed(), fixtures.when(1))
        new = parsed(status_of={1: "Closed Implemented"})
        recs, events = refresh.merge(first, new, fixtures.when(8))
        mine = [e for e in events if e["id"] == new[0]["id"]]
        fields = {e["field"]: e for e in mine}
        self.assertEqual(fields["status"]["old"], "Open Unimplemented")
        self.assertEqual(fields["status"]["new"], "Closed Implemented")
        self.assertEqual(fields["status"]["at"], "2031-03-08T06:00:00Z")
        self.assertIn("closed", fields, "the closed date the publisher added is its own event")
        self.assertEqual({e["id"] for e in events}, {new[0]["id"]}, "untouched records produce no events")
        rec = next(r for r in recs if r["id"] == new[0]["id"])
        self.assertEqual(rec["first_seen"], "2031-03-01")

    def test_a_record_that_leaves_the_file_is_kept_and_marked(self):
        first, _ = refresh.merge([], parsed(), fixtures.when(1))
        recs, events = refresh.merge(first, parsed(drop={4}), fixtures.when(8))
        self.assertEqual(len(recs), 8)
        gone = [r for r in recs if not r["in_export"]]
        self.assertEqual(len(gone), 1)
        self.assertEqual(gone[0]["gone_since"], "2031-03-08")
        self.assertEqual([(e["field"], e["new"]) for e in events], [("in_export", False)])
        # still absent a week later: no second event
        recs2, events2 = refresh.merge(recs, parsed(drop={4}), fixtures.when(15))
        self.assertEqual(events2, [])
        self.assertEqual(len(recs2), 8)
        # and when it comes back, that is an event too
        recs3, events3 = refresh.merge(recs2, parsed(), fixtures.when(22))
        self.assertEqual([(e["field"], e["new"]) for e in events3], [("in_export", True)])
        self.assertTrue(all(r["in_export"] for r in recs3))

    def test_a_new_record_is_an_added_event_after_the_first_file(self):
        first, _ = refresh.merge([], parsed(n=6), fixtures.when(1))
        recs, events = refresh.merge(first, parsed(n=8), fixtures.when(8))
        self.assertEqual(sorted(e["field"] for e in events), ["added", "added"])
        self.assertEqual({r["first_seen"] for r in recs}, {"2031-03-01", "2031-03-08"})


class Run(fixtures.TempData, unittest.TestCase):
    def run_with(self, day, **files):
        feed = fixtures.Feed(**files)
        with fixtures.quiet():
            status = refresh.run(now=fixtures.when(day), fetch=feed, probe=False, pause=0)
        return status["publishers"], feed

    def test_a_good_read_is_recorded_with_its_date_and_digest(self):
        raw = fixtures.hhs_csv()
        pubs, _ = self.run_with(1, hhs_oig=raw, dot_oig=fixtures.dot_csv())
        st = pubs["hhs-oig"]
        self.assertEqual(st["outcome"], "ok")
        self.assertEqual(st["retrieved_at"], "2031-03-01T06:00:00Z")
        self.assertEqual(st["rows"], 8)
        self.assertEqual(st["sha256"], sources.digest(raw))
        self.assertEqual(len(refresh.load_records("hhs-oig")), 8)
        self.assertEqual(len(refresh.load_records("dot-oig")), 6)
        self.assertEqual(refresh.load_events("hhs-oig"), [])

    def test_one_publisher_failing_leaves_the_other_and_its_own_last_good_file(self):
        self.run_with(1, hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv())
        before = fixtures.text(refresh.recs_path("hhs-oig"))
        pubs, _ = self.run_with(8, hhs_oig=net.Refused("HTTP 403"), dot_oig=fixtures.dot_csv(open_first=1))
        self.assertEqual(pubs["hhs-oig"]["outcome"], "refused")
        self.assertEqual(pubs["hhs-oig"]["retrieved_at"], "2031-03-01T06:00:00Z", "the read date stays the last good one")
        self.assertEqual(pubs["hhs-oig"]["refused_since"], "2031-03-08T06:00:00Z")
        self.assertEqual(fixtures.text(refresh.recs_path("hhs-oig")), before)
        self.assertEqual(pubs["dot-oig"]["outcome"], "ok")
        self.assertEqual(pubs["dot-oig"]["retrieved_at"], "2031-03-08T06:00:00Z")
        self.assertTrue(refresh.load_events("dot-oig"), "the other publisher's change was still recorded")
        # it answers again: the refusal marker clears
        pubs, _ = self.run_with(15, hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv(open_first=1))
        self.assertEqual(pubs["hhs-oig"]["outcome"], "ok")
        self.assertEqual(pubs["hhs-oig"]["refused_since"], "")

    def test_unreachable_is_retried_and_a_refusal_is_not(self):
        pubs, feed = self.run_with(1, hhs_oig=[net.Unreachable("timed out"), net.Unreachable("timed out"), fixtures.hhs_csv()], dot_oig=net.Refused("HTTP 403"))
        self.assertEqual(pubs["hhs-oig"]["outcome"], "ok")
        self.assertEqual(feed.calls.count("hhs-oig"), 3)
        self.assertEqual(feed.calls.count("dot-oig"), 1, "a refusal is accepted, not retried")
        self.assertEqual(pubs["dot-oig"]["outcome"], "refused")

    def test_a_file_that_fails_the_quality_gates_is_not_accepted(self):
        self.run_with(1, hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv())
        junk = (fixtures.HHS_HEAD + "\n" + "\n".join(f",,,,X-{i},Text {i},,,,,,,,,,,,," for i in range(9)) + "\n").encode()
        pubs, _ = self.run_with(8, hhs_oig=junk, dot_oig=b"<html>Just a moment...</html>")
        self.assertEqual(pubs["hhs-oig"]["outcome"], "rejected")
        self.assertEqual(pubs["dot-oig"]["outcome"], "rejected")
        self.assertEqual(len(refresh.load_records("hhs-oig")), 8)
        self.assertTrue(all(r["status"] for r in refresh.load_records("hhs-oig")))
        self.assertEqual(len(refresh.load_records("dot-oig")), 6)

    def test_a_file_that_shrank_implausibly_is_not_accepted(self):
        self.run_with(1, hhs_oig=fixtures.hhs_csv(n=8), dot_oig=fixtures.dot_csv())
        pubs, _ = self.run_with(8, hhs_oig=fixtures.hhs_csv(n=3), dot_oig=fixtures.dot_csv())
        self.assertEqual(pubs["hhs-oig"]["outcome"], "rejected")
        recs = refresh.load_records("hhs-oig")
        self.assertEqual(len(recs), 8)
        self.assertTrue(all(r["in_export"] for r in recs), "nothing is marked gone on the strength of a broken file")
        self.assertEqual(refresh.load_events("hhs-oig"), [])

    def test_running_twice_in_a_row_is_harmless(self):
        self.run_with(1, hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv())
        self.run_with(8, hhs_oig=fixtures.hhs_csv(status_of={2: "Closed Unimplemented"}), dot_oig=fixtures.dot_csv())
        events = refresh.load_events("hhs-oig")
        recs = fixtures.text(refresh.recs_path("hhs-oig"))
        feed = fixtures.Feed(hhs_oig=fixtures.hhs_csv(status_of={2: "Closed Unimplemented"}), dot_oig=fixtures.dot_csv())
        with fixtures.quiet():
            refresh.run(now=fixtures.when(8), fetch=feed, probe=False, pause=0, force=True)
        self.assertEqual(refresh.load_events("hhs-oig"), events, "a second run on the same file adds no events")
        self.assertEqual(fixtures.text(refresh.recs_path("hhs-oig")), recs)

    def test_a_rerun_soon_after_a_good_read_does_not_ask_the_publisher_again(self):
        self.run_with(1, hhs_oig=fixtures.hhs_csv(), dot_oig=net.Unreachable("down"))
        feed = fixtures.Feed(hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv())
        with fixtures.quiet():
            status = refresh.run(now=fixtures.when(1) + timedelta(hours=3), fetch=feed, probe=False, pause=0)
        self.assertNotIn("hhs-oig", feed.calls, "read three hours ago: left alone")
        self.assertIn("dot-oig", feed.calls, "the one that failed is tried again")
        self.assertEqual(status["publishers"]["hhs-oig"]["retrieved_at"], "2031-03-01T06:00:00Z")
        self.assertEqual(status["publishers"]["dot-oig"]["outcome"], "ok")
        feed = fixtures.Feed(hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv())
        with fixtures.quiet():
            refresh.run(now=fixtures.when(1) + timedelta(hours=4), fetch=feed, probe=False, pause=0, force=True)
        self.assertEqual(sorted(set(feed.calls)), ["dot-oig", "hhs-oig"])

    def test_record_files_hold_one_record_per_line(self):
        self.run_with(1, hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv())
        lines = fixtures.text(refresh.recs_path("hhs-oig")).splitlines()
        self.assertEqual(len(lines), 8 + 2)
        json.loads("\n".join(lines))

    def test_freshness_check(self):
        with fixtures.quiet():
            self.assertFalse(refresh.check_fresh(now=fixtures.when(1)), "nothing read yet")
            self.run_with(1, hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv())
            self.assertTrue(refresh.check_fresh(now=fixtures.when(2)))
            self.run_with(9, hhs_oig=fixtures.hhs_csv(), dot_oig=net.Unreachable("down"))
            self.assertTrue(refresh.check_fresh(now=fixtures.when(10)), "one missed read is within the limit")
            late = fixtures.when(1) + timedelta(days=60)
            self.assertFalse(refresh.check_fresh(now=late))


class Links(fixtures.TempData, unittest.TestCase):
    """The weekly check that the links every page carries still open."""

    def setUp(self):
        super().setUp()
        with fixtures.quiet():
            refresh.run(now=fixtures.when(1), fetch=fixtures.Feed(hhs_oig=fixtures.hhs_csv(), dot_oig=fixtures.dot_csv()), probe=False, pause=0)
        self.src = sources.BY_ID["hhs-oig"]
        self.cfg = refresh.load_config()
        recs = refresh.load_records("hhs-oig")
        self.newest = max(recs, key=lambda r: r["issued"])

    def getter(self, robots_txt=b"", report_body=None, report_status=200, tracker=(b"<html>tracker</html>", 200)):
        seen = []

        def get(url, ua, accept, max_bytes, timeout=120, trusted_hosts=None):
            seen.append(url)
            if url.endswith("/robots.txt"):
                return robots_txt, {}, 200 if robots_txt else 404
            if url == self.src["tracker"]:
                if isinstance(tracker, Exception):
                    raise tracker
                return tracker[0], {}, tracker[1]
            body = report_body if report_body is not None else f"<html>{self.newest['report_number']}</html>".encode()
            return body, {}, report_status
        return get, seen

    def test_working_links_are_recorded_as_ok_in_three_requests(self):
        get, seen = self.getter()
        out = refresh.verify_links(self.src, self.cfg, get=get)
        self.assertEqual(out, {"tracker": "ok", "report_link": "ok"})
        self.assertEqual(len(seen), 3)
        self.assertIn(self.newest["report_url"], seen)

    def test_a_report_link_that_no_longer_shows_the_report_is_noticed(self):
        get, _ = self.getter(report_body=b"<html>No results</html>")
        self.assertTrue(refresh.verify_links(self.src, self.cfg, get=get)["report_link"].startswith("opened, but"))
        get, _ = self.getter(report_status=404)
        self.assertEqual(refresh.verify_links(self.src, self.cfg, get=get)["report_link"], "HTTP 404")

    def test_robots_rules_are_respected_and_refusals_recorded(self):
        get, seen = self.getter(robots_txt=b"User-agent: *\nDisallow: /reports/\n")
        out = refresh.verify_links(self.src, self.cfg, get=get)
        self.assertIn("robots.txt", out["tracker"])
        self.assertEqual(len(seen), 1, "nothing but robots.txt was requested")
        get, _ = self.getter(tracker=net.Refused("HTTP 403"))
        self.assertTrue(refresh.verify_links(self.src, self.cfg, get=get)["tracker"].startswith("refused"))


if __name__ == "__main__":
    unittest.main()
