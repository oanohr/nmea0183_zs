"""Turn parsed NMEA 0183 sentences into sensor readings.

Reading keys follow the naming standard: <sentence>_<field>, e.g. gga_long_decimal.
The hub prefixes the key with the hub name, which gives entity ids like
sensor.bas_zs1477_gga_long_decimal. The talker (GP/GN/...) is deliberately not
part of the key, so the same value from different talkers shares one sensor.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

import pynmea2

_LOGGER = logging.getLogger(__name__)

SUPPORTED_SENTENCES = ("GGA", "RMC", "VTG", "GSA", "GST", "GSV", "HDT")

GSA_FIX_TYPE = {1: "No fix", 2: "2D", 3: "3D"}


@dataclass(frozen=True)
class Reading:
    """One value extracted from a sentence."""

    key: str
    value: str | int | float | None
    unit: str | None = None
    # True for unitless numbers, so they get a state class (graph) even without a value yet
    numeric: bool = False

    @property
    def name(self) -> str:
        """Friendly name whose slug is the key, e.g. 'GGA long decimal'."""
        first, *rest = self.key.split("_")
        return " ".join([first.upper(), *rest])


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal(msg, attr: str) -> float | None:
    """Decimal degrees, or None while the receiver has no position."""
    if not getattr(msg, attr[:3]):  # lat / lon raw field is empty without a fix
        return None
    try:
        return round(getattr(msg, attr), 8)
    except (TypeError, ValueError):
        return None


def _raw(msg, attr: str) -> float | None:
    """The coordinate as sent (ddmm.mmmm / dddmm.mmmm) as a number, negative for S and W."""
    number = _float(getattr(msg, attr))
    if number is None:
        return None
    return -number if getattr(msg, attr + "_dir") in ("S", "W") else number


def _gga(msg) -> list[Reading]:
    return [
        Reading("gga_lat", _raw(msg, "lat"), numeric=True),
        Reading("gga_long", _raw(msg, "lon"), numeric=True),
        Reading("gga_lat_decimal", _decimal(msg, "latitude"), "°"),
        Reading("gga_long_decimal", _decimal(msg, "longitude"), "°"),
        # GGA field 9: orthometric height (MSL reference)
        Reading("gga_msl", _float(msg.altitude), "m"),
        Reading("gga_geoide", _float(msg.geo_sep), "m"),
        Reading("gga_gps_quality", _int(msg.gps_qual), numeric=True),
        Reading("gga_satview", _int(msg.num_sats), numeric=True),
        Reading("gga_age", _float(msg.age_gps_data), "s"),
    ]


def _rmc(msg) -> list[Reading]:
    try:
        stamp = msg.datetime.isoformat() if msg.datestamp and msg.timestamp else None
    except (TypeError, ValueError, AttributeError):
        stamp = None
    return [
        Reading("rmc_utc", stamp),
        Reading("rmc_status", "Valid" if msg.status == "A" else "Warning"),
        Reading("rmc_speed", _float(msg.spd_over_grnd), "kn"),
        Reading("rmc_course", _float(msg.true_course), "°"),
    ]


def _vtg(msg) -> list[Reading]:
    return [
        Reading("vtg_track_true", _float(msg.true_track), "°"),
        Reading("vtg_track_mag", _float(msg.mag_track), "°"),
        Reading("vtg_speed_kn", _float(msg.spd_over_grnd_kts), "kn"),
        Reading("vtg_speed_kmh", _float(msg.spd_over_grnd_kmph), "km/h"),
    ]


def _gsa(msg) -> list[Reading]:
    fix = _int(msg.mode_fix_type)
    return [
        Reading(
            "gsa_fix_type",
            GSA_FIX_TYPE.get(fix, str(fix)) if fix is not None else None,
        ),
        Reading("gsa_pdop", _float(msg.pdop), numeric=True),
        Reading("gsa_hdop", _float(msg.hdop), numeric=True),
        Reading("gsa_vdop", _float(msg.vdop), numeric=True),
    ]


def _gst(msg) -> list[Reading]:
    return [
        Reading("gst_rms", _float(msg.rms), "m"),
        Reading("gst_std_major", _float(msg.std_dev_major), "m"),
        Reading("gst_std_minor", _float(msg.std_dev_minor), "m"),
        Reading("gst_std_lat", _float(msg.std_dev_latitude), "m"),
        Reading("gst_std_long", _float(msg.std_dev_longitude), "m"),
        Reading("gst_std_msl", _float(msg.std_dev_altitude), "m"),
    ]


def _gsv(msg) -> list[Reading]:
    # One sensor per constellation talker (GP, GL, GA, GB, ...)
    return [
        Reading(f"gsv_{msg.talker.lower()}_satview", _int(msg.num_sv_in_view), numeric=True),
    ]


def _hdt(msg) -> list[Reading]:
    return [Reading("hdt_heading", _float(msg.heading), "°")]


_EXTRACTORS = {
    "GGA": _gga,
    "RMC": _rmc,
    "VTG": _vtg,
    "GSA": _gsa,
    "GST": _gst,
    "GSV": _gsv,
    "HDT": _hdt,
}


def extract_readings(msg: pynmea2.NMEASentence) -> list[Reading]:
    """Return the readings for a sentence; empty for unsupported sentence types."""
    extractor = _EXTRACTORS.get(getattr(msg, "sentence_type", None))
    if extractor is None:
        return []
    try:
        return extractor(msg)
    except (AttributeError, IndexError, TypeError, ValueError) as err:
        _LOGGER.debug("Could not extract readings from %r: %s", msg, err)
        return []
