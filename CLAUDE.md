# CLAUDE.md — ha-meural Codebase Guide

## Project Overview

`ha-meural` is a Home Assistant custom integration (component) that enables control of NETGEAR Meural Canvas digital art frames. It implements a `media_player` entity with custom services and media browsing support.

- **Domain:** `meural`
- **Integration type:** Cloud polling + local device API
- **Authentication:** AWS Cognito via `boto3`
- **Current version:** 1.1.4

---

## Repository Structure

```
ha-meural/
├── .github/workflows/hassfest.yaml   # CI: validates HA integration structure
├── custom_components/
│   └── meural/
│       ├── __init__.py               # Entry point: setup, config entry lifecycle
│       ├── config_flow.py            # UI config flow (email + password auth)
│       ├── const.py                  # Constants (DOMAIN = "meural")
│       ├── manifest.json             # Integration metadata, dependencies
│       ├── media_player.py           # Main entity: MeuralEntity class + services
│       ├── pymeural.py               # API clients: PyMeural (cloud) + LocalMeural
│       ├── services.yaml             # Service parameter documentation
│       ├── strings.json              # Config flow UI strings
│       ├── util.py                   # snake_case() helper
│       └── translations/en.json      # English translations
├── images/                           # Screenshots for README
├── hacs.json                         # HACS marketplace metadata
├── info.md                           # HACS info card content
└── README.md                         # User-facing documentation
```

---

## Architecture

### API Layer (`pymeural.py`)

Two separate API clients:

**`PyMeural`** — Cloud API (`https://api.meural.com/v1/`)
- Authenticates with AWS Cognito using `boto3`
- Supports token refresh via callback (`token_update_callback`)
- Key methods: `get_user()`, `get_user_devices()`, `get_user_galleries()`, `get_user_items()`, `device_load_gallery()`, `device_load_item()`, `update_device()`, `upload_content()`, `send_postcard_cloud()`, `sync_device()`

**`LocalMeural`** — Local device HTTP API (`http://{device_ip}/remote/{path}`)
- Direct HTTP calls to the device on the LAN
- Key methods: `send_key_*()`, `send_control_backlight()`, `send_set_*()`, `send_change_*()`, `send_get_*()`, `send_postcard()` (local image upload)

**Custom exceptions:**
- `CannotConnect` — network/connection failure
- `InvalidAuth` — bad credentials
- `DeviceTurnedOff` — device offline or suspended

### Integration Setup (`__init__.py`)

- `async_setup_entry()`: Creates `PyMeural` instance with token refresh callback, forwards setup to `media_player` platform
- `async_unload_entry()`: Tears down the platform cleanly
- Stores `PyMeural` instance in `hass.data[DOMAIN][entry.id]`

### Config Flow (`config_flow.py`)

- Single step: user provides email + password
- Calls `pymeural.authenticate()` which uses AWS Cognito
- Stores credentials in config entry

### Media Player Entity (`media_player.py`)

**`MeuralEntity`** extends `MediaPlayerEntity`. One entity is created per Meural device.

**Supported features:**
`BROWSE_MEDIA | SELECT_SOURCE | NEXT_TRACK | PAUSE | PLAY | PLAY_MEDIA | PREVIOUS_TRACK | SHUFFLE_SET | TURN_ON | TURN_OFF`

**State mapping:**
- `STATE_PLAYING` — device is awake and displaying art
- `STATE_PAUSED` — duration set to 0 (artwork frozen)
- `STATE_OFF` — device suspended/sleeping

**Polling:** `async_update()` is called regularly; fetches sleep state, current gallery, and current item.

**Custom services registered via `entity_platform.async_register_entity_service()`:**
1. `set_brightness(brightness: 0–100)`
2. `reset_brightness()` — uses ambient light sensor
3. `preview_image(url, content_type)` — display image from URL locally
4. `preview_image_cloud(url, content_type)` — upload to cloud, display for 2 min, delete
5. `toggle_informationcard()` — show/hide museum placard
6. `set_device_option(option, value)` — configure orientation, shuffle, duration, etc.
7. `synchronize()` — sync device with Meural servers

---

## Key Conventions

### Home Assistant Patterns

- All public async methods use the `async_` prefix (e.g., `async_update`, `async_turn_on`)
- Use `self.async_write_ha_state()` after mutating entity state locally (optimistic updates)
- Use `self.schedule_update_ha_state(force_refresh=True)` to trigger a full poll cycle
- Configuration is stored in `hass.data[DOMAIN][entry.id]`
- Services are registered in `async_setup_entry()` in `media_player.py` via `entity_platform`

### API Calls

- Cloud API calls go through `self.meural` (PyMeural instance)
- Local device calls go through `self.local_meural` (LocalMeural instance)
- Prefer local API for real-time control (navigation, brightness, postcard)
- Use cloud API for gallery/playlist management and sync

### Naming

- `util.snake_case()` converts camelCase/PascalCase API response keys to snake_case
- Gallery = playlist in Meural terminology
- Item = individual artwork

### Error Handling

- Catch `CannotConnect` and `DeviceTurnedOff` for network/device issues
- `InvalidAuth` should trigger re-authentication flow

---

## Development Workflow

### No Build Step Required

This is a pure Python Home Assistant integration. No compilation, bundling, or build step needed.

### Installing for Development

1. Copy `custom_components/meural/` into your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via Settings → Devices & Services → Add Integration → Meural

### Dependency Management

Dependencies are declared in `manifest.json` under `"requirements"`:
```json
"requirements": ["boto3==1.38.15"]
```

Home Assistant installs these automatically at runtime. Do **not** add a `requirements.txt`.

### Testing

There are no automated tests in this repository. Validation is performed by:
- **`hassfest`** CI (`.github/workflows/hassfest.yaml`) — validates `manifest.json` and integration structure against HA standards
- Manual testing against a real Meural Canvas device

When adding features, test manually with a real device or the Meural API.

### CI/CD

The only CI pipeline is `hassfest`, which runs on every push and pull request. It validates:
- `manifest.json` schema and required fields
- Correct integration directory structure
- Dependency format

### Versioning

Version is tracked in `manifest.json` → `"version"`. Follow semantic versioning. Update this field when releasing changes.

---

## Making Changes

### Adding a new service

1. Add the service handler method to `MeuralEntity` in `media_player.py` (async, prefixed `async_`)
2. Register it in `async_setup_entry()` using `entity_platform.async_register_entity_service()`
3. Define the vol schema for parameters
4. Document the service in `services.yaml`

### Adding a new API method

1. Add to `PyMeural` (cloud) or `LocalMeural` (local) in `pymeural.py`
2. Use the existing `request()` pattern for cloud, or direct `aiohttp` GET for local

### Updating translations

- Edit `custom_components/meural/translations/en.json`
- Mirror changes in `strings.json` (used as template by HA tooling)

---

## Important Notes

- The Meural cloud API is unofficial/undocumented; endpoints may change without notice
- AWS Cognito token expiry is handled via `token_update_callback` — do not store tokens without this callback
- `preview_image_cloud` uploads to the user's Meural account and deletes after ~2 minutes; it is not instantaneous
- The `gesture` flip feature (next/prev track) can be configured per device and may require special handling in `async_media_next_track()` / `async_media_previous_track()`
- Device sleep/suspend state is separate from HA `STATE_OFF`; check `device["sleep"]` in `async_update()`
