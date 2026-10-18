#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "beautifulsoup4>=4.12"]
# ///
"""CLI for the Fryderyk e-journal (fryderyk.edu.pl): schedule, cancelled lessons, messages."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent / "custom_components" / "fryderyk"))
from parsing import (  # noqa: E402  (shared with the Home Assistant integration)
    ROUTINE_FLAGS,
    ROUTINE_NOTES,
    Day,
    Lesson,
    Message,
    apply_details,
    parse_announcement_body,
    parse_announcement_list,
    parse_lesson_details,
    parse_message_body,
    parse_message_list,
    parse_week,
    week_monday,
)

AJAX = {"X-Requested-With": "XMLHttpRequest"}


# --------------------------------------------------------------------------- config


def load_env() -> dict[str, str]:
    """Read .env from the CWD or next to this script; real env vars win."""
    env: dict[str, str] = {}
    for p in (Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"):
        if p.is_file():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip().lower()] = v.strip().strip("'\"")
            break
    for key in ("url", "login", "password"):
        if v := os.environ.get(f"FRYDERYK_{key.upper()}"):
            env[key] = v
    missing = [k for k in ("url", "login", "password") if not env.get(k)]
    if missing:
        sys.exit(f"error: missing {', '.join(missing)} in .env (or FRYDERYK_* env vars)")
    return env


# --------------------------------------------------------------------------- client


class Fryderyk:
    def __init__(self, url: str, login: str, password: str):
        parts = urlsplit(url)
        self.base = f"{parts.scheme}://{parts.netloc}"
        self.login_url = url if parts.path.strip("/") else f"{self.base}/users/login"
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "fryderyk-cli/1.0"
        self._login(login, password)

    def _login(self, login: str, password: str) -> None:
        r = self.s.post(
            self.login_url,
            data={"_method": "POST", "username": login, "password": password},
            timeout=30,
        )
        r.raise_for_status()
        if "/users/login" in r.url or 'name="password"' in r.text:
            sys.exit("error: login failed (check login/password in .env)")

    def get(self, path: str, ajax: bool = False) -> str:
        r = self.s.get(self.base + path, headers=AJAX if ajax else None, timeout=30)
        r.raise_for_status()
        return r.text

    def counts(self) -> dict[str, int]:
        out = {}
        for key, path in [
            ("unread_messages", "/app/messages-check/"),
            ("announcements", "/app/announcements-count/"),
            ("homeworks", "/app/homeworks-count/"),
            ("substitutions", "/app/substitutions-count/"),
        ]:
            try:
                data = json.loads(self.get(path, ajax=True) or "{}")
                out[key] = int(data.get("unread", data.get("count", 0)))
            except (ValueError, requests.RequestException):
                out[key] = 0
        return out


# --------------------------------------------------------------------------- fetching


def fetch_details(client: Fryderyk, lesson: Lesson) -> None:
    if lesson.details_url:
        apply_details(lesson, parse_lesson_details(client.get(lesson.details_url, ajax=True)))


def fetch_schedule(client: Fryderyk, start: date, weeks: int) -> list[Day]:
    days: list[Day] = []
    monday = week_monday(start)
    for w in range(weeks):
        m = monday + timedelta(weeks=w)
        # the plan page shows the Mon–Sun week containing the given date
        days += parse_week(client.get(f"/plans/mine/{m.isoformat()}"), m)
    return days


def fetch_messages(client: Fryderyk, folder: str, pages: int) -> list[Message]:
    msgs: list[Message] = []
    page, total = 1, 1
    while page <= min(total, pages):
        batch, total = parse_message_list(client.get(f"/messages/get-messages/{folder}/{page}", ajax=True))
        msgs += batch
        page += 1
    return msgs


def fetch_message_body(client: Fryderyk, msg: Message) -> None:
    """NOTE: opening a message on the server marks it as read."""
    parse_message_body(client.get(f"/messages/show-message/{msg.id}/{msg.folder or 'inbox'}", ajax=True), msg)


def fetch_announcements(client: Fryderyk, pages: int, with_body: bool) -> list[dict]:
    out: list[dict] = []
    page, total = 1, 1
    while page <= min(total, pages):
        batch, total = parse_announcement_list(client.get(f"/announcements/get-announcements/{page}", ajax=True))
        for a in batch:
            if with_body:
                a.body = parse_announcement_body(client.get(f"/announcements/show-announcement/{a.id}", ajax=True))
            item = asdict(a)
            if not with_body:
                item.pop("body")
            out.append(item)
        page += 1
    return out


# --------------------------------------------------------------------------- output


def dump_json(obj) -> None:
    def conv(o):
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
        raise TypeError(type(o))

    print(json.dumps(obj, default=conv, ensure_ascii=False, indent=2))


def lesson_line(l: Lesson, with_date: bool = False) -> str:
    status = "CANCELLED" if l.cancelled else ("SUBSTITUTION" if l.substitution else "")
    parts = [f"{l.date} " if with_date else "", f"{l.start}-{l.end}  {l.subject}"]
    if l.group:
        parts.append(f" [{l.group}]")
    if l.teacher or l.room:
        parts.append(f"  ({', '.join(x for x in (l.teacher, l.room) if x)})")
    if status:
        parts.append(f"  ** {status} **")
    extra = [f for f in l.flags if f not in ROUTINE_FLAGS]
    extra += [n for n in l.notes if n not in ROUTINE_NOTES]
    if extra:
        parts.append(f"  — {'; '.join(extra)}")
    return "".join(parts)


def print_schedule(days: list[Day]) -> None:
    for d in days:
        head = f"{d.date} {d.weekday}"
        if d.holiday:
            head += f"  [{d.holiday}]"
        print(head)
        for l in d.lessons:
            print("  " + lesson_line(l))
        if not d.lessons and not d.holiday:
            print("  —")


def print_messages(msgs: list[Message]) -> None:
    for m in msgs:
        mark = "●" if m.unread else " "
        print(f"{mark} {m.id:>6}  {m.date}  {m.author:<24.24}  {m.title}")
        if m.body is not None:
            print(f"\n    Sent: {m.sent_at}\n")
            print("\n".join("    " + ln for ln in m.body.splitlines()))
            print()


# --------------------------------------------------------------------------- commands


def parse_date(s: str) -> date:
    if s in ("today", "now"):
        return date.today()
    return datetime.strptime(s, "%Y-%m-%d").date()


def cmd_schedule(c: Fryderyk, a) -> None:
    days = fetch_schedule(c, a.date, a.weeks)
    if a.details:
        for d in days:
            for l in d.lessons:
                fetch_details(c, l)
    dump_json(days) if a.json else print_schedule(days)


def cmd_cancelled(c: Fryderyk, a) -> None:
    days = fetch_schedule(c, a.date, a.weeks)
    hits = [l for d in days for l in d.lessons if l.cancelled or l.substitution]
    if not a.past:
        today = date.today().isoformat()
        hits = [l for l in hits if l.date >= today]
    for l in hits:
        fetch_details(c, l)
    holidays = [{"date": d.date, "weekday": d.weekday, "name": d.holiday} for d in days if d.holiday]
    if not a.past:
        holidays = [h for h in holidays if h["date"] >= date.today().isoformat()]
    if a.json:
        dump_json({"lessons": hits, "holidays": holidays})
        return
    if not hits and not holidays:
        print("No cancelled lessons or substitutions.")
    for l in hits:
        print(lesson_line(l, with_date=True))
    if holidays:
        print("\nDays off:")
        for h in holidays:
            print(f"  {h['date']} {h['weekday']}  {h['name']}")


def cmd_messages(c: Fryderyk, a) -> None:
    msgs = fetch_messages(c, a.folder, a.pages)
    if a.unread:
        msgs = [m for m in msgs if m.unread]
    if a.grep:
        rx = re.compile(a.grep, re.I)
        msgs = [m for m in msgs if rx.search(m.title) or rx.search(m.preview)]
    msgs = msgs[: a.limit] if a.limit else msgs
    if a.body:
        for m in msgs:
            fetch_message_body(c, m)
    dump_json(msgs) if a.json else print_messages(msgs)


def cmd_message(c: Fryderyk, a) -> None:
    m = Message(id=str(a.id), folder=a.folder, date="", author="", title="", preview="", unread=False)
    fetch_message_body(c, m)
    if m.body is None:
        sys.exit(f"error: message {a.id} not found in {a.folder}")
    if a.json:
        dump_json(m)
    else:
        print(f"Subject: {m.title}\nSent:    {m.sent_at}\n\n{m.body}")


def cmd_announcements(c: Fryderyk, a) -> None:
    items = fetch_announcements(c, a.pages, a.body)
    if a.json:
        dump_json(items)
        return
    if not items:
        print("No announcements.")
    for i in items:
        print(f"{'●' if i['unread'] else ' '} {i['id']:>6}  {i['date']}  {i['author']:<24.24}  {i['title']}")
        if "body" in i:
            print("\n".join("    " + ln for ln in i["body"].splitlines()) + "\n")


def cmd_status(c: Fryderyk, a) -> None:
    counts = c.counts()
    dump_json(counts) if a.json else print("\n".join(f"{k:<16} {v}" for k, v in counts.items()))


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="output JSON")
    p = argparse.ArgumentParser(prog="fryderyk", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def week_args(sp, default_weeks):
        sp.add_argument(
            "-d",
            "--date",
            type=parse_date,
            default=date.today(),
            help="any date in the first week (YYYY-MM-DD, default today)",
        )
        sp.add_argument(
            "-w", "--weeks", type=int, default=default_weeks, help=f"number of weeks (default {default_weeks})"
        )

    sp = sub.add_parser("schedule", parents=[common], aliases=["plan"], help="weekly lesson plan")
    week_args(sp, 1)
    sp.add_argument("--details", action="store_true", help="fetch teacher/room per lesson (1 request each)")
    sp.set_defaults(func=cmd_schedule)

    sp = sub.add_parser(
        "cancelled", parents=[common], aliases=["canceled"], help="cancelled lessons / substitutions + days off"
    )
    week_args(sp, 2)
    sp.add_argument("--past", action="store_true", help="include past entries in the range")
    sp.set_defaults(func=cmd_cancelled)

    sp = sub.add_parser("messages", parents=[common], aliases=["msgs"], help="list messages")
    sp.add_argument("-f", "--folder", choices=["inbox", "sent", "trash"], default="inbox")
    sp.add_argument("-p", "--pages", type=int, default=1, help="list pages to fetch (default 1)")
    sp.add_argument("-n", "--limit", type=int, default=0, help="max messages to show")
    sp.add_argument("-u", "--unread", action="store_true", help="only unread")
    sp.add_argument("-g", "--grep", help="regex filter on subject/preview")
    sp.add_argument("-b", "--body", action="store_true", help="fetch full bodies (marks them as read!)")
    sp.set_defaults(func=cmd_messages)

    sp = sub.add_parser("message", parents=[common], aliases=["read"], help="show one message (marks it as read)")
    sp.add_argument("id", type=int)
    sp.add_argument("-f", "--folder", choices=["inbox", "sent", "trash"], default="inbox")
    sp.set_defaults(func=cmd_message)

    sp = sub.add_parser("announcements", parents=[common], aliases=["ann"], help="list announcements")
    sp.add_argument("-p", "--pages", type=int, default=1)
    sp.add_argument("-b", "--body", action="store_true", help="fetch full text")
    sp.set_defaults(func=cmd_announcements)

    sp = sub.add_parser("status", parents=[common], help="unread/new counters")
    sp.set_defaults(func=cmd_status)

    a = p.parse_args()
    env = load_env()
    a.func(Fryderyk(env["url"], env["login"], env["password"]), a)


if __name__ == "__main__":
    main()
