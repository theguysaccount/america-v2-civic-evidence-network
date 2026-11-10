"""The official publishers AuditLine mirrors, and how each one's export becomes plain records.

A publisher is listed under COVERED only if it offers an official export and answers an honest
automated request. Publishers that refuse automated requests are listed under NOT_COVERED, with
their own tracker linked, so the gap is visible instead of silently missing.

Nothing here judges a recommendation. `status` is the publisher's exact wording. `state` is only a
mechanical reading of that wording (it starts with "Open" or with "Closed").
"""
import csv
import hashlib
import io
import re
from urllib.parse import quote

from .common import slugify

COVERED = [
    {
        "id": "hhs-oig",
        "name": "HHS Office of Inspector General",
        "short": "HHS OIG",
        "department": "Department of Health and Human Services",
        "url": "https://oig.hhs.gov/recommendations/export-recs/",
        "hosts": ["oig.hhs.gov"],
        "tracker": "https://oig.hhs.gov/reports/recommendations/tracker/",
        "tracker_name": "HHS OIG Recommendation Tracker",
        "cadence": "The publisher updates its tracker about monthly.",
        "money_label": "Potential savings, as labelled by HHS OIG",
        "text_limit": 1000,     # the export cuts recommendation text at 1,000 characters
        "note": "HHS OIG's status, response, dates and potential-savings labels are the publisher's own claims.",
    },
    {
        "id": "dot-oig",
        "name": "DOT Office of Inspector General",
        "short": "DOT OIG",
        "department": "Department of Transportation",
        "url": "https://www.oig.dot.gov/recommendation-dashboard/export?page&_format=csv",
        "hosts": ["www.oig.dot.gov", "oig.dot.gov"],
        "tracker": "https://www.oig.dot.gov/recommendation-dashboard",
        "tracker_name": "DOT OIG Recommendation Dashboard",
        "cadence": "The publisher maintains its dashboard continuously.",
        "money_label": "Questioned costs, unsupported costs and funds put to better use, as reported by DOT OIG",
        "note": "DOT OIG's status and dollar figures are the publisher's own claims. Recommendations it marks sensitive are listed without their text.",
    },
]
NOT_COVERED = [
    {"name": "U.S. Government Accountability Office", "short": "GAO", "tracker": "https://www.gao.gov/reports-testimonies/recommendations-database",
     "tracker_name": "GAO Recommendations Database", "why": "gao.gov answers automated requests with “Access Denied”, including for its robots.txt and its downloadable datasets."},
    {"name": "Oversight.gov (Council of the Inspectors General)", "short": "Oversight.gov", "tracker": "https://www.oversight.gov/recommendations",
     "tracker_name": "Oversight.gov open recommendations", "why": "oversight.gov rejects automated requests."},
    {"name": "State Department Office of Inspector General", "short": "State OIG", "tracker": "https://www.stateoig.gov/reports-by-recommendations",
     "tracker_name": "State OIG recommendations", "why": "stateoig.gov puts a browser check in front of its export."},
]
BY_ID = {s["id"]: s for s in COVERED}

# DOT OIG names operating administrations by their initials.
DOT_AGENCY = {
    "FAA": "Federal Aviation Administration", "FHWA": "Federal Highway Administration", "FMCSA": "Federal Motor Carrier Safety Administration",
    "FRA": "Federal Railroad Administration", "FTA": "Federal Transit Administration", "MARAD": "Maritime Administration",
    "NHTSA": "National Highway Traffic Safety Administration", "OST": "Office of the Secretary of Transportation",
    "PHMSA": "Pipeline and Hazardous Materials Safety Administration", "GLS": "Great Lakes St. Lawrence Seaway Development Corporation",
    "SLSDC": "Saint Lawrence Seaway Development Corporation", "STB": "Surface Transportation Board", "NTSB": "National Transportation Safety Board",
    "AMTRAK": "Amtrak", "MWAA": "Metropolitan Washington Airports Authority", "RITA": "Research and Innovative Technology Administration",
    "DOT": "Department of Transportation (department-wide)", "OIG": "Office of Inspector General", "BTS": "Bureau of Transportation Statistics",
    "VOLPE": "Volpe National Transportation Systems Center", "RSPA": "Research and Special Programs Administration",
}
_WS = re.compile(r"\s+")


def _clean(s):
    return _WS.sub(" ", (s or "").replace("﻿", "")).strip()


def _date(s):
    """'2010-03-18' or '07.18.2007' or '7/18/2007' -> '2010-03-18'; anything else -> ''."""
    s = _clean(s)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m and 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= 31:
        return f"{int(m.group(3)):04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


def _amount(s):
    s = _clean(s).replace("$", "").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def state_of(status):
    low = (status or "").lower()
    if low.startswith("open"):
        return "open"
    if low.startswith("closed"):
        return "closed"
    return "other"


