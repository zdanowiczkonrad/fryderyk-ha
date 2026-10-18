"""Parser tests against synthetic fixtures that mirror the live Fryderyk markup."""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "fryderyk"))

import parsing  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_week_days_and_holiday():
    days = parsing.parse_week(load("plan_week.html"), date(2026, 10, 12))
    assert [d.date for d in days] == [f"2026-10-{n}" for n in range(12, 19)]  # sticky header ignored
    assert days[0].weekday == "Poniedziałek"
    assert days[2].holiday == "Dzień Edukacji Narodowej"
    assert days[5].free and days[6].free
    assert not days[1].lessons


def test_lessons_flags():
    days = parsing.parse_week(load("plan_week.html"), date(2026, 10, 12))
    first, cancelled, individual = days[0].lessons
    assert (first.start, first.end, first.subject, first.group) == ("17:35", "18:20", "kształcenie słuchu", "II B")
    assert first.status == "scheduled" and first.finished
    assert cancelled.cancelled and cancelled.status == "cancelled"
    assert cancelled.flags == ["Lekcja odwołana"]
    assert cancelled.details_url == "/lessons/details/200/2001/mine"
    assert individual.group == "" and not individual.finished


def test_substitution_and_time_padding():
    sub = parsing.parse_week(load("plan_week.html"), date(2026, 10, 12))[3].lessons[0]
    assert sub.substitution and not sub.cancelled and sub.status == "substitution"
    assert (sub.date, sub.start, sub.end) == ("2026-10-15", "09:05", "09:50")


def test_lesson_details():
    d = parsing.parse_lesson_details(load("lesson_details.html"))
    assert d == {"notes": ["Zajęcia zostały odwołane."], "teacher": "Nowak Anna", "room": "Sala 27"}


def test_message_list():
    msgs, pages = parsing.parse_message_list(load("inbox.html"))
    assert pages == 2
    assert [m.id for m in msgs] == ["5666", "5617"]
    assert msgs[0].unread and not msgs[1].unread
    assert msgs[0].title == "Odwołane zajęcia z panią Anną Nowak"  # untruncated variant
    assert msgs[0].author == "Sekretariat Szkoły"


def test_message_body():
    msg = parsing.Message(id="5617", folder="inbox", date="", author="", title="", preview="", unread=False)
    parsing.parse_message_body(load("message.html"), msg)
    assert msg.title == "Odwołane zajęcia"
    assert msg.sent_at == "piątek, 2026-10-09 08:40"
    assert msg.body.splitlines() == [
        "Szanowni Państwo,",
        "zajęcia w dniu 12.10.2026 (poniedziałek) są odwołane.",
        "Z poważaniem",
        "Sekretarz Szkoły",
    ]


def test_empty_and_login_pages():
    assert parsing.parse_week("<html></html>", date(2026, 10, 12)) == []
    assert parsing.parse_announcement_list("") == ([], 1)
    assert parsing.is_login_page('<input name="username"><input name="password">')
