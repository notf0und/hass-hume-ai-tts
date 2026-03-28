"""The Hume AI text-to-speech integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from hume import AsyncHumeClient
from hume.core import ApiError
from httpx import ConnectError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
)
from homeassistant.helpers.httpx_client import get_async_client

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.TTS]


@dataclass(kw_only=True, slots=True)
class HumeTTSData:
    """Hume AI TTS runtime data."""

    client: AsyncHumeClient


type HumeTTSConfigEntry = ConfigEntry[HumeTTSData]


async def async_setup_entry(hass: HomeAssistant, entry: HumeTTSConfigEntry) -> bool:
    """Set up Hume AI TTS from a config entry."""
    entry.add_update_listener(update_listener)
    httpx_client = get_async_client(hass)
    client = AsyncHumeClient(
        api_key=entry.data[CONF_API_KEY], httpx_client=httpx_client
    )

    # Validate the API key by listing voices
    try:
        pager = await client.tts.voices.list(provider="HUME_AI", page_size=1)
        async for _ in pager:
            break
    except ConnectError as err:
        raise ConfigEntryNotReady("Failed to connect to Hume AI") from err
    except ApiError as err:
        raise ConfigEntryAuthFailed("Hume AI authentication failed") from err

    entry.runtime_data = HumeTTSData(client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HumeTTSConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, config_entry: HumeTTSConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
