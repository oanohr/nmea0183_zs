"""
NMEA 0183 Hub Component for Home Assistant.

Reads NMEA 0183 sentences from a TCP stream and creates/updates Home Assistant
sensors based on received data.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
import logging
import time

import pynmea2

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .NMEA0183Sensor import NMEA0183Sensor
from .client import Nmea0183TcpClient, State
from .config_flow import parse_sentence_list
from .const import (
    CONF_HOST,
    CONF_MS_BETWEEN_UPDATES,
    CONF_PORT,
    CONF_SENTENCE_EXCLUDE,
    CONF_SENTENCE_INCLUDE,
    DEFAULT_MS_BETWEEN_UPDATES,
)
from .sentences import extract_readings

_LOGGER = logging.getLogger(__name__)

# Receivers send position fixes at 1-10 Hz; flag a value as stale after this long
# (NMEA0183Sensor multiplies the ttl by its UNAVAILABLE_FACTOR).
SENSOR_TTL = timedelta(seconds=10)


async def event_wait(evt, timeout):
    """Wait for an event with timeout. Returns True if the event is set."""
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(evt.wait(), timeout)
    return evt.is_set()


class Hub:
    """NMEA 0183 Hub for managing the TCP connection and sensors."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.stop_event = asyncio.Event()
        self.state = "Initializing"
        self.async_add_entities = None
        self.sensors: dict[str, NMEA0183Sensor] = {}
        self._tasks: list[asyncio.Task] = []

        self.message_count_per_interval = 0
        self.last_count_time = time.time()
        self.messages_per_minute = 0

        self.name = entry.data[CONF_NAME]
        self.time_between_updates = timedelta(
            milliseconds=entry.data.get(
                CONF_MS_BETWEEN_UPDATES, DEFAULT_MS_BETWEEN_UPDATES
            )
        )
        self.device_name = f"NMEA 0183 {self.name}"

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
        )
        self.total_messages_sensor = NMEA0183Sensor(
            sensor_id=self.name + "_total_messages",
            friendly_name="Total message count",
            initial_state=0,
            unit_of_measurement="messages",
            device_name=self.device_name,
            update_frequncy=self.time_between_updates,
        )
        self.msg_per_minute_sensor = NMEA0183Sensor(
            sensor_id=self.name + "_messages_per_minute",
            friendly_name="Messages per minute",
            initial_state=0,
            unit_of_measurement="msg/min",
            device_name=self.device_name,
        )

        self.client = Nmea0183TcpClient(
            host, port, include_sentences=include, exclude_sentences=exclude
        )
        self.client.set_receive_callback(self.receive_callback)
        self.client.set_status_callback(self.status_callback)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.stop)

    async def register_async_add_entities(
        self, async_add_entities: AddEntitiesCallback
    ) -> None:
        """Register the callback for adding entities and add the system sensors."""
        self.async_add_entities = async_add_entities
        self.async_add_entities(
            [self.state_sensor, self.total_messages_sensor, self.msg_per_minute_sensor]
        )

    async def update_tasks(self) -> None:
        """Periodic message rate calculation and sensor availability updates."""
        availability_interval = 300  # 5 minutes in seconds
        message_rate_interval = 10  # 10 seconds
        last_availability_update = time.time()

        while not await event_wait(self.stop_event, message_rate_interval):
            current_time = time.time()

            elapsed_time = current_time - self.last_count_time
            if elapsed_time > 0:
                self.messages_per_minute = int(
                    self.message_count_per_interval * (60 / elapsed_time)
                )
                self.msg_per_minute_sensor.set_state(self.messages_per_minute)
                self.message_count_per_interval = 0
                self.last_count_time = current_time

            if current_time - last_availability_update >= availability_interval:
                for sensor in self.sensors.values():
                    sensor.update_availability()
                last_availability_update = current_time

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
                ttl=SENSOR_TTL,
                is_numeric=isinstance(value, (int, float))
                or unit_of_measurement is not None,
            )
            _LOGGER.info("Created new sensor %s: %s", sensor_id, sensor)
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

        self.message_count_per_interval += 1
        self.total_messages_sensor.set_state(
            self.total_messages_sensor.native_value + 1
        )

        prefix = f"{self.name}_{message.talker}_{message.sentence_type}_"
        label = f"{message.talker} {message.sentence_type}"
        for reading in extract_readings(message):
            self._update_or_create_sensor(
                prefix + reading.key,
                f"{label} {reading.name}",
                reading.value,
                reading.unit,
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

    @callback
    async def stop(self, event: Event | None) -> None:
        """Close resources and disconnect."""
        _LOGGER.debug("NMEA0183 Hub %s closing", self.name)
        self.stop_event.set()
        self.client.stop()
        for task in self._tasks:
            task.cancel()
        _LOGGER.info("NMEA0183 Hub %s closed", self.name)
