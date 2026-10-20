"""Tests for NMEA 0183 sentence parsing and reading extraction."""
import pynmea2

from custom_components.nmea0183.client import Nmea0183TcpClient
from custom_components.nmea0183.sentences import extract_readings


def _checksum(body: str) -> str:
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"${body}*{cs:02X}"


def _values(sentence: str) -> dict:
    return {r.key: r.value for r in extract_readings(pynmea2.parse(sentence))}


GGA = _checksum("GNGGA,123519.00,5959.1234567,N,01049.7654321,E,4,12,0.8,45.6,M,39.1,M,1.0,0000")
RMC = _checksum("GNRMC,123519.00,A,5959.1234567,N,01049.7654321,E,0.05,84.4,230394,,,A,V")
VTG = _checksum("GNVTG,84.4,T,,M,0.05,N,0.09,K,A")
GSA = _checksum("GNGSA,A,3,01,02,03,04,05,06,,,,,,,1.4,0.8,1.1,1")
GST = _checksum("GNGST,123519.00,0.5,0.01,0.01,45.0,0.012,0.010,0.025")
GSV = _checksum("GPGSV,3,1,10,01,40,083,46,02,17,308,41,12,07,344,39,14,22,228,45,0")
HDT = _checksum("GNHDT,274.07,T")


def test_gga():
    values = _values(GGA)
    assert abs(values["gga_lat_decimal"] - (59 + 59.1234567 / 60)) < 1e-7
    assert abs(values["gga_long_decimal"] - (10 + 49.7654321 / 60)) < 1e-7
    assert values["gga_msl"] == 45.6
    assert values["gga_gps_quality"] == 4
    assert values["gga_lat"] == 5959.1234567
    assert values["gga_long"] == 1049.7654321
    assert values["gga_geoide"] == 39.1
    assert values["gga_age"] == 1.0
    assert values["gga_satview"] == 12


def test_gga_without_fix_has_no_position():
    values = _values(_checksum("GNGGA,123519.00,,,,,0,00,99.99,,M,,M,,"))
    assert values["gga_lat_decimal"] is None
    assert values["gga_long_decimal"] is None
    assert values["gga_gps_quality"] == 0


def test_rmc():
    values = _values(RMC)
    assert values["rmc_speed"] == 0.05
    assert values["rmc_course"] == 84.4
    assert values["rmc_status"] == "Valid"
    assert values["rmc_utc"].startswith("1994-03-23T12:35:19")


def test_vtg():
    values = _values(VTG)
    assert values["vtg_track_true"] == 84.4
    assert values["vtg_speed_kn"] == 0.05
    assert values["vtg_speed_kmh"] == 0.09


def test_gsa():
    values = _values(GSA)
    assert values["gsa_fix_type"] == "3D"
    assert values["gsa_pdop"] == 1.4
    assert values["gsa_hdop"] == 0.8
    assert values["gsa_vdop"] == 1.1


def test_gst():
    values = _values(GST)
    assert values["gst_std_lat"] == 0.012
    assert values["gst_std_long"] == 0.010
    assert values["gst_std_msl"] == 0.025


def test_gsv_and_hdt():
    assert _values(GSV)["gsv_gp_satview"] == 10
    assert _values(HDT)["hdt_heading"] == 274.07


def test_unsupported_sentence_yields_nothing():
    gll = _checksum("GNGLL,5959.12,N,01049.76,E,123519.00,A,A")
    assert extract_readings(pynmea2.parse(gll)) == []


# --- GNSS solution validity (#6) ---

def _gga(quality: str, lat="5959.1234567,N", lon="01049.7654321,E") -> dict:
    return _values(_checksum(f"GNGGA,123519.00,{lat},{lon},{quality},12,0.8,45.6,M,39.1,M,1.0,0000"))


def test_gga_fix_labels_rtk_fixed_and_float():
    assert _gga("4")["gga_fix"] == "RTK fixed"
    assert _gga("5")["gga_fix"] == "RTK float"
    assert _gga("1")["gga_fix"] == "GPS"
    assert _gga("4")["gga_lat_decimal"] is not None
    assert _gga("5")["gga_lat_decimal"] is not None


def test_gga_quality_zero_hides_decimal_position_but_keeps_raw():
    values = _gga("0")
    assert values["gga_fix"] == "No fix"
    assert values["gga_lat_decimal"] is None
    assert values["gga_long_decimal"] is None
    assert values["gga_lat"] == 5959.1234567
    assert values["gga_long"] == 1049.7654321


def test_gga_missing_quality_is_unknown_and_hides_position():
    values = _values(_checksum("GNGGA,123519.00,5959.1234567,N,01049.7654321,E,,,,,M,,M,,"))
    assert values["gga_fix"] is None
    assert values["gga_gps_quality"] is None
    assert values["gga_lat_decimal"] is None


