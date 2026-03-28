<p align="center">
  <img src="img/logo.png" alt="Hume AI Logo">
</p>

# Hume AI TTS for Home Assistant

A Home Assistant integration for [Hume AI Text-to-Speech (TTS)](https://dev.hume.ai/docs/text-to-speech-tts/overview).


[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=notf0und&repository=hass-hume-ai-tts&category=Integration)


[![GitHub Release](https://img.shields.io/github/release/notf0und/hass-hume-ai-tts.svg?style=flat-square)](https://github.com/notf0und/hass-hume-ai-tts/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/notf0und/hass-hume-ai-tts.svg?style=flat-square)](https://github.com/notf0und/hass-hume-ai-tts/commits/main)
[![License](https://img.shields.io/github/license/notf0und/hass-hume-ai-tts.svg?style=flat-square)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.1+-blue?style=flat-square)](https://www.home-assistant.io)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange?style=flat-square)](https://hacs.xyz/)

[![GitHub Sponsors][sponsorsbadge]][sponsors]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]


## Features

- 🔊 High-quality text-to-speech powered by Hume AI
- 🎯 Easy configuration through Home Assistant UI
- 🔐 Secure API key management
- ☁️ Cloud-based processing
- 🌍 Support for multiple languages
- 🎭 Emotionally aware voice synthesis

## Installation

### Via HACS (Recommended)

Click the button above or follow these steps:

1. Open Home Assistant
2. Go to **Settings** → **Devices & Services** → **Home Assistant Community Store (HACS)**
3. Click **Explore & Download Repositories**
4. Search for **Hume AI TTS**
5. Click **Download**
6. Restart Home Assistant

### Manual Installation

1. Copy the `hume_tts` folder from `custom_components` to your Home Assistant `custom_components` directory:
   ```bash
   cp -r hume_tts ~/.homeassistant/custom_components/
   ```

2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **+ Add Integration**
2. Search for **Hume AI TTS**
3. Enter your [Hume API key](https://console.hume.ai/)
4. Click **Create**

## Usage

Once configured, you can use the TTS service:

```yaml
action: tts.speak
target:
   entity_id: tts.hume_ai
data:
   message: Hello, this is a test message
   media_player_entity_id: media_player.living_room
   options:
      voice: Booming American Narrator
```

Or in automations:

```yaml
automation:
  - alias: "Announce motion detection"
    trigger:
      platform: state
      entity_id: binary_sensor.motion_sensor
      to: "on"
    action: tts.speak
    target:
      entity_id: tts.hume_ai
    data:
      message: Motion detected in the living room
      media_player_entity_id: media_player.living_room
```

Or add it to your voice assistant pipeline:

1. Go to **Settings** → **Voice Assistants** → ** +Add Assistant**
2. On field **Text-to-speech** → **Hume AI**
3. On field **Voice** → Select your desired voice
4. Click **Create**
5. Done! Your voice assistant will now use Hume AI for TTS responses.

## Getting an API Key

1. Visit [Hume AI Console](https://console.hume.ai/)
2. Sign up or log in
3. Create a new API key
4. Copy the key and add it to the integration configuration

## Support

For issues or feature requests, please visit the [GitHub Issues](https://github.com/notf0und/hass-hume-ai-tts/issues) page.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with Hume AI. It is a community-maintained integration.
