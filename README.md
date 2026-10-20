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
| GGA | `gga_lat`, `gga_long` (as sent, ddmm.mmmm, numeric, negative for S/W), `gga_lat_decimal`, `gga_long_decimal`, `gga_msl` (orthometric height), `gga_geoide`, `gga_gps_quality` (numeric), `gga_fix` (text), `gga_satview`, `gga_age` |
| RMC | `rmc_utc`, `rmc_status`, `rmc_speed` (kn), `rmc_course` |
| VTG | `vtg_track_true`, `vtg_track_mag`, `vtg_speed_kn`, `vtg_speed_kmh` |
| GSA | `gsa_fix_type`, `gsa_pdop`, `gsa_hdop`, `gsa_vdop` (primary system), `gsa_<system>_fix_type/pdop/hdop/vdop` (one set per constellation) |
| GST | `gst_rms`, `gst_std_major`, `gst_std_minor`, `gst_std_lat`, `gst_std_long`, `gst_std_msl` |
| GSV | `gsv_<talker>_satview` (one per constellation) |
| HDT | `hdt_heading` |

Other sentences are counted in the message statistics but produce no sensors.

### Position quality and multi-constellation DOP

- **`gga_lat` / `gga_long`** are the position exactly as the receiver reported it, also when it says it has no fix.
- **`gga_lat_decimal` / `gga_long_decimal`** are the usable position. They are `unknown` while GGA quality is 0 or missing, so a last-known position sent without a fix is not shown as current. Upgrade note: these two used to show whatever coordinates the sentence carried.
- **`gga_fix`** names the quality: `No fix`, `GPS`, `DGPS`, `PPS`, `RTK fixed`, `RTK float`, `Estimated`, `Manual`, `Simulation`. `rmc_status` is `Valid` or `Warning`.
- None of these describe the connection. Use `State` for the TCP link and `Data state` for freshness.
- **GSA** gives one set of sensors per constellation: `gsa_gp_*` (GPS), `gsa_gl_*` (GLONASS), `gsa_ga_*` (Galileo), `gsa_gb_*` (BeiDou), and so on. For the combined `GN` talker the system comes from the NMEA 4.11 system ID field. The old `gsa_fix_type`, `gsa_pdop`, `gsa_hdop` and `gsa_vdop` keep their entity ids and follow GPS, or the combined `GN` solution when the receiver sends no per-system GSA. Other constellations no longer overwrite them.

## ⏱ Receivers that send GGA every 30 seconds

The defaults are made for this case. Leave the two timeouts as they are unless you know the stream is slower:

| Setting | Default | Meaning |
|---------|---------|---------|
| Read timeout | 120 s | No bytes for this long: the connection is dropped and reopened. Four times the 30 s interval, so a few late or lost sentences cause no reconnect. |
| Stale timeout | 120 s | A value older than this becomes `unavailable`, and `Data state` becomes `Stale`. |
| Seconds between updates | 5 s | Lowest rate at which a sensor writes a new value to Home Assistant. |

Example: host `192.168.3.1`, port `28000`, include `GGA,RMC,GSA,GST`, and the three values above as shown.

### What the status sensors mean

| Sensor | Values | Describes |
|--------|--------|-----------|
| `State` | `Initializing`, `Running`, `Disconnected` | The TCP connection only. |
| `Data state` | `Waiting for data`, `Fresh`, `Stale` | Whether sentences arrive in time. A live connection with no data is `Stale`. |
| `gga_fix`, `rmc_status` | see above | The quality of the GNSS solution. |

A change to the settings reloads the integration once. Sensors keep the same entity ids across restarts and reloads.

### Statistics and recorder

| Sensor kind | State class | Long-term statistics |
|-------------|-------------|----------------------|
| `Total message count` | `total_increasing` | Yes. It restarts from 0 whenever the integration starts, and Home Assistant records that as a reset, not as a negative change. |
| Numbers such as `gga_lat_decimal`, `gga_msl`, `gga_satview`, `gsa_hdop`, `vtg_speed_kn` | `measurement` | Yes: mean, min and max per hour. |
| `gga_lat`, `gga_long` (raw `ddmm.mmmm`) | `measurement` | Recorded so Home Assistant draws a graph, but the mean of raw `ddmm.mmmm` values is not a position. Use the `_decimal` sensors for statistics. |
| `gga_gps_quality`, `gga_fix` | number / none | `gga_gps_quality` is a code (4 = RTK fixed), so its mean means little. `gga_fix` holds the same as text and has no statistics. |
| `State`, `Data state`, `rmc_status`, `gsa_*_fix_type` | none | Text; history only. |

Every sensor stores a row in the history each time its value changes, at most once per "seconds between updates". With GGA every 30 s and receiver noise in the last decimals, the position sensors change on every sentence. For many sites, exclude what you do not need from the recorder in `configuration.yaml`, for example:

```yaml
recorder:
  purge_keep_days: 10
  exclude:
    entity_globs:
      - sensor.*_gga_lat
      - sensor.*_gga_long
      - sensor.*_gga_geoide
      - sensor.*_gsa_*_pdop
      - sensor.*_gsa_*_vdop
```

Units are kept as the receiver reports them (`m`, `kn`, `km/h`, `°`, `s`). The sensors have no device class on purpose: with one, Home Assistant could convert and round values for imperial users, which would hide centimetre precision.

### Bad input and diagnostics

- Lines that are not NMEA, have a missing or wrong checksum, or are longer than 1024 bytes are dropped. The connection stays up and the next valid sentence is used as normal.
- Such lines never reach the log as text. Home Assistant gets at most one warning per 5 minutes, with counts. The same limit applies to connection failures: one warning, then a line when the connection is back.
- Going stale is logged once per outage, not once per sensor.
- **Settings > Devices & services > NMEA 0183 > Download diagnostics** shows what the receiver has sent: lines received, accepted, rejected for checksum, malformed, oversized, and seconds since the last accepted line. The host is redacted. These counts are separate from `Total message count`, which only counts sentences that passed the include/exclude filter.

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
