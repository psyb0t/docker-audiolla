#!/bin/bash
# /v1/midi/{compose,render,generate} end-to-end.
#
# Verifies the full I/O round-trip:
#   1. compose: JSON spec → MIDI bytes (must start with MThd)
#   2. render:  MIDI bytes → audio (must start with RIFF)
#   3. generate: spec → audio in one call (must start with RIFF)
#   4. staging: compose into FILES_DIR, then render the staged MIDI
#
# Needs fluidsynth + a SoundFont — both ship in the prod image via
# fluid-soundfont-gm. The dev image doesn't have them, so this MUST run
# against psyb0t/audiolla:local (the harness default).
#
#     bash tests/integration/e2e_midi.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

harness_start "midi-compose,midi-render"

# Minimal but musical: C major arpeggio over 4 beats at 120 BPM. Drums on
# channel 9 (GM drum kit) for kick on every beat.
SPEC='{
  "tempo_bpm": 120,
  "time_signature": [4, 4],
  "tracks": [
    {
      "name": "Lead",
      "program": 0,
      "channel": 0,
      "notes": [
        {"pitch": 60, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
        {"pitch": 64, "start_beats": 0.5, "duration_beats": 0.5, "velocity": 100},
        {"pitch": 67, "start_beats": 1.0, "duration_beats": 0.5, "velocity": 100},
        {"pitch": 72, "start_beats": 1.5, "duration_beats": 0.5, "velocity": 100}
      ]
    },
    {
      "name": "Drums",
      "program": 0,
      "channel": 9,
      "notes": [
        {"pitch": 36, "start_beats": 0.0, "duration_beats": 0.1, "velocity": 110},
        {"pitch": 36, "start_beats": 1.0, "duration_beats": 0.1, "velocity": 110},
        {"pitch": 36, "start_beats": 2.0, "duration_beats": 0.1, "velocity": 110},
        {"pitch": 36, "start_beats": 3.0, "duration_beats": 0.1, "velocity": 110}
      ]
    }
  ]
}'

# ── compose: JSON spec → MIDI bytes ──────────────────────────────────────────

test_midi_compose_returns_smf() {
    local code tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        --data "$SPEC" \
        "${AUDIOLLA_BASE_URL}/v1/midi/compose")
    assert_eq "$code" "200" "compose -> 200" || { rm -f "$tmp"; return 1; }
    if ! head -c 4 "$tmp" | grep -q "MThd"; then
        echo "  FAIL: response is not a Standard MIDI File (missing MThd)"
        rm -f "$tmp"; return 1
    fi
    # File must be plausibly sized — empty SMFs are still ~22 bytes (header only).
    local size
    size=$(stat -c%s "$tmp")
    if [ "$size" -lt 50 ]; then
        echo "  FAIL: composed MIDI is suspiciously small ($size bytes)"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: midi_compose_returns_smf ($size bytes)"
}

# ── compose with output_path: stages the .mid file ──────────────────────────

test_midi_compose_output_path() {
    local code body
    body=$(curl -s -o /tmp/audiolla-midi-resp.$$ -w "%{http_code}" \
        --max-time 30 -X POST -H "Content-Type: application/json" \
        --data "$SPEC" \
        "${AUDIOLLA_BASE_URL}/v1/midi/compose?output_path=midi/song.mid")
    code="$body"
    body=$(cat /tmp/audiolla-midi-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-midi-resp.$$
    assert_eq "$code" "200" "compose output_path -> 200" || return 1
    echo "$body" | grep -q '"path":"midi/song.mid"' || {
        echo "  FAIL: response missing path; got: $body"; return 1
    }

    # The staged .mid is retrievable and has MThd.
    local fetched
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/midi/song.mid")
    assert_eq "$code" "200" "GET staged MIDI -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "MThd" || {
        echo "  FAIL: staged file is not MIDI"; rm -f "$fetched"; return 1
    }
    rm -f "$fetched"
    echo "OK: midi_compose_output_path"
}

# ── render: MIDI bytes → audio bytes ─────────────────────────────────────────

test_midi_render_returns_audio() {
    # Build a tiny MIDI on disk first via compose, then feed it to render.
    local mid_path code tmp
    mid_path=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$mid_path" -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        --data "$SPEC" \
        "${AUDIOLLA_BASE_URL}/v1/midi/compose")
    if [ "$code" != "200" ]; then
        echo "  FAIL: pre-render compose failed -> $code"
        rm -f "$mid_path"; return 1
    fi

    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file=@${mid_path}" \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/midi/render")
    rm -f "$mid_path"
    assert_eq "$code" "200" "render -> 200" || { rm -f "$tmp"; return 1; }
    if ! head -c 4 "$tmp" | grep -q "RIFF"; then
        echo "  FAIL: response is not a WAV"
        rm -f "$tmp"; return 1
    fi
    local size
    size=$(stat -c%s "$tmp")
    if [ "$size" -lt 1000 ]; then
        echo "  FAIL: rendered WAV is suspiciously small ($size bytes)"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: midi_render_returns_audio ($size bytes)"
}

# ── render with file_path: stage MIDI then render it via file_path ──────────

