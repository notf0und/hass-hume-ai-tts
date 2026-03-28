"""Support for the Hume AI text-to-speech service."""

from __future__ import annotations

import base64
import logging
from typing import Any

from hume import AsyncHumeClient
from hume.core import ApiError
from hume.tts import FormatMp3, PostedUtterance, PostedUtteranceVoiceWithName

from homeassistant.components.tts import (
    ATTR_VOICE,
    TextToSpeechEntity,
    TtsAudioType,
    Voice,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

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

ATTR_DESCRIPTION = "description"

SUPPORTED_LANGUAGES = [
    "en",
    "es",
    "ja",
    "ko",
    "fr",
    "pt",
    "it",
    "de",
    "ru",
    "hi",
    "ar",
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: HumeTTSConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hume AI TTS platform via config entry."""
    _LOGGER.debug("Hume AI TTS: async_setup_entry START")
    client = config_entry.runtime_data.client
    default_voice_key = config_entry.options.get(CONF_VOICE, DEFAULT_VOICE)

    voices: list[Voice] = []
    for provider in (PROVIDER_HUME_AI, PROVIDER_CUSTOM):
        try:
            pager = await client.tts.voices.list(provider=provider, page_size=100)
            async for voice in pager:
                if voice.name:
                    key = f"{voice.name}{VOICE_KEY_SEPARATOR}{provider}"
                    voices.append(Voice(voice_id=key, name=voice.name))
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not fetch voices for provider %s", provider)

    voices.sort(key=lambda v: v.name.lower())

    _LOGGER.debug("Hume AI TTS: async_setup_entry adding %d voices, default=%s", len(voices), default_voice_key)
    async_add_entities(
        [
            HumeTTSEntity(
                client=client,
                voices=voices,
                default_voice_key=default_voice_key,
                entry_id=config_entry.entry_id,
            )
        ]
    )


def _parse_voice_key(voice_key: str) -> tuple[str, str]:
    """Split a stored voice key into (name, provider)."""
    if VOICE_KEY_SEPARATOR in voice_key:
        name, provider = voice_key.split(VOICE_KEY_SEPARATOR, 1)
        return name, provider
    return voice_key, PROVIDER_HUME_AI


def _build_utterance(text: str, voice_key: str, description: str | None = None) -> PostedUtterance:
    """Build a PostedUtterance from text, voice key, and optional acting instructions."""
    voice_name, provider = _parse_voice_key(voice_key)
    return PostedUtterance(
        text=text,
        voice=PostedUtteranceVoiceWithName(name=voice_name, provider=provider),
        description=description or None,
    )


class HumeTTSEntity(TextToSpeechEntity):
    """The Hume AI TTS entity."""

    _attr_supported_options = [ATTR_VOICE, ATTR_DESCRIPTION]

    def __init__(
        self,
        client: AsyncHumeClient,
        voices: list[Voice],
        default_voice_key: str,
        entry_id: str,
    ) -> None:
        """Init Hume AI TTS service."""
        self._client = client
        self._default_voice_key = default_voice_key
        self._voices = voices
        self._attr_name = "Hume AI"
        self._attr_unique_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            manufacturer="Hume AI",
            model="Octave TTS",
            name="Hume AI",
            entry_type=DeviceEntryType.SERVICE,
        )
        self._attr_supported_languages = SUPPORTED_LANGUAGES
        self._attr_default_language = "en"

    def async_get_supported_voices(self, language: str) -> list[Voice]:
        """Return a list of supported voices for a language."""
        return self._voices

    async def async_get_tts_audio(
        self, message: str, language: str, options: dict[str, Any]
    ) -> TtsAudioType:
        """Load TTS audio from the Hume AI API."""
        voice_key = options.get(ATTR_VOICE, self._default_voice_key)
        description = options.get(ATTR_DESCRIPTION)
        _LOGGER.debug("Hume AI TTS called: voice=%s description=%r text=%r", voice_key, description, message)

        try:
            result = await self._client.tts.synthesize_json(
                utterances=[_build_utterance(message, voice_key, description)],
                format=FormatMp3(),
                num_generations=1,
            )
        except ApiError as exc:
            _LOGGER.exception("Hume AI TTS API error: %s", exc)
            raise HomeAssistantError(exc) from exc
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during Hume AI TTS: %s", exc)
            raise HomeAssistantError(exc) from exc

        if not result.generations:
            _LOGGER.error("Hume AI returned no audio generations")
            raise HomeAssistantError("Hume AI returned no audio generations")

        audio_bytes = base64.b64decode(result.generations[0].audio)
        _LOGGER.debug("Hume AI TTS success: %d bytes", len(audio_bytes))
        return "mp3", audio_bytes

