"""HTML parsing for the Fryderyk e-journal.

Pure functions with no Home Assistant imports, shared by the integration,
the standalone CLI (fryderyk.py) and the tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from bs4 import BeautifulSoup, Tag

# Lesson icon tooltips that carry no extra information beyond the CSS flags.
ROUTINE_FLAGS = ("Lekcja indywidualna", "Lekcja odwołana")
ROUTINE_NOTES = ("Zajęcia zostały odwołane.",)


@dataclass
class Lesson:
    date: str  # ISO date
    start: str  # HH:MM
    end: str  # HH:MM
    subject: str
    group: str = ""
    cancelled: bool = False
    substitution: bool = False
    finished: bool = False
    flags: list[str] = field(default_factory=list)  # icon tooltips, e.g. "Lekcja odwołana"
    details_url: str = ""
    teacher: str = ""
    room: str = ""
    notes: list[str] = field(default_factory=list)  # alert texts from lesson details

    @property
    def key(self) -> str:
        """Stable identity of a lesson occurrence."""
        return self.details_url or f"{self.date}T{self.start}/{self.subject}"

    @property
    def status(self) -> str:
        if self.cancelled:
            return "cancelled"
        if self.substitution:
            return "substitution"
        return "scheduled"


@dataclass
class Day:
    date: str
    weekday: str
    holiday: str = ""
    free: bool = False
    lessons: list[Lesson] = field(default_factory=list)


@dataclass
class Message:
    id: str
    folder: str
    date: str
    author: str
    title: str
    preview: str
    unread: bool
    body: str | None = None
    sent_at: str | None = None


@dataclass
class Announcement:
    id: str
    date: str
    author: str
    title: str
    unread: bool
    body: str | None = None


def text(el: Tag | None) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def html_to_text(el: Tag) -> str:
    for br in el.find_all("br"):
        br.replace_with("\n")
    for p in el.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4"]):
        p.insert_after("\n")
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in el.get_text().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def is_login_page(html: str) -> bool:
    return 'name="password"' in html and 'name="username"' in html


def _total_pages(soup: BeautifulSoup) -> int:
    pager = soup.select_one(".pager[data-total_pages]")
    try:
        return int(pager["data-total_pages"]) if pager else 1
    except (KeyError, ValueError):
        return 1


def parse_week(html: str, monday: date) -> list[Day]:
    """Parse /plans/mine/<date>, which shows the Mon–Sun week containing <date>."""
    soup = BeautifulSoup(html, "html.parser")
    plan = soup.select_one("#plan")
    if not plan:
        return []
    days: list[Day] = []
    # direct children only: the sticky header duplicates the .day nodes
    for i, d in enumerate(plan.find_all("div", class_="day", recursive=False)):
        cls = d.get("class", [])
        title = text(d.select_one("header .title")).replace("Plan zajęć dnia:", "").strip()
        day = Day(
            date=(monday + timedelta(days=i)).isoformat(),
            weekday=title.split(" ")[-1] if title else "",
            holiday=text(d.select_one("header .short-desc")) if "holiday" in cls else "",
            free="free" in cls,
        )
        for les in d.find_all("div", class_="lesson", recursive=False):
            day.lessons.append(_parse_lesson(les, day.date))
        days.append(day)
    return days


def _parse_lesson(les: Tag, fallback_date: str) -> Lesson:
    lcls = les.get("class", [])
    block = les.select_one(".block") or les
    sr = text(les.select_one(".sr-only"))
    m_day = re.search(r"Dzień:\s*(\d{2})-(\d{2})-(\d{4})", sr)
    m_time = re.search(r"Godzina:\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", sr)
    if m_time:
        start, end = m_time[1], m_time[2]
    else:
        m = re.search(r"start-(\d+)-(\d+)", " ".join(lcls))
        start, end = (f"{int(m[1]):02d}:{m[2]}" if m else ""), ""
    return Lesson(
        date=f"{m_day[3]}-{m_day[2]}-{m_day[1]}" if m_day else fallback_date,
        start=start.zfill(5),
        end=end.zfill(5) if end else "",
        subject=text(les.select_one(".text a")),
        group=text(les.select_one(".text small")),
        cancelled="canceled" in lcls or "cancelled" in lcls,
        substitution="substitution" in lcls,
        finished="finished" in block.get("class", []),
        flags=[s["title"] for s in les.select("span.icon[title]")],
        details_url=block.get("data-url", ""),
    )


def parse_lesson_details(html: str) -> dict:
    """Parse the /lessons/details/... tooltip fragment: teacher, room, alert notes."""
    soup = BeautifulSoup(html, "html.parser")
    out = {
        "notes": [text(a) for a in soup.select(".alert .alert-content") if text(a)],
        "teacher": "",
        "room": "",
    }
    if t := soup.select_one(".teacher"):
        for a in t.find_all("a"):
            a.decompose()
        out["teacher"] = text(t).removeprefix("Nauczyciel:").strip()
    for div in soup.select(".section div"):
        s = text(div)
        if s.startswith("Sala:"):
            out["room"] = s.removeprefix("Sala:").strip()
    return out


def apply_details(lesson: Lesson, details: dict) -> None:
    lesson.teacher = details.get("teacher", "")
    lesson.room = details.get("room", "")
    lesson.notes = list(details.get("notes", []))


def parse_message_list(html: str) -> tuple[list[Message], int]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for m in soup.select('[data-role="message"][data-message-id]'):
        # the "visible-sm" spans carry the longest (least truncated) variant
        title = m.select_one(".title .visible-sm") or m.select_one(".title")
        prev = m.select_one(".text .visible-sm") or m.select_one(".text")
        out.append(
            Message(
                id=m["data-message-id"],
                folder=m.get("data-message-type", ""),
                date=text(m.select_one(".date")),
                author=text(m.select_one(".author")),
                title=text(title),
                preview=text(prev),
                unread="not-read" in m.get("class", []),
            )
        )
    return out, _total_pages(soup)


def parse_message_body(html: str, msg: Message) -> None:
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one("[data-message-content] .message")
    if not box:
        return
    msg.sent_at = text(box.select_one(".date"))
    if t := box.find("div", class_="title", recursive=False):
        msg.title = text(t).removeprefix("Temat:").strip() or msg.title
    body = box.find("div", class_="text", recursive=False)
    msg.body = html_to_text(body) if body else ""


def parse_announcement_list(html: str) -> tuple[list[Announcement], int]:
    # Markup inferred from the site's JS (no live sample seen yet); parsed defensively.
    soup = BeautifulSoup(html, "html.parser")
    out = [
        Announcement(
            id=a["data-announcement-id"],
            date=text(a.select_one(".date")),
            author=text(a.select_one(".author")),
            title=text(a.select_one(".title .visible-sm") or a.select_one(".title")),
            unread=bool(a.select_one(".badge-success")) or "not-read" in a.get("class", []),
        )
        for a in soup.select("[data-announcement-id]")
    ]
    return out, _total_pages(soup)


def parse_announcement_body(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return html_to_text(soup.select_one(".message .text") or soup)
