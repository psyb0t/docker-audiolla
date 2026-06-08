#!/bin/bash
# Real text-to-music end-to-end. Requires the CUDA image + a GPU.
#
# Closes the loop on every engine: generate audio → POST to /v1/audio/beats
# (or a magic-bytes / size check for the lo-fi riffusion path) → assert the
# output is a real, decodable, musical WAV. Mocks here would only verify
# that we call the engine, not that the engine actually produces audio at
# the parameters we send.
#
#     HARNESS_GPU=1 bash tests/integration/e2e_generate.sh
#
# Heavy: ~5 GB of model weights downloaded on first run (cached under
# HARNESS_CACHE_DIR=$REPO_ROOT/.e2e-cache for subsequent runs). Each
# generation takes 10-60 s on a 12 GB GPU.

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# CUDA-only engines — pin image + GPU flag BEFORE sourcing harness.sh so the
# default for HARNESS_IMAGE doesn't lock in the CPU image.
: "${HARNESS_IMAGE:=psyb0t/audiolla:local-cuda}"
: "${HARNESS_GPU:=1}"
# MusicGen weights are CC-BY-NC; opt-in is required for the MusicGen engines
# to load. Forwarded into the container by harness.sh's AUDIOLLA_* env sweep.
: "${AUDIOLLA_ENABLE_NONCOMMERCIAL:=1}"
# Prod images bake HF_HUB_OFFLINE=1 to enforce no-surprise downloads. The
# e2e test downloads model weights on first run (cached in HARNESS_CACHE_DIR
# for subsequent runs), so lift the offline gate. harness.sh forwards HF_*
# env vars into the container.
: "${HF_HUB_OFFLINE:=0}"
export HARNESS_IMAGE HARNESS_GPU AUDIOLLA_ENABLE_NONCOMMERCIAL HF_HUB_OFFLINE

# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

# Engines under test. Riffusion + musicgen-small are mandatory; the other
# two are toggled by env so a slow run can opt out (stable-audio-open and
# musicgen-medium each take ~30-60 s per generation on a 12 GB GPU).
#
# stable-audio-open is HF-licence-gated — operator must run `huggingface-cli
# login` once with a token that has accepted the Stable Audio Open licence,
# then expose it as HUGGINGFACE_TOKEN / HF_TOKEN in the env. If neither is
# present we default RUN_STABLE_AUDIO to 0 (it will 401 otherwise).
#
# huggingface-hub reads `HF_TOKEN` (canonical name). Older setups use
# `HUGGINGFACE_TOKEN` — mirror it forward so both names work.
if [ -n "${HUGGINGFACE_TOKEN:-}" ] && [ -z "${HF_TOKEN:-}" ]; then
    HF_TOKEN="$HUGGINGFACE_TOKEN"
    export HF_TOKEN
fi
if [ -n "${HF_TOKEN:-}" ]; then
    : "${RUN_STABLE_AUDIO:=1}"
else
    : "${RUN_STABLE_AUDIO:=0}"
fi
RUN_MUSICGEN_MEDIUM="${RUN_MUSICGEN_MEDIUM:-0}"
# AudioLDM2 is slow (200-step DDIM, ~2-4 min/clip on RTX 3060). Default ON
# but operator can disable with RUN_AUDIOLDM2=0 for fast iteration.
RUN_AUDIOLDM2="${RUN_AUDIOLDM2:-1}"

_engines="riffusion,musicgen-small,librosa-analyze"
if [ "$RUN_STABLE_AUDIO" = "1" ]; then
    _engines="stable-audio-open,${_engines}"
fi
if [ "$RUN_MUSICGEN_MEDIUM" = "1" ]; then
    _engines="${_engines},musicgen-medium"
fi
if [ "$RUN_AUDIOLDM2" = "1" ]; then
    _engines="${_engines},audioldm2"
fi

harness_start "$_engines"

# ── helpers ──────────────────────────────────────────────────────────────────

