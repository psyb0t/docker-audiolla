#!/bin/bash
# Bearer-token auth middleware end-to-end. Spawns a container with
# AUDIOLLA_AUTH_TOKEN set, verifies:
#   - Missing token → 401
#   - Wrong token   → 401
#   - Correct token → 200
#   - /healthz      → 200 (exempt) regardless of token
#
#     bash tests/integration/e2e_auth.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

# We can't use the standard harness — it doesn't set AUDIOLLA_AUTH_TOKEN.
# Spawn our own container with the env var set, then teardown via trap.

AUDIOLLA_TEST_TOKEN="test-token-abc-123-no-real-secret-here"

PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
NAME="audiolla-auth-$$-${RANDOM}"
BASE_URL="http://127.0.0.1:${PORT}"

cleanup() {
    docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

CACHE="${HARNESS_CACHE_DIR:-${_DIR}/../../.e2e-cache}"
mkdir -p "$CACHE"

echo "[e2e_auth] starting $NAME on port $PORT"
docker run -d --rm \
    --name "$NAME" \
    --user "$(id -u):$(id -g)" \
    -v "${CACHE}:/data" \
    -e AUDIOLLA_DEVICE=cpu \
    -e AUDIOLLA_ENABLED_ENGINES="librosa-analyze" \
    -e AUDIOLLA_AUTH_TOKEN="$AUDIOLLA_TEST_TOKEN" \
    -p "${PORT}:8000" \
    "${HARNESS_IMAGE:-psyb0t/audiolla:local}" >/dev/null

for _ in $(seq 1 60); do
    curl -sf --max-time 3 "${BASE_URL}/healthz" >/dev/null && break
    sleep 1
done

# ── /healthz is always reachable (no auth required) ──────────────────────────

test_healthz_no_auth() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${BASE_URL}/healthz")
    assert_eq "$code" "200" "/healthz reachable without token -> 200" || return 1
    echo "OK: healthz_no_auth"
}

# ── Missing Authorization header → 401 ───────────────────────────────────────

test_missing_auth_401() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        "${BASE_URL}/v1/engines")
    assert_eq "$code" "401" "no auth header -> 401" || return 1
    echo "OK: missing_auth_401"
}

# ── Wrong token → 401 ────────────────────────────────────────────────────────

test_wrong_token_401() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        -H "Authorization: Bearer not-the-real-token" \
        "${BASE_URL}/v1/engines")
    assert_eq "$code" "401" "wrong token -> 401" || return 1
    echo "OK: wrong_token_401"
}

# ── Wrong scheme (Basic instead of Bearer) → 401 ─────────────────────────────

test_wrong_scheme_401() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        -H "Authorization: Basic ${AUDIOLLA_TEST_TOKEN}" \
        "${BASE_URL}/v1/engines")
    assert_eq "$code" "401" "Basic scheme -> 401" || return 1
    echo "OK: wrong_scheme_401"
}

# ── Correct token → 200 ──────────────────────────────────────────────────────

test_correct_token_200() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        -H "Authorization: Bearer ${AUDIOLLA_TEST_TOKEN}" \
        "${BASE_URL}/v1/engines")
    assert_eq "$code" "200" "correct token -> 200" || return 1
    echo "OK: correct_token_200"
}

# ── 401 body is valid JSON ───────────────────────────────────────────────────

test_401_body_is_valid_json() {
    local body
    body=$(curl -s --max-time 5 "${BASE_URL}/v1/engines")
    if ! echo "$body" | jq -e '.detail | type == "string"' >/dev/null 2>&1; then
        echo "  FAIL: 401 body is not valid JSON with .detail string"
        echo "  body: $body"
        return 1
    fi
    echo "OK: 401_body_is_valid_json"
}

PASS=0
FAIL=0
FAILED=()
for t in \
    test_healthz_no_auth \
    test_missing_auth_401 \
    test_wrong_token_401 \
    test_wrong_scheme_401 \
    test_correct_token_200 \
    test_401_body_is_valid_json; do
    echo ""
    echo "──[ $t ]──"
    if "$t"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILED+=("$t")
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  e2e_auth.sh: pass=$PASS fail=$FAIL total=$((PASS + FAIL))"
if [ "$FAIL" -ne 0 ]; then
    echo "  failed:"
    for t in "${FAILED[@]}"; do
        echo "    - $t"
    done
fi
echo "═══════════════════════════════════════════════════════════"

[ "$FAIL" -eq 0 ]
