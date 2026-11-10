# OPERATIONS

Everything runs on GitHub Actions in `theguysaccount/america-v2-civic-evidence-network`. No human has a job here.

- Staged copy: https://theguysaccount.github.io/america-v2-civic-evidence-network/ (noindex).
- Live original: https://www.americav2.org/spokes/audit-line (a server app behind a Vercel proxy). Not touched.

## Automated jobs

| Workflow | When (UTC) | What it does | How it fails safely |
|---|---|---|---|
| **Refresh and deploy** `refresh.yml` | Tue 06:19 and Fri 06:43; every push to `main`; by hand | 1. `auditline.refresh`: for each publisher, robots.txt, then its official export (HHS OIG, DOT OIG); compare with the last file and append every change to `data/events/`; check that the tracker link and one per-report link still open; ask each publisher that is *not* covered for its robots.txt, once, to record how it answers. 2. Tests. 3. Build. 4. Share cards. 5. Guard. 6. Headless-Chrome check of search. 7. Commit `data/`. 8. Deploy. 9. Check the live site. A push skips step 1. | Each publisher is handled alone. Unreachable: tried three times, then its last good records stay. Refused (robots.txt, 401/403/406/429, a bot-check page): accepted, never retried or worked around. A file that fails the quality gates or lists 30% fewer recommendations is rejected. In every case pages keep showing the date of the last good file, and `data/status.json` says why. Any failure in steps 2 to 6 stops before deploy, so the last good site stays live. |
| **Weekly self-test** `selftest.yml` | Sun 08:37; by hand | Tests; live site: key pages and about 40 recommendation pages taken from the live search index (each must show the status the index lists and a read date); the live staged/indexed state must match the configuration; `refresh --check-fresh` (fails if a publisher has had no successful read in 16 days). If the live build is over 200 hours old or a publisher's copy is stale, it starts **Refresh and deploy**. Keep-alive. | Read-only apart from starting a refresh. A failure emails the repository owner. |
| **Tests** `test.yml` | Pull requests, other branches | Tests on Python 3.9 and 3.12, build, guard, browser check. | Never deploys. |

**Safe to re-run.** A publisher read successfully in the last 20 hours is not asked again (`min_hours_between_reads`),
and reading an unchanged file records nothing. Running the workflow twice in a row only rebuilds.

**Keep-alive.** Each read commits `data/status.json`, which keeps the schedules alive. As a backstop every scheduled
run calls `.github/scripts/keepalive.sh` (re-enables workflows GitHub paused for inactivity; empty commit after 45
quiet days).

**GitHub skips scheduled runs on this account.** Two read slots a week and the self-test's stale check mean no run
has to fire at a set time.

## What to watch
- **Actions → Refresh and deploy.** Red means the site was not updated; the previous site is still live. The failing
  step says why. Guard prints each problem.
- **`data/status.json`** (also shown on the site's Coverage page): per publisher `outcome` (`ok`, `refused`,
  `unreachable`, `rejected`), `retrieved_at` (last good file), `note`, `refused_since`, `links`.
  - `refused` for more than two weeks means the publisher now blocks automated readers. Do not work around it. Move
    it from `COVERED` to `NOT_COVERED` in `auditline/sources.py`; its pages stay, with their last read date.
  - `rejected` means the export's columns changed. Fix the parser in `auditline/sources.py` against the new file and
    add a fixture to `tests/`.
  - `links.report_link` not `ok` means the publisher changed its tracker addresses. Pages already fell back to the
    tracker's front page; update `report_url` in the parser.
- **A burst of events** in `data/events/<publisher>.json` after a publisher reformats text or dates. They are real
  differences between files, and the changes page shows them as such.
- **Size.** About 8,200 pages and 127 MB today; GitHub Pages allows 1 GB. Each new publisher of similar size adds
  about 60 MB.
- **A deploy that times out.** On 2026-11-10 one deploy sat in "syncing_files" for ten minutes and timed out; the
  previous site stayed live and a re-run took under a minute. The deploy job now offers the same build a second time
  before failing. If both attempts fail, re-run the failed job from the Actions tab.

## Manual levers
- **Run now:** Actions → Refresh and deploy → Run workflow. Untick "refresh" to only rebuild; tick "force" to ask
  the publishers again inside the 20-hour window.
- **Locally:** `python3 -m auditline.refresh --only hhs-oig --force`, then commit `data/`.
- **Add a publisher:** an entry in `COVERED` and a parser in `auditline/sources.py`, plus fixture tests. It must offer
  an official export and answer the job's honest request.
