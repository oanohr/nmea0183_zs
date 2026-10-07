# Copilot Instructions for nmea0183_zs

## Mandatory compliance policy

Before modifying this repository, read `/AI_REPOSITORY_POLICY.md`.

The license, provenance, NMEA intellectual-property, dependency, supply-chain and security rules in that file are mandatory. If a proposed change has uncertain provenance or licensing, stop and request human review. Never remove upstream attribution or copy protected NMEA standard material merely to complete a task.

## Project Overview

This is a Home Assistant custom integration that reads NMEA 0183 sentences from a TCP stream and exposes them as HA sensors.

This repository is derived in part from `tomer-w/ha-nmea2000` (Apache-2.0). Preserve applicable provenance and modified-file notices.

## Project Structure

- `custom_components/nmea0183/` — integration source
- `tests/` — pytest suite
- `AI_REPOSITORY_POLICY.md` — mandatory AI/commercial compliance rules
- `NOTICE` and `THIRD_PARTY_NOTICES.md` — provenance and third-party notices

## Key Dependencies

- `pynmea2==1.19.0` — runtime NMEA parser, MIT licensed
- `pytest-homeassistant-custom-component` — testing

Any new dependency requires license/provenance review per `AI_REPOSITORY_POLICY.md`.

## Testing

Run tests after code changes and before committing:

```bash
docker run --rm -v "${PWD}:/workspace" -w /workspace mcr.microsoft.com/devcontainers/python:3.13 bash -c "pip install --quiet -r requirements.txt -r requirements_test.txt 2>&1 | tail -3 && pytest tests/ -v 2>&1"
```

## Code conventions

- Entity ID sanitization happens in `NMEA0183Sensor.__init__`.
- `hub.py` passes raw sensor names to the sensor class.
- New sentence support belongs in `sentences.py` with tests in `tests/test_sentences.py`.
- Treat TCP/NMEA input as untrusted.
- Do not copy official NMEA 0183 standard text/tables into source or documentation without documented redistribution rights.
