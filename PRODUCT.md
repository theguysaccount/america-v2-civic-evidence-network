# PRODUCT: AuditLine (static edition)

**User.** A reporter, watchdog researcher or oversight staffer who needs to cite one specific recommendation an
inspector general made to an agency, and say what its official status is today.

**The painful job.** The publishers' trackers are search forms. A recommendation has no address of its own, there is
no record of when its status changed, and "how many are still open at this office, and how old is the oldest" means
downloading a spreadsheet.

**Promise.** Every official warning, and what the publisher says happened next: one permanent page per
recommendation, with the publisher's exact status, the date that status was read, and a dated history of every change.

**Wedge.** Pages people can search for and cite: `[agency] open inspector general recommendations`, a recommendation
number, a report number. Each office has a feed and an embeddable count; everything is also a CSV/JSON file.

**Why now.** Oversight of federal spending is under heavy scrutiny, and two inspectors general publish complete,
machine-readable exports that nobody has given stable pages.

**What it will not do (v1).**
- It will not say a recommendation was or was not carried out. "Open" and "closed" are the publisher's words.
- It will not rank offices for blame, score them, or name any person as responsible.
- It will not treat dollar figures as losses or savings. They are the publisher's labelled estimates.
- It will not summarise or classify anything with AI.
- It will not cover a publisher that refuses automated readers (GAO, State OIG, Oversight.gov today). The gap is shown.

**Activation metric.** A visitor opens a recommendation page and then follows the link to the publisher's report
(source click-through), or subscribes to an office's feed. Counted only if `GOATCOUNTER_URL` is set.

**First revenue event (key, off).** An organization pays for private watchlists and alerts hosted elsewhere; the
one marked slot on recommendation pages links to it when `WATCHLIST_URL` is set. GitHub Pages is non-commercial.

**The evaluator's cheapest test** was "publish 500 GAO recommendations as pages and see whether reporters return".
This edition publishes 8,091 inspector-general recommendation pages. GAO itself is not reachable by an automated job.
