# Derived in part from tomer-w/ha-nmea2000 (Apache-2.0).
# Modified for the NMEA 0183 integration. See NOTICE and THIRD_PARTY_NOTICES.md.
from collections.abc import Callable
from datetime import datetime, timedelta
import time
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=5)
INFINITE_DURATION = timedelta(days=10**6)


# SmartSensor class representing a basic sensor entity with state
class NMEA0183Sensor(SensorEntity):
    """Representation of a NMEA0183 sensor."""

    _attr_should_poll = False
    # Prefix entity ids with the device name so several hubs do not collide
    _attr_has_entity_name = True

    def __init__(
        self,
        sensor_id: str,
        friendly_name: str,
        initial_state: str | int | float,
        unit_of_measurement: str | None = None,
        device_name: str | None = None,
        via_device: str | None = None,
        update_frequncy: timedelta | None = None,
        ttl: timedelta | None = None,
        manufacturer: str | None = None,
        is_numeric: bool | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the sensor."""
        need_state_class = (
            is_numeric
            if is_numeric is not None
            else isinstance(initial_state, (int, float))
        )
        _LOGGER.debug(
            "Initializing NMEA0183Sensor: sensor_id=%s, friendly_name=%s, initial_state: %s (%s), unit_of_measurement=%s, device_name=%s, via_device=%s, update_frequncy=%s, ttl=%s, need_state_class=%s",
            sensor_id,
            friendly_name,
            initial_state,
            type(initial_state),
            unit_of_measurement,
            device_name,
            via_device,
            update_frequncy,
            ttl,
            need_state_class,
        )
        self._attr_unique_id = sensor_id.lower().replace(" ", "_").replace("-", "_")
        self._attr_name = friendly_name
        self._device_name = device_name
        self._attr_native_value = initial_state
        # What Home Assistant was last given; native_value may be newer (throttling)
        self._written_value = initial_state
        if need_state_class:  # HA will take units only for numerical data
            self._attr_native_unit_of_measurement = unit_of_measurement
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_name)},
            manufacturer=manufacturer if manufacturer is not None else "NMEA 0183",
            model=device_name,
            name=device_name,
            via_device=((DOMAIN, via_device) if via_device is not None else None),
        )
        self._clock = clock
        self._last_updated = datetime.now()
        self._last_seen = clock()  # monotonic: immune to wall-clock changes
        self.update_frequncy = (
            DEFAULT_UPDATE_INTERVAL if update_frequncy is None else update_frequncy
        )
        self.ttl = INFINITE_DURATION if ttl is None else ttl
        self._ready = False

        if initial_state is None:
            self._available = False
            _LOGGER.debug("Creating sensor: '%s' as unavailable", self._attr_name)
        else:
            self._available = True

    def __str__(self) -> str:
        return f"NMEA0183Sensor(name={self._attr_name}, state={self._attr_native_value}, unit={getattr(self, '_attr_native_unit_of_measurement', None)}, device={self._device_name}, attr_device_info={self._attr_device_info})"

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._attr_native_value

    @property
    def last_updated(self):
        """Return the last updated timestamp of the sensor."""
        return self._last_updated

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self._available

    def update_availability(self):
        """Update the availability status of the sensor."""

        if not self._ready:
            return

        availability_delta = timedelta(seconds=self._clock() - self._last_seen)
        new_availability = availability_delta < self.ttl

        if self._available != new_availability:
            # One line per sensor, so a stale stream would flood the log: the hub
            # reports the outage once, and this stays at debug level.
            _LOGGER.debug(
                "Setting sensor:'%s' as %s. Last value %s ago",
                self.entity_id,
                "available" if new_availability else "unavailable",
                availability_delta,
            )
            self._available = new_availability
            self.async_schedule_update_ha_state()

    def set_state(self, new_state, ignore_tracing=False):
        """Set the state of the sensor.

        The newest value is always kept in native_value. It is written to Home
        Assistant at most once per update interval, and only if it differs from
        what Home Assistant was last given.
        """
        self._attr_native_value = new_state
        self._last_seen = self._clock()

        if not self._ready:
            # Not yet added to Home Assistant: keep the value, which HA reads when
            # the entity is added, instead of dropping the first measurement.
            self._written_value = new_state
            self._available = True
            return

        now = datetime.now()

        should_update = False
        if not self._available:
            self._available = True
            should_update = True
            if not ignore_tracing:
                _LOGGER.debug("Setting sensor:'%s' as available", self.entity_id)

        if (not should_update) and (now - self._last_updated) < self.update_frequncy:
            # Too soon since the last write; the next message after the interval
            # writes the then-current value.
            _LOGGER.debug(
                "Skipping update for sensor:'%s' as of update frequency", self.entity_id
            )
            return

        if new_state != self._written_value:
            if not ignore_tracing:
                _LOGGER.debug(
                    "Setting state for sensor: '%s' to %s from %s",
                    self.entity_id,
                    new_state,
                    self._written_value,
                )
            should_update = True

        if should_update:
            self._last_updated = now
            self._written_value = new_state
            self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant."""
        # Now self.hass is available!
        _LOGGER.debug("async_added_to_hass called on: %s", self.entity_id)
        await super().async_added_to_hass()
        self._ready = True

    async def async_will_remove_from_hass(self):
        _LOGGER.debug("async_will_remove_from_hass called on: %s", self.entity_id)
        await super().async_will_remove_from_hass()
        self._ready = False
