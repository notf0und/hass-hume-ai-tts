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
    CONF_MODEL,
    CONF_VOICE,
    DEFAULT_MODEL,
    DEFAULT_VOICE,
    DOMAIN,
    MODEL_OPTIONS,
    PROVIDER_HUME_AI,
)
from .api.voices import VoiceInfo, fetch_voices

_LOGGER = logging.getLogger(__name__)

USER_STEP_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


async def _validate_api_key(hass: HomeAssistant, api_key: str) -> None:
    """Validate the API key by making a lightweight voices list call. Raises ApiError on failure."""
    httpx_client = get_async_client(hass)
    client = AsyncHumeClient(api_key=api_key, httpx_client=httpx_client)
    pager = await client.tts.voices.list(provider=PROVIDER_HUME_AI, page_size=1)
    async for _ in pager:
        break


async def _get_voices_for_selector(hass: HomeAssistant, api_key: str) -> list[VoiceInfo]:
    """Fetch voices using a temporary client for config/options flow use."""
    httpx_client = get_async_client(hass)
    client = AsyncHumeClient(api_key=api_key, httpx_client=httpx_client)
    return await fetch_voices(client)


def _voice_selector(voices: list[VoiceInfo]) -> SelectSelector:
    """Build a SelectSelector from a list of VoiceInfo."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(label=v.label, value=v.key) for v in voices]
        )
    )


def _model_selector() -> SelectSelector:
    """Build a SelectSelector for Octave model versions."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(label=opt["label"], value=opt["value"])
                for opt in MODEL_OPTIONS
            ]
        )
    )


class HumeTTSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hume AI TTS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._api_key: str = ""
        self._voices: list[VoiceInfo] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: validate the API key."""
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
                self._api_key = api_key
                self._voices = await _get_voices_for_selector(self.hass, api_key)
                if not self._voices:
                    errors["base"] = "no_voices"
                else:
                    return await self.async_step_voice()
        return self.async_show_form(
            step_id="user", data_schema=USER_STEP_SCHEMA, errors=errors
        )

    async def async_step_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the voice and model selection step."""
        if user_input is not None:
            return self.async_create_entry(
                title="Hume AI TTS",
                data={CONF_API_KEY: self._api_key},
                options={
                    CONF_VOICE: user_input[CONF_VOICE],
                    CONF_MODEL: user_input[CONF_MODEL],
                },
            )

        keys = [v.key for v in self._voices]
        default_voice = DEFAULT_VOICE if DEFAULT_VOICE in keys else (keys[0] if keys else DEFAULT_VOICE)
        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_VOICE): _voice_selector(self._voices),
                    vol.Required(CONF_MODEL): _model_selector(),
                }
            ),
            {CONF_VOICE: default_voice, CONF_MODEL: DEFAULT_MODEL},
        )
        return self.async_show_form(step_id="voice", data_schema=schema)

    @staticmethod
    def async_get_options_flow(config_entry: HumeTTSConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return HumeTTSOptionsFlow(config_entry)


class HumeTTSOptionsFlow(OptionsFlow):
    """Hume AI TTS options flow."""

    def __init__(self, config_entry: HumeTTSConfigEntry) -> None:
        """Initialize options flow."""
        self.api_key: str = config_entry.data[CONF_API_KEY]
        self.voices: list[VoiceInfo] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if not self.voices:
            self.voices = await _get_voices_for_selector(self.hass, self.api_key)

        if user_input is not None:
            return self.async_create_entry(title="Hume AI TTS", data=user_input)

        current_voice = self.config_entry.options.get(CONF_VOICE, DEFAULT_VOICE)
        current_model = self.config_entry.options.get(CONF_MODEL, DEFAULT_MODEL)
        schema = self.add_suggested_values_to_schema(
            vol.Schema(
                {
                    vol.Required(CONF_VOICE): _voice_selector(self.voices),
                    vol.Required(CONF_MODEL): _model_selector(),
                }
            ),
            {CONF_VOICE: current_voice, CONF_MODEL: current_model},
        )
        return self.async_show_form(step_id="init", data_schema=schema)
