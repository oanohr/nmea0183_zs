"""NMEA 0183 Integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.start import async_at_start

from .hub import Hub

PLATFORMS: list[Platform] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.info("Options for NMEA0183 have been updated - applying changes")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info("Setting up NMEA0183 integration entry: %s", entry.title)

    hub = Hub(hass, entry)
    entry.runtime_data = hub

    entry.async_on_unload(entry.add_update_listener(_update_listener))
    # Removed again when the entry unloads, so reloads do not pile up stop listeners
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, hub.stop)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start the hub AFTER the sensor platform is set up so that entities are
    # ready (async_added_to_hass has fired) before sentences update them.
    entry.async_on_unload(async_at_start(hass, hub.start))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unloading NMEA0183 integration entry: %s", entry.title)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # If the platforms stayed loaded the entities still belong to this hub: keep it
    if unload_ok:
        hub = entry.runtime_data
        if hub is not None:
            await hub.stop()

    return unload_ok
