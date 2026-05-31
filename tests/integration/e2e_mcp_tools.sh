#!/bin/bash
# Real MCP tools/call end-to-end — confirms every audio + MIDI tool
# actually works over the streamable-HTTP transport, including:
#   - tools/list lists all expected tools
#   - midi_compose returns base64 that decodes to a valid SMF (MThd)
#   - midi_render returns base64 that decodes to a valid WAV (RIFF)
#   - midi_generate one-shots spec → WAV
#   - fx processes audio via base64 + put_file pipeline
#   - put_file + get_file round-trip
#   - tool errors come back as isError=true (NOT HTTP 500)
#
#     bash tests/integration/e2e_mcp_tools.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

# All engines we want to drive over MCP.
harness_start "midi-compose,midi-render,fx-chain,librosa-analyze,sox-transform"

MCP_URL="${AUDIOLLA_BASE_URL}/v1/mcp/"

# Send a JSON-RPC call. Stateless MCP — no session, no init dance needed.
mcp_call() {
    local payload="$1"
    curl -s --max-time 120 \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -X POST "$MCP_URL" \
        -d "$payload"
}

# Extract the structuredContent (parsed JSON) from a tools/call response,
# given the field name we want from the dict. Prints empty + exit 1 on
# isError=true.
mcp_result_field() {
    local body="$1" field="$2"
    if echo "$body" | jq -e '.result.isError == true' >/dev/null 2>&1; then
        return 1
    fi
    echo "$body" | jq -r ".result.structuredContent.${field} // empty"
}

# Common: a 4-beat C-major arpeggio + kick on every beat. ~70-byte SMF.
SPEC='{"tempo_bpm":120,"tracks":[
  {"name":"Lead","program":0,"channel":0,"notes":[
    {"pitch":60,"start_beats":0.0,"duration_beats":0.5,"velocity":100},
    {"pitch":64,"start_beats":0.5,"duration_beats":0.5,"velocity":100},
    {"pitch":67,"start_beats":1.0,"duration_beats":0.5,"velocity":100},
    {"pitch":72,"start_beats":1.5,"duration_beats":0.5,"velocity":100}
  ]},
  {"name":"Kick","program":0,"channel":9,"notes":[
    {"pitch":36,"start_beats":0.0,"duration_beats":0.1,"velocity":110},
    {"pitch":36,"start_beats":1.0,"duration_beats":0.1,"velocity":110}
  ]}
]}'

# ── tools/list mentions every expected tool ──────────────────────────────────

test_mcp_tools_list_has_new_tools() {
    local body names missing tool
    body=$(mcp_call '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')
    names=$(echo "$body" | jq -r '.result.tools[].name' | sort | tr '\n' ',' || true)
    missing=()
    for tool in fx midi_compose midi_render midi_generate \
                 separate master analyze transform loudness \
                 list_engines list_files put_file get_file delete_file; do
        if ! echo ",$names" | grep -q ",${tool},"; then
            missing+=("$tool")
        fi
    done
    if [ "${#missing[@]}" -ne 0 ]; then
        echo "  FAIL: tools/list missing: ${missing[*]}"
        echo "  got: $names"
        return 1
    fi
    echo "OK: mcp_tools_list_has_new_tools"
}

# ── midi_compose: spec → base64 MIDI bytes (verified MThd header) ────────────

test_mcp_midi_compose_returns_smf_base64() {
    local payload body b64 size decoded
    payload=$(jq -n --argjson spec "$SPEC" \
        '{jsonrpc:"2.0",id:10,method:"tools/call",params:{name:"midi_compose",arguments:{spec:$spec}}}')
    body=$(mcp_call "$payload")
    b64=$(mcp_result_field "$body" "midi_base64") || { echo "  FAIL: isError; body: $body"; return 1; }
    size=$(mcp_result_field "$body" "size")
    if [ -z "$b64" ] || [ -z "$size" ]; then
        echo "  FAIL: missing midi_base64 / size; body: $body"
        return 1
    fi
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! head -c 4 "$decoded" | grep -q "MThd"; then
        echo "  FAIL: decoded base64 is not MIDI (no MThd)"
        rm -f "$decoded"; return 1
    fi
    local actual
    actual=$(stat -c%s "$decoded")
    rm -f "$decoded"
    if [ "$actual" != "$size" ]; then
        echo "  FAIL: reported size=$size doesn't match decoded=$actual"
        return 1
    fi
    echo "OK: mcp_midi_compose_returns_smf_base64 ($size bytes)"
}

