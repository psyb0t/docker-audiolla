#!/bin/bash
# Async job queue — submit / poll / cancel / list.
# Uses waveform (ffmpeg-render) as the async-capable worker.
#
#     bash tests/integration/e2e_jobs.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "ffmpeg-render"

# ── submit async job and poll until completed ────────────────────────────────

test_async_job_submit_and_poll() {
    local submit_body job_id poll_body status
    submit_body=$(curl -s --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "async_job=true" \
        "${AUDIOLLA_BASE_URL}/v1/audio/waveform")
    job_id=$(echo "$submit_body" | jq -r '.job_id // empty')
    if [ -z "$job_id" ]; then
        echo "  FAIL: no job_id in submit response; body: $submit_body"; return 1
    fi
    status_val=$(echo "$submit_body" | jq -r '.status // empty')
    if [ -z "$status_val" ]; then
        echo "  FAIL: no status in submit response; body: $submit_body"; return 1
    fi
    # Poll until completed or timeout (10s)
    local attempts=0
    while [ "$attempts" -lt 10 ]; do
        poll_body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/jobs/${job_id}")
        status=$(echo "$poll_body" | jq -r '.status // empty')
        [ "$status" = "completed" ] && break
        [ "$status" = "failed" ] && {
            echo "  FAIL: job failed; body: $poll_body"; return 1
        }
        sleep 1
        attempts=$((attempts + 1))
    done
    if [ "$status" != "completed" ]; then
        echo "  FAIL: job did not complete within 10s; last status: $status"; return 1
    fi
    if ! echo "$poll_body" | jq -e '.result != null' >/dev/null 2>&1; then
        echo "  FAIL: completed job has no result; body: $poll_body"; return 1
    fi
    if ! echo "$poll_body" | jq -e '.duration_sec | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: completed job missing duration_sec; body: $poll_body"; return 1
    fi
    echo "OK: async_job_submit_and_poll (job_id=${job_id})"
}

# ── GET /v1/jobs returns list ────────────────────────────────────────────────

test_jobs_list_returns_array() {
    local body
    body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/jobs")
    if ! echo "$body" | jq -e '.jobs | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: /v1/jobs.jobs not an array; body: $body"; return 1
    fi
    echo "OK: jobs_list_returns_array ($(echo "$body" | jq '.jobs | length') jobs)"
}

# ── GET /v1/jobs?status=completed filters correctly ──────────────────────────

test_jobs_list_filter_by_status() {
    local body
    body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/jobs?status=completed")
    if ! echo "$body" | jq -e '.jobs | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: filter by status returned non-array; body: $body"; return 1
    fi
    # Every returned job must have status == "completed".
    local bad
    bad=$(echo "$body" | jq -r '[.jobs[] | select(.status != "completed")] | length')
    if [ "${bad:-0}" -gt 0 ]; then
        echo "  FAIL: $bad jobs have wrong status after filter=completed"; return 1
    fi
    echo "OK: jobs_list_filter_by_status"
}

# ── GET /v1/jobs/{id} 404 for unknown id ─────────────────────────────────────

test_job_not_found_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
        "${AUDIOLLA_BASE_URL}/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert_eq "$code" "404" "GET unknown job -> 404" || return 1
    echo "OK: job_not_found_404"
}

# ── cancel a submitted job → status becomes cancelled ─────────────────────

test_async_job_cancel() {
    local submit_body job_id cancel_body status
    submit_body=$(curl -s --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "async_job=true" \
        "${AUDIOLLA_BASE_URL}/v1/audio/waveform")
    job_id=$(echo "$submit_body" | jq -r '.job_id // empty')
    if [ -z "$job_id" ]; then
        echo "  FAIL: no job_id in submit response; body: $submit_body"; return 1
    fi
    # Cancel immediately.
    cancel_body=$(curl -s --max-time 10 -X DELETE \
        "${AUDIOLLA_BASE_URL}/v1/jobs/${job_id}")
    if ! echo "$cancel_body" | jq -e '.job_id != null' >/dev/null 2>&1; then
        echo "  FAIL: cancel response missing job_id; body: $cancel_body"; return 1
    fi
    # After short delay, status should be cancelled or completed (fast jobs
    # complete before cancel reaches them).
    sleep 1
    local poll_body
    poll_body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/jobs/${job_id}")
    status=$(echo "$poll_body" | jq -r '.status // empty')
    if [ "$status" != "cancelled" ] && [ "$status" != "completed" ]; then
        echo "  FAIL: expected cancelled or completed after DELETE, got: $status"; return 1
    fi
    echo "OK: async_job_cancel (final_status=${status})"
}

# ── DELETE /v1/jobs/{id} 404 for unknown id ──────────────────────────────────

test_delete_job_not_found_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -X DELETE \
        "${AUDIOLLA_BASE_URL}/v1/jobs/00000000-0000-0000-0000-000000000001")
    assert_eq "$code" "404" "DELETE unknown job -> 404" || return 1
    echo "OK: delete_job_not_found_404"
}

harness_run_tests \
    test_async_job_submit_and_poll \
    test_jobs_list_returns_array \
    test_jobs_list_filter_by_status \
    test_job_not_found_404 \
    test_async_job_cancel \
    test_delete_job_not_found_404
