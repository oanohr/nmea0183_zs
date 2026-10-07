"""Tests for the NMEA 0183 Hub."""
from unittest.mock import MagicMock

import pynmea2
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nmea0183.const import DOMAIN, CONF_HOST, CONF_PORT
from custom_components.nmea0183.hub import Hub
from .test_sentences import GGA


async def test_hub_creates_sensors_from_sentence(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"name": "Test", CONF_HOST: "127.0.0.1", CONF_PORT: 1}
    )
    entry.add_to_hass(hass)
    hub = Hub(hass, entry)
    add_entities = MagicMock()
    await hub.register_async_add_entities(add_entities)

    # entities are not added to hass in this test, so mark them ready
    for sensor in (hub.state_sensor, hub.total_messages_sensor, hub.msg_per_minute_sensor):
        sensor._ready = True
        sensor.async_schedule_update_ha_state = MagicMock()

    await hub.receive_callback(pynmea2.parse(GGA))

    assert hub.total_messages_sensor.native_value == 1
    assert "Test_GN_GGA_latitude" in hub.sensors
    assert hub.sensors["Test_GN_GGA_satellites_used"].native_value == 12
    assert hub.sensors["Test_GN_GGA_altitude"].native_value == 45.6
