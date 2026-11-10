"""Ask each official source for its export once and report how it answers. Reads nothing private.

  python3 -m auditline.probe

Used to find out, from wherever it runs, which publishers answer an honest automated request.
A refusal is reported as a refusal; nothing here tries to get around one.
"""
import sys
import urllib.error
import urllib.request

UA = "AuditLineStatic/1.0 (+https://github.com/theguysaccount/america-v2-civic-evidence-network)"
SOURCES = [
    ("HHS OIG recommendation tracker", "https://oig.hhs.gov/recommendations/export-recs/"),
    ("State OIG recommendations", "https://www.stateoig.gov/recommendations/export/csv?action_office=All&financial_value=All&issue_date_from=&issue_date_to=&significant=All&status=All"),
    ("GAO duplication and cost savings 2026", "https://www.gao.gov/assets/2026-05/2026%20Duplication%20and%20Cost%20Savings%20-%20Downloadable%20Spreadsheet.csv"),
    ("GAO recommendations database", "https://www.gao.gov/reports-testimonies/recommendations-database"),
    ("GAO robots.txt", "https://www.gao.gov/robots.txt"),
    ("Oversight.gov recommendations", "https://www.oversight.gov/recommendations"),
    ("Oversight.gov robots.txt", "https://www.oversight.gov/robots.txt"),
    ("GovInfo GAO reports collection", "https://www.govinfo.gov/bulkdata/json/GAOREPORTS"),
]


def main():
    import socket
    import time
    for host in ("oig.hhs.gov",):
        try:
            print(host, "resolves to", sorted({a[4][0] for a in socket.getaddrinfo(host, 443)}))
        except Exception as e:
            print(host, "did not resolve:", e)
    for attempt in range(2):
        if attempt:
            time.sleep(20)
        once()
        print("---")
    return 0


def once():
    for name, url in SOURCES:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,text/html;q=0.9,text/plain;q=0.8,*/*;q=0.5"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read(4_000_000)
                print(f"{r.status}  {r.headers.get('Content-Type', '?'):40.40}  {len(body):>9,} bytes  {name}")
        except urllib.error.HTTPError as e:
            print(f"{e.code}  {e.headers.get('Content-Type', '?'):40.40}  {'refused':>15}  {name}")
        except Exception as e:
            print(f"---  {type(e).__name__:40.40}  {'no answer':>15}  {name}  ({str(getattr(e, 'reason', e))[:120]})")


if __name__ == "__main__":
    sys.exit(main())
