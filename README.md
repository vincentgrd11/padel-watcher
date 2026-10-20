# Padel watcher: Regent's Park and Hyde Park

This bot checks the Royal Parks padel booking feed every 5 minutes. When a Mon–Thu slot at 07:00, 08:00, 18:00, 19:00 or 20:00 changes from full to bookable, it sends a push to your phone. Tapping the push opens the booking page.

## Setup (about 10 minutes)

**1. Phone alerts (ntfy)**
- Install the **ntfy** app (iOS App Store / Google Play).
- In the app, tap **+** and subscribe to a topic name that is hard to guess, e.g. `vincent-padel-7f3k9q`. Anyone who knows the name can read the alerts, so don't use something obvious.

**2. GitHub repo**
- Create a free account at github.com if you don't have one.
- Create a new **private** repository, e.g. `padel-watcher`.
- Upload the files from this folder, keeping the paths:
  - `padel_watcher.py`
  - `.github/workflows/padel.yml`
  (GitHub's web uploader hides the `.github` folder. Instead, use **Add file → Create new file** and type `.github/workflows/padel.yml` as the name, then paste in the contents.)

**3. Secret**
- In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**.
- Name: `NTFY_TOPIC`. Value: your topic name from step 1.

**4. Turn it on**
- Go to the **Actions** tab, enable workflows if GitHub asks, open **Padel watcher** and click **Run workflow**.
- The first run sends one push listing every watched slot that is free right now. After that, you only get pushes for slots that newly open.

## Changing what it watches
Edit the CONFIG block at the top of `padel_watcher.py`:
- `WATCH_WEEKDAYS`: Mon=0 … Sun=6
- `WATCH_START_TIMES`: slot start times
- `VENUES`: remove one if you only want one park

## Running it on your laptop instead (optional)
```
NTFY_TOPIC=your-topic python3 padel_watcher.py --loop
```
This checks every 3 minutes while the laptop is awake. It needs Python 3.9+ and has no other dependencies.

## Notes
- GitHub's 5-minute schedule is best-effort, and runs can be a few minutes late at busy times. If cancelled slots are being taken within 1–2 minutes, the laptop `--loop` mode reacts faster.
- New days are released at 07:00 each morning (7 days ahead), so you'll also get a push for any new watched slots in that release.
- GitHub pauses scheduled workflows in repos with no activity for 60 days. This bot commits `state.json` whenever availability changes, which keeps the repo active.
- The bot only alerts you. It doesn't book, so you still book in the app yourself.
