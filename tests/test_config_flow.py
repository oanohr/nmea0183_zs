"""Tests for the NMEA 0183 config flow."""
import inspect
import json
from pathlib import Path
import re

import pytest
from unittest.mock import patch
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nmea0183.const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_SENTENCE_INCLUDE,
    CONF_SECONDS_BETWEEN_UPDATES,
    CONF_SENTENCE_EXCLUDE,
)
from custom_components.nmea0183 import config_flow
from custom_components.nmea0183.config_flow import parse_sentence_list

COMPONENT = Path(__file__).parent.parent / "custom_components" / "nmea0183"

pytestmark = pytest.mark.usefixtures("bypass_setup_entry")

USER_INPUT = {"name": "Boat", CONF_HOST: "192.168.3.1", CONF_PORT: 28000}


def test_parse_sentence_list():
    assert parse_sentence_list("gga, RMC") == ["GGA", "RMC"]
    assert parse_sentence_list("  ") == []


@pytest.mark.parametrize("value", ["GG", "GGAA", "GG!"])
def test_parse_sentence_list_invalid(value):
    with pytest.raises(ValueError):
        parse_sentence_list(value)


async def test_user_flow_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM

    with patch("custom_components.nmea0183.config_flow._can_connect", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Boat"
    assert result["data"][CONF_HOST] == "192.168.3.1"
    assert result["data"][CONF_PORT] == 28000


async def test_user_flow_cannot_connect(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch("custom_components.nmea0183.config_flow._can_connect", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_user_flow_include_and_exclude_rejected(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**USER_INPUT, CONF_SENTENCE_INCLUDE: "GGA", CONF_SENTENCE_EXCLUDE: "RMC"},
    )
    assert result["errors"][CONF_SENTENCE_EXCLUDE] == "include_exclude_only_one"


async def test_user_flow_invalid_sentence(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_SENTENCE_INCLUDE: "GGAA"}
    )
    assert result["errors"][CONF_SENTENCE_INCLUDE] == "sentence_not_valid"


async def test_user_flow_duplicate_name(hass):
    MockConfigEntry(domain=DOMAIN, data=USER_INPUT).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"]["name"] == "name_exists"


async def test_user_flow_duplicate_name_differs_only_by_case(hass):
    MockConfigEntry(domain=DOMAIN, data=USER_INPUT).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "name": "boat"}
    )
    assert result["errors"]["name"] == "name_exists"


# --- input validation and translations (#9) ---

@pytest.mark.parametrize("port", [0, -1, 65536, 100000])
async def test_user_flow_rejects_port_outside_1_65535_before_connecting(hass, port):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch("custom_components.nmea0183.config_flow._can_connect") as can_connect:
        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"], {**USER_INPUT, CONF_PORT: port}
            )
    can_connect.assert_not_called()


@pytest.mark.parametrize("port", [1, 65535])
async def test_user_flow_accepts_port_limits(hass, port):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch("custom_components.nmea0183.config_flow._can_connect", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, CONF_PORT: port}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("name", ["", "   "])
async def test_user_flow_rejects_blank_name(hass, name):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch("custom_components.nmea0183.config_flow._can_connect") as can_connect:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, "name": name}
        )
    assert result["errors"]["name"] == "name_required"
    can_connect.assert_not_called()


@pytest.mark.parametrize("host", ["", "  "])
async def test_user_flow_rejects_blank_host(hass, host):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch("custom_components.nmea0183.config_flow._can_connect") as can_connect:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, CONF_HOST: host}
        )
    assert result["errors"][CONF_HOST] == "host_required"
    can_connect.assert_not_called()


async def test_user_flow_trims_name_and_host(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch(
        "custom_components.nmea0183.config_flow._can_connect", return_value=True
    ) as can_connect:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, "name": "  Boat ", CONF_HOST: " 192.168.3.1 "}
        )
    assert result["title"] == "Boat"
    assert result["data"]["name"] == "Boat"
    assert result["data"][CONF_HOST] == "192.168.3.1"
    can_connect.assert_called_once_with("192.168.3.1", 28000)


async def test_user_flow_trimmed_duplicate_name_is_still_a_duplicate(hass):
    MockConfigEntry(domain=DOMAIN, data=USER_INPUT).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "name": " Boat "}
    )
    assert result["errors"]["name"] == "name_exists"


async def test_user_flow_update_interval_zero_ok_negative_rejected(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, CONF_SECONDS_BETWEEN_UPDATES: -1}
        )
    with patch("custom_components.nmea0183.config_flow._can_connect", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**USER_INPUT, CONF_SECONDS_BETWEEN_UPDATES: 0}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def _options_flow(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT)
    entry.add_to_hass(hass)
    return entry, await hass.config_entries.options.async_init(entry.entry_id)


async def test_options_flow_rejects_invalid_port(hass):
    _, result = await _options_flow(hass)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.3.1", CONF_PORT: 70000}
        )


async def test_options_flow_rejects_blank_host(hass):
    _, result = await _options_flow(hass)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOST: " ", CONF_PORT: 28000}
    )
    assert result["errors"][CONF_HOST] == "host_required"


async def test_options_flow_keeps_name_and_trims_host(hass):
    entry, result = await _options_flow(hass)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOST: " 10.0.0.5 ", CONF_PORT: 28001}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data["name"] == "Boat"
    assert entry.data[CONF_HOST] == "10.0.0.5"


def _load(name):
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def test_strings_json_matches_the_english_translation():
    assert _load("strings.json") == _load("translations/en.json")


def _fields(*schemas):
    return {str(key) for schema in schemas for key in schema}


def test_every_flow_field_has_a_label_and_no_label_is_orphaned():
    options_fields = _fields(config_flow._CONNECTION_FIELDS, config_flow._COMMON_OPTIONS)
    user_fields = options_fields | {"name"}
    en = _load("translations/en.json")
    assert set(en["config"]["step"]["user"]["data"]) == user_fields
    assert set(en["options"]["step"]["init"]["data"]) == options_fields


def test_every_error_code_in_the_flow_has_a_message():
    source = inspect.getsource(config_flow)
    codes = set(re.findall(r'errors(?:\[[^\]]+\])?\s*=\s*"([a-z_]+)"', source))
    assert {"name_exists", "name_required", "host_required", "cannot_connect"} <= codes
    en = _load("translations/en.json")
    for code in codes:
        assert code in en["config"]["error"], code
    # the options flow can raise everything except the name and connection errors
    for code in codes - {"name_exists", "name_required", "cannot_connect"}:
        assert code in en["options"]["error"], code
