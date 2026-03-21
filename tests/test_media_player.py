"""Tests for MeuralEntity — state mapping and property critical paths."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# conftest.py builds proper homeassistant stubs before any integration code is
# imported, so these constants are available via sys.modules.
from homeassistant.const import STATE_OFF, STATE_PAUSED, STATE_PLAYING

from custom_components.meural.media_player import MeuralEntity
from tests.conftest import DEVICE, GALLERY_STATUS, ITEM


def make_entity(device_overrides=None, item=None, gallery_status=None, sleep=False):
    """Create a MeuralEntity with controlled state, no real HA or network needed."""
    device = {**DEVICE, **(device_overrides or {})}
    mock_meural = AsyncMock()
    entity = MeuralEntity(mock_meural, device)
    entity._gallery_status = {**GALLERY_STATUS, **(gallery_status or {})}
    entity._current_item = dict(item) if item is not None else dict(ITEM)
    entity._sleep = sleep
    return entity


# ---------------------------------------------------------------------------
# state property
# ---------------------------------------------------------------------------

def test_state_playing_when_awake_and_duration_nonzero():
    """STATE_PLAYING when device is awake and imageDuration > 0."""
    entity = make_entity(sleep=False)
    assert entity.state == STATE_PLAYING


def test_state_paused_when_awake_and_duration_zero():
    """STATE_PAUSED when device is awake but imageDuration is 0."""
    entity = make_entity(device_overrides={"imageDuration": 0}, sleep=False)
    assert entity.state == STATE_PAUSED


def test_state_off_when_sleeping():
    """STATE_OFF when device sleep flag is True."""
    entity = make_entity(sleep=True)
    assert entity.state == STATE_OFF


# ---------------------------------------------------------------------------
# available property
# ---------------------------------------------------------------------------

def test_available_true_when_online():
    entity = make_entity(device_overrides={"status": "online"})
    assert entity.available is True


def test_available_false_when_offline():
    entity = make_entity(device_overrides={"status": "offline"})
    assert entity.available is False


# ---------------------------------------------------------------------------
# media_title
# ---------------------------------------------------------------------------

def test_media_title_returns_item_name():
    entity = make_entity()
    assert entity.media_title == "Starry Night"


def test_media_title_returns_none_when_item_empty():
    entity = make_entity(item={})
    assert entity.media_title is None


# ---------------------------------------------------------------------------
# media_artist
# ---------------------------------------------------------------------------

def test_media_artist_with_artist_name_and_year():
    """Combines artistName and year with a comma."""
    entity = make_entity()
    assert entity.media_artist == "Vincent van Gogh, 1889"


def test_media_artist_with_artist_name_no_year():
    entity = make_entity(item={**ITEM, "year": None})
    assert entity.media_artist == "Vincent van Gogh"


def test_media_artist_falls_back_to_author():
    entity = make_entity(item={**ITEM, "artistName": None, "author": "John Doe", "year": "2000"})
    assert entity.media_artist == "John Doe, 2000"


def test_media_artist_falls_back_to_author_no_year():
    entity = make_entity(item={**ITEM, "artistName": None, "author": "Jane Doe", "year": None})
    assert entity.media_artist == "Jane Doe"


def test_media_artist_unknown_with_year_only():
    entity = make_entity(item={**ITEM, "artistName": None, "author": None, "year": "1800"})
    assert entity.media_artist == "Unknown, 1800"


def test_media_artist_returns_none_when_no_artist_no_author_no_year():
    entity = make_entity(item={**ITEM, "artistName": None, "author": None, "year": None})
    assert entity.media_artist is None


def test_media_artist_returns_none_when_item_empty():
    entity = make_entity(item={})
    assert entity.media_artist is None


# ---------------------------------------------------------------------------
# media_image_url
# ---------------------------------------------------------------------------

def test_media_image_url_returns_item_image():
    entity = make_entity()
    assert entity.media_image_url == "https://example.com/starry-night.jpg"


def test_media_image_url_returns_none_when_item_empty():
    entity = make_entity(item={})
    assert entity.media_image_url is None


# ---------------------------------------------------------------------------
# shuffle / source / unique_id / source_list
# ---------------------------------------------------------------------------

def test_shuffle_reflects_device_setting():
    entity = make_entity(device_overrides={"imageShuffle": True})
    assert entity.shuffle is True


def test_shuffle_false_by_default():
    entity = make_entity()
    assert entity.shuffle is False


def test_source_returns_current_gallery_name():
    entity = make_entity(gallery_status={"current_gallery_name": "Impressionism",
                                         "current_gallery": "10", "current_item": "42"})
    assert entity.source == "Impressionism"


def test_source_list_returns_gallery_names():
    entity = make_entity()
    entity._galleries = [
        {"id": "10", "name": "Impressionism"},
        {"id": "20", "name": "Modern Art"},
    ]
    assert entity.source_list == ["Impressionism", "Modern Art"]


def test_unique_id_returns_product_key():
    entity = make_entity()
    assert entity.unique_id == "ABC123"


def test_name_returns_alias():
    entity = make_entity()
    assert entity.name == "My Canvas"


# ---------------------------------------------------------------------------
# async_update() — abort flag prevents polling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_update_skips_when_aborted():
    """async_update() exits early and makes no API calls when _abort is True."""
    entity = make_entity()
    entity._abort = True
    entity.meural = AsyncMock()

    # Provide a mock local_meural so property access doesn't fail
    with patch.object(type(entity), "local_meural", new_callable=lambda: property(lambda self: AsyncMock())):
        await entity.async_update()

    entity.meural.get_device.assert_not_called()


# ---------------------------------------------------------------------------
# async_media_pause / async_media_play — optimistic duration changes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_media_pause_stores_duration_and_sets_zero():
    """async_media_pause() stores current duration then updates device to 0."""
    entity = make_entity(device_overrides={"imageDuration": 300})
    entity.meural.update_device = AsyncMock()

    await entity.async_media_pause()

    assert entity._pause_duration == 300
    entity.meural.update_device.assert_called_once_with("device-1", {"imageDuration": 0})


@pytest.mark.asyncio
async def test_async_media_play_restores_stored_duration():
    """async_media_play() restores the previously stored pause_duration."""
    entity = make_entity()
    entity._pause_duration = 600
    entity.meural.update_device = AsyncMock()

    await entity.async_media_play()

    entity.meural.update_device.assert_called_once_with("device-1", {"imageDuration": 600})


@pytest.mark.asyncio
async def test_async_media_play_defaults_to_1800_when_no_stored_duration():
    """async_media_play() defaults to 1800 when _pause_duration is 0."""
    entity = make_entity()
    entity._pause_duration = 0
    entity.meural.update_device = AsyncMock()

    await entity.async_media_play()

    entity.meural.update_device.assert_called_once_with("device-1", {"imageDuration": 1800})


# ---------------------------------------------------------------------------
# gesture flip — next/previous track routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_next_track_sends_right_without_gesture_flip():
    """async_media_next_track() sends right key when gestureFlip is False."""
    entity = make_entity(device_overrides={"gestureFlip": False})
    mock_local = AsyncMock()
    with patch.object(type(entity), "local_meural", new_callable=lambda: property(lambda self: mock_local)):
        await entity.async_media_next_track()
    mock_local.send_key_right.assert_called_once()
    mock_local.send_key_left.assert_not_called()


@pytest.mark.asyncio
async def test_next_track_sends_left_with_gesture_flip():
    """async_media_next_track() sends left key when gestureFlip is True (reversed)."""
    entity = make_entity(device_overrides={"gestureFlip": True})
    mock_local = AsyncMock()
    with patch.object(type(entity), "local_meural", new_callable=lambda: property(lambda self: mock_local)):
        await entity.async_media_next_track()
    mock_local.send_key_left.assert_called_once()
    mock_local.send_key_right.assert_not_called()


@pytest.mark.asyncio
async def test_previous_track_sends_left_without_gesture_flip():
    """async_media_previous_track() sends left key when gestureFlip is False."""
    entity = make_entity(device_overrides={"gestureFlip": False})
    mock_local = AsyncMock()
    with patch.object(type(entity), "local_meural", new_callable=lambda: property(lambda self: mock_local)):
        await entity.async_media_previous_track()
    mock_local.send_key_left.assert_called_once()


@pytest.mark.asyncio
async def test_previous_track_sends_right_with_gesture_flip():
    """async_media_previous_track() sends right key when gestureFlip is True (reversed)."""
    entity = make_entity(device_overrides={"gestureFlip": True})
    mock_local = AsyncMock()
    with patch.object(type(entity), "local_meural", new_callable=lambda: property(lambda self: mock_local)):
        await entity.async_media_previous_track()
    mock_local.send_key_right.assert_called_once()
