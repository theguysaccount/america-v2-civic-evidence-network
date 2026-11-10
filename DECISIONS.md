# DECISIONS

1. **A static rebuild, not a port.** The original is a server app (vinext on Cloudflare Workers with D1) whose local
   tree does not build. The machine-driven brief asks for AuditLine only, on GitHub Pages, with no server. So this is a
   new, small pipeline in Python's standard library that keeps the original's contract and look.
2. **Staged, not launched.** `americav2.org` is live, so this copy is `noindex`, has no sitemap and skips IndexNow.
   Two settings switch it over (OPERATIONS.md). Jack decides.
3. **Only publishers that accept an honest automated reader.** The job sends a User-Agent that names this
   repository, reads robots.txt first, and treats 401/403/406/429 or a bot-check page as a refusal. It never disguises
   itself and never uses a browser to get past a refusal. That rules out GAO, State OIG and Oversight.gov today.
   HHS OIG (in the original's allowlist) and DOT OIG (new) both publish full exports and accept the request.
4. **The missing publishers are shown, not hidden.** The coverage page lists them, why they are missing, how they
   answered the last weekly robots.txt request, and their own trackers. Agency pages say counts are per publisher.
5. **Status is copied, never interpreted.** `state` (open/closed/other) is only whether the publisher's wording
   starts with "Open" or "Closed". A record with neither is listed apart.
6. **History starts the day a publisher was first read.** Earlier dates on a page are the publisher's. Changes are
   detected by comparing each new file with the last one; events are append-only; a record that leaves the file is
   kept and marked.
7. **"Overdue" became "past the publisher's expected-update date".** The original's brief asks for an overdue queue
   and also warns that "overdue" is a defamation risk. The list is date arithmetic on one HHS OIG field and says so.
8. **No human review queue, so no closure claims.** The original requires human review before a record implies
   closure. With no reviewer in a machine-run edition, the site makes no such claim at all.
9. **Fail closed on bad files.** A file is rejected if under 70% of rows have a number, an open/closed status or
   an issue date, or if it lists 30% fewer recommendations than the last good one. The last good records stay.
10. **One repaired TLS quirk.** oig.hhs.gov sends an incomplete certificate chain. Like a browser, the job fetches
    the missing issuer named in the site's own certificate; the chain must still end at a trusted root.
11. **Exact dollars.** Publisher figures are shown to the dollar, with the publisher's label.
12. **Per-report links are checked weekly.** If a publisher changes its tracker's address scheme, pages fall back to
    the tracker's front page instead of carrying broken links.
13. **Record files hold one record per line** so a status change is a one-line diff in this repository's history.
14. **Embeds are always `noindex`,** staged or not: they duplicate the office page they link to.

## Questions for Jack (nothing is blocked on them)
- Should AuditLine live at `auditline.americav2.org`, replace `americav2.org/spokes/audit-line`, or stay staged?
- Is someone willing to ask GAO for a sanctioned data feed, or to download its export by hand? (OPERATIONS.md, key 2)
