#!/bin/bash
# Real Demucs separation end-to-end. Requires the CUDA image + a GPU.
#
# Fixture: tests/integration/.fixtures/audio.wav (8 s stereo @ 44.1 kHz).
# If the fixture is absent every test skips cleanly.
#
#     bash tests/integration/e2e_separation.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# CUDA-only engine: pin image + GPU flag BEFORE sourcing harness.sh so its
# default for HARNESS_IMAGE doesn't lock in the CPU image.
: "${HARNESS_IMAGE:=psyb0t/audiolla:local-cuda}"
: "${HARNESS_GPU:=1}"
export HARNESS_IMAGE HARNESS_GPU

# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "htdemucs"

_skip_if_no_fixture() {
    if [ ! -f "$FIXTURE" ]; then
        echo "  SKIP: fixture not found at ${FIXTURE}"
        return 0
    fi
    return 1
}

# ── /healthz lists htdemucs ──────────────────────────────────────────────────

test_healthz_has_htdemucs() {
    local out
    out=$(audiolla_get "/healthz") || { echo "  FAIL: /healthz unreachable"; return 1; }
    assert_contains "$out" "htdemucs" "/healthz lists htdemucs" || return 1
    echo "OK: healthz_has_htdemucs"
}

# ── /v1/engines: htdemucs registers its stems ────────────────────────────────

test_engines_htdemucs_stems() {
    local out
    out=$(audiolla_get "/v1/engines") || { echo "  FAIL: /v1/engines unreachable"; return 1; }
    for stem in vocals drums bass other; do
        assert_contains "$out" "\"$stem\"" "/v1/engines lists $stem" || return 1
    done
    echo "OK: engines_htdemucs_stems"
}

# ── Single stem → audio bytes directly (not zip) ─────────────────────────────

test_separate_single_stem_audio() {
    _skip_if_no_fixture && return 0
    local tmp code
    tmp=$(mktemp -t audiolla-vocals.XXXXXX) || return 2
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN

    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 300 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=htdemucs" \
        -F "stems=vocals" \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate")
    assert_eq "$code" "200" "separate single stem -> 200" || return 1
    local head4
    head4=$(head -c 4 "$tmp" | od -An -c | tr -d ' \n')
    assert_eq "$head4" "RIFF" "single-stem response is a WAV (RIFF header)" || return 1
    local size
    size=$(stat -c %s "$tmp")
    if [ "$size" -lt 100000 ]; then
        echo "  FAIL: single-stem WAV too small ($size bytes)"; return 1
    fi
    echo "OK: separate_single_stem_audio (${size}B)"
}

# ── Multiple stems → ZIP with one entry per stem ─────────────────────────────

test_separate_multi_stem_zip() {
    _skip_if_no_fixture && return 0
    local tmp code
    tmp=$(mktemp -t audiolla-stems.XXXXXX) || return 2
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN

    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 300 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=htdemucs" \
        -F "stems=vocals" -F "stems=drums" -F "stems=bass" -F "stems=other" \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate")
    assert_eq "$code" "200" "separate 4 stems -> 200" || return 1
    local head2
    head2=$(head -c 2 "$tmp" | od -An -c | tr -d ' \n')
    assert_eq "$head2" "PK" "multi-stem response is a ZIP" || return 1

    local list
    list=$(unzip -l "$tmp" 2>/dev/null | awk 'NR>3 && NF>=4 {print $NF}' | head -4)
    for stem in vocals.wav drums.wav bass.wav other.wav; do
        if ! echo "$list" | grep -qx "$stem"; then
            echo "  FAIL: zip missing $stem"; return 1
        fi
    done
    echo "OK: separate_multi_stem_zip"
}

# ── Unknown engine slug → 404 ────────────────────────────────────────────────

test_separate_unknown_engine_404() {
    _skip_if_no_fixture && return 0
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=this-does-not-exist" \
        -F "stems=vocals" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate")
    assert_eq "$code" "404" "unknown engine -> 404" || return 1
    echo "OK: separate_unknown_engine_404"
}

# ── Unknown stem → 400 ───────────────────────────────────────────────────────

test_separate_unknown_stem_400() {
    _skip_if_no_fixture && return 0
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=htdemucs" \
        -F "stems=not-a-real-stem" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate")
    assert_eq "$code" "400" "unknown stem -> 400" || return 1
    echo "OK: separate_unknown_stem_400"
}

# ── cuda_only enforcement — htdemucs_ft has cuda_only=true in engines.json.
# Spawn a short-lived CPU container with AUDIOLLA_DEVICE=cpu and confirm the
# server rejects an htdemucs_ft separate request with 400.

test_separate_cuda_only_on_cpu_400() {
    _skip_if_no_fixture && return 0
    local port name code
    port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
    name="audiolla-cudaonly-$$-${RANDOM}"
    # Use the CUDA image (which has htdemucs_ft in engines.json) but FORCE
    # AUDIOLLA_DEVICE=cpu so the cuda_only validator fires. Realistic
    # "operator pinned device=cpu on a GPU image" scenario.
    docker run -d --rm --name "$name" \
        --user "$(id -u):$(id -g)" \
        -v "${HARNESS_CACHE_DIR}:/data" \
        -e AUDIOLLA_DEVICE=cpu \
        -e AUDIOLLA_ENABLED_ENGINES="htdemucs_ft" \
        -p "${port}:8000" psyb0t/audiolla:local-cuda >/dev/null
    # shellcheck disable=SC2064
    trap "docker rm -f '$name' >/dev/null 2>&1 || true" RETURN

    # Wait for /healthz. htdemucs_ft prefetch is ~320MB across 4 sub-models.
    for _ in $(seq 1 240); do
        curl -sf --max-time 3 "http://127.0.0.1:${port}/healthz" >/dev/null && break
        sleep 2
    done

    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=htdemucs_ft" \
        -F "stems=vocals" \
        "http://127.0.0.1:${port}/v1/audio/separate")
    assert_eq "$code" "400" "htdemucs_ft on cpu device -> 400" || return 1
    echo "OK: separate_cuda_only_on_cpu_400"
}

harness_run_tests \
    test_healthz_has_htdemucs \
    test_engines_htdemucs_stems \
    test_separate_single_stem_audio \
    test_separate_multi_stem_zip \
    test_separate_unknown_engine_404 \
    test_separate_unknown_stem_400 \
    test_separate_cuda_only_on_cpu_400
