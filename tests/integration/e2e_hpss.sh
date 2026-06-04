#!/bin/bash
# HPSS (harmonic/percussive source separation) — /v1/audio/separate/hpss end-to-end.
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

# ── returns a ZIP with harmonic + percussive stems ───────────────────────────

test_hpss_returns_zip() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss")
    assert_eq "$code" "200" "hpss -> 200" || { rm -f "$tmpout"; return 1; }
    # ZIP magic bytes: 50 4b 03 04
    if ! head -c 2 "$tmpout" | od -A n -t x1 | grep -q "50 4b"; then
        echo "  FAIL: response is not a ZIP; first bytes: $(head -c 8 "$tmpout" | od -A n -t x1)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: hpss_returns_zip ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── ZIP contains harmonic.wav and percussive.wav ────────────────────────────

test_hpss_zip_contains_both_stems() {
    local tmpout entries
    tmpout=$(mktemp)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss" > "$tmpout"
    entries=$(python3 -c "
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as z:
    print(' '.join(sorted(z.namelist())))
" "$tmpout" 2>/dev/null)
    rm -f "$tmpout"
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
    local tmpout tmpdir
    tmpout=$(mktemp)
    tmpdir=$(mktemp -d)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss" > "$tmpout"
    python3 -c "
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
" "$tmpout" "$tmpdir"
    rm -f "$tmpout"
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
    local tmpout entries
    tmpout=$(mktemp)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss" > "$tmpout"
    entries=$(python3 -c "
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as z:
    print(' '.join(sorted(z.namelist())))
" "$tmpout" 2>/dev/null)
    rm -f "$tmpout"
    if [[ "$entries" != *"harmonic.mp3"* ]]; then
        echo "  FAIL: harmonic.mp3 not in ZIP (output_format=mp3); entries: $entries"; return 1
    fi
    echo "OK: hpss_output_format_mp3 (entries: $entries)"
}

# ── missing file → 400 ──────────────────────────────────────────────────────

test_hpss_missing_file_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=nonexistent/ghost.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate/hpss")
    assert_eq "$code" "400" "missing file -> 400" || return 1
    echo "OK: hpss_missing_file_400"
}

# ── output_path: writes ZIP to staging area ──────────────────────────────────

test_hpss_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=hpss/stems.zip" \
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
    test_hpss_missing_file_400 \
    test_hpss_output_path