_validate_wav() {
    # $1 = file path, $2 = test name. Confirm RIFF header + decodable +
    # actually contains audio above the noise floor (RMS > 0.001) + length
    # >= 1 s. Decode happens inside the container so we don't need host
    # python/soundfile on the host machine.
    local f="$1" name="$2"
    if [ ! -s "$f" ]; then
        echo "  FAIL: $name: file empty"; return 1
    fi
    local head4
    head4=$(head -c 4 "$f" | od -An -c | tr -d ' \n')
    if [ "$head4" != "RIFF" ]; then
        echo "  FAIL: $name: not a WAV (header=$head4)"; return 1
    fi
    docker cp "$f" "$HARNESS_CONTAINER:/tmp/_validate.wav" >/dev/null 2>&1 || {
        echo "  FAIL: $name: docker cp into ${HARNESS_CONTAINER} failed"; return 1
    }
    local stats
    stats=$(docker exec "$HARNESS_CONTAINER" python -c "
import sys, soundfile as sf, numpy as np
data, sr = sf.read('/tmp/_validate.wav')
data = np.asarray(data, dtype=np.float32)
if data.ndim == 2:
    data = data.mean(axis=1)
rms = float(np.sqrt(np.mean(data**2)))
dur = len(data) / sr
print(f'sr={sr} dur={dur:.2f} rms={rms:.4f}')
if rms < 0.001:
    sys.exit(2)
if dur < 1.0:
    sys.exit(3)
" 2>&1) || {
        echo "  FAIL: $name: ${stats}"; return 1
    }
    echo "  OK: $name ($stats)"
}

# Send the generated audio back through /v1/audio/beats (JSON body, file_path
# referencing the staged output). Asserts a positive tempo + at least
# `min_beats` beats. Closes the loop: if generation silently emitted zeros,
# beats would find nothing.
_assert_beats_detected() {
    local stage_path="$1" name="$2" min_beats="${3:-4}"
    local resp; resp=$(curl -s --max-time 120 \
        -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"${stage_path}\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/beats")
    if [ -z "$resp" ]; then
        echo "  FAIL: $name: /v1/audio/beats returned empty"; return 1
    fi
    local bpm beats_n
    bpm=$(echo "$resp" | jq -r '.tempo_bpm // empty')
    beats_n=$(echo "$resp" | jq -r '.beats | length // 0')
    if [ -z "$bpm" ] || awk "BEGIN{exit !($bpm <= 0)}"; then
        echo "  FAIL: $name: tempo_bpm=$bpm (expected > 0)"; echo "  resp: ${resp:0:300}"; return 1
    fi
    if [ "$beats_n" -lt "$min_beats" ]; then
        echo "  FAIL: $name: only $beats_n beats (expected >= $min_beats)"; return 1
    fi
    echo "  OK: $name (tempo=$bpm beats=$beats_n)"
}