# ── midi_compose with output_path: writes to staging via MCP ────────────────

test_mcp_midi_compose_output_path() {
    local payload body resp_path
    payload=$(jq -n --argjson spec "$SPEC" \
        '{jsonrpc:"2.0",id:11,method:"tools/call",params:{name:"midi_compose",arguments:{spec:$spec,output_path:"mcp/song.mid"}}}')
    body=$(mcp_call "$payload")
    resp_path=$(mcp_result_field "$body" "path") || { echo "  FAIL: isError; body: $body"; return 1; }
    if [ "$resp_path" != "mcp/song.mid" ]; then
        echo "  FAIL: response path=$resp_path, expected mcp/song.mid"
        echo "  body: $body"
        return 1
    fi
    # Confirm the file ACTUALLY exists in staging via REST GET /v1/files.
    local fetched code
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/mcp/song.mid")
    if [ "$code" != "200" ]; then
        echo "  FAIL: staged file unreachable via REST -> $code"
        rm -f "$fetched"; return 1
    fi
    if ! head -c 4 "$fetched" | grep -q "MThd"; then
        echo "  FAIL: staged file is not MIDI"
        rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: mcp_midi_compose_output_path"
}

# ── midi_generate: spec → audio (one-shot compose + render) ─────────────────

test_mcp_midi_generate_returns_wav_base64() {
    local payload body b64 decoded size
    payload=$(jq -n --argjson spec "$SPEC" \
        '{jsonrpc:"2.0",id:12,method:"tools/call",params:{name:"midi_generate",arguments:{spec:$spec,output_format:"wav"}}}')
    body=$(mcp_call "$payload")
    b64=$(mcp_result_field "$body" "audio_base64") || { echo "  FAIL: isError; body: $body"; return 1; }
    if [ -z "$b64" ]; then
        echo "  FAIL: no audio_base64 in result; body: $body"
        return 1
    fi
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! head -c 4 "$decoded" | grep -q "RIFF"; then
        echo "  FAIL: decoded base64 is not WAV (no RIFF)"
        rm -f "$decoded"; return 1
    fi
    size=$(stat -c%s "$decoded")
    rm -f "$decoded"
    if [ "$size" -lt 1000 ]; then
        echo "  FAIL: rendered WAV suspiciously small ($size bytes)"
        return 1
    fi
    echo "OK: mcp_midi_generate_returns_wav_base64 ($size bytes)"
}

# ── put_file + midi_render via file_path: full staged-input pipeline ────────

test_mcp_put_file_then_midi_render() {
    # 1. midi_compose (output_path=mcp/render-in.mid) — stages MIDI.
    local payload body
    payload=$(jq -n --argjson spec "$SPEC" \
        '{jsonrpc:"2.0",id:20,method:"tools/call",params:{name:"midi_compose",arguments:{spec:$spec,output_path:"mcp/render-in.mid"}}}')
    body=$(mcp_call "$payload")
    if echo "$body" | jq -e '.result.isError == true' >/dev/null 2>&1; then
        echo "  FAIL: compose-to-stage isError; body: $body"; return 1
    fi

    # 2. midi_render with file_path → base64 WAV.
    payload='{"jsonrpc":"2.0","id":21,"method":"tools/call","params":{"name":"midi_render","arguments":{"file_path":"mcp/render-in.mid","output_format":"wav"}}}'
    body=$(mcp_call "$payload")
    local b64
    b64=$(mcp_result_field "$body" "audio_base64") || { echo "  FAIL: isError; body: $body"; return 1; }
    if [ -z "$b64" ]; then
        echo "  FAIL: no audio_base64; body: $body"; return 1
    fi
    local decoded size
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! head -c 4 "$decoded" | grep -q "RIFF"; then
        echo "  FAIL: decoded base64 is not WAV"
        rm -f "$decoded"; return 1
    fi
    size=$(stat -c%s "$decoded")
    rm -f "$decoded"
    echo "OK: mcp_put_file_then_midi_render ($size bytes)"
}

# ── fx via put_file + file_path: stage WAV, apply pedalboard chain ──────────

