"""Polling coordinator for Fryderyk."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FryderykApi, FryderykAuthError, FryderykError
from .const import (
    CONF_SCAN_MINUTES,
    CONF_WEEKS,
    DEFAULT_SCAN_MINUTES,
    DEFAULT_WEEKS,
    DOMAIN,
    EVENT_LESSON_CANCELLED,
    EVENT_NEW_MESSAGE,
)
from .parsing import Announcement, Day, Lesson, Message, apply_details

_LOGGER = logging.getLogger(__name__)

type FryderykConfigEntry = ConfigEntry[FryderykCoordinator]


@dataclass
class FryderykData:
    days: list[Day] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    announcements: list[Announcement] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def lessons(self) -> list[Lesson]:
        return [les for d in self.days for les in d.lessons]

    def upcoming(self, now: datetime) -> list[Lesson]:
        """Lessons that have not ended yet, in order."""
        return [les for les in self.lessons if lesson_end(les) > now]


def lesson_start(les: Lesson) -> datetime:
    return _at(les.date, les.start)


def lesson_end(les: Lesson) -> datetime:
    return _at(les.date, les.end or les.start)


def _at(day: str, hhmm: str) -> datetime:
    h, m = (int(x) for x in (hhmm or "00:00").split(":"))
    d = date.fromisoformat(day)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=dt_util.get_default_time_zone())


def lesson_dict(les: Lesson) -> dict:
    out = asdict(les)
    out["status"] = les.status
    out.pop("details_url", None)
    return out


class FryderykCoordinator(DataUpdateCoordinator[FryderykData]):
    config_entry: FryderykConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FryderykConfigEntry, api: FryderykApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=entry.options.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES)),
        )
        self.api = api
        # details (teacher/room/notes) per lesson URL; cancelled lessons are always refetched
        self._details: dict[str, dict] = {}
        self._seen_cancelled: set[str] | None = None
        self._seen_messages: set[str] | None = None

    @property
    def weeks(self) -> int:
        return int(self.config_entry.options.get(CONF_WEEKS, DEFAULT_WEEKS))

    async def enrich(self, lessons: list[Lesson]) -> None:
        """Attach teacher/room/notes, using the cache for unchanged lessons."""
        for les in lessons:
            if not les.details_url:
                continue
            changed = les.cancelled or les.substitution
            if changed or les.details_url not in self._details:
                try:
                    self._details[les.details_url] = await self.api.lesson_details(les.details_url)
                except FryderykError as err:
                    _LOGGER.debug("Details for %s failed: %s", les.details_url, err)
                    continue
            apply_details(les, self._details[les.details_url])

    async def _async_update_data(self) -> FryderykData:
        try:
            days = await self.api.weeks(dt_util.now().date(), self.weeks)
            await self.enrich([les for d in days for les in d.lessons])
            messages, _ = await self.api.messages("inbox", 1)
            announcements, _ = await self.api.announcements(1)
            counts = await self.api.counts()
        except FryderykAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FryderykError as err:
            raise UpdateFailed(str(err)) from err

        data = FryderykData(days=days, messages=messages, announcements=announcements, counts=counts)
        self._fire_events(data)
        return data

    def _fire_events(self, data: FryderykData) -> None:
        """Fire bus events for newly seen cancellations and messages (not on the first refresh)."""
        now = dt_util.now()
        changed = {les.key: les for les in data.upcoming(now) if les.cancelled or les.substitution}
        if self._seen_cancelled is not None:
            for key in changed.keys() - self._seen_cancelled:
                self.hass.bus.async_fire(EVENT_LESSON_CANCELLED, lesson_dict(changed[key]))
        self._seen_cancelled = set(changed) | (self._seen_cancelled or set())

        ids = {m.id: m for m in data.messages}
        if self._seen_messages is not None:
            for mid in ids.keys() - self._seen_messages:
                self.hass.bus.async_fire(EVENT_NEW_MESSAGE, asdict(ids[mid]))
        self._seen_messages = set(ids) | (self._seen_messages or set())
