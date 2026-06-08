#!/bin/bash
# Audio metadata read/write via mutagen — ID3 (MP3) and WAV.
#
#     bash tests/integration/e2e_metadata.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE_WAV="${_DIR}/.fixtures/audio.wav"
FIXTURE_MP3="${_DIR}/.fixtures/audio.mp3"
FIXTURE_DIR="${_DIR}/.fixtures"

harness_start "metadata"

# Build MP3 fixture if missing.
build_mp3_fixture() {
    if [ -f "$FIXTURE_MP3" ]; then
        return 0
    fi
    docker run --rm \
        --entrypoint ffmpeg \
        -v "${FIXTURE_DIR}:${FIXTURE_DIR}" \
        "$HARNESS_IMAGE" \
        -y -hide_banner -nostats \
        -i "$FIXTURE_WAV" -b:a 192k \
        "$FIXTURE_MP3" >/dev/null 2>&1
    [ -f "$FIXTURE_MP3" ] || { echo "  FAIL: could not build MP3 fixture"; return 1; }
}

# ── read WAV: returns duration + sample rate ──────────────────────────────────

test_metadata_read_wav_returns_info() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE_WAV}")"
    curl -sf -X PUT --data-binary "@${FIXTURE_WAV}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/metadata")
    if ! echo "$body" | jq -e '.duration_sec | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: duration_sec missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.sample_rate == 44100' >/dev/null 2>&1; then
        echo "  FAIL: sample_rate not 44100; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.channels | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: channels missing; body: $body"; return 1
    fi
    echo "OK: metadata_read_wav_returns_info ($(echo "$body" | jq -r '.duration_sec')s)"
}

# ── read MP3: tags dict present ───────────────────────────────────────────────

test_metadata_read_mp3_returns_tags() {
    build_mp3_fixture || return 1
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE_MP3}")"
    curl -sf -X PUT --data-binary "@${FIXTURE_MP3}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/metadata")
    if ! echo "$body" | jq -e 'has("title") and has("artist")' >/dev/null 2>&1; then
        echo "  FAIL: title/artist fields missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e 'has("duration_sec") and has("sample_rate")' >/dev/null 2>&1; then
        echo "  FAIL: duration_sec/sample_rate missing; body: $body"; return 1
    fi
    echo "OK: metadata_read_mp3_returns_tags"
}

# ── write + read back: tags round-trip on MP3 ────────────────────────────────

test_metadata_write_tags_roundtrip_mp3() {
    build_mp3_fixture || return 1
    local body title artist
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE_MP3}")"
    curl -sf -X PUT --data-binary "@${FIXTURE_MP3}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    # tags is a JSON-encoded string carrying the tag map.
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"tags\":\"{\\\"title\\\":\\\"My Track\\\",\\\"artist\\\":\\\"Test Artist\\\"}\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/metadata")
    title=$(echo "$body" | jq -r '.title // empty')
    artist=$(echo "$body" | jq -r '.artist // empty')
    if [ "$title" != "My Track" ]; then
        echo "  FAIL: title not written; expected 'My Track' got '$title'; body: $body"
        return 1
    fi
    if [ "$artist" != "Test Artist" ]; then
        echo "  FAIL: artist not written; expected 'Test Artist' got '$artist'; body: $body"
        return 1
    fi
    echo "OK: metadata_write_tags_roundtrip_mp3 (title='$title' artist='$artist')"
}

# ── invalid tags JSON → 400 ───────────────────────────────────────────────────

test_metadata_bad_tags_json_400() {
    build_mp3_fixture || return 1
    local code body
    tmpfile=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE_MP3}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE_MP3}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"tags\":\"not-json-at-all\"}" \
        -o "$tmpfile" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/metadata")
    body=$(cat "$tmpfile")
    rm -f "$tmpfile"
    [[ "$code" = "400" || "$code" = "422" ]] || { echo "  FAIL: invalid tags JSON -> got $code"; return 1; }
    if ! echo "$body" | grep -qi "tags"; then
        echo "  FAIL: detail missing 'tags'; body: $body"; return 1
    fi
    echo "OK: metadata_bad_tags_json_400 (code=$code)"
}

# ── missing engine → 404 ─────────────────────────────────────────────────────

test_metadata_engine_missing_404() {
    # The harness_start already ensured "metadata" is available. This test
    # calls the endpoint with a staged file_path that doesn't exist to trigger
    # the AudioConversionError path.
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"nonexistent/path/file.wav\"}" -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/metadata")
    [[ "$code" = "400" || "$code" = "404" || "$code" = "422" ]] || { echo "  FAIL: nonexistent file -> got $code"; return 1; }
    echo "OK: metadata_engine_missing_404 (code=$code)"
}

harness_run_tests \
    test_metadata_read_wav_returns_info \
    test_metadata_read_mp3_returns_tags \
    test_metadata_write_tags_roundtrip_mp3 \
    test_metadata_bad_tags_json_400 \
    test_metadata_engine_missing_404
