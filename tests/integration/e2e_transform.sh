#!/bin/bash
# pysox transform chain end-to-end. CPU-only.
#
# Fixture: tests/integration/.fixtures/audio.wav.
#
#     bash tests/integration/e2e_transform.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "sox-transform"

_skip_if_no_fixture() {
    if [ ! -f "$FIXTURE" ]; then
        echo "  SKIP: fixture not found at ${FIXTURE}"
        return 0
    fi
    return 1
}

_post_transform() {
    local outfile="$1" ops="$2" fmt="${3:-wav}"
    curl -s -o "$outfile" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "operations=${ops}" \
        -F "output_format=${fmt}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform"
}

# ── Single op: gain -3 dB → RIFF WAV ─────────────────────────────────────────

test_transform_gain() {
    _skip_if_no_fixture && return 0
    local tmp code
    tmp=$(mktemp -t audiolla-tx.XXXXXX) || return 2
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN
    code=$(_post_transform "$tmp" '[{"op":"gain","params":{"db":-3}}]' wav)
    assert_eq "$code" "200" "transform gain -> 200" || return 1
    local head4
    head4=$(head -c 4 "$tmp" | od -An -c | tr -d ' \n')
    assert_eq "$head4" "RIFF" "transform gain → RIFF" || return 1
    echo "OK: transform_gain"
}

# ── Chain of 4 ops (EQ + compressor + reverb + normalize) ────────────────────

test_transform_chain() {
    _skip_if_no_fixture && return 0
    local tmp code
    tmp=$(mktemp -t audiolla-chain.XXXXXX) || return 2
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN
    local ops='[
      {"op":"equalizer","params":{"frequency":3000,"width_q":1.5,"gain_db":2}},
      {"op":"compand","params":{"attack_time":0.02,"decay_time":0.2,"soft_knee_db":6,"tf_points":[[-70,-70],[-30,-30],[-20,-15],[0,-10]]}},
      {"op":"reverb","params":{"reverberance":30,"pre_delay_ms":0,"room_scale":50}},
      {"op":"gain","params":{"db":-1}}
    ]'
    code=$(_post_transform "$tmp" "$ops" wav)
    assert_eq "$code" "200" "transform chain -> 200" || return 1
    local size
    size=$(stat -c %s "$tmp")
    if [ "$size" -lt 100000 ]; then
        echo "  FAIL: chain output too small ($size bytes)"; return 1
    fi
    echo "OK: transform_chain (${size}B)"
}

# ── Pitch shift +2 semitones → still RIFF ────────────────────────────────────

test_transform_pitch() {
    _skip_if_no_fixture && return 0
    local tmp code
    tmp=$(mktemp -t audiolla-pitch.XXXXXX) || return 2
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN
    code=$(_post_transform "$tmp" '[{"op":"pitch","params":{"n_semitones":2}}]' wav)
    assert_eq "$code" "200" "pitch +2 semitones -> 200" || return 1
    local head4
    head4=$(head -c 4 "$tmp" | od -An -c | tr -d ' \n')
    assert_eq "$head4" "RIFF" "pitch shift → RIFF" || return 1
    echo "OK: transform_pitch"
}

# ── Empty operations list → still 200 (no-op identity) ───────────────────────

test_transform_empty_ops() {
    _skip_if_no_fixture && return 0
    local tmp code
    tmp=$(mktemp -t audiolla-noop.XXXXXX) || return 2
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN
    code=$(_post_transform "$tmp" '[]' wav)
    assert_eq "$code" "200" "empty ops -> 200" || return 1
    echo "OK: transform_empty_ops"
}

# ── Unknown op → 400 ─────────────────────────────────────────────────────────

test_transform_unknown_op_400() {
    _skip_if_no_fixture && return 0
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F 'operations=[{"op":"not-a-real-op","params":{}}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "400" "unknown op -> 400" || return 1
    echo "OK: transform_unknown_op_400"
}

# ── Malformed JSON → 400 ─────────────────────────────────────────────────────

test_transform_bad_json_400() {
    _skip_if_no_fixture && return 0
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F 'operations=this is not json' \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "400" "malformed JSON -> 400" || return 1
    echo "OK: transform_bad_json_400"
}

harness_run_tests \
    test_transform_gain \
    test_transform_chain \
    test_transform_pitch \
    test_transform_empty_ops \
    test_transform_unknown_op_400 \
    test_transform_bad_json_400
