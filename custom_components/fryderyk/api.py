"""Async client for the Fryderyk e-journal web UI (scrapes the same endpoints the site's JS uses)."""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from urllib.parse import urlsplit

import aiohttp

from .parsing import (
    Announcement,
    Day,
    Message,
    is_login_page,
    parse_announcement_list,
    parse_lesson_details,
    parse_message_body,
    parse_message_list,
    parse_week,
    week_monday,
)

AJAX = {"X-Requested-With": "XMLHttpRequest"}
TIMEOUT = aiohttp.ClientTimeout(total=30)


class FryderykError(Exception):
    """Base error."""


class FryderykAuthError(FryderykError):
    """Login rejected."""


class FryderykConnectionError(FryderykError):
    """Site unreachable or returned an error."""


def base_url(url: str) -> str:
    """Accept 'host', 'https://host' or 'https://host/users/login'; return 'https://host'."""
    if "://" not in url:
        url = f"https://{url}"
    parts = urlsplit(url.strip())
    return f"{parts.scheme}://{parts.netloc}"


class FryderykApi:
    def __init__(self, session: aiohttp.ClientSession, url: str, username: str, password: str) -> None:
        self._session = session
        self.base = base_url(url)
        self._username = username
        self._password = password
        self._logged_in = False
        self._lock = asyncio.Lock()

    async def login(self) -> None:
        try:
            async with self._session.post(
                f"{self.base}/users/login",
                data={"_method": "POST", "username": self._username, "password": self._password},
                timeout=TIMEOUT,
            ) as r:
                r.raise_for_status()
                html = await r.text()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise FryderykConnectionError(str(err)) from err
        # a failed login re-renders the login form
        if is_login_page(html):
            raise FryderykAuthError("Invalid username or password")
        self._logged_in = True

    async def _get(self, path: str, ajax: bool = False) -> str:
        """GET with a transparent re-login when the session has expired."""
        async with self._lock:
            if not self._logged_in:
                await self.login()
        for attempt in (1, 2):
            try:
                async with self._session.get(self.base + path, headers=AJAX if ajax else None, timeout=TIMEOUT) as r:
                    if r.status in (401, 403) or "/users/login" in str(r.url):
                        expired = True
                    else:
                        r.raise_for_status()
                        html = await r.text()
                        expired = not ajax and is_login_page(html)
            except (TimeoutError, aiohttp.ClientError) as err:
                raise FryderykConnectionError(f"{path}: {err}") from err
            if not expired:
                return html
            if attempt == 2:
                raise FryderykAuthError("Session expired and re-login did not help")
            async with self._lock:
                self._logged_in = False
                await self.login()
        raise AssertionError("unreachable")

    async def week(self, any_day: date) -> list[Day]:
        monday = week_monday(any_day)
        return parse_week(await self._get(f"/plans/mine/{monday.isoformat()}"), monday)

    async def weeks(self, start: date, count: int) -> list[Day]:
        monday = week_monday(start)
        results = await asyncio.gather(*(self.week(monday + timedelta(weeks=i)) for i in range(count)))
        return [d for days in results for d in days]

    async def lesson_details(self, details_url: str) -> dict:
        return parse_lesson_details(await self._get(details_url, ajax=True))

    async def messages(self, folder: str = "inbox", page: int = 1) -> tuple[list[Message], int]:
        return parse_message_list(await self._get(f"/messages/get-messages/{folder}/{page}", ajax=True))

    async def message_body(self, msg: Message) -> Message:
        """NOTE: opening a message on the server marks it as read."""
        parse_message_body(await self._get(f"/messages/show-message/{msg.id}/{msg.folder or 'inbox'}", ajax=True), msg)
        return msg

    async def announcements(self, page: int = 1) -> tuple[list[Announcement], int]:
        return parse_announcement_list(await self._get(f"/announcements/get-announcements/{page}", ajax=True))

    async def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for key, path in (
            ("unread_messages", "/app/messages-check/"),
            ("announcements", "/app/announcements-count/"),
            ("homeworks", "/app/homeworks-count/"),
            ("substitutions", "/app/substitutions-count/"),
        ):
            try:
                data = json.loads(await self._get(path, ajax=True) or "{}")
                out[key] = int(data.get("unread", data.get("count", 0)))
            except (ValueError, AttributeError):
                out[key] = 0
        return out