test_midi_render_with_file_path() {
    # Compose to staging first.
    local code body
    body=$(curl -s -o /tmp/audiolla-midi-resp.$$ -w "%{http_code}" \
        --max-time 30 -X POST -H "Content-Type: application/json" \
        --data "$SPEC" \
        "${AUDIOLLA_BASE_URL}/v1/midi/compose?output_path=midi/in.mid")
    code="$body"
    rm -f /tmp/audiolla-midi-resp.$$
    if [ "$code" != "200" ]; then
        echo "  FAIL: compose-to-stage failed -> $code"; return 1
    fi

    # Now render via file_path.
    local tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file_path=midi/in.mid" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/midi/render")
    assert_eq "$code" "200" "render file_path -> 200" || { rm -f "$tmp"; return 1; }
    # MP3 starts with ID3 tag or 0xFF 0xFB sync word.
    local first
    first=$(head -c 3 "$tmp" | od -An -tx1 | tr -d ' \n')
    if [[ "$first" != "494433"* && ! "$first" =~ ^fff[abe] ]]; then
        echo "  FAIL: rendered file is not MP3 (first bytes: $first)"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: midi_render_with_file_path"
}

# ── generate: one-shot compose + render ──────────────────────────────────────

test_midi_generate_one_shot() {
    local code tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 60 \
        -X POST -H "Content-Type: application/json" \
        --data "$SPEC" \
        "${AUDIOLLA_BASE_URL}/v1/midi/generate?output_format=wav")
    assert_eq "$code" "200" "generate -> 200" || { rm -f "$tmp"; return 1; }
    if ! head -c 4 "$tmp" | grep -q "RIFF"; then
        echo "  FAIL: response is not a WAV"
        rm -f "$tmp"; return 1
    fi
    local size
    size=$(stat -c%s "$tmp")
    if [ "$size" -lt 1000 ]; then
        echo "  FAIL: generated WAV is suspiciously small ($size bytes)"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: midi_generate_one_shot ($size bytes)"
}

# ── generate with output_path: writes WAV into staging ──────────────────────

test_midi_generate_output_path() {
    local code body
    body=$(curl -s -o /tmp/audiolla-midi-resp.$$ -w "%{http_code}" \
        --max-time 60 -X POST -H "Content-Type: application/json" \
        --data "$SPEC" \
        "${AUDIOLLA_BASE_URL}/v1/midi/generate?output_format=wav&output_path=midi/out.wav")
    code="$body"
    body=$(cat /tmp/audiolla-midi-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-midi-resp.$$
    assert_eq "$code" "200" "generate output_path -> 200" || return 1
    echo "$body" | grep -q '"path":"midi/out.wav"' || {
        echo "  FAIL: response missing path; got: $body"; return 1
    }
    # Round-trip the staged WAV.
    local fetched
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/midi/out.wav")
    assert_eq "$code" "200" "GET generated WAV -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "RIFF" || {
        echo "  FAIL: staged generated file is not WAV"; rm -f "$fetched"; return 1
    }
    rm -f "$fetched"
    echo "OK: midi_generate_output_path"
}

# ── validation: bad pitch → 400 ──────────────────────────────────────────────

test_midi_compose_bad_pitch_400() {
    local code body
    body=$(curl -s -o /tmp/audiolla-midi-resp.$$ -w "%{http_code}" \
        --max-time 30 -X POST -H "Content-Type: application/json" \
        --data '{
            "tempo_bpm": 120,
            "tracks": [{"program": 0, "channel": 0, "notes": [
                {"pitch": 200, "start_beats": 0, "duration_beats": 1, "velocity": 100}
            ]}]
        }' \
        "${AUDIOLLA_BASE_URL}/v1/midi/compose")
    code="$body"
    body=$(cat /tmp/audiolla-midi-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-midi-resp.$$
    assert_eq "$code" "400" "compose bad pitch -> 400" || return 1
    echo "$body" | grep -qi "pitch" || {
        echo "  FAIL: detail missing pitch; got: $body"; return 1
    }
    echo "OK: midi_compose_bad_pitch_400"
}

# ── validation: render rejects non-MIDI bytes → 400 ──────────────────────────

test_midi_render_non_midi_400() {
    local code body bogus
    bogus=$(mktemp)
    echo "not a midi file at all" > "$bogus"
    body=$(curl -s -o /tmp/audiolla-midi-resp.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file=@${bogus}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/render")
    code="$body"
    body=$(cat /tmp/audiolla-midi-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-midi-resp.$$ "$bogus"
    assert_eq "$code" "400" "render non-MIDI -> 400" || return 1
    echo "$body" | grep -qi "MThd" || {
        echo "  FAIL: detail missing MThd; got: $body"; return 1
    }
    echo "OK: midi_render_non_midi_400"
}

harness_run_tests \
    test_midi_compose_returns_smf \
    test_midi_compose_output_path \
    test_midi_render_returns_audio \
    test_midi_render_with_file_path \
    test_midi_generate_one_shot \
    test_midi_generate_output_path \
    test_midi_compose_bad_pitch_400 \
    test_midi_render_non_midi_400
