"""Diagnostics for the NMEA 0183 integration (Settings > Devices & services > Download)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """What the receiver has sent, counted per kind, and how fresh the data is."""
    hub = entry.runtime_data
    stats = hub.client.stats
    now = hub.clock()
    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "connection": hub.state,
        "data_state": hub.data_state_sensor.native_value,
        "lines": {
            **{k: v for k, v in stats.as_dict().items() if k != "last_accepted"},
            "seconds_since_last_accepted": (
                None if stats.last_accepted is None else round(now - stats.last_accepted, 1)
            ),
        },
        "messages_delivered": hub.total_messages_sensor.native_value,
        "sensors": len(hub.sensors),
    }
