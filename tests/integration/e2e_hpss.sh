#!/bin/bash
# HPSS (harmonic/percussive source separation) — /v1/audio/separate/hpss end-to-end.
#
# The endpoint accepts JSON request and produces a ZIP archive at the
# requested output_path containing harmonic.<fmt> and percussive.<fmt>.
# The HTTP response is JSON {path, size, stems, output_format}.
#
#     bash tests/integration/e2e_hpss.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "hpss"

# ── basic call returns JSON {path, ...}, ZIP is staged at output_path ────────

test_hpss_returns_zip() {
    local body code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="hpss-out/result-$$-$RANDOM.zip"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss")
    if ! echo "$body" | jq -e '.path == "'"$_out"'"' >/dev/null 2>&1; then
        echo "  FAIL: response missing expected path; body: $body"; return 1
    fi
    # Fetch the staged ZIP
    local fetched
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/${_out}")
    assert_eq "$code" "200" "GET staged ZIP -> 200" || { rm -f "$fetched"; return 1; }
    # ZIP magic bytes: 50 4b 03 04
    if ! head -c 2 "$fetched" | od -A n -t x1 | grep -q "50 4b"; then
        echo "  FAIL: staged file is not a ZIP; first bytes: $(head -c 8 "$fetched" | od -A n -t x1)"
        rm -f "$fetched"; return 1
    fi
    echo "OK: hpss_returns_zip ($(stat -c%s "$fetched") bytes)"
    rm -f "$fetched"
}

# ── ZIP contains harmonic.wav and percussive.wav ─────────────────────────────

test_hpss_zip_contains_both_stems() {
    local body entries
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="hpss-out/stems-$$-$RANDOM.zip"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss")
    echo "$body" | jq -e '.path' >/dev/null 2>&1 || {
        echo "  FAIL: no path in response: $body"; return 1
    }
    local fetched
    fetched=$(mktemp)
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged ZIP"; rm -f "$fetched"; return 1
    }
    entries=$(python3 -c "
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as z:
    print(' '.join(sorted(z.namelist())))
" "$fetched" 2>/dev/null)
    rm -f "$fetched"
    if [[ "$entries" != *"harmonic.wav"* ]]; then
        echo "  FAIL: harmonic.wav not in ZIP; entries: $entries"; return 1
    fi
    if [[ "$entries" != *"percussive.wav"* ]]; then
        echo "  FAIL: percussive.wav not in ZIP; entries: $entries"; return 1
    fi
    echo "OK: hpss_zip_contains_both_stems (entries: $entries)"
}

# ── each stem is valid WAV audio ────────────────────────────────────────────

test_hpss_stems_are_valid_wav() {
    local body fetched tmpdir
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="hpss-out/valid-$$-$RANDOM.zip"
    fetched=$(mktemp)
    tmpdir=$(mktemp -d)
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss")
    echo "$body" | jq -e '.path' >/dev/null 2>&1 || {
        echo "  FAIL: no path in response: $body"
        rm -f "$fetched"; rm -rf "$tmpdir"; return 1
    }
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged ZIP"
        rm -f "$fetched"; rm -rf "$tmpdir"; return 1
    }
    python3 -c "
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
" "$fetched" "$tmpdir"
    rm -f "$fetched"
    for stem in harmonic percussive; do
        if ! head -c 4 "${tmpdir}/${stem}.wav" | grep -q "RIFF"; then
            echo "  FAIL: ${stem}.wav is not WAV"
            rm -rf "$tmpdir"; return 1
        fi
    done
    echo "OK: hpss_stems_are_valid_wav"
    rm -rf "$tmpdir"
}

# ── output_format=mp3 changes stem extension ────────────────────────────────

test_hpss_output_format_mp3() {
    local body entries fetched
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="hpss-out/mp3-$$-$RANDOM.zip"
    fetched=$(mktemp)
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss")
    echo "$body" | jq -e '.path' >/dev/null 2>&1 || {
        echo "  FAIL: no path in response: $body"; rm -f "$fetched"; return 1
    }
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged ZIP"; rm -f "$fetched"; return 1
    }
    entries=$(python3 -c "
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as z:
    print(' '.join(sorted(z.namelist())))
" "$fetched" 2>/dev/null)
    rm -f "$fetched"
    if [[ "$entries" != *"harmonic.mp3"* ]]; then
        echo "  FAIL: harmonic.mp3 not in ZIP (output_format=mp3); entries: $entries"; return 1
    fi
    echo "OK: hpss_output_format_mp3 (entries: $entries)"
}

# ── missing file → 404 (handler-level — file_path provided but file absent) ─

test_hpss_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"nonexistent/ghost.wav\",\"output_path\":\"hpss-out/ghost-$$.zip\"}" \
        -o "/dev/null" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: hpss_missing_file_404"
}

# ── output_path: writes ZIP to staging area ──────────────────────────────────

test_hpss_output_path() {
    local body code tmpout
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"hpss/stems.zip\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss")
    if ! echo "$body" | jq -e '.path == "hpss/stems.zip"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/hpss/stems.zip")
    assert_eq "$code" "200" "GET staged ZIP -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 2 "$tmpout" | od -A n -t x1 | grep -q "50 4b"; then
        echo "  FAIL: staged file is not a ZIP"
        rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: hpss_output_path"
}

harness_run_tests \
    test_hpss_returns_zip \
    test_hpss_zip_contains_both_stems \
    test_hpss_stems_are_valid_wav \
    test_hpss_output_format_mp3 \
    test_hpss_missing_file_404 \
    test_hpss_output_path
