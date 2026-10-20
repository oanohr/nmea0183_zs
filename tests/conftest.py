"""Fixtures for ha-nmea0183 tests."""
import pytest
from unittest.mock import patch

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield


@pytest.fixture
def bypass_setup_entry():
    """Prevent async_setup_entry from running; request this in config flow tests only."""
    with patch(
        "custom_components.nmea0183.async_setup_entry", return_value=True
    ):
        yield
