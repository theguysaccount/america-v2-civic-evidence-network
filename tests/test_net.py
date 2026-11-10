"""The download: robots.txt first, refusals are accepted, and a web page is never taken for the export."""
import unittest

from auditline import net, robots, sources
from auditline.common import load_config
from tests import fixtures

SRC = sources.BY_ID["hhs-oig"]


class FakeGet:
    def __init__(self, robots_answer, export_answer):
        self.answers = {"robots": robots_answer, "export": export_answer}
        self.calls = []

    def __call__(self, url, ua, accept, max_bytes, timeout=120, trusted_hosts=None):
        self.calls.append((url, ua, trusted_hosts))
        ans = self.answers["robots" if url.endswith("/robots.txt") else "export"]
        if isinstance(ans, Exception):
            raise ans
        return ans


class FetchExport(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()
        self._get = net.get

    def tearDown(self):
        net.get = self._get

    def fetch(self, robots_answer, export_answer):
        fake = FakeGet(robots_answer, export_answer)
        net.get = fake
        return fake, lambda: net.fetch_export(SRC, self.cfg)

    def test_reads_robots_first_then_the_export_with_an_honest_user_agent(self):
        raw = fixtures.hhs_csv()
        fake, go = self.fetch((b"User-agent: *\nDisallow: /search\n", {}, 200), (raw, {"content-type": "text/csv"}, 200))
        body, _ = go()
        self.assertEqual(body, raw)
        self.assertTrue(fake.calls[0][0].endswith("/robots.txt"))
        self.assertEqual(fake.calls[1][0], SRC["url"])
        ua = fake.calls[1][1]
        self.assertIn("AuditLine", ua)
        self.assertIn("github.com/", ua, "the User-Agent says where to find the operator")
        self.assertNotIn("Mozilla", ua)
        self.assertNotIn("@", ua, "no email address in the User-Agent")
        self.assertEqual(fake.calls[1][2], SRC["hosts"], "redirects must stay on the publisher's hosts")

    def test_a_robots_disallow_is_a_refusal_and_the_export_is_not_requested(self):
        path = "/" + SRC["url"].split("/", 3)[3].split("?")[0]
        fake, go = self.fetch((f"User-agent: *\nDisallow: {path}\n".encode(), {}, 200), (b"x", {}, 200))
        with self.assertRaises(net.Refused):
            go()
        self.assertEqual(len(fake.calls), 1)

    def test_a_refused_robots_file_is_a_refusal(self):
        fake, go = self.fetch(net.Refused("HTTP 403"), (b"x", {}, 200))
        with self.assertRaises(net.Refused):
            go()
        self.assertEqual(len(fake.calls), 1)

    def test_a_bot_check_page_is_a_refusal_not_data(self):
        for robots_answer, export_answer in (
                ((b"<!DOCTYPE html><html><body>Checking your browser</body></html>", {}, 200), (b"x", {}, 200)),
                ((b"", {}, 404), (b"<!doctype html><html>Access Denied</html>", {"content-type": "text/csv"}, 200)),
                ((b"", {}, 404), (b"Recommendation Number\n1\n", {"content-type": "text/html; charset=utf-8"}, 200))):
            _, go = self.fetch(robots_answer, export_answer)
            with self.assertRaises(net.Refused):
                go()

    def test_server_errors_are_unreachable_so_they_can_be_retried(self):
        _, go = self.fetch((b"", {}, 503), (b"x", {}, 200))
        with self.assertRaises(net.Unreachable):
            go()
        _, go = self.fetch((b"", {}, 404), (b"", {}, 502))
        with self.assertRaises(net.Unreachable):
            go()

    def test_no_robots_file_means_no_rules(self):
        raw = fixtures.hhs_csv()
        _, go = self.fetch((b"", {}, 404), (raw, {"content-type": "text/csv"}, 200))
        self.assertEqual(go()[0], raw)


class Robots(unittest.TestCase):
    def test_longest_rule_wins_and_allow_wins_a_tie(self):
        r = robots.Robots("User-agent: *\nDisallow: /recommendations/\nAllow: /recommendations/export-recs/\n")
        self.assertTrue(r.allowed("https://example.gov/recommendations/export-recs/", "AuditLineStatic"))
        self.assertFalse(r.allowed("https://example.gov/recommendations/other", "AuditLineStatic"))

    def test_a_group_naming_this_reader_replaces_the_general_one(self):
        r = robots.Robots("User-agent: *\nAllow: /\n\nUser-agent: AuditLineStatic\nDisallow: /\n")
        self.assertFalse(r.allowed("https://example.gov/export", "AuditLineStatic"))
        self.assertTrue(r.allowed("https://example.gov/export", "SomeoneElse"))

    def test_wildcards_and_query_strings(self):
        r = robots.Robots("User-agent: *\nDisallow: /*?*_format=csv\n")
        self.assertFalse(r.allowed("https://example.gov/dashboard/export?page&_format=csv", "AuditLineStatic"))
        self.assertTrue(r.allowed("https://example.gov/dashboard/export", "AuditLineStatic"))


if __name__ == "__main__":
    unittest.main()
