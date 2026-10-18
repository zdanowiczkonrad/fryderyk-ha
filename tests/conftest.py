"""Shared fixtures; HA tests need pytest-homeassistant-custom-component (see scripts/check.sh)."""

import pytest

try:
    import pytest_homeassistant_custom_component  # noqa: F401
except ImportError:  # parser-only runs
    pass
else:

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        yield
