# STATE (2026-11-10)

**Staged copy:** https://theguysaccount.github.io/america-v2-civic-evidence-network/ (noindex; the original at
americav2.org is live and unchanged).

## Works
- 8,091 inspector-general recommendations mirrored from two official exports: HHS OIG (4,658) and DOT OIG (3,433).
- One page per recommendation: the publisher's exact status, the date its file was read, the text, dates, response,
  dollar labels, a dated history, sibling recommendations and a one-click link to the report in the publisher's tracker.
- One page per responsible office (32), per publisher, an open-by-agency table, search, a changes page, CSV/JSON
  mirror, Atom feeds (site and per office), an embeddable open count per office.
- Twice-weekly read with change detection, source-link check, weekly self-test, keep-alive. 50 tests.
  Both scheduled workflows have passed on GitHub's own schedule trigger (first on 2026-11-10), not only by hand.

## What the original has that this copy does not
- GAO and State OIG records. Both sites refuse automated requests (HTTP 403), from this Mac and from GitHub's
  runners, so they are listed on the coverage page with their own trackers instead. Oversight.gov answers 406.
- Accounts, watchlists, the reviewer queue, corrections workflow, the API, and the other eleven surfaces. All need
  the server (Cloudflare D1) the original runs on.

## Reused from the original (`america-2`, read-only copy)
- The contract: source before summary, publisher status is labelled, no inferred fraud or waste, every change is an event.
- The HHS OIG export address from `db/audit-sources.ts`; the brand line, headline and palette of `app/spokes/audit-line`.

## Broken or missing in the original tree
- 47 files exist only as iCloud " 2" duplicates, so the tree does not build. Nothing here depends on it.

## Not done
- No GAO coverage (needs a human: OPERATIONS.md, key 2). No analytics. No custom domain. Paid watchlists slot is off.