test_mcp_fx_chain_with_staged_file() {
    # 1. Stage the fixture via REST PUT — base64-via-jq blows the
    # command-line size limit on 1+ MB files. The MCP put_file tool is
    # still tested separately by test_mcp_put_get_roundtrip; here we
    # just need *something* in staging for fx to chew on.
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/files/mcp/in.wav")
    if [ "$code" != "201" ]; then
        echo "  FAIL: REST PUT to stage fixture -> $code"; return 1
    fi

    # 2. fx: chain Compressor + Reverb + Gain via file_path.
    payload='{"jsonrpc":"2.0","id":31,"method":"tools/call","params":{"name":"fx","arguments":{
        "file_path":"mcp/in.wav",
        "effects":[
            {"type":"Compressor","params":{"threshold_db":-18,"ratio":4.0}},
            {"type":"Reverb","params":{"room_size":0.5,"wet_level":0.3}},
            {"type":"Gain","params":{"gain_db":-3.0}}
        ],
        "output_format":"wav"
    }}}'
    body=$(mcp_call "$payload")
    local b64
    b64=$(mcp_result_field "$body" "audio_base64") || { echo "  FAIL: fx isError; body: $body"; return 1; }
    if [ -z "$b64" ]; then
        echo "  FAIL: fx no audio_base64; body: $body"; return 1
    fi
    local decoded
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! head -c 4 "$decoded" | grep -q "RIFF"; then
        echo "  FAIL: fx output is not WAV"
        rm -f "$decoded"; return 1
    fi
    rm -f "$decoded"
    echo "OK: mcp_fx_chain_with_staged_file"
}

# ── error path: bad tool args come back as isError=true, NOT HTTP 500 ──────

