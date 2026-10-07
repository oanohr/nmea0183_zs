# 📡 Home Assistant NMEA 0183 Integration

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](http://www.apache.org/licenses/LICENSE-2.0)

A Home Assistant integration that reads NMEA 0183 sentences from a plain TCP stream and turns them into sensors. Built for GNSS receivers such as the [Septentrio mosaic-X5](https://www.septentrio.com/en/products/gnss-receivers/gnss-receiver-modules/mosaic-x5), but works with any source that serves NMEA 0183 over TCP. Parsing is done with [pynmea2](https://github.com/Knio/pynmea2).

This project is a fork of [tomer-w/ha-nmea2000](https://github.com/tomer-w/ha-nmea2000), rewritten for NMEA 0183.

## ✨ Features

- Sensor entity ids are `sensor.<name>_<sentence>_<field>`, e.g. `sensor.bas_zs1477_gga_long_decimal`
- Checksum verification; invalid lines are ignored
- Automatic reconnect if the receiver or network drops
- Include/exclude filter on sentence types and a throttle for how often sensors update

### Supported sentences

| Sentence | Sensors |
|----------|---------|
| GGA | `gga_lat`, `gga_long` (as sent, ddmm.mmmm, numeric, negative for S/W), `gga_lat_decimal`, `gga_long_decimal`, `gga_msl` (orthometric height), `gga_geoide`, `gga_gps_quality` (numeric), `gga_satview`, `gga_age` |
| RMC | `rmc_utc`, `rmc_status`, `rmc_speed` (kn), `rmc_course` |
| VTG | `vtg_track_true`, `vtg_track_mag`, `vtg_speed_kn`, `vtg_speed_kmh` |
| GSA | `gsa_fix_type`, `gsa_pdop`, `gsa_hdop`, `gsa_vdop` |
| GST | `gst_rms`, `gst_std_major`, `gst_std_minor`, `gst_std_lat`, `gst_std_long`, `gst_std_msl` |
| GSV | `gsv_<talker>_satview` (one per constellation) |
| HDT | `hdt_heading` |

Other sentences are counted in the message statistics but produce no sensors.

## 🔧 Receiver setup (Septentrio mosaic-X5)

The receiver must serve NMEA 0183 on a TCP (IP server) port. In the mosaic-X5 web UI, configure an IP server port and an NMEA output stream on it with the sentences you want (see the Septentrio mosaic-X5 Reference Guide for the exact commands). Enable at least `GGA` and `RMC`; add `GST` if you want the receiver's own precision estimate.


## 🛠 Installation

1. Copy `custom_components/nmea0183` into `/config/custom_components/` (or add this repository to HACS as a custom repository).
2. Restart Home Assistant.
3. Go to Settings → Devices & Services → + Add Integration and search for **NMEA 0183**.
4. Enter a name, the receiver's IP address and the TCP port. The integration checks that it can connect.
5. Optionally restrict which sentences to use (e.g. include `GGA,RMC`) and set the minimum number of milliseconds between sensor updates.

# Acknowledgements

- Forked from [tomer-w/ha-nmea2000](https://github.com/tomer-w/ha-nmea2000). Thanks to Rob from [Smart Boat Innovations](https://github.com/SmartBoatInnovations/) whose code was the initial inspiration for that project.
- NMEA 0183 parsing by [pynmea2](https://github.com/Knio/pynmea2).
