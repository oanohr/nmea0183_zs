"""Tests for the NMEA 0183 config flow."""
import pytest
from unittest.mock import patch
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nmea0183.const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_SENTENCE_INCLUDE,
    CONF_SENTENCE_EXCLUDE,
)
from custom_components.nmea0183.config_flow import parse_sentence_list

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
