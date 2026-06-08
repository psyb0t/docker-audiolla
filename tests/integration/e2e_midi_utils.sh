#!/bin/bash
# /v1/midi/inspect + /v1/midi/transform — counterparts to midi/compose.
#
#     bash tests/integration/e2e_midi_utils.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

# midi-compose covers compose + inspect + transform.
harness_start "midi-compose"

# Compose a known song so we can verify inspect/transform see it.
SPEC='{
  "tempo_bpm": 120,
  "time_signature": [4, 4],
  "tracks": [
    {"name":"Lead","program":0,"channel":0,"notes":[
      {"pitch":60,"start_beats":0.0,"duration_beats":0.5,"velocity":100},
      {"pitch":64,"start_beats":0.5,"duration_beats":0.5,"velocity":100},
      {"pitch":67,"start_beats":1.0,"duration_beats":0.5,"velocity":100}
    ]},
    {"name":"Kick","program":0,"channel":9,"notes":[
      {"pitch":36,"start_beats":0.0,"duration_beats":0.1,"velocity":110},
      {"pitch":36,"start_beats":1.0,"duration_beats":0.1,"velocity":110}
    ]}
  ]
}'

build_demo_midi() {
    local out="$1"
    local code
    code=$(curl -s -o "$out" -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        --data "$SPEC" \
        "${AUDIOLLA_BASE_URL}/v1/midi/compose")
    if [ "$code" != "200" ]; then
        echo "  FAIL: pre-test compose failed -> $code"
        return 1
    fi
}

# ── inspect: reads back tempo + track names ──────────────────────────────

test_inspect_returns_structure() {
    local mid body
    mid=$(mktemp --suffix=.mid)
    build_demo_midi "$mid" || { rm -f "$mid"; return 1; }
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/inspect")
    rm -f "$mid"
    if ! echo "$body" | jq -e '.type == 1' >/dev/null 2>&1; then
        echo "  FAIL: type != 1; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.tempo_changes[0].bpm | (. > 119 and . < 121)' >/dev/null 2>&1; then
        echo "  FAIL: tempo not ~120; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.tracks | map(.name) | any(. == "Lead")' >/dev/null 2>&1; then
        echo "  FAIL: Lead track missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.tracks | map(.name) | any(. == "Kick")' >/dev/null 2>&1; then
        echo "  FAIL: Kick track missing; body: $body"; return 1
    fi
    echo "OK: inspect_returns_structure"
}

# ── inspect rejects non-MIDI input → 400 ──────────────────────────────────

test_inspect_rejects_non_midi() {
    local code body bogus
    bogus=$(mktemp)
    echo "definitely not a midi file" > "$bogus"
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${bogus}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${bogus}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/tmp/audiolla-mi.$$" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/inspect")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/tmp/audiolla-mi.$$" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    code="$body"
    body=$(cat /tmp/audiolla-mi.$$ 2>/dev/null)
    rm -f /tmp/audiolla-mi.$$ "$bogus"
    assert_eq "$code" "400" "non-MIDI -> 400" || return 1
    echo "$body" | grep -qi "MThd" || { echo "  FAIL: detail missing MThd; body: $body"; return 1; }
    echo "OK: inspect_rejects_non_midi"
}

# ── transform: transpose +12 and confirm via inspect of the output ─────────

