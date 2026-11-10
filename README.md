# AuditLine (static edition)

**Staged copy:** https://theguysaccount.github.io/america-v2-civic-evidence-network/ (not indexed).
**Live original:** https://www.americav2.org/spokes/audit-line (unchanged; the cutover is a separate decision, see [OPERATIONS.md](OPERATIONS.md)).

Every official warning, and what the publisher says happened next. One page per recommendation a federal inspector
general has made to an agency: the exact wording, the responsible office, the publisher's own status with the date it
was read, and a dated history of every change. AuditLine repeats official records. It does not judge them.

No server, no API keys, no dependencies: Python's standard library reads official exports and writes a static site.

## Publishers

| Publisher | Official export | Covered |
|---|---|---|
| HHS Office of Inspector General | [Recommendation Tracker](https://oig.hhs.gov/reports/recommendations/tracker/) | yes |
| DOT Office of Inspector General | [Recommendation Dashboard](https://www.oig.dot.gov/recommendation-dashboard) | yes |
| GAO, State OIG, Oversight.gov | their own trackers | **no**: they refuse automated readers, and this project does not work around a refusal |

## The rules the code enforces

1. **Primary sources open in one click.** Every page links the report in the publisher's tracker and names the file
   it was read from, with its date, size and SHA-256.
2. **Publisher status is labelled.** Statuses are copied exactly and shown with the date they were read.
3. **No inferred fraud or waste.** No scores, no blame, no verdicts. Dollar figures keep the publisher's label.
4. **Every change becomes an event.** Files are compared read to read; differences are appended, never edited.

## Layout

| Path | What it is |
|---|---|
| `auditline/sources.py` | The publishers, and how each export becomes plain records |
| `auditline/net.py`, `robots.py` | One polite download: robots.txt first, an honest User-Agent, refusals accepted |
| `auditline/refresh.py` | Reads each publisher on its own, diffs into `data/events/`, checks source links, `data/status.json` |
| `auditline/build.py`, `og.py` | The static site, search index, CSV/JSON mirror, feeds, embeds, share cards |
| `auditline/guard.py`, `e2e.py`, `selftest.py` | Pre-deploy checks, browser check of search, live check |
| `config/site.json` | Base URL default, staged/indexable flag, quality gates and limits |
| `data/recs/` | One file per publisher, one record per line. Committed by the refresh job |
| `data/events/` | Append-only change history per publisher (created at the first observed change) |

## Run it

```sh
python3 -m unittest discover -s tests -t .      # tests (Python 3.9+; no installs)
python3 -m auditline.refresh                     # read the publishers (skips one read in the last 20 hours)
python3 -m auditline.build --site _site          # build the site
python3 -m auditline.og --site _site             # share cards (needs Chrome; falls back to the default card)
python3 -m auditline.guard _site                 # the checks every deploy must pass
python3 -m auditline.e2e _site                   # search in headless Chrome
python3 -m auditline.selftest                    # check the live site
```

To preview locally, serve a folder that contains `_site` under the name `america-v2-civic-evidence-network`, or build
with `SITE_URL=http://localhost:8000`.

## Licence

Code: MIT. Compiled data: CC0 1.0 (the publishers' records are federal public records).
More: [PRODUCT.md](PRODUCT.md), [DECISIONS.md](DECISIONS.md), [STATE.md](STATE.md), [LAUNCH.md](LAUNCH.md).
