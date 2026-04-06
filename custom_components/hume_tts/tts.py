"""Support for the Hume AI text-to-speech service."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp
from hume import AsyncHumeClient
from hume.core import ApiError, RequestOptions
from hume.tts import FormatMp3, PostedUtterance, PostedUtteranceVoiceWithName

from homeassistant.components.tts import (
    ATTR_VOICE,
    TextToSpeechEntity,
    TtsAudioType,
    Voice,
)
from homeassistant.components.tts.entity import TTSAudioRequest, TTSAudioResponse
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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

HUME_WS_TTS_URL = "wss://api.hume.ai/v0/tts/stream/input"

# Regex for sentence-boundary flushing: ends with .!? optionally followed by quotes/brackets
_SENTENCE_END_RE = re.compile(r'[.!?]["\'\)\]]*\s*$')

_LOGGER = logging.getLogger(__name__)

ATTR_DESCRIPTION = "description"

# Hume Octave API character limit per utterance
MAX_CHARS_PER_UTTERANCE = 500

# Generous timeout for long multi-utterance synthesis (seconds)
TTS_TIMEOUT_SECONDS = 60

# Timeout waiting for first audio chunk from Hume WS (seconds)
WS_FIRST_CHUNK_TIMEOUT = 10


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
                api_key=config_entry.data[CONF_API_KEY],
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
        api_key: str,
        voices: list[Voice],
        default_voice_key: str,
        model: str,
        entry_id: str,
    ) -> None:
        """Init Hume AI TTS service."""
        self._client = client
        self._api_key = api_key
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

    async def async_stream_tts_audio(
        self, request: TTSAudioRequest
    ) -> TTSAudioResponse:
        """Stream TTS audio from Hume AI via WebSocket.

        Called by HA's pipeline when the LLM response is long enough to stream
        (>= STREAM_RESPONSE_CHARS chars).  Hume's WS endpoint allows us to feed
        text incrementally and receive MP3 chunks in real time, so the satellite
        can start playing before synthesis is complete.
        """
        voice_key = request.options.get(ATTR_VOICE, self._default_voice_key)
        description = request.options.get(ATTR_DESCRIPTION)
        voice_name, provider = _parse_voice_key(voice_key)

        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        # Set once _send_text has sent all utterances; switches receive to a short timeout.
        send_done = asyncio.Event()

        async def _stream_chunks() -> AsyncGenerator[bytes, None]:
            """Yield MP3 chunks from the queue until the sentinel None is received."""
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    return
                yield chunk

        async def _run_ws() -> None:
            """Connect to Hume WS, feed LLM tokens, collect audio chunks."""
            url = (
                f"{HUME_WS_TTS_URL}"
                f"?api_key={self._api_key}"
                f"&instant_mode=true"
                f"&strip_headers=true"
                f"&no_binary=true"
            )
            session = async_get_clientsession(self.hass)

            try:
                async with session.ws_connect(url) as ws:
                    send_task = asyncio.ensure_future(_send_text(ws))
                    receive_task = asyncio.ensure_future(_receive_audio(ws))

                    try:
                        await asyncio.gather(send_task, receive_task)
                    except Exception:
                        send_task.cancel()
                        receive_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await send_task
                        with contextlib.suppress(asyncio.CancelledError):
                            await receive_task
                        raise
                    await ws.close()
            except Exception as exc:
                _LOGGER.exception("Hume AI streaming TTS error: %s", exc)
                raise HomeAssistantError(exc) from exc
            finally:
                await audio_queue.put(None)

        async def _send_text(ws: aiohttp.ClientWebSocketResponse) -> None:
            """Read LLM token stream and send utterances to Hume at sentence boundaries."""
            buffer = ""
            async for token in request.message_gen:
                buffer += token
                if _SENTENCE_END_RE.search(buffer):
                    await _flush_utterance(ws, buffer.strip())
                    buffer = ""
                    # Yield so _receive_audio can process early chunks between flushes.
                    await asyncio.sleep(0)

            if buffer.strip():
                await _flush_utterance(ws, buffer.strip())

            # All text sent — receiver switches to a short idle timeout.
            send_done.set()
            _LOGGER.debug("Hume AI streaming TTS: all text sent")

        async def _flush_utterance(ws: aiohttp.ClientWebSocketResponse, text: str) -> None:
            """Send one utterance + flush to Hume using the WS flat PublishTts format."""
            _LOGGER.debug("Hume AI streaming TTS: sending %d chars", len(text))
            # WS endpoint uses flat PublishTts fields, NOT the REST "utterances" wrapper.
            msg: dict = {
                "text": text,
                "voice": {"name": voice_name, "provider": provider},
                "flush": True,
            }
            if description:
                msg["description"] = description
            await ws.send_str(json.dumps(msg))

        async def _receive_audio(ws: aiohttp.ClientWebSocketResponse) -> None:
            """Collect base64 audio chunks from Hume and push decoded bytes to the queue."""
            chunks_received = 0
            while True:
                # After all text is sent, allow 5 s of silence before giving up.
                # Before that, wait up to 30 s (covers slow LLM token generation).
                timeout = 5.0 if send_done.is_set() else 30.0
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        "Hume AI streaming TTS: receive timeout (send_done=%s, chunks=%d)",
                        send_done.is_set(), chunks_received,
                    )
                    break

                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        _LOGGER.warning("Hume AI streaming TTS: invalid JSON: %.200s", msg.data)
                        continue

                    # Log non-audio fields to help understand Hume's protocol.
                    meta = {k: v for k, v in data.items() if k != "audio"}
                    if meta:
                        _LOGGER.debug("Hume AI streaming TTS: msg meta: %s", meta)

                    if audio_b64 := data.get("audio"):
                        audio_bytes = base64.b64decode(audio_b64)
                        await audio_queue.put(audio_bytes)
                        chunks_received += 1
                        _LOGGER.debug(
                            "Hume AI streaming TTS: chunk %d (%d bytes)",
                            chunks_received,
                            len(audio_bytes),
                        )
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    _LOGGER.debug(
                        "Hume AI streaming TTS: WS closed (type=%s, data=%s)",
                        msg.type, msg.data,
                    )
                    break

            _LOGGER.debug("Hume AI streaming TTS: receive complete (%d chunks)", chunks_received)

        asyncio.ensure_future(_run_ws())
        return TTSAudioResponse(extension="mp3", data_gen=_stream_chunks())

