#!/bin/bash
# shellcheck shell=bash
# Container lifecycle harness for audiolla integration tests.
#
# Each test_*.sh / e2e_*.sh sources this, declares the engine slugs it needs,
# calls harness_start, runs checks via harness_run_tests, and the EXIT trap
# tears the container down. No shared state between files.
#
#     bash tests/integration/test_endpoints.sh
#     bash tests/integration/e2e_separation.sh
#
# Env knobs:
#   HARNESS_IMAGE          docker image (default psyb0t/audiolla:local)
#   HARNESS_CACHE_DIR      host dir for /data mount (default $REPO_ROOT/.e2e-cache)
#   HARNESS_READY_TIMEOUT  seconds to wait for /healthz (default 600)
#   HARNESS_KEEP=1         leave container running on exit (debug)
#
# Exported for callers:
#   HARNESS_PORT           ephemeral host port the container is mapped to
#   AUDIOLLA_BASE_URL      http://127.0.0.1:$HARNESS_PORT
#   HARNESS_ENABLED_ENGINES comma-separated slugs the container is serving
#   HARNESS_CONTAINER      docker container name (for debugging)

HARNESS_IMAGE="${HARNESS_IMAGE:-psyb0t/audiolla:local}"
HARNESS_READY_TIMEOUT="${HARNESS_READY_TIMEOUT:-600}"

# HARNESS_GPU=1 → pass `--gpus all` + AUDIOLLA_DEVICE=cuda. Required for any
# test that exercises the demucs engine. Caller is responsible for ensuring
# HARNESS_IMAGE points at the CUDA build.
HARNESS_GPU="${HARNESS_GPU:-0}"

_HARNESS_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HARNESS_CACHE_DIR="${HARNESS_CACHE_DIR:-${_HARNESS_REPO_ROOT}/.e2e-cache}"

HARNESS_PORT=""
AUDIOLLA_BASE_URL=""
HARNESS_ENABLED_ENGINES=""
HARNESS_CONTAINER=""

# ── pre-flight ───────────────────────────────────────────────────────────────

harness_preflight() {
    local bin
    for bin in docker curl jq python3; do
        command -v "$bin" >/dev/null 2>&1 || {
            echo "FATAL: $bin not on PATH" >&2
            return 2
        }
    done
    if ! docker image inspect "$HARNESS_IMAGE" >/dev/null 2>&1; then
        echo "FATAL: image $HARNESS_IMAGE not on host — build it first (make build)" >&2
        return 2
    fi
    mkdir -p "$HARNESS_CACHE_DIR"
    _harness_generate_fixtures || return $?
    return 0
}

# Always-regenerate the synthetic audio fixtures so tests are deterministic
# and never depend on a committed binary. Uses the prod image's ffmpeg (no
# host ffmpeg dependency). Three files:
#
#   audio.wav      — 8 s stereo 440 Hz sine, 44.1 kHz pcm_s16le
#   audio_ref.wav  — same source attenuated -6 dB, used as the matchering
#                    reference in e2e_mastering.sh (must differ from target)
#   beat_120.wav   — 8 s mono 120 BPM click track (880 Hz pulse every 0.5 s,
#                    50 ms on / 450 ms off); used by beat-dependent tests
#                    (beat-slice, bpm-match, loop-point, dj-prep, MIR beats)
_harness_generate_fixtures() {
    local fx="${_HARNESS_REPO_ROOT}/tests/integration/.fixtures"
    mkdir -p "$fx"
    if ! docker image inspect "$HARNESS_IMAGE" >/dev/null 2>&1; then
        echo "FATAL: cannot generate fixtures — image $HARNESS_IMAGE missing" >&2
        return 2
    fi
    echo "[harness] regenerating synthetic fixtures in ${fx}"
    docker run --rm \
        -u "$(id -u):$(id -g)" \
        -v "${fx}:/fx" \
        --entrypoint ffmpeg "$HARNESS_IMAGE" \
        -hide_banner -loglevel error \
        -f lavfi -i "sine=frequency=440:duration=8" \
        -af "pan=stereo|c0=c0|c1=c0" \
        -ar 44100 -y /fx/audio.wav \
        || { echo "FATAL: fixture audio.wav generation failed" >&2; return 1; }
    docker run --rm \
        -u "$(id -u):$(id -g)" \
        -v "${fx}:/fx" \
        --entrypoint ffmpeg "$HARNESS_IMAGE" \
        -hide_banner -loglevel error \
        -y -i /fx/audio.wav -af "volume=-6dB" /fx/audio_ref.wav \
        || { echo "FATAL: fixture audio_ref.wav generation failed" >&2; return 1; }
    docker run --rm \
        -u "$(id -u):$(id -g)" \
        -v "${fx}:/fx" \
        --entrypoint ffmpeg "$HARNESS_IMAGE" \
        -hide_banner -loglevel error \
        -f lavfi \
        -i "aevalsrc=sin(2*PI*880*t)*if(lt(mod(t\,0.5)\,0.05)\,1\,0):s=44100:d=8" \
        -ar 44100 -y /fx/beat_120.wav \
        || { echo "FATAL: fixture beat_120.wav generation failed" >&2; return 1; }
    return 0
}

