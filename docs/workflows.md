---
title: "Presets, pipelines and batch"
description: "Chain audiolla operations server-side: shipped YAML presets, ad-hoc /v1/pipeline steps, the 24 pipeline ops, /v1/batch and /v1/catalog."
nav_order: 14
---

# Presets, pipelines and batch

Three ways to run several operations without moving audio back and forth between calls:

- A preset is a named list of steps in a YAML file on the server. One POST runs the whole list.
- A pipeline is the same thing sent ad hoc in the request body.
- A batch runs independent single operations on different files in one request.

Presets and pipelines feed each step's output straight into the next step in memory, so intermediates never touch the staging area. The code is in [`src/audiolla/pipeline.py`](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/pipeline.py) and [`src/audiolla/presets.py`](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/presets.py).

## Presets

```bash
# stage the input
curl -X PUT --data-binary @mix.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/mix.wav

# master a mix for streaming: 3-band compression, then -14 LUFS
curl -X POST http://localhost:8000/v1/presets/master-for-spotify \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/mix.wav",
    "output_path": "out/mastered.wav"
  }'
# -> {"path":"out/mastered.wav","size":...,"preset":"master-for-spotify","steps":[...]}

curl -o mastered.wav http://localhost:8000/v1/files/out/mastered.wav

# list presets, then look at one before running it
curl http://localhost:8000/v1/presets | jq '.data[] | {name, description}'
curl http://localhost:8000/v1/presets/podcast-cleanup | jq '.steps'
```

