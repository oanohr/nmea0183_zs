# Copilot Instructions for nmea0183_zs

## Mandatory compliance policy

Before modifying this repository, read `/AI_REPOSITORY_POLICY.md`.

The license, provenance, NMEA intellectual-property, dependency, supply-chain and security rules in that file are mandatory. If a proposed change has uncertain provenance or licensing, stop and request human review. Never remove upstream attribution or copy protected NMEA standard material merely to complete a task.

This repository is derived in part from `tomer-w/ha-nmea2000` (Apache-2.0). Preserve applicable provenance and modified-file notices; see `NOTICE` and `THIRD_PARTY_NOTICES.md`.

## Project Overview

This is a Home Assistant custom integration that reads NMEA 0183 sentences from a TCP stream and exposes them as HA sensors.

## Project Structure

- `custom_components/nmea0183/` — Integration source code
  - `__init__.py` — Integration setup and entry points
  - `client.py` — Async TCP client: connect, read lines, parse with pynmea2, reconnect
  - `sentences.py` — Maps parsed sentences (GGA, RMC, ...) to sensor readings
  - `hub.py` — Orchestrates client, sensor creation and statistics sensors
  - `NMEA0183Sensor.py` — Sensor entity class
  - `config_flow.py` — Configuration UI flow
  - `const.py` — Constants and configuration keys
- `tests/` — Pytest test suite
- `AI_REPOSITORY_POLICY.md` — mandatory AI/commercial compliance rules
- `NOTICE` and `THIRD_PARTY_NOTICES.md` — provenance and third-party notices
- `.devcontainer/` — Dev container configuration for Linux-based development

## Key Dependencies

- `pynmea2` (MIT licensed; listed in `requirements.txt` and `manifest.json`)
- `pytest-homeassistant-custom-component` for testing (listed in `requirements_test.txt`)

## Testing

Tests depend on `pytest-homeassistant-custom-component` which requires Linux. Run them in Docker using the devcontainer image:

```bash
docker run --rm -v "${PWD}:/workspace" -w /workspace mcr.microsoft.com/devcontainers/python:3.13 bash -c "pip install --quiet -r requirements.txt -r requirements_test.txt 2>&1 | tail -3 && pytest tests/ -v 2>&1"
```

Always run tests after making code changes and before committing.

Any new dependency requires license/provenance review per `AI_REPOSITORY_POLICY.md`.

## CI/CD

- `.github/workflows/validate.yaml` — Runs HACS validation, hassfest, ruff lint and pytest on push/PR.

## Code Conventions

- Entity ID sanitization (spaces, hyphens → underscores) happens in `NMEA0183Sensor.__init__`, not in the hub.
- `hub.py` passes raw names as `sensor_id` to `NMEA0183Sensor`; the sensor class handles all ID normalization.
- To support a new sentence, add an extractor in `sentences.py` and a test in `tests/test_sentences.py`.
- Use `pyproject.toml` for all project metadata (PEP 621). No `setup.py`.
- Treat TCP/NMEA input as untrusted.
- Do not copy official NMEA 0183 standard text or tables into source or documentation without documented redistribution rights.