test_mcp_tool_error_returns_iserror_not_500() {
    # midi_compose with an invalid pitch → should be isError=true 200.
    local code body
    code=$(curl -s -o /tmp/audiolla-mcp.$$ -w "%{http_code}" --max-time 30 \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -X POST "$MCP_URL" \
        -d '{"jsonrpc":"2.0","id":40,"method":"tools/call","params":{"name":"midi_compose","arguments":{"spec":{"tempo_bpm":120,"tracks":[{"program":0,"channel":0,"notes":[{"pitch":999,"start_beats":0,"duration_beats":1,"velocity":100}]}]}}}}')
    body=$(cat /tmp/audiolla-mcp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-mcp.$$
    assert_eq "$code" "200" "MCP tool-call always HTTP 200" || return 1
    if ! echo "$body" | jq -e '.result.isError == true' >/dev/null 2>&1; then
        echo "  FAIL: expected isError=true; body: $body"
        return 1
    fi
    if ! echo "$body" | grep -qi "pitch"; then
        echo "  FAIL: error doesn't mention pitch; body: $body"
        return 1
    fi
    echo "OK: mcp_tool_error_returns_iserror_not_500"
}

# ── put_file + get_file round-trip ─────────────────────────────────────────

test_mcp_put_get_roundtrip() {
    local payload body size_in size_out fetched_b64
    size_in=128
    local content_b64
    content_b64=$(head -c $size_in /dev/urandom | base64 -w 0)
    payload=$(jq -n --arg b64 "$content_b64" \
        '{jsonrpc:"2.0",id:50,method:"tools/call",params:{name:"put_file",arguments:{path:"mcp/roundtrip.bin",content_base64:$b64}}}')
    body=$(mcp_call "$payload")
    if ! mcp_result_field "$body" "path" >/dev/null; then
        echo "  FAIL: put_file isError; body: $body"; return 1
    fi

    payload='{"jsonrpc":"2.0","id":51,"method":"tools/call","params":{"name":"get_file","arguments":{"path":"mcp/roundtrip.bin"}}}'
    body=$(mcp_call "$payload")
    fetched_b64=$(mcp_result_field "$body" "content_base64") || { echo "  FAIL: get_file isError; body: $body"; return 1; }
    if [ "$fetched_b64" != "$content_b64" ]; then
        echo "  FAIL: round-trip mismatch — bytes differ"
        return 1
    fi
    size_out=$(mcp_result_field "$body" "size")
    assert_eq "$size_out" "$size_in" "round-trip size" || return 1
    echo "OK: mcp_put_get_roundtrip"
}

# ── list_engines: enumerate configured engines via MCP ──────────────────────

test_mcp_list_engines() {
    local body slugs
    body=$(mcp_call '{"jsonrpc":"2.0","id":100,"method":"tools/call","params":{"name":"list_engines","arguments":{}}}')
    slugs=$(echo "$body" | jq -r '.result.structuredContent.engines[].slug' 2>/dev/null | sort | tr '\n' ',' || true)
    if [ -z "$slugs" ]; then
        echo "  FAIL: no engines in result; body: $body"; return 1
    fi
    # Sanity: harness's enabled set must be reflected here.
    for slug in midi-compose midi-render fx-chain librosa-analyze sox-transform; do
        if ! echo ",$slugs" | grep -q ",${slug},"; then
            echo "  FAIL: list_engines missing $slug; got: $slugs"
            return 1
        fi
    done
    echo "OK: mcp_list_engines"
}

# ── analyze via librosa: file_path → JSON features ──────────────────────────

test_mcp_analyze_via_file_path() {
    local code body bpm
    # Stage the fixture via REST.
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/files/mcp/analyze.wav")
    if [ "$code" != "201" ]; then
        echo "  FAIL: stage fixture -> $code"; return 1
    fi
    body=$(mcp_call '{"jsonrpc":"2.0","id":110,"method":"tools/call","params":{"name":"analyze","arguments":{"file_path":"mcp/analyze.wav","features":["bpm","duration","loudness"]}}}')
    if echo "$body" | jq -e '.result.isError == true' >/dev/null 2>&1; then
        echo "  FAIL: analyze isError; body: $body"; return 1
    fi
    # Fixture is a steady 440Hz sine — duration must be ~8s, loudness defined.
    if ! echo "$body" | jq -e '.result.structuredContent.duration > 7 and .result.structuredContent.duration < 9' >/dev/null 2>&1; then
        echo "  FAIL: duration not ~8s; body: $body"; return 1
    fi
    bpm=$(echo "$body" | jq -r '.result.structuredContent.bpm // empty')
    if [ -z "$bpm" ] || [ "$bpm" = "null" ]; then
        echo "  FAIL: no bpm in result; body: $body"; return 1
    fi
    echo "OK: mcp_analyze_via_file_path (duration ~8s, bpm=${bpm})"
}

# ── transform via sox: file_path → base64 WAV ───────────────────────────────

test_mcp_transform_via_file_path() {
    local code body b64 decoded
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/files/mcp/transform.wav")
    if [ "$code" != "201" ]; then
        echo "  FAIL: stage fixture -> $code"; return 1
    fi
    body=$(mcp_call '{"jsonrpc":"2.0","id":120,"method":"tools/call","params":{"name":"transform","arguments":{"file_path":"mcp/transform.wav","operations":[{"op":"gain","params":{"db":-3}},{"op":"reverb","params":{"reverberance":50}}],"output_format":"wav"}}}')
    b64=$(mcp_result_field "$body" "audio_base64") || { echo "  FAIL: isError; body: $body"; return 1; }
    if [ -z "$b64" ]; then
        echo "  FAIL: no audio_base64; body: $body"; return 1
    fi
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! head -c 4 "$decoded" | grep -q "RIFF"; then
        echo "  FAIL: not a WAV"
        rm -f "$decoded"; return 1
    fi
    rm -f "$decoded"
    echo "OK: mcp_transform_via_file_path"
}

# ── loudness (measure): file_path → JSON without normalization ──────────────

test_mcp_loudness_measure() {
    local code body lufs
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/files/mcp/loudness.wav")
    if [ "$code" != "201" ]; then
        echo "  FAIL: stage fixture -> $code"; return 1
    fi
    body=$(mcp_call '{"jsonrpc":"2.0","id":130,"method":"tools/call","params":{"name":"loudness","arguments":{"file_path":"mcp/loudness.wav"}}}')
    if echo "$body" | jq -e '.result.isError == true' >/dev/null 2>&1; then
        echo "  FAIL: loudness isError; body: $body"; return 1
    fi
    lufs=$(echo "$body" | jq -r '.result.structuredContent.loudness_lufs // empty')
    if [ -z "$lufs" ] || [ "$lufs" = "null" ]; then
        echo "  FAIL: no loudness_lufs; body: $body"; return 1
    fi
    # Verify normalized=false on the measurement path.
    if ! echo "$body" | jq -e '.result.structuredContent.normalized == false' >/dev/null 2>&1; then
        echo "  FAIL: normalized should be false on measure-only call"
        return 1
    fi
    echo "OK: mcp_loudness_measure (LUFS=$lufs)"
}

# ── loudness (normalize): with target_lufs → base64 audio + measured LUFS ──

test_mcp_loudness_normalize() {
    local code body b64 measured
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/files/mcp/loud-norm.wav")
    if [ "$code" != "201" ]; then
        echo "  FAIL: stage fixture -> $code"; return 1
    fi
    body=$(mcp_call '{"jsonrpc":"2.0","id":131,"method":"tools/call","params":{"name":"loudness","arguments":{"file_path":"mcp/loud-norm.wav","target_lufs":-14,"output_format":"wav"}}}')
    b64=$(mcp_result_field "$body" "audio_base64") || { echo "  FAIL: isError; body: $body"; return 1; }
    if [ -z "$b64" ]; then
        echo "  FAIL: no audio_base64; body: $body"; return 1
    fi
    measured=$(echo "$body" | jq -r '.result.structuredContent.measured_lufs // empty')
    if [ -z "$measured" ] || [ "$measured" = "null" ]; then
        echo "  FAIL: no measured_lufs; body: $body"; return 1
    fi
    local decoded
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! head -c 4 "$decoded" | grep -q "RIFF"; then
        echo "  FAIL: normalized output is not WAV"
        rm -f "$decoded"; return 1
    fi
    rm -f "$decoded"
    echo "OK: mcp_loudness_normalize (measured=$measured -> -14 LUFS)"
}

# ── list_files: confirms files we staged are visible ────────────────────────

test_mcp_list_files() {
    local body
    # The prior tests in this file have already staged at least
    # `mcp/loudness.wav` — confirm it shows up here.
    body=$(mcp_call '{"jsonrpc":"2.0","id":140,"method":"tools/call","params":{"name":"list_files","arguments":{}}}')
    if echo "$body" | jq -e '.result.isError == true' >/dev/null 2>&1; then
        echo "  FAIL: list_files isError; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.result.structuredContent.files | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: files is not an array; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.result.structuredContent.files | map(.path) | any(. == "mcp/loudness.wav")' >/dev/null 2>&1; then
        echo "  FAIL: list_files missing previously-staged mcp/loudness.wav"
        return 1
    fi
    echo "OK: mcp_list_files"
}

# ── delete_file: round-trip — put then delete via MCP, confirm gone via REST

test_mcp_delete_file() {
    local code body
    # Stage a temp file via REST.
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "marker" \
        "${AUDIOLLA_BASE_URL}/v1/files/mcp/to-delete.txt")
    if [ "$code" != "201" ]; then
        echo "  FAIL: stage marker -> $code"; return 1
    fi
    # Delete via MCP.
    body=$(mcp_call '{"jsonrpc":"2.0","id":150,"method":"tools/call","params":{"name":"delete_file","arguments":{"path":"mcp/to-delete.txt"}}}')
    if echo "$body" | jq -e '.result.isError == true' >/dev/null 2>&1; then
        echo "  FAIL: delete_file isError; body: $body"; return 1
    fi
    # Verify the file is really gone via REST GET.
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/mcp/to-delete.txt")
    if [ "$code" != "404" ]; then
        echo "  FAIL: file still reachable after MCP delete -> $code"
        return 1
    fi
    echo "OK: mcp_delete_file"
}

harness_run_tests \
    test_mcp_tools_list_has_new_tools \
    test_mcp_list_engines \
    test_mcp_midi_compose_returns_smf_base64 \
    test_mcp_midi_compose_output_path \
    test_mcp_midi_generate_returns_wav_base64 \
    test_mcp_put_file_then_midi_render \
    test_mcp_fx_chain_with_staged_file \
    test_mcp_analyze_via_file_path \
    test_mcp_transform_via_file_path \
    test_mcp_loudness_measure \
    test_mcp_loudness_normalize \
    test_mcp_list_files \
    test_mcp_delete_file \
    test_mcp_tool_error_returns_iserror_not_500 \
    test_mcp_put_get_roundtrip
