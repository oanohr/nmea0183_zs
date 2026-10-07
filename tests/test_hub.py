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
    for sensor in (hub.state_sensor, hub.total_messages_sensor):
        sensor._ready = True
        sensor.async_schedule_update_ha_state = MagicMock()

    await hub.receive_callback(pynmea2.parse(GGA))

    assert hub.total_messages_sensor.native_value == 1
    assert "Test_gga_lat_decimal" in hub.sensors
    assert hub.sensors["Test_gga_satview"].native_value == 12
    assert hub.sensors["Test_gga_msl"].native_value == 45.6


async def test_two_hubs_do_not_share_state_or_ids(hass):
    hubs = []
    for name in ("Boat A", "Boat B"):
        entry = MockConfigEntry(
            domain=DOMAIN, data={"name": name, CONF_HOST: "127.0.0.1", CONF_PORT: 1}
        )
        entry.add_to_hass(hass)
        hub = Hub(hass, entry)
        await hub.register_async_add_entities(MagicMock())
        for sensor in (hub.state_sensor, hub.total_messages_sensor):
            sensor._ready = True
            sensor.async_schedule_update_ha_state = MagicMock()
        hubs.append(hub)

    await hubs[0].receive_callback(pynmea2.parse(GGA))

    assert hubs[0].total_messages_sensor.native_value == 1
    assert hubs[1].total_messages_sensor.native_value == 0
    assert hubs[1].sensors == {}

    await hubs[1].receive_callback(pynmea2.parse(GGA))
    ids_a = {s.unique_id for s in hubs[0].sensors.values()}
    ids_b = {s.unique_id for s in hubs[1].sensors.values()}
    assert ids_a and not ids_a & ids_b
    assert hubs[0].device_name != hubs[1].device_name
