#!/usr/bin/env python3
"""Padel slot watcher - Royal Parks (Regent's Park + Hyde Park).
Sends an ntfy push when a watched slot goes from full to bookable."""

import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------- CONFIG ----------------
VENUES = {
    "the-regents-park-courts": "Regent's Park",
    "hyde-park-courts": "Hyde Park",
}
WATCH_WEEKDAYS = {5, 6}      # Mon=0 ... Sun=6 -> Saturday & Sunday
WATCH_START_TIMES = None     # None = any time; or e.g. {"10:00", "11:00"}
DAYS_AHEAD = 8               # booking window is 7 days ahead
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
STATE_FILE = Path(__file__).with_name("state.json")
# ----------------------------------------

API = "https://flow.onl/api/activities/venue/{venue}/activity/padel/v2/times?date={d}"
BOOK_URL = "https://sportsandleisureroyalparks.bookings.flow.onl/location/{venue}/padel/{d}/by-time"
LONDON = ZoneInfo("Europe/London")
UA = "Mozilla/5.0 (personal padel availability watcher)"


def fetch_slots(venue, d):
    req = urllib.request.Request(API.format(venue=venue, d=d.isoformat()),
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("data", []) or []


def main():
    now = datetime.now(LONDON)
    try:
        previous = set(json.loads(STATE_FILE.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        previous = set()

    avail, failed = {}, []
    for i in range(DAYS_AHEAD):
        d = now.date() + timedelta(days=i)
        if d.weekday() not in WATCH_WEEKDAYS:
            continue
        for venue, name in VENUES.items():
            try:
                slots = fetch_slots(venue, d)
            except Exception as e:
                print(f"WARN {name} {d}: {e}", file=sys.stderr)
                failed.append(f"{venue}|{d.isoformat()}|")
                continue
            for s in slots:
                start = (s.get("starts_at") or {}).get("format_24_hour")
                if WATCH_START_TIMES is not None and start not in WATCH_START_TIMES:
                    continue
                if (s.get("action_to_show") or {}).get("status") != "BOOK" or not s.get("spaces"):
                    continue
                if s.get("timestamp") and datetime.fromtimestamp(s["timestamp"], LONDON) <= now:
                    continue
                avail[f"{venue}|{d.isoformat()}|{start}"] = {
                    "venue": venue, "name": name, "date": d.isoformat(), "start": start,
                    "end": (s.get("ends_at") or {}).get("format_24_hour"),
                }
            time.sleep(0.5)

    keep = {k for k in previous if any(k.startswith(f) for f in failed)}
    new = [avail[k] for k in sorted(set(avail) - previous)]
    print(f"[{now:%Y-%m-%d %H:%M}] free: {len(avail)}, newly opened: {len(new)}")

    if new:
        new.sort(key=lambda x: (x["date"], x["start"], x["name"]))
        body = "\n".join(
            f"{x['name']} · {date.fromisoformat(x['date']).strftime('%a %d %b')} · {x['start']}–{x['end']}"
            for x in new)
        title = f"Padel: {len(new)} slot{'s' if len(new) > 1 else ''} just opened"
        print(title + "\n" + body)
        if NTFY_TOPIC:
            req = urllib.request.Request(
                f"https://ntfy.sh/{NTFY_TOPIC}", data=body.encode("utf-8"), method="POST",
                headers={"Title": title, "Priority": "high", "Tags": "tennis",
                         "Click": BOOK_URL.format(venue=new[0]["venue"], d=new[0]["date"])})
            urllib.request.urlopen(req, timeout=20).read()
        else:
            print("NTFY_TOPIC not set - no push sent", file=sys.stderr)

    STATE_FILE.write_text(json.dumps(sorted(set(avail) | keep), indent=1) + "\n")


if __name__ == "__main__":
    main()
