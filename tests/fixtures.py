"""Small made-up exports in the publishers' real column layouts. Nothing here is a real record."""
import contextlib
import io
import os
import shutil
import tempfile
from datetime import datetime, timezone

from auditline import common, net

HHS_HEAD = ("Report Number,Report Title,Report Agency,Report Type,Recommendation Number,Recommendation,Status,Responsible Agency,"
            "Potential Savings,Issued Date,Response,Last Update Received,Next Update Expected,Closed Date,Legislative Related,"
            "Issue Area,Target Group,Financial Group,Top Recommendation")
DOT_HEAD = ('"Project Title","Project ID","Issue Date",Agency,Year,"Recommendation Number",Subheading,"Recommendation Text",Sensitive,'
            '"Pandemic Oversight",Status,"Closed Date","Questioned Cost","Unsupported Cost","Funds Put to Better Use"')


def hhs_rows(n=8, open_first=3, status_of=None, drop=()):
    """n recommendations across two reports and two agencies; the first `open_first` are open."""
    rows = []
    for i in range(1, n + 1):
        if i in drop:
            continue
        status = (status_of or {}).get(i) or ("Open Unimplemented" if i <= open_first else "Closed Implemented")
        closed = "" if status.startswith("Open") else f"2024-0{(i % 8) + 1}-15"
        agency = "Example Health Agency" if i % 2 else "Example Services & Programs Office"
        savings = "1250000" if i == 1 else ""
        nxt = "2001-01-31" if i == 2 else ""
        rows.append(f'A-0{1 + i % 2}-20-0000{1 + i % 2},Review of Example Program {1 + i % 2},{agency},Audit,21-A-0{1 + i % 2}-00{i}.0{i},'
                    f'"We recommend that the agency, for example, finish step {i} <of the plan>.",{status},{agency},{savings},'
                    f'2021-03-{10 + i:02d},Concur,2025-06-01,{nxt},{closed},{"Yes" if i == 3 else "No"},Example Area|Second Area,,,{"True" if i == 1 else "False"}')
    return rows


def hhs_csv(**kw):
    return ("﻿" + HHS_HEAD + "\n" + "\n".join(hhs_rows(**kw)) + "\n").encode("utf-8")


def dot_rows(n=6, open_first=2):
    rows = []
    for i in range(1, n + 1):
        status = "Open" if i <= open_first else "Closed"
        closed = "" if status == "Open" else f"0{(i % 8) + 1}.20.2023"
        sensitive = "Yes" if i == 2 else ""
        text = "Sensitive information redacted" if sensitive else f"Develop and carry out example plan {i}."
        cost = "594000" if i == 1 else ""
        rows.append(f'"Example Oversight of Program {1 + i % 2}",EX202100{1 + i % 2},0{i}.1{i}.2021,{"FAA" if i % 2 else "ZZTOP"},2021,{i},'
                    f'{"a" if i == 4 else ""},"{text}",{sensitive},,{status},{closed},{cost},,')
    return rows


def dot_csv(**kw):
    return ("﻿" + DOT_HEAD + "\n" + "\n".join(dot_rows(**kw)) + "\n").encode("utf-8")


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def when(day=1, month=3, year=2031):
    return datetime(year, month, day, 6, 0, 0, tzinfo=timezone.utc)


def quiet():
    """Swallow the progress lines the pipeline prints."""
    return contextlib.redirect_stdout(io.StringIO())


class Feed:
    """Stands in for net.fetch_export: hands out what a test set for each publisher."""

    def __init__(self, **files):
        self.files = {k.replace("_", "-"): v for k, v in files.items()}
        self.calls = []

    def __call__(self, source, cfg):
        self.calls.append(source["id"])
        v = self.files.get(source["id"], net.Unreachable("no answer in this test"))
        if isinstance(v, list):                 # a queue: one answer per attempt
            v = v.pop(0) if len(v) > 1 else v[0]
        if isinstance(v, Exception):
            raise v
        return v, {"last-modified": ""}


class TempData:
    """Point the pipeline's data folder at an empty temporary folder for one test."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="auditline-test-")
        self._old = common.DATA_DIR[0]
        common.DATA_DIR[0] = os.path.join(self._tmp, "data")
        self.site = os.path.join(self._tmp, "site")
        self._env = {k: os.environ.pop(k, None) for k in ("SITE_URL", "SITE_INDEXABLE", "GOATCOUNTER_URL", "WATCHLIST_URL", "CLOCK_OFFSET_SECONDS")}

    def tearDown(self):
        common.DATA_DIR[0] = self._old
        shutil.rmtree(self._tmp, ignore_errors=True)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
