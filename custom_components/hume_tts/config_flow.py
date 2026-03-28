"""Config flow for Hume AI TTS integration."""

from __future__ import annotations

import logging
from typing import Any

from hume import AsyncHumeClient
from hume.core import ApiError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from . import HumeTTSConfigEntry
from .const import (
    CONF_VOICE,
    DEFAULT_VOICE,
    DOMAIN,
    PROVIDER_CUSTOM,
    PROVIDER_HUME_AI,
    VOICE_KEY_SEPARATOR,
)

_LOGGER = logging.getLogger(__name__)

USER_STEP_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


async def _validate_api_key(hass: HomeAssistant, api_key: str) -> None:
    """Validate the API key by making a lightweight voices list call. Raises ApiError on failure."""
    httpx_client = get_async_client(hass)
    client = AsyncHumeClient(api_key=api_key, httpx_client=httpx_client)
    pager = await client.tts.voices.list(provider=PROVIDER_HUME_AI, page_size=1)
    async for _ in pager:
        break


async def get_voices(hass: HomeAssistant, api_key: str) -> dict[str, str]:
    """Fetch all available voices (Hume AI presets + custom) as {key: label}."""
    httpx_client = get_async_client(hass)
    client = AsyncHumeClient(api_key=api_key, httpx_client=httpx_client)
    voices: dict[str, str] = {}

    # Hume AI preset voices
    try:
        pager = await client.tts.voices.list(provider=PROVIDER_HUME_AI, page_size=100)
        async for voice in pager:
            if voice.name:
                key = f"{voice.name}{VOICE_KEY_SEPARATOR}{PROVIDER_HUME_AI}"
                voices[key] = f"{voice.name} (Hume AI)"
    except ApiError:
        _LOGGER.debug("Could not fetch Hume AI preset voices")

    # User's custom voices
    try:
        pager = await client.tts.voices.list(provider=PROVIDER_CUSTOM, page_size=100)
        async for voice in pager:
            if voice.name:
                key = f"{voice.name}{VOICE_KEY_SEPARATOR}{PROVIDER_CUSTOM}"
                voices[key] = f"{voice.name} (Custom)"
    except ApiError:
        _LOGGER.debug("Could not fetch custom voices")

    return voices


class HumeTTSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hume AI TTS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            try:
                await _validate_api_key(self.hass, api_key)
            except ApiError:
                errors["base"] = "invalid_api_key"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                voices = await get_voices(self.hass, api_key)
                default_voice = DEFAULT_VOICE if DEFAULT_VOICE in voices else (list(voices)[0] if voices else DEFAULT_VOICE)
                return self.async_create_entry(
                    title="Hume AI TTS",
                    data=user_input,
                    options={CONF_VOICE: default_voice},
                )
        return self.async_show_form(
            step_id="user", data_schema=USER_STEP_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry: HumeTTSConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return HumeTTSOptionsFlow(config_entry)


class HumeTTSOptionsFlow(OptionsFlow):
    """Hume AI TTS options flow."""

    def __init__(self, config_entry: HumeTTSConfigEntry) -> None:
        """Initialize options flow."""
        self.api_key: str = config_entry.data[CONF_API_KEY]
        self.voices: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if not self.voices:
            self.voices = await get_voices(self.hass, self.api_key)

        if user_input is not None:
            return self.async_create_entry(title="Hume AI TTS", data=user_input)

        current_voice = self.config_entry.options.get(CONF_VOICE, DEFAULT_VOICE)
        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_VOICE): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(label=label, value=key)
                                for key, label in self.voices.items()
                            ]
                        )
                    ),
                }
            ),
            {CONF_VOICE: current_voice},
        )
        return self.async_show_form(step_id="init", data_schema=schema)
