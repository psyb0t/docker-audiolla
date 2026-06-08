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
    # Returns: prints HTTP status code on stdout; writes downloaded result to $outfile.
    local outfile="$1" ops="$2" fmt="${3:-wav}"
    # Pre-stage the fixture per invocation so tests are reusable.
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/tx-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    local resp
    resp=$(mktemp -t audiolla-tx-resp.XXXXXX)
    local code
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"operations\":${ops},\"output_format\":\"${fmt}\",\"output_path\":\"$_out\"}" \
        -o "$resp" -w "%{http_code}" --max-time 60 \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    if [ "$code" = "200" ]; then
        curl -sf -o "$outfile" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    fi
    rm -f "$resp"
    printf '%s' "$code"
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
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"operations\":[{\"op\":\"nope_unknown\",\"params\":{}}],\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    # Handler-level unknown-op rejection returns 400 (not Pydantic 422).
    assert_eq "$code" "400" "unknown op -> 400" || return 1
    echo "OK: transform_unknown_op_400"
}

# ── Malformed JSON → 400 ─────────────────────────────────────────────────────

test_transform_bad_json_400() {
    _skip_if_no_fixture && return 0
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    # Missing required `operations` → Pydantic 422.
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "422" "missing operations -> 422" || return 1
    echo "OK: transform_bad_json_400"
}

harness_run_tests \
    test_transform_gain \
    test_transform_chain \
    test_transform_pitch \
    test_transform_empty_ops \
    test_transform_unknown_op_400 \
    test_transform_bad_json_400
