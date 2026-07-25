# @psyb0t/audiolla

An OpenClaw/MCP plugin that connects your agent to a self-hosted
[audiolla](https://github.com/psyb0t/docker-audiolla) audio-production API
over the [Model Context Protocol](https://modelcontextprotocol.io).

audiolla already serves a Streamable-HTTP MCP endpoint at `/v1/mcp`. This
package is a thin stdio↔HTTP bridge (via
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote)) for MCP clients that
speak local stdio servers — it forwards everything to your running audiolla
instance and authenticates with your bearer token when the server requires one.

> audiolla is **self-hosted**. This plugin does not ship the audio engines —
> it connects to an audiolla server that **you** run. See the
> [audiolla repo](https://github.com/psyb0t/docker-audiolla) to stand one up.

## Tools

The audiolla MCP tools become available to your agent: Demucs/MDX/BS-Roformer
stem separation, matchering reference mastering and pedalboard preset
mastering, librosa MIR analysis (BPM, key, LUFS, beat grid, onsets, melody,
structural segments), SoX and pedalboard DSP chains, multiband compression,
transient shaping, sidechain ducking, de-essing, mid/side processing, silence
detection and trimming, spectrogram/waveform/video visualisation, Chromaprint
fingerprinting, AI restoration (de-reverb / de-echo / de-noise via UVR),
DeepFilterNet speech enhancement, voice activity detection, speaker
diarization, time-stretch/pitch-shift/BPM-match/key-match, pitch correction,
beat slicing, audio-to-MIDI transcription (basic-pitch), MIDI compose /
inspect / transform / render / humanize / quantize, drum pattern generation,
AudioSet tagging, CLAP embeddings/similarity/classification, ID3/Vorbis/FLAC
metadata read/write, curated server-side workflow presets, ad-hoc op
pipelines, and text-to-music/SFX generation. See the
[audiolla skill](https://github.com/psyb0t/docker-audiolla/tree/main/.agents/skills/audiolla)
or `GET /v1/catalog` on your running instance for the full, current tool
surface.

## Configuration

| Env var | Required | Description |
|---|---|---|
| `AUDIOLLA_URL` | yes | Base URL of your running audiolla server, e.g. `http://localhost:8000`. The bridge appends `/v1/mcp`. |
| `AUDIOLLA_AUTH_TOKEN` | no | Bearer token — only if the audiolla server was started with `AUDIOLLA_AUTH_TOKEN` set. |

## Install

Install it into your OpenClaw agent from ClawHub:

```bash
openclaw plugins install clawhub:@psyb0t/audiolla
```

Then set `AUDIOLLA_URL` (and `AUDIOLLA_AUTH_TOKEN` if your server uses auth) in
the plugin's environment.

## Native remote MCP (no install)

If your MCP client already supports **remote** Streamable-HTTP servers, you
don't need this bridge — point the client straight at
`$AUDIOLLA_URL/v1/mcp` with an `Authorization: Bearer <token>` header.

## License

MIT. See [LICENSE](LICENSE).
