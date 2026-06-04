#!/bin/bash
# MIDI humanize — /v1/midi/humanize.
#
#     bash tests/integration/e2e_midi_humanize.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "midi-compose"

# Generate a minimal valid MIDI fixture.
make_midi_fixture() {
    python3 - "$1" <<'PY'
import sys, struct

def write_midi(path):
    # Minimal Type-0 MIDI: tempo 120bpm, one note C4 quarter note
    tpb = 480
    tempo = 500000  # 120bpm in microseconds per beat

    # Track events (delta, event)
    events = bytearray()
    # Tempo meta event
    events += bytes([0x00, 0xFF, 0x51, 0x03])
    events += struct.pack('>I', tempo)[1:]  # 3 bytes
    # Note on C4 vel 80
    events += bytes([0x00, 0x90, 0x3C, 0x50])
    # Note off after 1 beat
    events += bytes([0x83, 0x60, 0x80, 0x3C, 0x00])
    # End of track
    events += bytes([0x00, 0xFF, 0x2F, 0x00])

    header = b'MThd' + struct.pack('>I', 6) + struct.pack('>HHH', 0, 1, tpb)
    track = b'MTrk' + struct.pack('>I', len(events)) + bytes(events)
    with open(path, 'wb') as f:
        f.write(header + track)

write_midi(sys.argv[1])
PY
}

MIDI_FIXTURE=$(mktemp --suffix=.mid)
make_midi_fixture "$MIDI_FIXTURE"
trap "rm -f $MIDI_FIXTURE" EXIT

# ── default params return valid MIDI ─────────────────────────────────────────

test_humanize_returns_midi() {
    local tmpf code sz
    tmpf=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${MIDI_FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    assert_eq "$code" "200" "humanize default -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "MThd"; then
        echo "  FAIL: output is not MIDI"; rm -f "$tmpf"; return 1
    fi
    sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    if [ "$sz" -lt 20 ]; then
        echo "  FAIL: MIDI too small ($sz bytes)"; return 1
    fi
    echo "OK: humanize_returns_midi (${sz}B)"
}

# ── seed makes output deterministic ──────────────────────────────────────────

test_humanize_seed_deterministic() {
    local tmp1 tmp2 code1 code2
    tmp1=$(mktemp --suffix=.mid)
    tmp2=$(mktemp --suffix=.mid)
    code1=$(curl -s -o "$tmp1" -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${MIDI_FIXTURE}" \
        -F "seed=42" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    code2=$(curl -s -o "$tmp2" -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${MIDI_FIXTURE}" \
        -F "seed=42" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    assert_eq "$code1" "200" "humanize seed 1st call -> 200" || { rm -f "$tmp1" "$tmp2"; return 1; }
    assert_eq "$code2" "200" "humanize seed 2nd call -> 200" || { rm -f "$tmp1" "$tmp2"; return 1; }
    if ! cmp -s "$tmp1" "$tmp2"; then
        echo "  FAIL: same seed produced different output"; rm -f "$tmp1" "$tmp2"; return 1
    fi
    rm -f "$tmp1" "$tmp2"
    echo "OK: humanize_seed_deterministic"
}

# ── output_path stages result ────────────────────────────────────────────────

test_humanize_output_path() {
    local body code fetched
    body=$(curl -s --max-time 30 -X POST \
        -F "file=@${MIDI_FIXTURE}" \
        -F "timing_ms=5" \
        -F "velocity_pct=5" \
        -F "output_path=humanize_test/out.mid" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    if ! echo "$body" | jq -e '.path == "humanize_test/out.mid"' >/dev/null 2>&1; then
        echo "  FAIL: path missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.timing_ms == 5' >/dev/null 2>&1; then
        echo "  FAIL: timing_ms missing from response; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/humanize_test/out.mid")
    assert_eq "$code" "200" "GET staged humanized MIDI -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "MThd" || {
        echo "  FAIL: staged file not MIDI"; rm -f "$fetched"; return 1
    }
    rm -f "$fetched"
    echo "OK: humanize_output_path"
}

# ── non-MIDI file → 400 ───────────────────────────────────────────────────────

test_humanize_non_midi_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    assert_eq "$code" "400" "non-MIDI file -> 400" || return 1
    echo "OK: humanize_non_midi_400"
}

# ── timing_ms out of range → 400 ─────────────────────────────────────────────

test_humanize_invalid_timing_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${MIDI_FIXTURE}" \
        -F "timing_ms=1000" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    assert_eq "$code" "400" "timing_ms=1000 -> 400" || return 1
    echo "OK: humanize_invalid_timing_400"
}

harness_run_tests \
    test_humanize_returns_midi \
    test_humanize_seed_deterministic \
    test_humanize_output_path \
    test_humanize_non_midi_400 \
    test_humanize_invalid_timing_400