def test_gga_missing_fields_do_not_raise():
    values = _values(_checksum("GNGGA,,,,,,,,,,M,,M,,"))
    assert values["gga_fix"] is None
    assert values["gga_lat"] is None


def test_rmc_invalid_status_is_warning():
    values = _values(_checksum("GNRMC,123519.00,V,,,,,,,230394,,,N,V"))
    assert values["rmc_status"] == "Warning"


# --- multi-constellation GSA (#6) ---

def _gsa(talker: str, hdop: str, system: str | None = None, fix: str = "3") -> dict:
    tail = f",{system}" if system else ""
    return _values(_checksum(f"{talker}GSA,A,{fix},01,02,03,,,,,,,,,,1.4,{hdop},1.1{tail}"))


def test_gsa_primary_system_uses_the_plain_keys_and_others_get_their_own():
    gp, gl = _gsa("GP", "0.8"), _gsa("GL", "1.9")
    assert gp["gsa_hdop"] == 0.8 and gl["gsa_gl_hdop"] == 1.9
    assert "gsa_gl_hdop" not in gp and "gsa_hdop" not in gl
    assert "gsa_ga_hdop" in _gsa("GA", "1.2") and "gsa_hdop" not in _gsa("GA", "1.2")


def test_gsa_never_publishes_the_same_value_under_two_keys():
    for talker, system in [("GP", None), ("GL", None), ("GN", None), ("GN", "1"), ("GN", "3")]:
        keys = list(_gsa(talker, "0.8", system))
        assert len(keys) == len(set(keys)) == 4
        assert not ({"gsa_hdop", "gsa_gp_hdop"} <= set(keys))
        assert not ({"gsa_hdop", "gsa_gn_hdop"} <= set(keys))


def test_gsa_gn_with_system_id_splits_systems():
    gps = _gsa("GN", "0.8", "1")
    glonass = _gsa("GN", "1.9", "2")
    galileo = _gsa("GN", "1.2", "3")
    assert gps["gsa_hdop"] == 0.8 and "gsa_gp_hdop" not in gps
    assert glonass["gsa_gl_hdop"] == 1.9 and "gsa_hdop" not in glonass
    assert galileo["gsa_ga_hdop"] == 1.2 and "gsa_hdop" not in galileo


def test_gsa_gn_without_system_id_is_combined_solution():
    values = _gsa("GN", "0.6")
    assert values["gsa_hdop"] == 0.6 and "gsa_gn_hdop" not in values


def test_gsa_interleaved_sequence_keeps_aggregate_stable():
    """GPS, GLONASS, Galileo interleaved: the aggregate is never overwritten by the others."""
    latest = {}
    for talker, hdop, system in [("GN", "0.8", "1"), ("GN", "1.9", "2"), ("GN", "1.2", "3"),
                                 ("GN", "0.7", "1"), ("GN", "2.0", "2")]:
        latest.update(_gsa(talker, hdop, system))
    assert latest["gsa_hdop"] == 0.7
    assert latest["gsa_gl_hdop"] == 2.0 and latest["gsa_ga_hdop"] == 1.2


def test_gsa_no_fix_keeps_fix_type_per_system():
    assert _gsa("GP", "99.99", fix="1")["gsa_fix_type"] == "No fix"
    assert _gsa("GL", "99.99", fix="1")["gsa_gl_fix_type"] == "No fix"


# --- client line parsing ---

def test_parse_line_accepts_valid_sentence():
    msg = Nmea0183TcpClient("h", 1).parse_line(GGA + "\r\n")
    assert msg is not None and msg.sentence_type == "GGA"


def test_parse_line_rejects_bad_checksum_and_garbage():
    client = Nmea0183TcpClient("h", 1)
    assert client.parse_line(GGA[:-2] + "00") is None
    assert client.parse_line("not nmea") is None
    assert client.parse_line("") is None


def test_parse_line_include_and_exclude():
    assert Nmea0183TcpClient("h", 1, include_sentences=["RMC"]).parse_line(GGA) is None
    assert Nmea0183TcpClient("h", 1, include_sentences=["GGA"]).parse_line(GGA) is not None
    assert Nmea0183TcpClient("h", 1, exclude_sentences=["GGA"]).parse_line(GGA) is None


def test_reading_names_slugify_back_to_keys():
    """Entity ids come from the friendly name, so its slug must equal the key."""
    from homeassistant.util import slugify

    for sentence in (GGA, RMC, VTG, GSA, GST, GSV, HDT):
        for reading in extract_readings(pynmea2.parse(sentence)):
            assert slugify(reading.name) == reading.key
