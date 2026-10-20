"""End-to-end tests: the real setup/unload of the integration against a fake NMEA server.

The cadence is scaled down: 0.3 s stands in for the 30 s GGA interval, so the
4x read/stale timeouts of 1.2 s correspond to the production 120 s.
"""
import asyncio
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    EVENT_STATE_CHANGED,
    STATE_UNAVAILABLE,
)
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nmea0183.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_READ_TIMEOUT,
    CONF_SECONDS_BETWEEN_UPDATES,
    CONF_STALE_TIMEOUT,
    DOMAIN,
)

from .fake_nmea_server import FakeNmeaServer

CADENCE = 0.3
TIMEOUT = 1.2


@pytest.fixture(autouse=True)
def fast_timers(socket_enabled):
    with patch("custom_components.nmea0183.hub.FRESHNESS_CHECK_INTERVAL", 0.1), patch(
        "custom_components.nmea0183.client.RECONNECT_DELAY", 0.1
    ):
        yield


@pytest.fixture
async def server():
    srv = FakeNmeaServer()
    await srv.start()
    yield srv
    await srv.stop()


def make_entry(hass, port, **extra):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "name": "Test",
            CONF_HOST: "127.0.0.1",
            CONF_PORT: port,
            CONF_SECONDS_BETWEEN_UPDATES: 0,
            CONF_READ_TIMEOUT: TIMEOUT,
            CONF_STALE_TIMEOUT: TIMEOUT,
            **extra,
        },
    )
    entry.add_to_hass(hass)
    return entry


def entity_id(hass, key):
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"test_{key}")


def state(hass, key):
    eid = entity_id(hass, key)
    obj = hass.states.get(eid) if eid else None
    return obj.state if obj else None


async def wait_for(hass, predicate, timeout=5.0):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.02)
            await hass.async_block_till_done()


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_first_sentence_creates_populated_sensors(hass, server):
    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)
    await wait_for(hass, lambda: state(hass, "state") == "Running")
    assert state(hass, "data_state") == "Waiting for data"

    await server.send()
    await wait_for(hass, lambda: state(hass, "gga_satview") == "12")

    assert state(hass, "gga_msl") == "45.6"
    assert state(hass, "data_state") == "Fresh"
    assert state(hass, "total_messages") == "1"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_steady_cadence_with_jitter_has_no_flapping(hass, server):
    """Regression for #4/#5: an on-time stream must not disconnect or go unavailable."""
    entry = make_entry(hass, server.port)
    seen = []

    def record(event):
        new = event.data["new_state"]
        if new is not None:
            seen.append((event.data["entity_id"], new.state))

    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)
    server.start_cadence(CADENCE, jitter=0.3)
    await wait_for(hass, lambda: state(hass, "gga_satview") == "12")
    hass.bus.async_listen(EVENT_STATE_CHANGED, record)

    await asyncio.sleep(4 * TIMEOUT)  # several read/stale timeouts worth of stream

    assert server.connections == 1
    assert state(hass, "state") == "Running"
    assert state(hass, "data_state") == "Fresh"
    assert state(hass, "gga_satview") == "12"
    assert not [s for s in seen if s[1] in ("Disconnected", "Stale", STATE_UNAVAILABLE)]

    server.stop_cadence()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_stream_stops_goes_stale_then_recovers(hass, server):
    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)
    server.start_cadence(CADENCE)
    await wait_for(hass, lambda: state(hass, "gga_satview") == "12")

    server.stop_cadence()  # TCP stays up, the data stops

    await wait_for(hass, lambda: state(hass, "gga_satview") == STATE_UNAVAILABLE)
    assert state(hass, "data_state") == "Stale"
    await wait_for(hass, lambda: server.connections >= 2)  # read timeout forced a reconnect

    # A reconnect alone does not make old readings fresh
    await asyncio.sleep(0.5)
    assert state(hass, "gga_satview") == STATE_UNAVAILABLE

    await server.send()
    await wait_for(hass, lambda: state(hass, "gga_satview") == "12")
    assert state(hass, "data_state") == "Fresh"
    assert state(hass, "state") == "Running"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_eof_reconnects_immediately(hass, server):
    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)

    server.drop_clients()

    await wait_for(hass, lambda: server.connections == 2, timeout=TIMEOUT / 2)
    await wait_for(hass, lambda: state(hass, "state") == "Running")

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_then_setup_again_keeps_entities_unique(hass, server):
    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)
    await server.send()
    await wait_for(hass, lambda: state(hass, "gga_satview") == "12")
    registry = er.async_get(hass)
    before = {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}

    assert await hass.config_entries.async_unload(entry.entry_id)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 2)
    await server.send()
    await wait_for(hass, lambda: state(hass, "gga_satview") == "12")

    after = {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert after == before
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_option_change_reloads_exactly_once(hass, server):
    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)

    reload = hass.config_entries.async_reload
    with patch.object(hass.config_entries, "async_reload", wraps=reload) as spy:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "127.0.0.1",
                CONF_PORT: server.port,
                CONF_SECONDS_BETWEEN_UPDATES: 7,
                CONF_READ_TIMEOUT: 120,
                CONF_STALE_TIMEOUT: 120,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert spy.call_count == 1
    assert entry.data[CONF_SECONDS_BETWEEN_UPDATES] == 7
    assert entry.data["name"] == "Test"  # kept, the name is not editable
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_reloads_do_not_accumulate_stop_listeners(hass, server):
    def listeners() -> int:
        return hass.bus.async_listeners().get(EVENT_HOMEASSISTANT_STOP, 0)

    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    during = listeners()

    for _ in range(3):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert listeners() == during

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert listeners() == during - 1  # only this entry's stop listener goes away


async def test_unload_stops_all_hub_tasks(hass, server):
    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)
    hub = entry.runtime_data
    tasks = list(hub._tasks)
    assert tasks and not any(t.done() for t in tasks)

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert all(t.done() for t in tasks)
    assert hub._tasks == []


async def test_state_classes_separate_counter_measurements_and_states(hass, server):
    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)
    await server.send()
    await wait_for(hass, lambda: state(hass, "gga_satview") == "12")

    def state_class(key):
        return hass.states.get(entity_id(hass, key)).attributes.get("state_class")

    assert state_class("total_messages") == "total_increasing"
    assert hass.states.get(entity_id(hass, "total_messages")).attributes["unit_of_measurement"] == "messages"
    # sampled values are measurements
    for key in ("gga_satview", "gga_lat_decimal", "gga_msl", "gga_gps_quality", "gga_lat"):
        assert state_class(key) == "measurement", key
    # states and text carry no statistics
    for key in ("state", "data_state", "gga_fix"):
        assert state_class(key) is None, key
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_message_counter_restarts_from_zero_after_a_reload(hass, server):
    entry = make_entry(hass, server.port)
    await setup(hass, entry)
    await wait_for(hass, lambda: server.connections == 1)
    await server.send()
    await wait_for(hass, lambda: state(hass, "total_messages") == "1")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await setup(hass, entry)

    # a fresh start counts from 0 again, which a total_increasing sensor records as a reset
    await wait_for(hass, lambda: state(hass, "total_messages") == "0")
    assert hass.states.get(entity_id(hass, "total_messages")).attributes["state_class"] == "total_increasing"
    assert await hass.config_entries.async_unload(entry.entry_id)
