# Copilot Instructions for ha-nmea0183

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
- `.devcontainer/` — Dev container configuration for Linux-based development

## Key Dependencies

- `pynmea2` (listed in `requirements.txt` and `manifest.json`)
- `pytest-homeassistant-custom-component` for testing (listed in `requirements_test.txt`)

## Testing

Tests depend on `pytest-homeassistant-custom-component` which requires Linux. Run them in Docker using the devcontainer image:

```bash
docker run --rm -v "${PWD}:/workspace" -w /workspace mcr.microsoft.com/devcontainers/python:3.13 bash -c "pip install --quiet -r requirements.txt -r requirements_test.txt 2>&1 | tail -3 && pytest tests/ -v 2>&1"
```

Always run tests after making code changes and before committing.

## CI/CD

- `.github/workflows/validate.yaml` — Runs HACS validation, hassfest, and pytest on push/PR.

## Code Conventions

- Entity ID sanitization (spaces, hyphens → underscores) happens in `NMEA0183Sensor.__init__`, not in the hub.
- `hub.py` passes raw names as `sensor_id` to `NMEA0183Sensor`; the sensor class handles all ID normalization.
- To support a new sentence, add an extractor in `sentences.py` and a test in `tests/test_sentences.py`.
- Use `pyproject.toml` for all project metadata (PEP 621). No `setup.py`.
