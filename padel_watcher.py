#!/usr/bin/env python3
"""
Padel slot watcher — Royal Parks courts (Regent's Park + Hyde Park).

Polls the public availability feed of the Flow booking system used by
sportsandleisureroyalparks.bookings.flow.onl and sends a phone push (ntfy)
whenever a slot you care about goes from "full" to "bookable".

Standard library only — no pip install needed.

Usage:
  python padel_watcher.py            # one check (used by GitHub Actions)
  python padel_watcher.py --loop     # check every POLL_MINUTES, forever (laptop mode)
  python padel_watcher.py --dry-run  # print what would be sent, no push, no state saved
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ----------------------------------------------------------------------------
# CONFIG — edit freely
# ----------------------------------------------------------------------------
VENUES = {
    "the-regents-park-courts": "Regent's Park",
    "hyde-park-courts": "Hyde Park",
}

# Weekdays to watch: Monday=0 ... Sunday=6
WATCH_WEEKDAYS = {5, 6}  # Saturday & Sunday

# Slot START times to watch (24h, "HH:MM"). 60-min slots.
# None = any time of day. To narrow, e.g.: {"09:00", "10:00", "11:00"}
WATCH_START_TIMES = None

DAYS_AHEAD = 8          # booking window is 7 days ahead; 8 covers the 7am release
POLL_MINUTES = 3        # only used in --loop mode
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")  # set as a secret / env var
STATE_FILE = Path(os.environ.get("STATE_FILE", Path(__file__).with_name("state.json")))
# Alert for slots that are already free the very first time the bot runs?
ALERT_ON_FIRST_RUN = True
# ----------------------------------------------------------------------------

API = "https://flow.onl/api/activities/venue/{venue}/activity/padel/v2/times?date={d}"
BOOK_URL = ("https://sportsandleisureroyalparks.bookings.flow.onl/location/"
            "{venue}/padel/{d}/by-time")
LONDON = ZoneInfo("Europe/London")
UA = "Mozilla/5.0 (personal padel availability watcher; polite polling)"


def fetch_slots(venue: str, d: date) -> list[dict]:
    req = urllib.request.Request(
        API.format(venue=venue, d=d.isoformat()),
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("data", []) or []


def dates_to_check(today: date) -> list[date]:
    return [today + timedelta(days=i) for i in range(DAYS_AHEAD)
            if (today + timedelta(days=i)).weekday() in WATCH_WEEKDAYS]


def is_bookable(slot: dict) -> bool:
    status = (slot.get("action_to_show") or {}).get("status")
    return status == "BOOK" and (slot.get("spaces") or 0) > 0


def current_availability(now: datetime) -> tuple[dict, list[str]]:
    """Return ({key: info}, errors) for watched slots that are bookable now."""
    avail, errors = {}, []
    for d in dates_to_check(now.date()):
        for venue, venue_name in VENUES.items():
            try:
                slots = fetch_slots(venue, d)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                errors.append(f"{venue_name} {d}: {e}")
                continue
            for s in slots:
                start = (s.get("starts_at") or {}).get("format_24_hour")
                 if WATCH_START_TIMES is not None and start not in WATCH_START_TIMES:
                    continue
                if not is_bookable(s):
                    continue
                # Skip slots that have already started
                ts = s.get("timestamp")
                if ts and datetime.fromtimestamp(ts, LONDON) <= now:
                    continue
                key = f"{venue}|{d.isoformat()}|{start}"
                avail[key] = {
                    "venue": venue,
                    "venue_name": venue_name,
                    "date": d.isoformat(),
                    "start": start,
                    "end": (s.get("ends_at") or {}).get("format_24_hour"),
                    "court": s.get("location"),
                    "spaces": s.get("spaces"),
                }
            time.sleep(0.5)  # be gentle with the server
    return avail, errors


def load_state() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return {}


def save_state(avail: dict) -> None:
    STATE_FILE.write_text(json.dumps(sorted(avail.keys()), indent=1) + "\n")


def format_line(info: dict) -> str:
    d = date.fromisoformat(info["date"])
    court = f" ({info['court']})" if info.get("court") and info["court"] != "Multiple" else ""
    return f"{info['venue_name']} · {d.strftime('%a %d %b')} · {info['start']}–{info['end']}{court}"


def notify(new: list[dict], dry_run: bool) -> None:
    new.sort(key=lambda i: (i["date"], i["start"], i["venue_name"]))
    body = "\n".join(format_line(i) for i in new)
    title = f"Padel: {len(new)} slot{'s' if len(new) > 1 else ''} just opened"
    first = new[0]
    click = BOOK_URL.format(venue=first["venue"], d=first["date"])

    print(f"{title}\n{body}\n-> {click}")
    if dry_run:
        return
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set — skipping push.", file=sys.stderr)
        return
    req = urllib.request.Request(
        f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "high",
            "Tags": "tennis",
            "Click": click,
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=20).read()


def run_once(dry_run: bool = False) -> int:
    now = datetime.now(LONDON)
    previous = load_state()
    avail, errors = current_availability(now)

    for e in errors:
        print(f"WARN fetch failed: {e}", file=sys.stderr)

    if previous is None:
        new_keys = set(avail) if ALERT_ON_FIRST_RUN else set()
    else:
        new_keys = set(avail) - set(previous)

    print(f"[{now:%Y-%m-%d %H:%M}] watched slots free: {len(avail)}, newly opened: {len(new_keys)}")
    if new_keys:
        notify([avail[k] for k in new_keys], dry_run)

    # If every request failed, keep the old state so we don't re-alert later.
    if not dry_run and not (errors and not avail and previous):
        save_state(avail)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--loop", action="store_true", help="poll forever (laptop mode)")
    p.add_argument("--dry-run", action="store_true", help="no push, no state saved")
    a = p.parse_args()
    if not a.loop:
        return run_once(a.dry_run)
    while True:
        try:
            run_once(a.dry_run)
        except Exception as e:  # keep the loop alive
            print(f"ERROR: {e}", file=sys.stderr)
        time.sleep(POLL_MINUTES * 60)


if __name__ == "__main__":
    sys.exit(main())
