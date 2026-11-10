# LAUNCH

This build is **staged**. It is public at its GitHub Pages address so it can be reviewed, but it tells search engines
to stay away, because americav2.org is live. Nothing has been posted, sent or submitted anywhere.

## What is live
- https://theguysaccount.github.io/america-v2-civic-evidence-network/ (noindex, robots.txt disallows crawling, no sitemap).
- The IndexNow key file is published but nothing is submitted while the site is staged.

## Going live (Jack's decision)
The exact DNS record and the two settings are in OPERATIONS.md under "Cutover". In short: add
`auditline.americav2.org` as a CNAME to GitHub Pages, set `SITE_URL`, and set `SITE_INDEXABLE=true`.

## Once indexed: the search surfaces
| Query pattern | Page |
|---|---|
| "[agency] open inspector general recommendations", "[agency] OIG recommendations" | `/agency/<publisher>/<office>/` |
| a recommendation number, a report number, the first words of a recommendation | `/rec/<publisher>/<number>/` |
| "HHS OIG open recommendations", "DOT OIG recommendation dashboard" | `/publisher/<id>/`, `/open/` |
| "HHS OIG recommendations csv", "inspector general recommendations dataset" | `/data/` |

Every recommendation page is a real record with the publisher's wording, status, dates and a link to its report.
There are no thin or duplicated pages: closed-list pages exist only for offices with more than 150 closed
recommendations, and embeds are never indexed. `Dataset` and `WebSite` structured data, feeds and the CSV/JSON
mirror are in place for search and for AI answer engines that cite sources.

## Loops built into the product
- **Per-office Atom feeds**: follow one office and get every status change. This is the free version of "alerts".
- **Embeddable open count** per office, with the read date, linking back to the office page.
- **Open mirror**: `data/recommendations.csv`, `data/recommendations.json`, one file pair per publisher.

## The cheapest test (for a human; nothing here has been sent)
The evaluator's test was to offer three investigative reporters alerts and count who comes back after a week. The
free version is the per-office feed. Draft note:

> AuditLine gives every HHS and DOT inspector-general recommendation its own page, with the official status and a
> record of each change. Here is the page for [office]. Each office has a feed. Would a weekly digest of status
> changes for the agencies you cover be useful, and which publishers are missing?

## What a launch cannot fix
GAO is the publisher most people search for, and it is not here: gao.gov refuses automated readers. See
OPERATIONS.md, key 2.
