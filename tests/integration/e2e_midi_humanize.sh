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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${MIDI_FIXTURE}")"
    local _out="out/result-$$-$RANDOM.mid"
    curl -sf -X PUT --data-binary "@${MIDI_FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o /dev/null \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    assert_eq "$code" "200" "humanize default -> 200" || return 1
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: GET staged humanized MIDI failed"; rm -f "$tmpf"; return 1
    }
    if [ "$(head -c 4 "$tmpf")" != "MThd" ]; then
        echo "  FAIL: staged file is not MIDI (no MThd)"; rm -f "$tmpf"; return 1
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
    local _stage="uploads/$(basename "${MIDI_FIXTURE}")"
    local _out1="out/result-$$-${RANDOM}-1.mid"
    local _out2="out/result-$$-${RANDOM}-2.mid"
    curl -sf -X PUT --data-binary "@${MIDI_FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code1=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"seed\":42,\"output_path\":\"$_out1\"}" \
        -o /dev/null \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    curl -sf -o "$tmp1" "${AUDIOLLA_BASE_URL}/v1/files/${_out1}" || true
    code2=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"seed\":42,\"output_path\":\"$_out2\"}" \
        -o /dev/null \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    curl -sf -o "$tmp2" "${AUDIOLLA_BASE_URL}/v1/files/${_out2}" || true
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${MIDI_FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${MIDI_FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"timing_ms\":5,\"velocity_pct\":5,\"output_path\":\"humanize_test/out.mid\"}" \
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
    if [ "$(head -c 4 "$fetched")" != "MThd" ]; then
        echo "  FAIL: staged file not MIDI (no MThd)"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: humanize_output_path"
}

# ── non-MIDI file → 400 ───────────────────────────────────────────────────────

test_humanize_non_midi_400() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.mid"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/humanize")
    assert_eq "$code" "400" "non-MIDI file -> 400" || return 1
    echo "OK: humanize_non_midi_400"
}

# ── timing_ms out of range → 400 ─────────────────────────────────────────────

test_humanize_invalid_timing_400() {
    local code
    local _stage="uploads/$(basename "${MIDI_FIXTURE}")"
    local _out="out/result-$$-$RANDOM.mid"
    curl -sf -X PUT --data-binary "@${MIDI_FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"timing_ms\":1000,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
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
