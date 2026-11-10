"""Download each publisher's official export, record what changed since last time, and keep the rest.

  python3 -m auditline.refresh                 # what the weekly job runs
  python3 -m auditline.refresh --only hhs-oig  # one publisher
  python3 -m auditline.refresh --force         # ask again even if a publisher was read in the last few hours
  python3 -m auditline.refresh --check-fresh   # exit 1 if a covered publisher has not been read in time

Each publisher is handled on its own. If one refuses, is unreachable, sends a file that fails the
quality gates, or sends a file that has shrunk implausibly, its last good records stay exactly as
they are and data/status.json records why. Pages always show the date each publisher was last read.

History is append-only. A change of status, date, response, agency, text or dollar figure becomes an
event with the date it was observed. Nothing is ever inferred: an event says only that the
publisher's file differed from the publisher's previous file.
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import timedelta

from . import net, robots, sources
from .common import data_path, iso, load_config, now_utc, parse_iso, read_json, write_json

MAX_EVENTS = 200_000


def recs_path(pid):
    return data_path("recs", f"{pid}.json")


def events_path(pid):
    return data_path("events", f"{pid}.json")


def status_path():
    return data_path("status.json")


def changes_path():
    return data_path("changes.json")


def load_records(pid):
    return (read_json(recs_path(pid), {"records": []}) or {"records": []})["records"]


def write_records(pid, records):
    """One record per line, keys sorted: a status change shows up as a one-line change in the repository."""
    path = recs_path(pid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ",\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in records)
    text = '{"publisher":' + json.dumps(pid) + ',"records":[\n' + lines + "\n]}\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def load_events(pid):
    return (read_json(events_path(pid), {"events": []}) or {"events": []})["events"]


def merge(old_records, new_records, when):
    """Compare a publisher's new file with its previous one.

    Returns (records, events). Records no longer in the file are kept and marked, never deleted.
    """
    stamp = iso(when)
    day = stamp[:10]
    old = {r["id"]: r for r in old_records}
    first_file = not old_records
    out, events = [], []
    for r in new_records:
        prev = old.pop(r["id"], None)
        rec = dict(r)
        rec["in_export"] = True
        if prev is None:
            rec["first_seen"] = day
            if not first_file:
                events.append({"at": stamp, "id": r["id"], "field": "added", "old": "", "new": r["status"]})
        else:
            rec["first_seen"] = prev.get("first_seen", day)
            if not prev.get("in_export", True):
                events.append({"at": stamp, "id": r["id"], "field": "in_export", "old": False, "new": True})
            for field in sources.TRACKED:
                if prev.get(field) != r.get(field):
                    events.append({"at": stamp, "id": r["id"], "field": field, "old": prev.get(field), "new": r.get(field)})
        out.append(rec)
    for rid, prev in old.items():           # in the last file, not in this one
        rec = dict(prev)
        if rec.get("in_export", True):
            rec["in_export"] = False
            rec["gone_since"] = day
            events.append({"at": stamp, "id": rid, "field": "in_export", "old": True, "new": False})
        out.append(rec)
    out.sort(key=lambda r: r["id"])
    return out, events


def refresh_one(source, cfg, now, fetch=net.fetch_export, pause=45):
    """Returns a status dict for this publisher. Raises nothing.

    A publisher that cannot be reached is tried three times, a little apart. A refusal is never retried.
    """
    pid = source["id"]
    st = {"checked_at": iso(now)}
    for attempt in range(3):
        try:
            raw, headers = fetch(source, cfg)
            break
        except net.Refused as e:
            return dict(st, outcome="refused", note=str(e))
        except net.Unreachable as e:
            if attempt == 2:
                return dict(st, outcome="unreachable", note=str(e))
            print(f"{pid}: no answer ({e}); trying again", flush=True)
            time.sleep(pause * (attempt + 1))
        except Exception as e:  # anything unexpected is also "keep what we have"
            traceback.print_exc()
            return dict(st, outcome="unreachable", note=f"{type(e).__name__}: {e}"[:200])
    try:
        new = sources.PARSERS[pid](raw)
    except Exception as e:
        traceback.print_exc()
        return dict(st, outcome="rejected", note=f"could not be parsed: {type(e).__name__}"[:200])
    q = sources.quality(new)
    if not new or min(q.values()) < cfg["min_quality"]:
        return dict(st, outcome="rejected", note="file failed the quality gates: " + ", ".join(f"{k} {v:.0%}" for k, v in q.items()), rows=len(new))
    old = load_records(pid)
    live_before = sum(1 for r in old if r.get("in_export", True))
    if live_before and len(new) < live_before * (1 - cfg["max_shrink"]):
        return dict(st, outcome="rejected", rows=len(new),
                    note=f"file has {len(new):,} recommendations, the last good file had {live_before:,}; kept the last good file")
    records, events = merge(old, new, now)
    write_records(pid, records)
    if events:
        all_events = (load_events(pid) + events)[-MAX_EVENTS:]
        write_json(events_path(pid), {"publisher": pid, "events": all_events}, compact=True)
    counts = {}
    for e in events:
        counts[e["field"]] = counts.get(e["field"], 0) + 1
    return dict(st, outcome="ok", retrieved_at=iso(now), rows=len(new), bytes=len(raw), sha256=sources.digest(raw),
                last_modified=headers.get("last-modified", ""), events=counts, first_file=not old,
                note=f"{len(new):,} recommendations read; {len(events):,} changes recorded")


def verify_links(source, cfg, get=net.get):
    """Check the two kinds of link every page of this publisher carries: its tracker, and a per-report link.

    Three requests at most (robots.txt, the tracker, one report link built the way the pages build them).
    The answer is recorded; if per-report links stop working, pages fall back to the tracker's front page.
    """
    ua = cfg["user_agent"]
    out = {"tracker": "not checked", "report_link": "not checked"}
    recs = [r for r in load_records(source["id"]) if r.get("in_export", True) and r.get("report_url") and r.get("report_number")]
    sample = max(recs, key=lambda r: r["issued"]) if recs else None
    try:
        host = source["tracker"].split("/")[2]
        body, _, status = get(f"https://{host}/robots.txt", ua, "text/plain,*/*;q=0.5", 500_000, timeout=40)
        rules, _ = robots.from_response(status, body.decode("utf-8", "replace") if status == 200 else "")
    except Exception as e:
        return dict(out, tracker=f"robots.txt: {type(e).__name__}"[:80])
    for key, url, needle in (("tracker", source["tracker"], None),
                             ("report_link", sample["report_url"] if sample else "", sample["report_number"] if sample else "")):
        if not url:
            continue
        if not rules.allowed(url, cfg["robots_token"]):
            out[key] = "robots.txt asks automated readers not to open it"
            continue
        try:
            body, _, status = get(url, ua, "text/html,*/*;q=0.5", 6_000_000, timeout=60)
            if status != 200:
                out[key] = f"HTTP {status}"
            elif needle and needle.encode() not in body:
                out[key] = "opened, but the report was not on the page"
            else:
                out[key] = "ok"
        except net.Refused as e:
            out[key] = f"refused ({e})"
        except Exception as e:
            out[key] = f"no answer ({type(e).__name__})"
    return out


def probe_uncovered(cfg, get=net.get):
    """Ask each publisher we do not cover for its robots.txt (the one file meant for automated readers),
    once, so the coverage page can say how it answers today. Nothing else is requested from them."""
    out = {}
    for s in sources.NOT_COVERED:
        host = s["tracker"].split("/")[2]
        try:
            _, _, status = get(f"https://{host}/robots.txt", cfg["user_agent"], "text/plain,*/*;q=0.5", 500_000, timeout=40)
            out[s["short"]] = "answers" if status in (200, 404) else f"HTTP {status}"
        except net.Refused as e:
            out[s["short"]] = f"refuses automated requests ({e})"
        except Exception as e:
            out[s["short"]] = f"no answer ({type(e).__name__})"
    return out


def run(only=None, now=None, fetch=net.fetch_export, probe=True, pause=45, force=False):
    now = now or now_utc()
    cfg = load_config()
    status = read_json(status_path(), {}) or {}
    publishers = status.setdefault("publishers", {})
    run_events = {}
    asked = set()
    for source in sources.COVERED:
        pid = source["id"]
        if only and pid not in only:
            continue
        prev = publishers.get(pid, {})
        last = parse_iso(prev.get("retrieved_at"))
        if not force and prev.get("outcome") == "ok" and last and now - last < timedelta(hours=cfg["min_hours_between_reads"]):
            # A second run soon after a good read (a re-run, a backstop slot) does not ask the publisher again.
            print(f"{pid}: read {prev['retrieved_at']}; not asking again yet", flush=True)
            continue
        asked.add(pid)
        res = refresh_one(source, cfg, now, fetch, pause)
        merged = dict(prev)
        merged.update(checked_at=res["checked_at"], outcome=res["outcome"], note=res.get("note", ""))
        if res["outcome"] == "ok":
            merged.update({k: res[k] for k in ("retrieved_at", "rows", "bytes", "sha256", "last_modified")})
            merged["refused_since"] = ""
            if res["events"] or res["first_file"]:
                merged["last_changed"] = res["retrieved_at"]
            run_events[pid] = res["events"]
        elif not prev.get("refused_since") and res["outcome"] in ("refused", "unreachable"):
            merged["refused_since"] = res["checked_at"]
        publishers[pid] = merged
        print(f"{pid}: {res['outcome']} {res.get('note', '')}", flush=True)
    if probe:
        for source in sources.COVERED:
            pid = source["id"]
            if pid not in asked or publishers.get(pid, {}).get("outcome") != "ok":
                continue
            try:
                publishers[pid]["links"] = dict(verify_links(source, cfg), checked_at=iso(now))
                print(f"{pid}: links {publishers[pid]['links']}", flush=True)
            except Exception:
                traceback.print_exc()
    if probe and not only and asked:
        try:
            status["uncovered"] = {"checked_at": iso(now), "answers": probe_uncovered(cfg)}
        except Exception:
            traceback.print_exc()
    write_json(status_path(), status)
    if any(run_events.values()):
        changes = read_json(changes_path(), {"runs": []}) or {"runs": []}
        changes["runs"].append({"at": iso(now), "publishers": run_events})
        changes["runs"] = changes["runs"][-120:]
        write_json(changes_path(), changes)
    return status


def check_fresh(now=None):
    """Every covered publisher must have been read successfully within the limit."""
    now = now or now_utc()
    cfg = load_config()
    limit = timedelta(days=cfg["stale_after_days"])
    pubs = (read_json(status_path(), {}) or {}).get("publishers", {})
    bad = []
    for s in sources.COVERED:
        st = pubs.get(s["id"], {})
        last = parse_iso(st.get("retrieved_at"))
        if last is None or now - last > limit:
            bad.append(f"{s['short']}: last read {st.get('retrieved_at', 'never')} (limit {limit.days} days); "
                       f"last attempt: {st.get('outcome', 'none')} {st.get('note', '')}")
    for b in bad:
        print("STALE", b)
    return not bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated publisher ids")
    ap.add_argument("--force", action="store_true", help="ask every publisher again even if it was read in the last few hours")
    ap.add_argument("--check-fresh", action="store_true")
    a = ap.parse_args(argv)
    if a.check_fresh:
        return 0 if check_fresh() else 1
    run(only=set(filter(None, a.only.split(","))), force=a.force)
    # The job fails only when there is nothing at all to publish.
    return 0 if any(load_records(s["id"]) for s in sources.COVERED) else 1


if __name__ == "__main__":
    sys.exit(main())
