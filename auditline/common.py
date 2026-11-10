"""Shared helpers: paths, config, time, JSON files, text."""
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = [os.path.join(ROOT, "data")]   # a one-item list so tests can point the pipeline at a temporary folder
CONFIG = os.path.join(ROOT, "config", "site.json")


def data_path(*parts):
    return os.path.join(DATA_DIR[0], *parts)


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def site_url(cfg=None):
    """The one base-URL setting: env SITE_URL (a repository variable in the workflows) or the config default."""
    cfg = cfg or load_config()
    return (os.environ.get("SITE_URL") or cfg["default_url"]).rstrip("/")


def indexable(cfg=None):
    """Staged copies are not indexable. SITE_INDEXABLE=true|false overrides the config."""
    cfg = cfg or load_config()
    env = os.environ.get("SITE_INDEXABLE", "").strip().lower()
    if env in ("true", "false"):
        return env == "true"
    return bool(cfg.get("indexable", False))


def now_utc():
    """Current UTC time. CLOCK_OFFSET_SECONDS (a development aid) is subtracted, for a machine whose clock runs fast."""
    skew = int(os.environ.get("CLOCK_OFFSET_SECONDS", "0") or 0)
    return datetime.fromtimestamp(time.time() - skew, timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def human_date(d):
    """'November 15, 2021' from a date, datetime or 'YYYY-MM-DD...' string; '' when there is none."""
    if not d:
        return ""
    if isinstance(d, str):
        d = parse_iso(d if "T" in d else d[:10] + "T00:00:00Z")
        if d is None:
            return ""
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def short_date(d):
    if not d:
        return ""
    if isinstance(d, str):
        d = parse_iso(d if "T" in d else d[:10] + "T00:00:00Z")
        if d is None:
            return ""
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, obj, compact=False):
    """Write JSON atomically, and only when the content changed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if compact:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except FileNotFoundError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return True


def slugify(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def money(x):
    """$5.4 million / $812,000. None -> ''."""
    if x is None:
        return ""
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e9:
        return f"{sign}${x / 1e9:.2f} billion"
    if x >= 1e6:
        return f"{sign}${x / 1e6:.1f} million"
    return f"{sign}${x:,.0f}"


def clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"
