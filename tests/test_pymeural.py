"""Tests for pymeural.py — API client critical paths."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp.client_exceptions import ClientResponseError, ClientConnectorError

from custom_components.meural.pymeural import (
    PyMeural,
    LocalMeural,
    authenticate,
    InvalidAuth,
    DeviceTurnedOff,
)


# ---------------------------------------------------------------------------
# authenticate()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authenticate_returns_token_on_success(mock_session):
    """authenticate() extracts AccessToken from Cognito response."""
    cognito_response = {
        "AuthenticationResult": {"AccessToken": "test-token-abc"}
    }
    with patch("boto3.client") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        mock_client.initiate_auth.return_value = cognito_response

        token = await authenticate(mock_session, "user@example.com", "correct-password")

    assert token == "test-token-abc"


@pytest.mark.asyncio
async def test_authenticate_raises_invalid_auth_when_no_result(mock_session):
    """authenticate() raises InvalidAuth when Cognito returns no AuthenticationResult."""
    with patch("boto3.client") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        mock_client.initiate_auth.return_value = {}  # challenge flow, not a result

        with pytest.raises(InvalidAuth):
            await authenticate(mock_session, "user@example.com", "wrong-password")


# ---------------------------------------------------------------------------
# PyMeural.request()
# ---------------------------------------------------------------------------

def _make_json_response(data):
    """Return a mock response that yields the given data as JSON."""
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"data": data})
    return mock_resp


@pytest.mark.asyncio
async def test_request_returns_data_on_success(py_meural):
    """request() returns the 'data' field from a successful response."""
    py_meural.session.request = AsyncMock(return_value=_make_json_response({"id": 1}))

    result = await py_meural.request("get", "user")

    assert result == {"id": 1}


@pytest.mark.asyncio
async def test_request_fetches_token_when_none(py_meural):
    """request() calls get_new_token() when token is None before the first request."""
    py_meural.token = None
    py_meural.session.request = AsyncMock(return_value=_make_json_response({"ok": True}))

    with patch.object(py_meural, "get_new_token", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.side_effect = lambda: setattr(py_meural, "token", "new-token")
        await py_meural.request("get", "user")

    mock_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_request_retries_on_401_and_succeeds(py_meural):
    """request() re-authenticates on 401 and retries the original request."""
    error_401 = ClientResponseError(MagicMock(), MagicMock(), status=401)
    ok_response = _make_json_response({"id": 42})

    py_meural.session.request = AsyncMock(side_effect=[error_401, ok_response])

    with patch.object(py_meural, "get_new_token", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.side_effect = lambda: setattr(py_meural, "token", "refreshed-token")
        result = await py_meural.request("get", "user")

    mock_refresh.assert_called_once()
    assert result == {"id": 42}


@pytest.mark.asyncio
async def test_request_raises_on_second_consecutive_401(py_meural):
    """request() raises after a 401 that occurs immediately after token refresh."""
    error_401 = ClientResponseError(MagicMock(), MagicMock(), status=401)

    # Simulate token=None so the first request immediately fetches a new token,
    # then the request itself still returns 401.
    py_meural.token = None
    py_meural.session.request = AsyncMock(side_effect=error_401)

    with patch.object(py_meural, "get_new_token", new_callable=AsyncMock) as mock_refresh:
        mock_refresh.side_effect = lambda: setattr(py_meural, "token", "new-token")
        with pytest.raises(ClientResponseError):
            await py_meural.request("get", "user")


@pytest.mark.asyncio
async def test_request_raises_on_non_401_http_error(py_meural):
    """request() propagates non-401 HTTP errors without retry."""
    error_500 = ClientResponseError(MagicMock(), MagicMock(), status=500)
    py_meural.session.request = AsyncMock(side_effect=error_500)

    with pytest.raises(ClientResponseError) as exc_info:
        await py_meural.request("get", "user")

    assert exc_info.value.status == 500


# ---------------------------------------------------------------------------
# LocalMeural.request()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_request_returns_response_field(local_meural):
    """LocalMeural.request() returns the 'response' field from device JSON."""
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"response": True, "status": "pass"})
    local_meural.session.request = AsyncMock(return_value=mock_resp)

    result = await local_meural.request("get", "control_check/sleep/")

    assert result is True


@pytest.mark.asyncio
async def test_local_request_raises_device_turned_off_on_connection_error(local_meural):
    """LocalMeural.request() raises DeviceTurnedOff when the device is unreachable."""
    local_meural.session.request = AsyncMock(
        side_effect=ClientConnectorError(MagicMock(), OSError("Connection refused"))
    )

    with pytest.raises(DeviceTurnedOff):
        await local_meural.request("get", "control_check/sleep/")


@pytest.mark.asyncio
async def test_local_send_get_sleep(local_meural):
    """send_get_sleep() hits the correct endpoint and returns device sleep state."""
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"response": False, "status": "pass"})
    local_meural.session.request = AsyncMock(return_value=mock_resp)

    result = await local_meural.send_get_sleep()

    assert result is False
    call_args = local_meural.session.request.call_args
    assert "control_check/sleep/" in call_args[0][1]


@pytest.mark.asyncio
async def test_local_send_key_right(local_meural):
    """send_key_right() calls the correct local endpoint."""
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"response": "ok", "status": "pass"})
    local_meural.session.request = AsyncMock(return_value=mock_resp)

    await local_meural.send_key_right()

    call_args = local_meural.session.request.call_args
    assert "set_key/right/" in call_args[0][1]


@pytest.mark.asyncio
async def test_local_send_key_left(local_meural):
    """send_key_left() calls the correct local endpoint."""
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"response": "ok", "status": "pass"})
    local_meural.session.request = AsyncMock(return_value=mock_resp)

    await local_meural.send_key_left()

    call_args = local_meural.session.request.call_args
    assert "set_key/left/" in call_args[0][1]