The image ships three presets from [`presets/`](https://github.com/psyb0t/docker-audiolla/tree/main/presets):

| Preset | Steps | Engines it needs |
| --- | --- | --- |
| `master-for-spotify` | `multiband_compress` (crossovers at 200 Hz and 3 kHz, three bands), then `normalize` to -14 LUFS. | `librosa-analyze` |
| `podcast-cleanup` | `enhance` with DeepFilterNet, `deess` (-18 dB, 6.5 kHz, 4:1), then `normalize` to -16 LUFS. | `deepfilter`, `librosa-analyze` |
| `vocal-cleanup` | `restore` with `uvr-dereverb`, `restore` with `uvr-denoise`, `deess` (-20 dB, 7 kHz, 4:1), then `fx` with a 3:1 compressor at -18 dB and +2 dB gain. | `uvr-dereverb`, `uvr-denoise`, `fx-chain` |

The run body takes `file_path` or `file_url`, `output_path` or `output_url`, `output_format`, `async_job` and `webhook_url`, like any audio-producing endpoint (see [getting started](getting-started.md#input-and-output) and [jobs](jobs.md)). The response adds `preset` and the `steps` log. An unknown preset name is a 404 that lists the configured names.

### Writing a preset

A preset file is a YAML mapping:

```yaml
name: podcast-cleanup
description: Voice enhance, de-ess, normalize to -16 LUFS
steps:
  - op: enhance
    params:
      engine: deepfilter
  - op: deess
    params:
      threshold_db: -18
      ratio: 4
  - op: normalize
    params:
      target_lufs: -16
```

| Field | Required | Rules |
| --- | --- | --- |
| `name` | yes | Non-empty string. This is the URL name in `/v1/presets/{name}`. |
| `description` | no | String, shown by `GET /v1/presets`. |
| `steps` | yes | Non-empty list. Each step is a mapping with a string `op` and an optional `params` mapping. |

The server reads every `*.yaml` and `*.yml` file in `AUDIOLLA_PRESETS_DIR` (default `/app/presets`, where the image copies the shipped presets) once at startup. A malformed file is logged and skipped, not fatal. When two files use the same `name`, the first in file-name order wins and the other is logged. Op names and params are not checked at load time; a bad step fails with a 400 when the preset runs.

To add presets, mount a directory with your files and point the variable at it. Copy the shipped files in too if you want to keep them, because the variable replaces the directory rather than adding to it. Restart the container after changing a preset.

```bash
docker run --rm \
  -v $HOME/.audiolla-data:/data \
  -v $HOME/audiolla-presets:/presets:ro \
  -e AUDIOLLA_PRESETS_DIR=/presets \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest
```

## Ad-hoc pipelines

```bash
# de-noise, 3-band compress, normalize: one request
curl -X POST http://localhost:8000/v1/pipeline \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "output_path": "out/pipelined.wav",
    "steps": [
      {
        "op": "restore",
        "params": {"engine": "uvr-denoise"}
      },
      {
        "op": "multiband_compress",
        "params": {
          "crossovers_hz": [200, 3000],
          "bands": [
            {"threshold_db": -18, "ratio": 3},
            {"threshold_db": -14, "ratio": 2.5},
            {"threshold_db": -10, "ratio": 2}
          ]
        }
      },
      {
        "op": "normalize",
        "params": {"target_lufs": -14}
      }
    ]
  }'
# -> {"path":"out/pipelined.wav","size":...,"steps":[...]}

# list the op names
curl http://localhost:8000/v1/ops | jq .
```

`steps` must be a non-empty list of `{op, params}`. The other body fields are the same as for presets. The `steps` log in the response has one entry per step: `step` (index), `op`, `params` and `size_after` (bytes).

A failing step stops the run with a 400 whose detail names the step, such as `step 1 (multiband_compress): bad params: ...`. An unknown op lists the valid ones.

Every op writes WAV unless its own `params` say otherwise, and the top-level `output_format` does not re-encode the result. To get MP3 or FLAC out of a pipeline or preset, put `"output_format": "mp3"` in the last step's `params` and use the same value at the top level, so the staged file name and content type match.

### Ops

`GET /v1/ops` returns the 24 op names (`{"object": "list", "data": [...]}`), without their params. The params are the keyword arguments of the matching op function in `pipeline.py`, which mostly match the REST endpoint of the same name:

| Op | Params (default) | Engine needed |
| --- | --- | --- |
| `restore` | `engine` (required), `aggressive` (`false`) | a UVR engine such as `uvr-dereverb` |
| `enhance` | `engine` (`deepfilter`) | `deepfilter` |
| `noise_reduce` | `engine` (`noise-reduce`), `stationary` (`false`), `prop_decrease` (`1.0`) | `noise-reduce` or `uvr-denoise` |
| `fx` | `effects` (required) | `fx-chain` |
| `transform` | `operations` (required) | `sox-transform` |
| `normalize` | `target_lufs` (required) | `librosa-analyze` |
| `master` | `mode` (required), `preset`, `target_lufs` | `pedalboard-chain` for `mode: chain` |
| `pitch_correct` | `strength` (`1.0`) | `librosa-analyze` |
| `stretch` | `tempo_factor` (`1.0`), `pitch_semitones` (`0.0`) | `stretch` |
| `thumbnail` | `duration_sec` (`30.0`) | `librosa-analyze` |
| `trim` | `start_sec` (`0.0`), `end_sec` (required) | none |
| `speed` | `speed` (required) | none |
| `convert` | `sample_rate`, `channels` | none |
| `fade` | `fade_in` (`0.0`), `fade_out` (`0.0`), `curve` (`tri`) | none |
| `reverse` | none | none |
| `loop` | `count` (`2`) | none |
| `stereo_width` | `width` (`1.0`) | none |
| `pan` | `position` (`0.0`) | none |
| `eq` | `bands` (required, a list) | none |
| `mid_side` | `mode` (required, `encode` or `decode`) | none |
| `repair` | `declip` (`true`), `dehum` (`false`), `hum_freq` (`50.0`) | none |
| `transient` | `attack_gain_db` (`0.0`), `sustain_gain_db` (`0.0`) | none |
| `multiband_compress` | `crossovers_hz` (required), `bands` (required) | none |
| `deess` | `threshold_db` (`-20.0`), `frequency_hz` (`6000.0`), `ratio` (`4.0`) | none |

Every op also takes `output_format` (`wav`). Analysis endpoints are not ops, because a pipeline passes audio bytes from step to step. Operations that need a second input (convolution reverb, mix, concat, sidechain duck) are not ops either. `master` works only with `mode: chain` here: `mode: reference` needs the reference audio as bytes, which a JSON step cannot carry.

## Batch

`POST /v1/batch` takes a JSON array of independent operations and runs them one after another. A failed item does not stop the rest, and the response is HTTP 200 with one entry per item.

```bash
curl -X PUT --data-binary @track.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/work/track.wav

curl -X POST http://localhost:8000/v1/batch \
  -H 'Content-Type: application/json' \
  -d '[
    {
      "op": "trim",
      "file_path": "work/track.wav",
      "output_path": "work/chorus.wav",
      "start_sec": 30,
      "end_sec": 60
    },
    {
      "op": "convert",
      "file_path": "work/track.wav",
      "output_path": "work/track.mp3",
      "output_format": "mp3"
    },
    {
      "op": "reverse",
      "file_path": "work/track.wav",
      "output_path": "work/reversed.wav"
    }
  ]' | jq '.results[].status'
# -> "ok" "ok" "ok"
```

Each item has `op`, `file_path` or `file_url`, `output_path`, `output_format` (`wav`) and the op's own fields:

| Op | Fields |
| --- | --- |
| `convert` | `sample_rate`, `channels` |
| `normalize` | `target_lufs` (`-14.0`) |
| `trim` | `start_sec` (`0.0`), `end_sec` (required) |
| `fade` | `fade_in` (`0.0`), `fade_out` (`0.0`), `curve` (`tri`) |
| `reverse` | none |
| `speed` | `speed` (required) |
| `eq` | `bands` as a JSON-encoded string, such as `"[{\"freq\": 60, \"gain_db\": -12}]"`. A plain JSON list fails with an unexpected-error entry. |

The response is `{"results": [...]}`. A successful item is `{"index": i, "op": "...", "status": "ok", "path": "...", "size": ...}`; a failed one is `{"index": i, "op": "...", "error": "..."}`. Batch items cannot use `output_url`. Without `output_path` an item succeeds but its output is thrown away and only `size` comes back. Batch has no `async_job`.

## Catalog

`GET /v1/catalog` returns endpoints grouped into 18 categories: `separation`, `restoration`, `dynamics`, `eq-spatial`, `mastering`, `time-pitch`, `editing`, `analysis`, `effects-creative`, `generate`, `visualize`, `midi`, `metadata`, `workflow`, `speech`, `files`, `jobs` and `management`. Each entry has `method`, `path` and a one-line `summary`. Agents and scripts can use it for discovery without reading the whole OpenAPI spec.

```bash
curl http://localhost:8000/v1/catalog \
  | jq '.categories[] | {name, endpoint_count: (.endpoints | length)}'
```

The catalog is a hand-written list in `src/audiolla/server.py` (`_CATALOG_GROUPS`), not generated from the routes. It currently leaves out `POST /v1/audio/convert`, `POST /v1/audio/transform` and `POST /v1/midi/generate`. The [REST API reference](api.md) is the complete list.
