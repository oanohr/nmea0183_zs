"""
NMEA 0183 Hub Component for Home Assistant.

Reads NMEA 0183 sentences from a TCP stream and creates/updates Home Assistant
sensors based on received data.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from datetime import timedelta
import logging
import time

import pynmea2

from homeassistant.components.sensor import SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .NMEA0183Sensor import NMEA0183Sensor
from .client import Nmea0183TcpClient, State
from .config_flow import parse_sentence_list
from .const import (
    CONF_HOST,
    CONF_SECONDS_BETWEEN_UPDATES,
    CONF_PORT,
    CONF_READ_TIMEOUT,
    CONF_SENTENCE_EXCLUDE,
    CONF_SENTENCE_INCLUDE,
    CONF_STALE_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_SECONDS_BETWEEN_UPDATES,
    DEFAULT_STALE_TIMEOUT,
)
from .sentences import extract_readings

_LOGGER = logging.getLogger(__name__)

FRESHNESS_CHECK_INTERVAL = 10  # seconds

DATA_WAITING = "Waiting for data"
DATA_FRESH = "Fresh"
DATA_STALE = "Stale"


async def event_wait(evt, timeout):
    """Wait for an event with timeout. Returns True if the event is set."""
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(evt.wait(), timeout)
    return evt.is_set()


class Hub:
    """NMEA 0183 Hub for managing the TCP connection and sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hass = hass
        self.clock = clock
        self.entry = entry
        self.stop_event = asyncio.Event()
        self.state = "Initializing"
        self.async_add_entities = None
        self.sensors: dict[str, NMEA0183Sensor] = {}
        self._tasks: list[asyncio.Task] = []


        self.name = entry.data[CONF_NAME]
        self.time_between_updates = timedelta(
            seconds=entry.data.get(
                CONF_SECONDS_BETWEEN_UPDATES, DEFAULT_SECONDS_BETWEEN_UPDATES
            )
        )
        self.device_name = self.name
        self.stale_timeout = timedelta(
            seconds=entry.data.get(CONF_STALE_TIMEOUT, DEFAULT_STALE_TIMEOUT)
        )
        read_timeout = entry.data.get(CONF_READ_TIMEOUT, DEFAULT_READ_TIMEOUT)
        self._last_data: float | None = None

        include = parse_sentence_list(entry.data.get(CONF_SENTENCE_INCLUDE) or "")
        exclude = parse_sentence_list(entry.data.get(CONF_SENTENCE_EXCLUDE) or "")
        host, port = entry.data[CONF_HOST], entry.data[CONF_PORT]
        _LOGGER.info(
            "Configuring %s: host=%s, port=%s, include=%s, exclude=%s",
            self.name,
            host,
            port,
            include,
            exclude,
        )

        self.state_sensor = NMEA0183Sensor(
            sensor_id=self.name + "_state",
            friendly_name="State",
            initial_state=self.state,
            device_name=self.device_name,
            update_frequncy=timedelta(0),
            clock=self.clock,
        )
        self.total_messages_sensor = NMEA0183Sensor(
            sensor_id=self.name + "_total_messages",
            friendly_name="Total message count",
            initial_state=0,
            unit_of_measurement="messages",
            device_name=self.device_name,
            update_frequncy=self.time_between_updates,
            clock=self.clock,
            # Counts up from 0 at every start: HA reads the drop as a new cycle, so
            # long-term statistics do not see a negative change after a restart
            state_class=SensorStateClass.TOTAL_INCREASING,
        )

        self.data_state_sensor = NMEA0183Sensor(
            sensor_id=self.name + "_data_state",
            friendly_name="Data state",
            initial_state=DATA_WAITING,
            device_name=self.device_name,
            update_frequncy=timedelta(0),
            clock=self.clock,
        )

        self.client = Nmea0183TcpClient(
            host,
            port,
            include_sentences=include,
            exclude_sentences=exclude,
            read_timeout=read_timeout,
        )
        self.client.set_receive_callback(self.receive_callback)
        self.client.set_status_callback(self.status_callback)

    async def register_async_add_entities(
        self, async_add_entities: AddEntitiesCallback
    ) -> None:
        """Register the callback for adding entities and add the system sensors."""
        self.async_add_entities = async_add_entities
        self.async_add_entities(
            [self.state_sensor, self.total_messages_sensor, self.data_state_sensor]
        )

    def check_freshness(self) -> None:
        """Mark sensors without a recent value unavailable, and update the data state.

        Freshness depends only on when values arrived, never on the TCP state, so
        a reconnect does not make old readings look current.
        """
        for sensor in self.sensors.values():
            sensor.update_availability()

        if self._last_data is None:
            return
        stale = self.clock() - self._last_data >= self.stale_timeout.total_seconds()
        new_state = DATA_STALE if stale else DATA_FRESH
        if new_state != self.data_state_sensor.native_value:
            # One line per outage instead of one per sensor
            if stale:
                _LOGGER.warning(
                    "%s: no data for %s s, values are unavailable until it resumes",
                    self.name,
                    int(self.stale_timeout.total_seconds()),
                )
        self.data_state_sensor.set_state(new_state)

    async def update_tasks(self) -> None:
        """Periodic freshness checks."""
        while not await event_wait(self.stop_event, FRESHNESS_CHECK_INTERVAL):
            self.check_freshness()

    async def status_callback(self, state: State) -> None:
        """Process changes in connection state."""
        self.state = "Running" if state == State.CONNECTED else "Disconnected"
        self.state_sensor.set_state(self.state)

    def _update_or_create_sensor(
        self,
        sensor_id: str,
        friendly_name: str,
        value,
        unit_of_measurement: str | None,
        numeric: bool = False,
    ) -> None:
        sensor = self.sensors.get(sensor_id)
        if sensor is None:
            sensor = NMEA0183Sensor(
                sensor_id=sensor_id,
                friendly_name=friendly_name,
                initial_state=value,
                unit_of_measurement=unit_of_measurement,
                device_name=self.device_name,
                update_frequncy=self.time_between_updates,
                ttl=self.stale_timeout,
                clock=self.clock,
                is_numeric=numeric or isinstance(value, (int, float))
                or unit_of_measurement is not None,
            )
            _LOGGER.debug("Created new sensor %s: %s", sensor_id, sensor)
            self.async_add_entities([sensor])
            self.sensors[sensor_id] = sensor
        else:
            sensor.set_state(value)

    async def receive_callback(self, message: pynmea2.NMEASentence) -> None:
        """Process a received NMEA 0183 sentence."""
        if self.async_add_entities is None:
            _LOGGER.debug(
                "Can't handle messages as async_add_entities is not registered yet"
            )
            return

        self._last_data = self.clock()
        if self.data_state_sensor.native_value == DATA_STALE:
            _LOGGER.info("%s: data is flowing again", self.name)
        self.data_state_sensor.set_state(DATA_FRESH)
        self.total_messages_sensor.set_state(
            self.total_messages_sensor.native_value + 1
        )

        prefix = f"{self.name}_"
        for reading in extract_readings(message):
            self._update_or_create_sensor(
                prefix + reading.key,
                reading.name,
                reading.value,
                reading.unit,
                reading.numeric,
            )

    async def start(self, _event=None) -> None:
        """Start the TCP client and background tasks."""
        _LOGGER.debug("NMEA0183 %s starting", self.name)
        self._tasks = [
            self.entry.async_create_background_task(
                self.hass, self.client.run(), "nmea0183_client"
            ),
            self.entry.async_create_background_task(
                self.hass, self.update_tasks(), "update_tasks"
            ),
        ]

    async def stop(self, event: Event | None = None) -> None:
        """Close resources and disconnect. Safe to call more than once."""
        _LOGGER.debug("NMEA0183 Hub %s closing", self.name)
        self.stop_event.set()
        self.client.stop()
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        # Wait for the tasks, so unload leaves nothing running behind it
        await asyncio.gather(*tasks, return_exceptions=True)
        _LOGGER.info("NMEA0183 Hub %s closed", self.name)
