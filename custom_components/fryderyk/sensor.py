"""Sensors for Fryderyk."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FryderykConfigEntry, FryderykCoordinator, FryderykData, lesson_dict, lesson_start
from .entity import FryderykEntity

PARALLEL_UPDATES = 0
MAX_LISTED = 10


@dataclass(frozen=True, kw_only=True)
class FryderykSensorDescription(SensorEntityDescription):
    value: Callable[[FryderykData, datetime], Any]
    attrs: Callable[[FryderykData, datetime], dict[str, Any]] = lambda d, now: {}


def _next_lesson(d: FryderykData, now: datetime):
    return next((les for les in d.upcoming(now) if not les.cancelled and lesson_start(les) > now), None)


def _today(d: FryderykData, now: datetime):
    today = now.date().isoformat()
    return [les for les in d.lessons if les.date == today]


def _changed(d: FryderykData, now: datetime):
    return [les for les in d.upcoming(now) if les.cancelled or les.substitution]


def _days_off(d: FryderykData, now: datetime):
    today = now.date().isoformat()
    return [
        {"date": day.date, "weekday": day.weekday, "name": day.holiday}
        for day in d.days
        if day.holiday and day.date >= today
    ]


def _msg(m) -> dict:
    out = asdict(m)
    for k in ("body", "sent_at", "folder"):
        out.pop(k, None)
    return out


SENSORS: tuple[FryderykSensorDescription, ...] = (
    FryderykSensorDescription(
        key="next_lesson",
        translation_key="next_lesson",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d, now: lesson_start(les) if (les := _next_lesson(d, now)) else None,
        attrs=lambda d, now: lesson_dict(les) if (les := _next_lesson(d, now)) else {},
    ),
    FryderykSensorDescription(
        key="lessons_today",
        translation_key="lessons_today",
        value=lambda d, now: sum(1 for les in _today(d, now) if not les.cancelled),
        attrs=lambda d, now: {"lessons": [lesson_dict(les) for les in _today(d, now)]},
    ),
    FryderykSensorDescription(
        key="cancelled_lessons",
        translation_key="cancelled_lessons",
        value=lambda d, now: len(_changed(d, now)),
        attrs=lambda d, now: {
            "lessons": [lesson_dict(les) for les in _changed(d, now)],
            "days_off": _days_off(d, now),
        },
    ),
    FryderykSensorDescription(
        key="unread_messages",
        translation_key="unread_messages",
        value=lambda d, now: d.counts.get("unread_messages", sum(m.unread for m in d.messages)),
        attrs=lambda d, now: {"messages": [_msg(m) for m in d.messages[:MAX_LISTED]]},
    ),
    FryderykSensorDescription(
        key="latest_message",
        translation_key="latest_message",
        value=lambda d, now: d.messages[0].title[:255] if d.messages else None,
        attrs=lambda d, now: _msg(d.messages[0]) if d.messages else {},
    ),
    FryderykSensorDescription(
        key="announcements",
        translation_key="announcements",
        value=lambda d, now: d.counts.get("announcements", len(d.announcements)),
        attrs=lambda d, now: {"announcements": [asdict(a) for a in d.announcements[:MAX_LISTED]]},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: FryderykConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(FryderykSensor(entry.runtime_data, desc) for desc in SENSORS)


class FryderykSensor(FryderykEntity, SensorEntity):
    entity_description: FryderykSensorDescription
    # list attributes change often and are bulky; keep them out of the recorder
    _unrecorded_attributes = frozenset(
        {"lessons", "messages", "announcements", "days_off", "preview", "notes", "flags"}
    )

    def __init__(self, coordinator: FryderykCoordinator, description: FryderykSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data, dt_util.now())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs(self.coordinator.data, dt_util.now())
