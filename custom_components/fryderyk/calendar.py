"""Calendar of lessons and days off for Fryderyk."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import FryderykError
from .const import MAX_CALENDAR_WEEKS
from .coordinator import FryderykConfigEntry, FryderykCoordinator, lesson_end, lesson_start
from .entity import FryderykEntity
from .parsing import Day, Lesson, week_monday

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FryderykConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([FryderykCalendar(entry.runtime_data)])


def _lesson_event(les: Lesson) -> CalendarEvent:
    summary = les.subject + (f" ({les.group})" if les.group else "")
    if les.cancelled:
        summary = f"❌ {summary} – odwołane"
    elif les.substitution:
        summary = f"🔁 {summary} – zastępstwo"
    desc = [x for x in (f"Nauczyciel: {les.teacher}" if les.teacher else "", *les.notes, *les.flags) if x]
    return CalendarEvent(
        start=lesson_start(les),
        end=lesson_end(les) if les.end else lesson_start(les) + timedelta(minutes=45),
        summary=summary,
        description="\n".join(dict.fromkeys(desc)) or None,
        location=les.room or None,
        uid=les.key,
    )


def _events(days: list[Day]) -> list[CalendarEvent]:
    out: list[CalendarEvent] = []
    for d in days:
        if d.holiday:
            day = date.fromisoformat(d.date)
            out.append(
                CalendarEvent(
                    start=day, end=day + timedelta(days=1), summary=f"🎉 {d.holiday}", uid=f"holiday-{d.date}"
                )
            )
        out += [_lesson_event(les) for les in d.lessons]
    return out


class FryderykCalendar(FryderykEntity, CalendarEntity):
    _attr_translation_key = "lessons"

    def __init__(self, coordinator: FryderykCoordinator) -> None:
        super().__init__(coordinator, "calendar")

    @property
    def event(self) -> CalendarEvent | None:
        """Current or next lesson that actually takes place."""
        now = dt_util.now()
        les = next((x for x in self.coordinator.data.upcoming(now) if not x.cancelled), None)
        return _lesson_event(les) if les else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        days = self.coordinator.data.days
        have = {d.date for d in days}
        first, last = dt_util.as_local(start_date).date(), dt_util.as_local(end_date).date()
        covered = days and first.isoformat() >= min(have) and last.isoformat() <= max(have)
        if not covered:
            weeks = min((week_monday(last) - week_monday(first)).days // 7 + 1, MAX_CALENDAR_WEEKS)
            try:
                days = await self.coordinator.api.weeks(first, weeks)
                await self.coordinator.enrich([les for d in days if d.date in have for les in d.lessons])
            except FryderykError as err:
                _LOGGER.warning("Could not fetch lessons for %s–%s: %s", first, last, err)
                days = self.coordinator.data.days
        return [
            ev
            for ev in _events(days)
            if dt_util.as_local(_as_dt(ev.end)) > start_date and dt_util.as_local(_as_dt(ev.start)) < end_date
        ]


def _as_dt(v: date | datetime) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime(v.year, v.month, v.day, tzinfo=dt_util.get_default_time_zone())