# ── container lifecycle ──────────────────────────────────────────────────────

_harness_pick_port() {
    python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}

_harness_cleanup() {
    local rc=$?
    if [ "${HARNESS_KEEP:-0}" = "1" ] && [ -n "$HARNESS_CONTAINER" ]; then
        echo ""
        echo "[harness] HARNESS_KEEP=1 — leaving ${HARNESS_CONTAINER} on port ${HARNESS_PORT}"
        echo "          logs: docker logs -f ${HARNESS_CONTAINER}"
        echo "          rm:   docker rm -f ${HARNESS_CONTAINER}"
        return $rc
    fi
    if [ -n "$HARNESS_CONTAINER" ]; then
        echo ""
        echo "[harness] tearing down ${HARNESS_CONTAINER}"
        docker rm -f "$HARNESS_CONTAINER" >/dev/null 2>&1 || true
    fi
    return $rc
}

# harness_start <engines_csv>
harness_start() {
    local engines="$1"
    if [ -z "$engines" ]; then
        echo "FATAL: harness_start needs a comma-separated engine list" >&2
        return 2
    fi

    harness_preflight || return $?

    HARNESS_PORT="$(_harness_pick_port)"
    AUDIOLLA_BASE_URL="http://127.0.0.1:${HARNESS_PORT}"
    HARNESS_ENABLED_ENGINES="$engines"
    HARNESS_CONTAINER="audiolla-e2e-$$-${RANDOM}"
    export AUDIOLLA_BASE_URL HARNESS_PORT HARNESS_ENABLED_ENGINES HARNESS_CONTAINER

    trap _harness_cleanup EXIT

    echo "[harness] starting ${HARNESS_CONTAINER}"
    echo "          image:   ${HARNESS_IMAGE}"
    echo "          port:    ${HARNESS_PORT}"
    echo "          cache:   ${HARNESS_CACHE_DIR}"
    echo "          engines: ${HARNESS_ENABLED_ENGINES}"

    local gpu_args=() device="cpu"
    if [ "${HARNESS_GPU}" = "1" ]; then
        gpu_args=(--gpus all)
        device="cuda"
    fi

    # Forward any AUDIOLLA_* env vars the caller set into the container —
    # lets a test override AUDIOLLA_FETCH_MODE / AUDIOLLA_AUTH_TOKEN / etc.
    # without altering the harness signature. DEVICE / ENABLED_ENGINES are
    # set explicitly above, so we skip them here to avoid duplicate flags.
    local forwarded_env=()
    local name value
    for name in $(compgen -e | grep '^AUDIOLLA_' || true); do
        case "$name" in
            AUDIOLLA_DEVICE|AUDIOLLA_ENABLED_ENGINES)
                continue
                ;;
        esac
        value="${!name}"
        forwarded_env+=(-e "${name}=${value}")
    done

    docker run -d --rm \
        "${gpu_args[@]}" \
        --name "$HARNESS_CONTAINER" \
        --user "$(id -u):$(id -g)" \
        -v "${HARNESS_CACHE_DIR}:/data" \
        -e AUDIOLLA_DEVICE="${device}" \
        -e AUDIOLLA_ENABLED_ENGINES="${HARNESS_ENABLED_ENGINES}" \
        "${forwarded_env[@]}" \
        -p "${HARNESS_PORT}:8000" \
        "$HARNESS_IMAGE" >/dev/null

    echo "[harness] waiting for /healthz (timeout ${HARNESS_READY_TIMEOUT}s)..."
    local i
    for ((i = 0; i < HARNESS_READY_TIMEOUT; i += 2)); do
        if curl -sf --max-time 5 "${AUDIOLLA_BASE_URL}/healthz" >/dev/null 2>&1; then
            echo "[harness] /healthz ok (after ${i}s)"
            return 0
        fi
        if ! docker inspect -f '{{.State.Running}}' "$HARNESS_CONTAINER" 2>/dev/null \
            | grep -q true; then
            echo "[harness] container exited during boot — last 80 lines:" >&2
            docker logs --tail 80 "$HARNESS_CONTAINER" >&2 2>&1 || true
            return 1
        fi
        sleep 2
    done
    echo "[harness] /healthz never came up in ${HARNESS_READY_TIMEOUT}s. Last logs:" >&2
    docker logs --tail 80 "$HARNESS_CONTAINER" >&2 2>&1 || true
    return 1
}

# ── test runner ──────────────────────────────────────────────────────────────

harness_run_tests() {
    local pass=0 fail=0
    local failed=()
    local t
    for t in "$@"; do
        echo ""
        echo "──[ $t ]──"
        if "$t"; then
            pass=$((pass + 1))
        else
            fail=$((fail + 1))
            failed+=("$t")
        fi
    done
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  $(basename "${BASH_SOURCE[1]:-suite}"): pass=$pass fail=$fail total=$((pass + fail))"
    if [ "$fail" -ne 0 ]; then
        echo "  failed:"
        for t in "${failed[@]}"; do
            echo "    - $t"
        done
    fi
    echo "═══════════════════════════════════════════════════════════"
    [ "$fail" -eq 0 ]
}
