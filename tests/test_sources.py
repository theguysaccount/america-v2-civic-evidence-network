"""Reading the publishers' exports: fields are copied, never judged."""
import unittest

from auditline import sources
from tests import fixtures


class Parse(unittest.TestCase):
    def test_hhs_fields_are_copied_as_written(self):
        recs = sources.parse_hhs(fixtures.hhs_csv())
        self.assertEqual(len(recs), 8)
        r = recs[0]
        self.assertEqual(r["publisher"], "hhs-oig")
        self.assertEqual(r["status"], "Open Unimplemented")
        self.assertEqual(r["state"], "open")
        self.assertEqual(r["agency"], "Example Health Agency")
        self.assertEqual(r["issued"], "2021-03-11")
        self.assertEqual(r["closed"], "")
        self.assertEqual(r["response"], "Concur")
        self.assertEqual(r["amounts"], {"potential_savings": 1250000.0})
        self.assertIn("Top recommendation", r["flags"])
        self.assertEqual(r["topics"], ["Example Area", "Second Area"])
        self.assertIn("<of the plan>", r["text"])
        self.assertTrue(r["report_url"].startswith("https://oig.hhs.gov/"))
        self.assertEqual(recs[2]["flags"], ["Legislative"])
        self.assertEqual(recs[5]["state"], "closed")
        self.assertTrue(recs[5]["closed"])

    def test_dot_fields_dates_and_agency_names(self):
        recs = sources.parse_dot(fixtures.dot_csv())
        self.assertEqual(len(recs), 6)
        r = recs[0]
        self.assertEqual(r["number"], "EX2021002-1")
        self.assertEqual(r["agency"], "Federal Aviation Administration")
        self.assertEqual(r["agency_code"], "FAA")
        self.assertEqual(r["issued"], "2021-01-11")
        self.assertEqual(r["amounts"], {"questioned_cost": 594000.0})
        self.assertEqual(recs[1]["agency"], "ZZTOP", "initials the map does not know are kept as written")
        self.assertIn("Sensitive", recs[1]["flags"])
        self.assertEqual(recs[3]["number"], "EX2021001-4a")
        self.assertEqual(recs[2]["closed"], "2023-04-20")

    def test_ids_are_unique_and_stable(self):
        raw = fixtures.hhs_csv()
        a, b = sources.parse_hhs(raw), sources.parse_hhs(raw)
        self.assertEqual([r["id"] for r in a], [r["id"] for r in b])
        self.assertEqual(len({r["id"] for r in a}), len(a))
        twice = (fixtures.HHS_HEAD + "\n" + "\n".join(fixtures.hhs_rows(2) + fixtures.hhs_rows(2)) + "\n").encode()
        ids = [r["id"] for r in sources.parse_hhs(twice)]
        self.assertEqual(len(set(ids)), 4, "a repeated number gets its own page, not a silent overwrite")
        self.assertTrue(ids[2].endswith("-2"))

    def test_state_is_only_a_reading_of_the_publishers_word(self):
        self.assertEqual(sources.state_of("Open Unimplemented"), "open")
        self.assertEqual(sources.state_of("Closed Acceptable Alternative"), "closed")
        self.assertEqual(sources.state_of("closed"), "closed")
        self.assertEqual(sources.state_of(""), "other")
        self.assertEqual(sources.state_of("Under review"), "other")

    def test_dates_and_amounts(self):
        self.assertEqual(sources._date("07.18.2007"), "2007-07-18")
        self.assertEqual(sources._date("7/8/2007"), "2007-07-08")
        self.assertEqual(sources._date("2010-03-18"), "2010-03-18")
        self.assertEqual(sources._date("soon"), "")
        self.assertEqual(sources._date("13.40.2007"), "")
        self.assertEqual(sources._amount("$1,250,000.50"), 1250000.5)
        self.assertIsNone(sources._amount("0"))
        self.assertIsNone(sources._amount("n/a"))

    def test_quality_gates_measure_the_essentials(self):
        good = sources.quality(sources.parse_hhs(fixtures.hhs_csv()))
        self.assertEqual(min(good.values()), 1.0)
        junk = (fixtures.HHS_HEAD + "\n" + ",,,,X-1,Some text,,,,,,,,,,,,,\n,,,,X-2,More text,,,,,,,,,,,,,\n").encode()
        q = sources.quality(sources.parse_hhs(junk))
        self.assertEqual(q["status"], 0)
        self.assertEqual(q["issued"], 0)
        self.assertEqual(sources.parse_hhs(b"<html><body>Access Denied</body></html>"), [])

    def test_every_covered_publisher_is_described(self):
        for s in sources.COVERED:
            for key in ("id", "name", "short", "url", "hosts", "tracker", "tracker_name", "note", "cadence", "department"):
                self.assertTrue(s.get(key), f"{s.get('id')}: {key}")
            self.assertTrue(s["url"].startswith("https://"))
            self.assertIn(s["url"].split("/")[2], s["hosts"])
            self.assertIn(s["id"], sources.PARSERS)
        for s in sources.NOT_COVERED:
            for key in ("name", "short", "tracker", "tracker_name", "why"):
                self.assertTrue(s.get(key))


if __name__ == "__main__":
    unittest.main()
