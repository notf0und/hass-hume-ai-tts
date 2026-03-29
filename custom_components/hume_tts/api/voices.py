"""Shared helpers for the Hume AI TTS integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from hume import AsyncHumeClient
from hume.core import ApiError

from ..const import PROVIDER_CUSTOM, PROVIDER_HUME_AI, VOICE_KEY_SEPARATOR

_LOGGER = logging.getLogger(__name__)


@dataclass
class VoiceInfo:
    """Information about a single Hume AI voice."""

    key: str    # stored key: "{name}::{provider}"
    name: str   # plain voice name
    label: str  # display label (adds "(Custom)" suffix for custom voices)


async def fetch_voices(client: AsyncHumeClient) -> list[VoiceInfo]:
    """Fetch all available voices (Hume AI presets + custom), sorted alphabetically."""
    voices: list[VoiceInfo] = []

    try:
        pager = await client.tts.voices.list(provider=PROVIDER_HUME_AI, page_size=100)
        async for voice in pager:
            if voice.name:
                key = f"{voice.name}{VOICE_KEY_SEPARATOR}{PROVIDER_HUME_AI}"
                voices.append(VoiceInfo(key=key, name=voice.name, label=voice.name))
    except ApiError:
        _LOGGER.debug("Could not fetch Hume AI preset voices")

    try:
        pager = await client.tts.voices.list(provider=PROVIDER_CUSTOM, page_size=100)
        async for voice in pager:
            if voice.name:
                key = f"{voice.name}{VOICE_KEY_SEPARATOR}{PROVIDER_CUSTOM}"
                voices.append(VoiceInfo(key=key, name=voice.name, label=f"{voice.name} (Custom)"))
    except ApiError:
        _LOGGER.debug("Could not fetch custom voices")

    voices.sort(key=lambda v: v.label.lower())
    return voices
