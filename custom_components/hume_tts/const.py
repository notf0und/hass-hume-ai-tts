"""Constants for the Hume AI TTS integration."""

DOMAIN = "hume_tts"

CONF_VOICE = "voice"
CONF_MODEL = "model"

# Default voice from Hume's Voice Library
DEFAULT_VOICE = "Ava Song::HUME_AI"

# Model version options; "auto" omits the version field (Hume routes automatically)
DEFAULT_MODEL = "auto"
MODEL_OPTIONS = [
    {"value": "auto", "label": "Auto (recommended)"},
    {"value": "1", "label": "Octave 1"},
    {"value": "2", "label": "Octave 2 (preview)"},
]

# Separator between voice name and provider used as the stored key
VOICE_KEY_SEPARATOR = "::"
PROVIDER_HUME_AI = "HUME_AI"
PROVIDER_CUSTOM = "CUSTOM_VOICE"
