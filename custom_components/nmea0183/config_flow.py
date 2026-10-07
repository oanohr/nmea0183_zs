import asyncio
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_HOST,
    CONF_SECONDS_BETWEEN_UPDATES,
    CONF_PORT,
    CONF_SENTENCE_EXCLUDE,
    CONF_SENTENCE_INCLUDE,
    DEFAULT_SECONDS_BETWEEN_UPDATES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TEST_TIMEOUT = 5

_COMMON_OPTIONS = {
    vol.Optional(CONF_SENTENCE_INCLUDE): str,
    vol.Optional(CONF_SENTENCE_EXCLUDE): str,
    vol.Optional(CONF_SECONDS_BETWEEN_UPDATES, default=DEFAULT_SECONDS_BETWEEN_UPDATES): vol.All(vol.Coerce(int), vol.Range(min=0)),
}

_CONNECTION_FIELDS = {
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_PORT): int,
}


def _normalize(name: str) -> str:
    """Same normalisation the sensors apply to their unique ids."""
    return name.lower().replace(" ", "_").replace("-", "_")


def parse_sentence_list(input_str: str) -> list[str]:
    """Parse a comma-separated list of three-letter sentence types, e.g. "GGA, rmc"."""
    sentences = []
    for value in input_str.split(","):
        value = value.strip().upper()
        if not value:
            continue
        if len(value) != 3 or not value.isalnum():
            raise ValueError(f"Invalid sentence type: '{value}' in input '{input_str}'")
        sentences.append(value)
    return sentences


def _validate_options(user_input: dict) -> dict[str, str]:
    errors = {}
    for key in (CONF_SENTENCE_INCLUDE, CONF_SENTENCE_EXCLUDE):
        if user_input.get(key):
            try:
                parse_sentence_list(user_input[key])
            except ValueError:
                errors[key] = "sentence_not_valid"
    if user_input.get(CONF_SENTENCE_INCLUDE) and user_input.get(CONF_SENTENCE_EXCLUDE):
        errors[CONF_SENTENCE_EXCLUDE] = "include_exclude_only_one"
    return errors


async def _can_connect(host: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), CONNECT_TEST_TIMEOUT
        )
    except (OSError, asyncio.TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True


class NMEA0183ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        _LOGGER.debug("async_step_user called with user_input: %s", user_input)
        errors = {}

        if user_input is not None:
            existing_names = {
                _normalize(entry.data.get(CONF_NAME) or "")
                for entry in self._async_current_entries()
            }
            if _normalize(user_input[CONF_NAME]) in existing_names:
                errors[CONF_NAME] = "name_exists"
            else:
                errors.update(_validate_options(user_input))

            if not errors and not await _can_connect(
                user_input[CONF_HOST], user_input[CONF_PORT]
            ):
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_NAME): str, **_CONNECTION_FIELDS, **_COMMON_OPTIONS}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        current_data = self.config_entry.data
        errors = {}

        if user_input is not None:
            errors = _validate_options(user_input)
            if not errors:
                # the name is not editable here, keep it
                new_data = {**user_input, CONF_NAME: current_data[CONF_NAME]}
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data=None)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({**_CONNECTION_FIELDS, **_COMMON_OPTIONS}), current_data
            ),
            errors=errors,
        )