def _rows(raw):
    text = raw.decode("utf-8-sig", "replace").replace("﻿", "")
    reader = csv.DictReader(io.StringIO(text))
    return [{_clean(k): (v or "") for k, v in row.items() if k} for row in reader]


def _unique(records):
    """Give each record a stable, unique slug; identical publisher numbers get -2, -3 in file order."""
    seen = {}
    for r in records:
        base = slugify(r["number"]) or "unnumbered"
        seen[base] = seen.get(base, 0) + 1
        r["slug"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
        r["id"] = f"{r['publisher']}/{r['slug']}"
    return records


def parse_hhs(raw):
    out = []
    for row in _rows(raw):
        number, text = _clean(row.get("Recommendation Number")), _clean(row.get("Recommendation"))
        if not number and not text:
            continue
        report = _clean(row.get("Report Number"))
        status = _clean(row.get("Status"))
        out.append({
            "publisher": "hhs-oig", "number": number, "text": text, "status": status, "state": state_of(status),
            "agency": _clean(row.get("Responsible Agency")) or _clean(row.get("Report Agency")),
            "report_number": report, "report_title": _clean(row.get("Report Title")), "report_type": _clean(row.get("Report Type")),
            "report_url": f"https://oig.hhs.gov/reports/recommendations/tracker/?search={quote(report)}&view-mode=report-grouped" if report else "",
            "issued": _date(row.get("Issued Date")), "closed": _date(row.get("Closed Date")),
            "response": _clean(row.get("Response")), "last_update": _date(row.get("Last Update Received")),
            "next_update": _date(row.get("Next Update Expected")),
            "amounts": {k: v for k, v in {"potential_savings": _amount(row.get("Potential Savings"))}.items() if v},
            "flags": [f for f, on in (("Top recommendation", _clean(row.get("Top Recommendation")).lower() == "true"),
                                      ("Legislative", _clean(row.get("Legislative Related")).lower() == "yes")) if on],
            "topics": [t.strip() for t in _clean(row.get("Issue Area")).split("|") if t.strip()],
        })
    return _unique(out)


def parse_dot(raw):
    out = []
    for row in _rows(raw):
        project, num = _clean(row.get("Project ID")), _clean(row.get("Recommendation Number"))
        if not project and not num:
            continue
        sub = _clean(row.get("Subheading"))
        number = f"{project}-{num}{sub}" if project else f"{num}{sub}"
        status = _clean(row.get("Status"))
        abbr = _clean(row.get("Agency"))
        sensitive = bool(_clean(row.get("Sensitive")))
        amounts = {"questioned_cost": _amount(row.get("Questioned Cost")), "unsupported_cost": _amount(row.get("Unsupported Cost")),
                   "funds_better_use": _amount(row.get("Funds Put to Better Use"))}
        out.append({
            "publisher": "dot-oig", "number": number, "text": _clean(row.get("Recommendation Text")), "status": status,
            "state": state_of(status), "agency": DOT_AGENCY.get(abbr.upper(), abbr), "agency_code": abbr,
            "report_number": project, "report_title": _clean(row.get("Project Title")), "report_type": "",
            "report_url": f"https://www.oig.dot.gov/recommendation-dashboard?combine={quote(project)}" if project else "",
            "issued": _date(row.get("Issue Date")),
            "closed": _date(row.get("Closed Date")), "response": "", "last_update": "", "next_update": "",
            "amounts": {k: v for k, v in amounts.items() if v},
            "flags": [f for f, on in (("Sensitive", sensitive), ("Pandemic oversight", bool(_clean(row.get("Pandemic Oversight"))))) if on],
            "topics": [],
        })
    return _unique(out)


PARSERS = {"hhs-oig": parse_hhs, "dot-oig": parse_dot}
AMOUNT_LABEL = {"potential_savings": "Potential savings", "questioned_cost": "Questioned costs", "unsupported_cost": "Unsupported costs",
                "funds_better_use": "Funds put to better use"}
TRACKED = ["status", "closed", "response", "next_update", "last_update", "agency", "text", "amounts"]
FIELD_LABEL = {"status": "Status", "closed": "Closed date", "response": "Agency response", "next_update": "Next update expected",
               "last_update": "Last update received", "agency": "Responsible agency", "text": "Recommendation text",
               "amounts": "Dollar figures"}


def quality(records):
    """Share of records with each essential field. An export that fails these gates is not accepted."""
    n = len(records) or 1
    return {"number": sum(1 for r in records if r["number"]) / n,
            "status": sum(1 for r in records if r["state"] in ("open", "closed")) / n,
            "issued": sum(1 for r in records if r["issued"]) / n}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()