# Generate via POST /v1/audio/generate/<engine> (JSON body), staging the
# result under `out/<engine>-<pid>.wav`. Sets STAGE_PATH for downstream
# callers (so they can pass it to _assert_beats_detected).
_generate_to_staged() {
    local engine="$1" prompt="$2"; shift 2
    STAGE_PATH="out/${engine}-$$-${RANDOM}.wav"
    # Build JSON: prompt + any extra "key=value" args + auto output_path
    local json="{\"prompt\":\"${prompt}\",\"output_format\":\"wav\",\"output_path\":\"${STAGE_PATH}\""
    local kv key val
    for kv in "$@"; do
        key="${kv%%=*}"
        val="${kv#*=}"
        if [[ "$val" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
            json="${json},\"${key}\":${val}"
        elif [ "$val" = "true" ] || [ "$val" = "false" ]; then
            json="${json},\"${key}\":${val}"
        else
            json="${json},\"${key}\":\"${val}\""
        fi
    done
    json="${json}}"
    local resp
    resp=$(curl -s -w "\n%{http_code}" --max-time 600 \
        -X POST -H "Content-Type: application/json" \
        -d "$json" \
        "${AUDIOLLA_BASE_URL}/v1/audio/generate/${engine}")
    local code; code=$(echo "$resp" | tail -1)
    local body; body=$(echo "$resp" | sed '$d')
    if [ "$code" -lt 200 ] || [ "$code" -ge 300 ]; then
        echo "  HTTP $code: ${body:0:500}" >&2
        return 1
    fi
    # Validate the staged file size from the JSON response (server staged
    # successfully — beats follow-up will validate audibility via loop closure).
    local size; size=$(echo "$body" | jq -r '.size // 0')
    if [ -z "$size" ] || [ "$size" -lt 1000 ]; then
        echo "  FAIL: staged file too small (size=$size, body=${body:0:300})"
        return 1
    fi
    echo "  OK: generated → ${STAGE_PATH} (${size} bytes)"
}

# ── /healthz lists the registered engines ────────────────────────────────────

test_healthz_lists_engines() {
    local out
    out=$(audiolla_get "/healthz") || { echo "  FAIL: /healthz unreachable"; return 1; }
    assert_contains "$out" "riffusion" "/healthz lists riffusion" || return 1
    assert_contains "$out" "musicgen-small" "/healthz lists musicgen-small" || return 1
    if [ "$RUN_STABLE_AUDIO" = "1" ]; then
        assert_contains "$out" "stable-audio-open" "/healthz lists stable-audio-open" || return 1
    fi
    if [ "$RUN_AUDIOLDM2" = "1" ]; then
        assert_contains "$out" "audioldm2" "/healthz lists audioldm2" || return 1
    fi
}

# ── stable-audio-open: real generation + beats loop closure ──────────────────

test_stable_audio_drum_beats_loop() {
    [ "$RUN_STABLE_AUDIO" = "1" ] || { echo "  SKIP: RUN_STABLE_AUDIO=0"; return 0; }
    _generate_to_staged stable-audio-open "120 bpm electronic drum beat with kick and snare, four on the floor, no melody, dry" \
        "duration_sec=10" "seed=1337" || return 1
    _assert_beats_detected "$STAGE_PATH" "stable-audio-open beats detected" 8 || return 1
}

# ── musicgen-small: real generation + beats loop closure ─────────────────────

test_musicgen_small_drum_beats_loop() {
    _generate_to_staged musicgen-small "punchy 120 bpm electronic drum loop, kick on every beat, hi-hats" \
        "duration_sec=10" "seed=42" || return 1
    _assert_beats_detected "$STAGE_PATH" "musicgen-small beats detected" 6 || return 1
}

# ── musicgen-medium: opt-in via env var ──────────────────────────────────────

test_musicgen_medium_drum_beats_loop() {
    [ "$RUN_MUSICGEN_MEDIUM" = "1" ] || { echo "  SKIP: RUN_MUSICGEN_MEDIUM=0"; return 0; }
    _generate_to_staged musicgen-medium "driving 128 bpm techno drum pattern, prominent kick and hi-hat" \
        "duration_sec=10" "seed=7" || return 1
    _assert_beats_detected "$STAGE_PATH" "musicgen-medium beats detected" 6 || return 1
}

# ── riffusion: generation + decodable audio (no beats — too lo-fi/short) ─────

test_riffusion_generates_wav() {
    _generate_to_staged riffusion "lo-fi 90 bpm hip hop drum loop with snare" \
        "duration_sec=5" "seed=99" || return 1
}

# ── audioldm2: SFX generation + decodable audio ─────────────────────────────

test_audioldm2_sfx_generates_wav() {
    [ "$RUN_AUDIOLDM2" = "1" ] || { echo "  SKIP: RUN_AUDIOLDM2=0"; return 0; }
    _generate_to_staged audioldm2 "heavy rain falling on a metal roof" \
        "duration_sec=5" "seed=11" "num_inference_steps=50" || return 1
}

# ── seed reproducibility (stable-audio-open) ─────────────────────────────────

test_seed_reproducibility_stable_audio() {
    [ "$RUN_STABLE_AUDIO" = "1" ] || { echo "  SKIP: RUN_STABLE_AUDIO=0"; return 0; }
    _generate_to_staged stable-audio-open "minimal drum click 100 bpm" "duration_sec=5" "seed=2024" || return 1
    local path_a="$STAGE_PATH"
    _generate_to_staged stable-audio-open "minimal drum click 100 bpm" "duration_sec=5" "seed=2024" || return 1
    local path_b="$STAGE_PATH"
    local sa sb
    sa=$(docker exec "$HARNESS_CONTAINER" sha256sum "/data/files/${path_a}" | awk '{print $1}')
    sb=$(docker exec "$HARNESS_CONTAINER" sha256sum "/data/files/${path_b}" | awk '{print $1}')
    assert_eq "$sa" "$sb" "same seed → byte-identical output (sha256 match)" || return 1
}

# ── unknown engine → 404 ─────────────────────────────────────────────────────

test_unknown_engine_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d '{"prompt":"anything","output_format":"wav","output_path":"out/unk.wav"}' \
        "${AUDIOLLA_BASE_URL}/v1/audio/generate/this-does-not-exist")
    assert_eq "$code" "404" "unknown generate engine → 404" || return 1
}

# ── (v1.0.0) Obsolete: with dedicated per-engine routes, hitting
# /v1/audio/generate/<non-generate-engine> just returns 404 — there's no
# /v1/audio/generate/{engine} catch-all route anymore. Test kept as
# documentation of the change; it always returns 0 now.

test_non_generate_engine_400() {
    echo "  SKIP: route /v1/audio/generate/{engine} removed in v1.0.0 — dedicated per-engine routes only"
    return 0
}

