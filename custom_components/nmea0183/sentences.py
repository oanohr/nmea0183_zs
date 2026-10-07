"""Turn parsed NMEA 0183 sentences into sensor readings."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import pynmea2

_LOGGER = logging.getLogger(__name__)

SUPPORTED_SENTENCES = ("GGA", "RMC", "VTG", "GSA", "GST", "GSV", "HDT")

GPS_QUALITY = {
    0: "No fix",
    1: "GPS",
    2: "DGPS",
    3: "PPS",
    4: "RTK fixed",
    5: "RTK float",
    6: "Dead reckoning",
    7: "Manual",
    8: "Simulation",
}

GSA_FIX_TYPE = {1: "No fix", 2: "2D", 3: "3D"}


@dataclass(frozen=True)
class Reading:
    """One value extracted from a sentence."""

    key: str
    name: str
    value: str | int | float | None
    unit: str | None = None


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


def _coordinate(msg, attr: str) -> float | None:
    """Decimal degrees, or None while the receiver has no position."""
    if not getattr(msg, attr[:3]):  # lat / lon raw field is empty without a fix
        return None
    try:
        return round(getattr(msg, attr), 8)
    except (TypeError, ValueError):
        return None


def _gga(msg) -> list[Reading]:
    quality = _int(msg.gps_qual)
    return [
        Reading("latitude", "Latitude", _coordinate(msg, "latitude"), "°"),
        Reading("longitude", "Longitude", _coordinate(msg, "longitude"), "°"),
        Reading(
            "orthometric_height",
            "Orthometric height (MSL)",
            _float(msg.altitude),
            "m",
        ),
        Reading("geoid_separation", "Geoid separation", _float(msg.geo_sep), "m"),
        Reading(
            "fix_quality",
            "Fix quality",
            GPS_QUALITY.get(quality, str(quality)) if quality is not None else None,
        ),
        Reading("satellites_used", "Satellites used", _int(msg.num_sats)),
        Reading(
            "differential_age", "Differential age", _float(msg.age_gps_data), "s"
        ),
    ]


def _rmc(msg) -> list[Reading]:
    try:
        stamp = msg.datetime.isoformat() if msg.datestamp and msg.timestamp else None
    except (TypeError, ValueError, AttributeError):
        stamp = None
    return [
        Reading("utc_time", "UTC time", stamp),
        Reading("status", "Status", "Valid" if msg.status == "A" else "Warning"),
        Reading("speed_over_ground", "Speed over ground", _float(msg.spd_over_grnd), "kn"),
        Reading("course_over_ground", "Course over ground", _float(msg.true_course), "°"),
    ]


def _vtg(msg) -> list[Reading]:
    return [
        Reading("track_true", "True track", _float(msg.true_track), "°"),
        Reading("track_magnetic", "Magnetic track", _float(msg.mag_track), "°"),
        Reading("speed_knots", "Speed", _float(msg.spd_over_grnd_kts), "kn"),
        Reading("speed_kmh", "Speed", _float(msg.spd_over_grnd_kmph), "km/h"),
    ]


def _gsa(msg) -> list[Reading]:
    fix = _int(msg.mode_fix_type)
    return [
        Reading(
            "fix_type",
            "Fix type",
            GSA_FIX_TYPE.get(fix, str(fix)) if fix is not None else None,
        ),
        Reading("pdop", "PDOP", _float(msg.pdop)),
        Reading("hdop", "HDOP", _float(msg.hdop)),
        Reading("vdop", "VDOP", _float(msg.vdop)),
    ]


def _gst(msg) -> list[Reading]:
    return [
        Reading("rms", "Range residual RMS", _float(msg.rms), "m"),
        Reading("std_major", "Error ellipse semi-major", _float(msg.std_dev_major), "m"),
        Reading("std_minor", "Error ellipse semi-minor", _float(msg.std_dev_minor), "m"),
        Reading("std_latitude", "Latitude error (1σ)", _float(msg.std_dev_latitude), "m"),
        Reading("std_longitude", "Longitude error (1σ)", _float(msg.std_dev_longitude), "m"),
        Reading("std_altitude", "Altitude error (1σ)", _float(msg.std_dev_altitude), "m"),
    ]


def _gsv(msg) -> list[Reading]:
    return [
        Reading("satellites_in_view", "Satellites in view", _int(msg.num_sv_in_view)),
    ]


def _hdt(msg) -> list[Reading]:
    return [Reading("heading_true", "True heading", _float(msg.heading), "°")]


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
