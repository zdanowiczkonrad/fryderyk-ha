"""Config flow for Fryderyk."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FryderykApi, FryderykAuthError, FryderykConnectionError, base_url
from .const import CONF_SCAN_MINUTES, CONF_WEEKS, DEFAULT_SCAN_MINUTES, DEFAULT_WEEKS, DOMAIN

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)


class FryderykConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, url: str, username: str, password: str) -> str | None:
        """Try to log in; return an error key or None."""
        api = FryderykApi(async_create_clientsession(self.hass), url, username, password)
        try:
            await api.login()
        except FryderykAuthError:
            return "invalid_auth"
        except FryderykConnectionError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = base_url(user_input[CONF_URL])
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(f"{url}|{username}".lower())
            self._abort_if_unique_id_configured()
            if not (err := await self._validate(url, username, user_input[CONF_PASSWORD])):
                return self.async_create_entry(
                    title=f"{username} @ {url.split('://', 1)[1]}",
                    data={CONF_URL: url, CONF_USERNAME: username, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
            errors["base"] = err
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            if not (
                err := await self._validate(entry.data[CONF_URL], entry.data[CONF_USERNAME], user_input[CONF_PASSWORD])
            ):
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = err
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
            ),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return FryderykOptionsFlow()


class FryderykOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_WEEKS: int(user_input[CONF_WEEKS]), CONF_SCAN_MINUTES: int(user_input[CONF_SCAN_MINUTES])}
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_WEEKS, default=DEFAULT_WEEKS): NumberSelector(
                    NumberSelectorConfig(min=1, max=8, step=1, mode="box")
                ),
                vol.Required(CONF_SCAN_MINUTES, default=DEFAULT_SCAN_MINUTES): NumberSelector(
                    NumberSelectorConfig(min=15, max=240, step=5, mode="box", unit_of_measurement="min")
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options)
        )
