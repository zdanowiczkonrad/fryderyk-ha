"""The Fryderyk e-journal integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import FryderykApi
from .coordinator import FryderykConfigEntry, FryderykCoordinator

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: FryderykConfigEntry) -> bool:
    # dedicated session: the login cookie must not leak into HA's shared session
    session = async_create_clientsession(hass)
    api = FryderykApi(session, entry.data[CONF_URL], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = FryderykCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FryderykConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _reload_on_options(hass: HomeAssistant, entry: FryderykConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
