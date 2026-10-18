"""Home Assistant tests: config flow, setup, sensors, calendar, events (HTTP mocked)."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events  # noqa: E402

from custom_components.fryderyk.const import DOMAIN, EVENT_LESSON_CANCELLED, EVENT_NEW_MESSAGE  # noqa: E402
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState  # noqa: E402
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402

BASE = "https://school.fryderyk.edu.pl"
FIX = Path(__file__).parent / "fixtures"
LOGIN_FORM = '<form><input name="username"><input name="password"></form>'
DATA = {CONF_URL: BASE, CONF_USERNAME: "kid", CONF_PASSWORD: "secret"}
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo("Europe/Warsaw"))


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def mock_site(aioclient_mock, *, inbox: str | None = None, login_ok: bool = True) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/users/login", text="<html>plan</html>" if login_ok else LOGIN_FORM)
    aioclient_mock.get(f"{BASE}/plans/mine/2026-10-12", text=fx("plan_week.html"))
    aioclient_mock.get(f"{BASE}/plans/mine/2026-10-19", text='<div id="plan"></div>')
    for url in ("100/1001", "200/2001", "300/3001", "200/2002"):
        aioclient_mock.get(f"{BASE}/lessons/details/{url}/mine", text=fx("lesson_details.html"))
    aioclient_mock.get(f"{BASE}/messages/get-messages/inbox/1", text=inbox if inbox is not None else fx("inbox.html"))
    aioclient_mock.get(f"{BASE}/announcements/get-announcements/1", text="")
    aioclient_mock.get(f"{BASE}/app/messages-check/", json={"unread": 1})
    for name in ("announcements", "homeworks", "substitutions"):
        aioclient_mock.get(f"{BASE}/app/{name}-count/", json={"count": 0})


@pytest.fixture
async def setup(hass: HomeAssistant, aioclient_mock, freezer):
    await hass.config.async_set_time_zone("Europe/Warsaw")
    freezer.move_to(NOW)
    mock_site(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id=f"{BASE}|kid")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_flow_success(hass: HomeAssistant, aioclient_mock) -> None:
    mock_site(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**DATA, CONF_URL: "https://school.fryderyk.edu.pl/users/login"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_URL] == BASE  # normalised to the host


async def test_flow_invalid_auth(hass: HomeAssistant, aioclient_mock) -> None:
    mock_site(aioclient_mock, login_ok=False)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_setup_failed_auth_starts_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    mock_site(aioclient_mock, login_ok=False)
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id=f"{BASE}|kid")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_sensors(hass: HomeAssistant, setup) -> None:
    assert setup.state is ConfigEntryState.LOADED

    cancelled = hass.states.get("sensor.fryderyk_kid_cancelled_lessons")
    assert cancelled.state == "2"  # one cancellation + one substitution
    lessons = cancelled.attributes["lessons"]
    assert lessons[0]["subject"] == "podstawy rytmiki" and lessons[0]["status"] == "cancelled"
    assert lessons[0]["teacher"] == "Nowak Anna" and lessons[0]["room"] == "Sala 27"
    assert lessons[1]["status"] == "substitution"
    assert cancelled.attributes["days_off"] == [
        {"date": "2026-10-14", "weekday": "Środa", "name": "Dzień Edukacji Narodowej"}
    ]

    nxt = hass.states.get("sensor.fryderyk_kid_next_lesson")
    assert nxt.state == "2026-10-12T15:35:00+00:00"  # 17:35 Warsaw
    assert nxt.attributes["subject"] == "kształcenie słuchu"

    assert hass.states.get("sensor.fryderyk_kid_lessons_today").state == "2"  # 3 minus the cancelled one
    assert hass.states.get("sensor.fryderyk_kid_unread_messages").state == "1"
    latest = hass.states.get("sensor.fryderyk_kid_latest_message")
    assert latest.state == "Odwołane zajęcia z panią Anną Nowak"
    assert latest.attributes["unread"] is True
    assert hass.states.get("sensor.fryderyk_kid_announcements").state == "0"


async def test_calendar(hass: HomeAssistant, setup) -> None:
    state = hass.states.get("calendar.fryderyk_kid_lessons")
    assert state.attributes["message"] == "kształcenie słuchu (II B)"
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.fryderyk_kid_lessons",
            "start_date_time": "2026-10-12T00:00:00+02:00",
            "duration": {"days": 7},
        },
        blocking=True,
        return_response=True,
    )
    summaries = [e["summary"] for e in events["calendar.fryderyk_kid_lessons"]["events"]]
    assert "❌ podstawy rytmiki (II B) – odwołane" in summaries
    assert "🔁 podstawy rytmiki (II B) – zastępstwo" in summaries
    assert "🎉 Dzień Edukacji Narodowej" in summaries
    assert len(summaries) == 5


async def test_events_fire_for_new_items_only(hass: HomeAssistant, setup, aioclient_mock) -> None:
    cancelled = async_capture_events(hass, EVENT_LESSON_CANCELLED)
    new_msg = async_capture_events(hass, EVENT_NEW_MESSAGE)
    coordinator = setup.runtime_data

    await coordinator.async_refresh()  # same data: nothing new
    assert not cancelled and not new_msg

    extra = fx("inbox.html").replace('data-message-id="5666"', 'data-message-id="9999"')
    mock_site(aioclient_mock, inbox=extra)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert [e.data["id"] for e in new_msg] == ["9999"]
    assert not cancelled


async def test_unload(hass: HomeAssistant, setup) -> None:
    assert await hass.config_entries.async_unload(setup.entry_id)
    assert setup.state is ConfigEntryState.NOT_LOADED
