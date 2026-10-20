"""Turn parsed NMEA 0183 sentences into sensor readings.

Reading keys follow the naming standard: <sentence>_<field>, e.g. gga_long_decimal.
The hub prefixes the key with the hub name, which gives entity ids like
sensor.bas_zs1477_gga_long_decimal. The talker (GP/GN/...) is deliberately not
part of the key for most sentences. GSV and GSA are the exception: they carry one
sensor per constellation, because their values describe a single constellation.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

import pynmea2

_LOGGER = logging.getLogger(__name__)

SUPPORTED_SENTENCES = ("GGA", "RMC", "VTG", "GSA", "GST", "GSV", "HDT")

GSA_FIX_TYPE = {1: "No fix", 2: "2D", 3: "3D"}

# GGA field 6 (GPS quality indicator)
GGA_FIX = {
    0: "No fix",
    1: "GPS",
    2: "DGPS",
    3: "PPS",
    4: "RTK fixed",
    5: "RTK float",
    6: "Estimated",
    7: "Manual",
    8: "Simulation",
}

# NMEA 4.11 GSA "GNSS system ID" field, used when the talker is the combined GN
GSA_SYSTEM = {1: "gp", 2: "gl", 3: "ga", 4: "gb", 5: "gq", 6: "gi"}


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
    quality = _int(msg.gps_qual)
    # gga_lat/gga_long are the position as reported. The decimal position is only
    # given while the receiver claims a fix, so a last-known position sent with
    # quality 0 is never shown as the current one.
    usable = quality is not None and quality > 0
    return [
        Reading("gga_lat", _raw(msg, "lat"), numeric=True),
        Reading("gga_long", _raw(msg, "lon"), numeric=True),
        Reading("gga_lat_decimal", _decimal(msg, "latitude") if usable else None, "°"),
        Reading("gga_long_decimal", _decimal(msg, "longitude") if usable else None, "°"),
        # GGA field 9: orthometric height (MSL reference)
        Reading("gga_msl", _float(msg.altitude), "m"),
        Reading("gga_geoide", _float(msg.geo_sep), "m"),
        Reading("gga_gps_quality", quality, numeric=True),
        Reading("gga_fix", GGA_FIX.get(quality, str(quality)) if quality is not None else None),
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


def _gsa_system(msg) -> str:
    """Constellation a GSA sentence describes: talker, or the NMEA 4.11 system ID for GN."""
    talker = msg.talker.lower()
    if talker != "gn":
        return talker
    try:
        system_id = _int(msg.data[17])  # field after VDOP, absent before NMEA 4.11
    except IndexError:
        return talker
    return GSA_SYSTEM.get(system_id, talker) if system_id is not None else talker


def _gsa(msg) -> list[Reading]:
    fix = _int(msg.mode_fix_type)
    fields = (
        ("fix_type", GSA_FIX_TYPE.get(fix, str(fix)) if fix is not None else None, False),
        ("pdop", _float(msg.pdop), True),
        ("hdop", _float(msg.hdop), True),
        ("vdop", _float(msg.vdop), True),
    )
    system = _gsa_system(msg)
    readings = [Reading(f"gsa_{system}_{name}", value, numeric=n) for name, value, n in fields]
    # gsa_fix_type/pdop/hdop/vdop keep their ids: they follow the primary system (GPS), or
    # the combined GN solution when the receiver sends no per-system sentences. Other
    # systems no longer overwrite them.
    if system in ("gp", "gn"):
        readings += [Reading(f"gsa_{name}", value, numeric=n) for name, value, n in fields]
    return readings


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
