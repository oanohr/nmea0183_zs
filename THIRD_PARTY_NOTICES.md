# Third-Party Notices

This file records known third-party provenance and dependencies for commercial distribution and AI-assisted maintenance.

## tomer-w/ha-nmea2000

- Source: https://github.com/tomer-w/ha-nmea2000
- License: Apache License 2.0
- Role: upstream project from which this repository was forked and substantially rewritten for NMEA 0183.
- Provenance: repository history contains upstream commits and some source files retain substantial upstream structure/code.
- Requirement: preserve applicable copyright, license and attribution notices and mark modified derivative files as changed.

Known derivative or substantially upstream-derived areas include:
- custom_components/nmea0183/NMEA0183Sensor.py
- custom_components/nmea0183/sensor.py
- custom_components/nmea0183/update_integration.sh
- architectural/implementation ancestry in hub.py and config_flow.py

## pynmea2 1.19.0

- Source: https://github.com/Knio/pynmea2
- Package: pynmea2==1.19.0
- License: MIT
- Role: runtime parsing of NMEA 0183 sentences.

The pynmea2 source code is not vendored into this repository. If a future distribution bundles third-party source or package contents, include the license/copyright material required by the MIT license.

## Home Assistant

- Source: https://github.com/home-assistant/core
- License: Apache License 2.0
- Role: platform/API against which this custom integration runs.
- Home Assistant source is not currently vendored by this repository.

## NMEA 0183 standard

NMEA 0183 itself is a separately copyrighted/licensed standard. This repository's Apache-2.0 license does not grant a right to redistribute NMEA's standard text, tables, PDFs, or other protected standard material.

AI agents and contributors must not copy protected NMEA standard material into this repository without documented permission.

## Maintenance rule

Any PR adding a runtime/build dependency, copied external code, generated material based on an external source, or vendor SDK must update this file when attribution or licensing is relevant. Unknown licensing blocks merge pending human review.