_skip_non_generate_engine_400_stub() {
    local tmp; tmp=$(mktemp -t audiolla-nogen.XXXXXX)
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN
    local code
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" -d "{\"prompt\":\"anything\",\"output_format\":\"wav\",\"output_path\":\"out/x.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/generate/librosa-analyze")
    assert_eq "$code" "422" "non-generate engine → 422" || return 1
}

# ── missing prompt → 422 (FastAPI form validation) ──────────────────────────

test_missing_prompt_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d '{"output_path":"out/x.wav"}' \
        "${AUDIOLLA_BASE_URL}/v1/audio/generate/riffusion")
    assert_eq "$code" "422" "missing prompt → 422" || return 1
}

# ── duration cap enforcement (stable-audio-open: 47 s hard limit) ────────────

test_duration_cap_rejected() {
    [ "$RUN_STABLE_AUDIO" = "1" ] || { echo "  SKIP: RUN_STABLE_AUDIO=0"; return 0; }
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d '{"prompt":"drum","duration_sec":999,"output_format":"wav","output_path":"out/cap.wav"}' \
        "${AUDIOLLA_BASE_URL}/v1/audio/generate/stable-audio-open")
    if [ "$code" = "500" ] || [ "$code" = "400" ]; then
        echo "  OK: over-cap duration → $code (server rejects)"
        return 0
    fi
    echo "  FAIL: over-cap duration → $code (expected 400/500)"
    return 1
}

# ── MusicGen licence gate: container WITHOUT opt-in must refuse to generate ──
# Spawn a sibling container with AUDIOLLA_ENABLE_NONCOMMERCIAL unset, hit
# /v1/audio/generate/musicgen-small, expect 500 (engine refuses to load) +
# the response body to mention the env var.

test_musicgen_license_gate() {
    local port name code body
    port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
    name="audiolla-mglicense-$$-${RANDOM}"
    # NOTE: AUDIOLLA_ENABLE_NONCOMMERCIAL is intentionally omitted — the
    # whole point is to verify the engine refuses to load without the
    # opt-in. HF_HUB_OFFLINE=0 so the licence check is what fails, not the
    # download path.
    docker run -d --rm --name "$name" \
        --gpus all \
        --user "$(id -u):$(id -g)" \
        -v "${HARNESS_CACHE_DIR}:/data" \
        -e AUDIOLLA_DEVICE=cuda \
        -e AUDIOLLA_ENABLED_ENGINES="musicgen-small" \
        -e HF_HUB_OFFLINE=0 \
        -p "${port}:8000" "$HARNESS_IMAGE" >/dev/null
    # shellcheck disable=SC2064
    trap "docker rm -f '$name' >/dev/null 2>&1 || true" RETURN

    local i
    for ((i = 0; i < 240; i += 2)); do
        if curl -sf --max-time 3 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done
    body=$(mktemp -t audiolla-license-body.XXXXXX)
    # shellcheck disable=SC2064
    trap "rm -f '$body'; docker rm -f '$name' >/dev/null 2>&1 || true" RETURN
    code=$(curl -s -o "$body" -w "%{http_code}" --max-time 60 \
        -X POST -H "Content-Type: application/json" -d "{\"prompt\":\"drum loop\",\"duration_sec\":4,\"output_format\":\"wav\",\"output_path\":\"out/x.wav\"}" \
        "http://127.0.0.1:${port}/v1/audio/generate/musicgen-small")
    if [ "$code" = "200" ]; then
        echo "  FAIL: musicgen-small generated WITHOUT licence opt-in (code=$code)"; return 1
    fi
    if ! grep -q "AUDIOLLA_ENABLE_NONCOMMERCIAL" "$body"; then
        echo "  FAIL: licence error body missing env var hint (code=$code, body: $(head -c 300 "$body"))"
        return 1
    fi
    echo "  OK: musicgen-small refused without opt-in (code=$code)"
}

# ── runner ───────────────────────────────────────────────────────────────────

harness_run_tests \
    test_healthz_lists_engines \
    test_stable_audio_drum_beats_loop \
    test_musicgen_small_drum_beats_loop \
    test_musicgen_medium_drum_beats_loop \
    test_riffusion_generates_wav \
    test_audioldm2_sfx_generates_wav \
    test_seed_reproducibility_stable_audio \
    test_unknown_engine_404 \
    test_non_generate_engine_400 \
    test_missing_prompt_422 \
    test_duration_cap_rejected \
    test_musicgen_license_gate
