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
    assert abs(values["latitude"] - (59 + 59.1234567 / 60)) < 1e-7
    assert abs(values["longitude"] - (10 + 49.7654321 / 60)) < 1e-7
    assert values["altitude"] == 45.6
    assert values["fix_quality"] == "RTK fixed"
    assert values["satellites_used"] == 12
    assert values["hdop"] == 0.8


def test_gga_without_fix_has_no_position():
    values = _values(_checksum("GNGGA,123519.00,,,,,0,00,99.99,,M,,M,,"))
    assert values["latitude"] is None
    assert values["longitude"] is None
    assert values["fix_quality"] == "No fix"


def test_rmc():
    values = _values(RMC)
    assert values["speed_over_ground"] == 0.05
    assert values["course_over_ground"] == 84.4
    assert values["status"] == "Valid"
    assert values["utc_time"].startswith("1994-03-23T12:35:19")


def test_vtg():
    values = _values(VTG)
    assert values["track_true"] == 84.4
    assert values["speed_knots"] == 0.05
    assert values["speed_kmh"] == 0.09


def test_gsa():
    values = _values(GSA)
    assert values["fix_type"] == "3D"
    assert values["pdop"] == 1.4
    assert values["hdop"] == 0.8
    assert values["vdop"] == 1.1


def test_gst():
    values = _values(GST)
    assert values["std_latitude"] == 0.012
    assert values["std_longitude"] == 0.010
    assert values["std_altitude"] == 0.025


def test_gsv_and_hdt():
    assert _values(GSV)["satellites_in_view"] == 10
    assert _values(HDT)["heading_true"] == 274.07


def test_unsupported_sentence_yields_nothing():
    gll = _checksum("GNGLL,5959.12,N,01049.76,E,123519.00,A,A")
    assert extract_readings(pynmea2.parse(gll)) == []


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
