# Fryderyk for Home Assistant

Custom integration (plus a standalone CLI) for **Fryderyk**, the e-journal used by
Polish music schools (`*.fryderyk.edu.pl`). It logs in with the parent/student account
and scrapes the lesson plan, cancelled lessons, messages and announcements.

## What you get

| Entity | State | Attributes |
| --- | --- | --- |
| `calendar.fryderyk_<login>_lessons` | current/next lesson | events: lessons (❌ cancelled, 🔁 substitution, room, teacher) and 🎉 days off |
| `sensor.…_next_lesson` | timestamp of the next lesson that takes place | subject, teacher, room, group |
| `sensor.…_lessons_today` | lessons today, excluding cancelled | `lessons` |
| `sensor.…_cancelled_lessons` | upcoming cancelled + substituted lessons | `lessons`, `days_off` |
| `sensor.…_unread_messages` | unread messages | `messages` (latest 10) |
| `sensor.…_latest_message` | subject of the newest message | id, date, author, preview, unread |
| `sensor.…_announcements` | announcement count | `announcements` |

Bus events for automations (not fired on the first refresh after start-up):

- `fryderyk_lesson_cancelled`: a new cancelled or substituted lesson appeared. Data includes the lesson fields plus `status`.
- `fryderyk_new_message`: a new message appeared in the inbox. Data includes `id, date, author, title, preview, unread`.

The integration **never opens message bodies**, because opening one on the site marks it as read.

## Install

**HACS (custom repository):** HACS → ⋮ → Custom repositories → add this repo as *Integration* → install **Fryderyk** → restart.

**Manual:** copy `custom_components/fryderyk` into `<config>/custom_components/` and restart.

Then: Settings → Devices & services → Add integration → **Fryderyk**. Enter the school address
(e.g. `https://twojaszkola.fryderyk.edu.pl`), login and password.
Options: weeks ahead to fetch (default 2) and the update interval (default 30 min).

### Example automation

```yaml
automation:
  - alias: Fryderyk – lesson cancelled
    triggers:
      - trigger: event
        event_type: fryderyk_lesson_cancelled
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "Lekcja odwołana"
          message: "{{ trigger.event.data.date }} {{ trigger.event.data.start }} {{ trigger.event.data.subject }}"
```

## CLI

`fryderyk.py` uses the same parser and reads `url`, `login` and `password` from `.env`:

```sh
./fryderyk.py status
./fryderyk.py schedule -d 2026-10-19 --details
./fryderyk.py cancelled -w 4
./fryderyk.py messages -u            # list only; `message <id>` / `-b` marks messages as read
```

## Development

`./scripts/check.sh` runs ruff, the parser tests and the Home Assistant tests (needs `uv`).
See `AISDLC.md` for how work on this repo is run.
