"""Support for the Hume AI text-to-speech service."""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

from hume import AsyncHumeClient
from hume.core import ApiError, RequestOptions
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
    CONF_MODEL,
    CONF_VOICE,
    DEFAULT_MODEL,
    DEFAULT_VOICE,
    DOMAIN,
    PROVIDER_HUME_AI,
    VOICE_KEY_SEPARATOR,
)
from .api.voices import fetch_voices

_LOGGER = logging.getLogger(__name__)

ATTR_DESCRIPTION = "description"

# Hume Octave API character limit per utterance
MAX_CHARS_PER_UTTERANCE = 500

# Generous timeout for long multi-utterance synthesis (seconds)
TTS_TIMEOUT_SECONDS = 60


def _split_text_into_chunks(text: str, max_chars: int = MAX_CHARS_PER_UTTERANCE) -> list[str]:
    """Split text into chunks at sentence boundaries, each within max_chars."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks: list[str] = []
    current: str = ""

    for sentence in sentences:
        if not sentence:
            continue
        # If a single sentence still exceeds the limit, split further at clause boundaries
        if len(sentence) > max_chars:
            clauses = re.split(r'(?<=[,;])\s+', sentence)
            for clause in clauses:
                if not clause:
                    continue
                candidate = (current + " " + clause).strip() if current else clause
                if len(candidate) <= max_chars:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                    current = clause
        else:
            candidate = (current + " " + sentence).strip() if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence

    if current:
        chunks.append(current)

    return chunks if chunks else [text]


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
    model = config_entry.options.get(CONF_MODEL, DEFAULT_MODEL)

    voices: list[Voice] = [
        Voice(voice_id=v.key, name=v.name)
        for v in await fetch_voices(client)
    ]

    _LOGGER.debug("Hume AI TTS: async_setup_entry adding %d voices, default=%s", len(voices), default_voice_key)
    async_add_entities(
        [
            HumeTTSEntity(
                client=client,
                voices=voices,
                default_voice_key=default_voice_key,
                model=model,
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
        model: str,
        entry_id: str,
    ) -> None:
        """Init Hume AI TTS service."""
        self._client = client
        self._default_voice_key = default_voice_key
        self._model = model
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
        version = self._model if self._model != "auto" else None
        _LOGGER.debug("Hume AI TTS called: voice=%s model=%s description=%r text=%r", voice_key, self._model, description, message)

        try:
            chunks = _split_text_into_chunks(message)
            utterances = [_build_utterance(chunk, voice_key, description) for chunk in chunks]
            _LOGGER.debug("Hume AI TTS: %d utterance chunk(s) for %d chars", len(chunks), len(message))
            result = await self._client.tts.synthesize_json(
                utterances=utterances,
                format=FormatMp3(),
                num_generations=1,
                version=version,
                request_options=RequestOptions(timeout_in_seconds=TTS_TIMEOUT_SECONDS),
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

