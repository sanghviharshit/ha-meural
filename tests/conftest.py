"""Shared fixtures for ha-meural tests.

We stub the ``homeassistant`` package at the sys.modules level so that
``pymeural.py`` and ``media_player.py`` can be imported without a full HA
installation.  The stubs provide just enough structure for the code under test
to work correctly.
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock
import pytest


# ---------------------------------------------------------------------------
# Build minimal homeassistant stubs BEFORE any component code is imported.
# ---------------------------------------------------------------------------

def _make_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Real exception base so our custom exceptions are proper classes.
class HomeAssistantError(Exception):
    """Minimal stub for homeassistant.exceptions.HomeAssistantError."""


# homeassistant.exceptions
_ha_exc = _make_module("homeassistant.exceptions")
_ha_exc.HomeAssistantError = HomeAssistantError

# homeassistant (top-level)
_ha = _make_module("homeassistant")
_ha.exceptions = _ha_exc

# homeassistant.const
_ha_const = _make_module("homeassistant.const")
_ha_const.STATE_PLAYING = "playing"
_ha_const.STATE_PAUSED = "paused"
_ha_const.STATE_OFF = "off"
_ha_const.MAJOR_VERSION = 2024
_ha_const.MINOR_VERSION = 1

# homeassistant.config_entries
_ha_cfg = _make_module("homeassistant.config_entries")
_ha_cfg.ConfigEntry = MagicMock
_ha_cfg.ConfigFlow = MagicMock
_ha_cfg.CONN_CLASS_CLOUD_POLL = "cloud_poll"

# homeassistant.core
_ha_core = _make_module("homeassistant.core")
_ha_core.HomeAssistant = MagicMock
_ha_core.callback = lambda f: f

# homeassistant.helpers.*
_ha_helpers = _make_module("homeassistant.helpers")
_ha_aiohttp = _make_module("homeassistant.helpers.aiohttp_client")
_ha_aiohttp.async_get_clientsession = MagicMock(return_value=AsyncMock())
_ha_network = _make_module("homeassistant.helpers.network")
_ha_network.get_url = MagicMock(return_value="http://homeassistant.local:8123")
_make_module("homeassistant.helpers.entity_platform")

# homeassistant.components.*
_make_module("homeassistant.components")
_make_module("homeassistant.components.http")
_ha_http_auth = _make_module("homeassistant.components.http.auth")
_ha_http_auth.async_sign_path = MagicMock(return_value="/signed/path")

# media_player sub-modules (need real-ish values for MediaClass / MediaType)
_mp = _make_module("homeassistant.components.media_player")
_mp.MediaPlayerEntity = object          # base class
_mp.BrowseError = Exception
_mp.BrowseMedia = MagicMock

_mp_types = _make_module("homeassistant.components.media_player.const")
_mp_types.MediaPlayerEntityFeature = MagicMock()

# Provide MediaClass / MediaType as simple namespace objects
class _NS:
    def __getattr__(self, item):
        return item

_mp.MediaClass = _NS()
_mp.MediaType = _NS()

# media_source
_ms = _make_module("homeassistant.components.media_source")
_ms.is_media_source_id = MagicMock(return_value=False)
_ms.async_browse_media = AsyncMock()
_ms.async_resolve_media = AsyncMock()

# homeassistant.auth
_ha_auth = _make_module("homeassistant.auth")
_ha_auth_models = _make_module("homeassistant.auth.models")
_ha_auth_models.RefreshToken = MagicMock

# ---------------------------------------------------------------------------
# Now it is safe to import the integration code.
# ---------------------------------------------------------------------------
from custom_components.meural.pymeural import LocalMeural, PyMeural  # noqa: E402

# Re-export constants so test modules can import them directly.
STATE_PLAYING = _ha_const.STATE_PLAYING
STATE_PAUSED = _ha_const.STATE_PAUSED
STATE_OFF = _ha_const.STATE_OFF


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

DEVICE = {
    "id": "device-1",
    "alias": "My Canvas",
    "name": "Meural Canvas",
    "productKey": "ABC123",
    "localIp": "192.168.1.100",
    "status": "online",
    "version": "5.0.0",
    "frameModel": {"name": "Canvas II"},
    "imageDuration": 1800,
    "imageShuffle": False,
    "gestureFlip": False,
    "orientation": "landscape",
    "sleep": False,
}

GALLERY_STATUS = {
    "current_gallery": "10",
    "current_gallery_name": "Impressionism",
    "current_item": "42",
}

ITEM = {
    "id": 42,
    "name": "Starry Night",
    "artistName": "Vincent van Gogh",
    "author": None,
    "year": "1889",
    "image": "https://example.com/starry-night.jpg",
    "description": "A swirling night sky.",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    """Return a mock aiohttp ClientSession."""
    return AsyncMock()


@pytest.fixture
def py_meural(mock_session):
    """Return a PyMeural instance with mocked session and pre-set token."""
    callback = MagicMock()
    return PyMeural(
        username="user@example.com",
        password="password",
        token="existing-token",
        token_update_callback=callback,
        session=mock_session,
    )


@pytest.fixture
def local_meural(mock_session):
    """Return a LocalMeural instance with mocked session."""
    return LocalMeural(dict(DEVICE), mock_session)