- **Limits:** `config/site.json` (`min_quality`, `max_shrink`, `stale_after_days`, `min_hours_between_reads`).

## Cutover: taking this out of staging (Jack decides)

Current state, checked 2026-11-10: `americav2.org` uses SiteGround nameservers (`ns1/ns2.siteground.net`). The apex
has `A 216.150.1.1` and `www` is a CNAME to `e11917d7863062a4.vercel-dns-016.com.` (the Vercel proxy in front of the
server app). `auditline.americav2.org` does not exist. The original AuditLine is a path on the server app
(`/spokes/audit-line`), so this static site cannot replace it by DNS alone; it goes beside it on a subdomain.

1. **DNS** (SiteGround → Site Tools → Domain → DNS Zone Editor, zone `americav2.org`): add
   `CNAME  auditline  →  theguysaccount.github.io.`
   Change nothing else.
2. **GitHub Pages:** repository Settings → Pages → Custom domain → `auditline.americav2.org` → Save. Wait for the
   certificate, then tick "Enforce HTTPS".
   CLI: `gh api -X PUT repos/theguysaccount/america-v2-civic-evidence-network/pages -f cname=auditline.americav2.org`
3. **The base-URL setting:**
   `gh variable set SITE_URL --body "https://auditline.americav2.org" -R theguysaccount/america-v2-civic-evidence-network`
4. **The indexing setting:**
   `gh variable set SITE_INDEXABLE --body true -R theguysaccount/america-v2-civic-evidence-network`
5. Actions → Refresh and deploy → Run workflow (refresh unticked). Canonical links, sitemap, robots.txt, feeds, embed
   snippets and IndexNow all follow the two settings. The weekly self-test checks the live state matches.
6. **Optional, in the original's own repositories (not this one):** redirect `/spokes/audit-line` on the server app to
   `https://auditline.americav2.org/`, so the two do not compete in search.
7. **Roll back:** delete the `auditline` CNAME, clear the Pages custom domain, delete the two variables, run the workflow.

To replace all of `americav2.org` instead (this takes the other eleven surfaces offline, so it is not recommended):
apex `A` records `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`, `www` CNAME to
`theguysaccount.github.io.`, Pages custom domain `www.americav2.org`, and `SITE_URL=https://www.americav2.org`.

## Keys Jack can turn later

1. **Custom domain / cutover.** Above. Other owned names that fit a later section: `stateauditor.org` (state audit
   findings; must not look like an official office), `proofofstate.org`.
2. **GAO, State OIG and Oversight.gov.** Needs a human because all three refuse automated readers (GAO and State OIG
   answer 403, Oversight.gov 406, checked weekly and shown on the Coverage page), and this project does not disguise
   its reader or use a browser to get round a refusal. Ways in, in order of preference:
   - Ask the publisher for a sanctioned feed, or permission for this job's User-Agent: GAO's public contact for the
     recommendations database; CIGIE for Oversight.gov; the State OIG webmaster.
   - Have a person download the export in a browser on a schedule and commit it under `inbox/<publisher>.csv`. The
     parser for that file is not written: it has to be written against a real file, with fixture tests, like the two
     in `auditline/sources.py`. A hand-fed publisher must be labelled as such on its pages, with the download date.
   If a publisher starts answering, the Coverage page's weekly check shows "answers" and it can be added like any other.
3. **Money: private watchlists.** One marked slot ("Paid service") on every recommendation page, off until
   `gh variable set WATCHLIST_URL --body "https://<service>" -R theguysaccount/america-v2-civic-evidence-network`.
   GitHub Pages is non-commercial, so the service itself (Stripe, email, accounts) must live on other hosting. The
   per-office feeds and `data/<publisher>.json` (records plus events) are what such a service would read.
4. **Analytics.** `gh variable set GOATCOUNTER_URL --body "https://<code>.goatcounter.com/count" -R …` after creating a
   GoatCounter site (needs an account). Without it the site counts nothing.
5. **More publishers.** A scheduled Claude routine could look, monthly, for another inspector general that offers an
   official export and answers an honest request, and open a pull request with the `COVERED` entry, parser and
   fixtures. Nothing here depends on it.
6. **Search Console** after cutover: verify `americav2.org` with a DNS TXT record and submit `/sitemap.xml`.

## Costs
$0. Public repository, GitHub-hosted runners (a few minutes a week), GitHub Pages, no keys.