test_transform_transpose_round_trips() {
    local mid out before after
    mid=$(mktemp --suffix=.mid)
    build_demo_midi "$mid" || { rm -f "$mid"; return 1; }

    out=$(mktemp --suffix=.mid)
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"transpose_semitones\":12,\"output_path\":\"$_out\"}" \
        -o "$out" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/transform")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$out" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "transform -> 200" || { rm -f "$mid" "$out"; return 1; }
    if [ "$(stat -c%s "$out")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$mid" "$out"; return 1
    fi

    # Inspect both to confirm the structure is preserved.
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    before=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/inspect")
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${out}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${out}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    after=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/inspect")
    rm -f "$mid" "$out"

    local lead_count_before lead_count_after
    lead_count_before=$(echo "$before" | jq -r '[.tracks[] | select(.name == "Lead")] | .[0].note_on_count')
    lead_count_after=$(echo "$after"  | jq -r '[.tracks[] | select(.name == "Lead")] | .[0].note_on_count')
    if [ "$lead_count_before" != "$lead_count_after" ]; then
        echo "  FAIL: lead note count changed ($lead_count_before -> $lead_count_after)"
        return 1
    fi
    echo "OK: transform_transpose_round_trips (lead notes preserved: $lead_count_after)"
}

# ── transform: drop_channels removes drums ─────────────────────────────────

test_transform_drop_drums() {
    local mid out after
    mid=$(mktemp --suffix=.mid)
    build_demo_midi "$mid" || { rm -f "$mid"; return 1; }

    out=$(mktemp --suffix=.mid)
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"drop_channels\":\"9\",\"output_path\":\"$_out\"}" \
        -o "$out" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/transform")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$out" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "transform drop_channels -> 200" || { rm -f "$mid" "$out"; return 1; }

    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${out}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${out}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    after=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/inspect")
    rm -f "$mid" "$out"
    # No track should claim channel 9 anymore.
    if echo "$after" | jq -e '.tracks | any(.channels | any(. == 9))' >/dev/null 2>&1; then
        echo "  FAIL: channel 9 still present after drop; body: $after"; return 1
    fi
    echo "OK: transform_drop_drums"
}

# ── transform: tempo override + output_path ────────────────────────────────

test_transform_tempo_output_path() {
    local mid body code fetched after
    mid=$(mktemp --suffix=.mid)
    build_demo_midi "$mid" || { rm -f "$mid"; return 1; }

    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"tempo_bpm\":200,\"output_path\":\"midi/transformed.mid\"}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/transform")
    rm -f "$mid"
    if ! echo "$body" | jq -e '.path == "midi/transformed.mid"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    # Fetch + re-inspect to confirm tempo flipped.
    fetched=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/midi/transformed.mid")
    assert_eq "$code" "200" "GET staged -> 200" || { rm -f "$fetched"; return 1; }
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${fetched}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${fetched}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    after=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/inspect")
    rm -f "$fetched"
    if ! echo "$after" | jq -e '.tempo_changes[0].bpm | (. > 199 and . < 201)' >/dev/null 2>&1; then
        echo "  FAIL: tempo not 200 after transform; body: $after"; return 1
    fi
    echo "OK: transform_tempo_output_path"
}

# ── transform: quantize_grid_beats snaps notes to grid ────────────────────────

test_transform_quantize_grid_beats() {
    local mid out code
    mid=$(mktemp --suffix=.mid)
    build_demo_midi "$mid" || { rm -f "$mid"; return 1; }
    out=$(mktemp --suffix=.mid)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"quantize_grid_beats\":0.25,\"output_path\":\"$_out\"}" \
        -o "$out" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/transform")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$out" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    rm -f "$mid"
    assert_eq "$code" "200" "quantize_grid_beats -> 200" || { rm -f "$out"; return 1; }
    [ -s "$out" ] || { echo "  FAIL: not MIDI"; rm -f "$out"; return 1; }
    rm -f "$out"
    echo "OK: transform_quantize_grid_beats"
}

# ── transform: keep_channels whitelists only specified channels ────────────────

test_transform_keep_channels() {
    local mid out after code
    mid=$(mktemp --suffix=.mid)
    build_demo_midi "$mid" || { rm -f "$mid"; return 1; }
    out=$(mktemp --suffix=.mid)
    # Keep only channel 0 (Lead) — channel 9 (Kick) should disappear.
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"keep_channels\":\"0\",\"output_path\":\"$_out\"}" \
        -o "$out" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/transform")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$out" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "keep_channels=0 -> 200" || { rm -f "$mid" "$out"; return 1; }
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${out}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${out}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    after=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/inspect")
    rm -f "$mid" "$out"
    # Channel 9 must be gone after keeping only channel 0.
    if echo "$after" | jq -e '.tracks | any(.channels | any(. == 9))' >/dev/null 2>&1; then
        echo "  FAIL: channel 9 still present after keep_channels=0; body: $after"
        return 1
    fi
    echo "OK: transform_keep_channels"
}

# ── invalid: both keep + drop → 400 ───────────────────────────────────────

test_transform_both_keep_drop_400() {
    local mid code body
    mid=$(mktemp --suffix=.mid)
    build_demo_midi "$mid" || { rm -f "$mid"; return 1; }
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"keep_channels\":\"0\",\"drop_channels\":\"9\",\"output_path\":\"$_out\"}" \
        -o "/tmp/audiolla-mt.$$" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/transform")
    code="$body"
    body=$(cat /tmp/audiolla-mt.$$ 2>/dev/null)
    rm -f /tmp/audiolla-mt.$$ "$mid"
    assert_eq "$code" "400" "both lists -> 400" || return 1
    echo "OK: transform_both_keep_drop_400"
}

harness_run_tests \
    test_inspect_returns_structure \
    test_inspect_rejects_non_midi \
    test_transform_transpose_round_trips \
    test_transform_drop_drums \
    test_transform_tempo_output_path \
    test_transform_quantize_grid_beats \
    test_transform_keep_channels \
    test_transform_both_keep_drop_400
