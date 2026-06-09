"""End-to-end test for ``POST /v1/audio/mid-side``.

Encode stereo to Mid/Side or decode M/S back to stereo.
"""

from __future__ import annotations

import httpx

from .helpers import assert_wav


def test_mid_side_encode_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """mode=encode (L/R → M/S) returns a valid WAV of expected size."""
    r = client.post(
        "/v1/audio/mid-side",
        json={
            "file_path": staged_audio,
            "mode": "encode",
            "output_path": "out/ms_encode.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100_000)


def test_mid_side_decode_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """mode=decode (M/S → L/R) returns a valid WAV."""
    r = client.post(
        "/v1/audio/mid-side",
        json={
            "file_path": staged_audio,
            "mode": "decode",
            "output_path": "out/ms_decode.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_mid_side_roundtrip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """encode → decode roundtrip stays within ±5% of original size."""
    enc = client.post(
        "/v1/audio/mid-side",
        json={
            "file_path": staged_audio,
            "mode": "encode",
            "output_path": "out/ms_rt_enc.wav",
        },
    )
    assert enc.status_code == 200, enc.text

    dec = client.post(
        "/v1/audio/mid-side",
        json={
            "file_path": "out/ms_rt_enc.wav",
            "mode": "decode",
            "output_path": "out/ms_rt_dec.wav",
        },
    )
    assert dec.status_code == 200, dec.text

    orig = client.get(f"/v1/files/{staged_audio}").content
    decoded = client.get("/v1/files/out/ms_rt_dec.wav").content
    drift = abs(len(decoded) - len(orig))
    assert drift <= len(orig) // 20, (
        f"roundtrip size drift {drift} too far from {len(orig)}"
    )


def test_mid_side_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/mid-side",
        json={
            "file_path": staged_audio,
            "mode": "encode",
            "output_path": "ms_test/encoded.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "ms_test/encoded.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_mid_side_invalid_mode_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """An invalid mode value → Pydantic 422 (enum coercion)."""
    r = client.post(
        "/v1/audio/mid-side",
        json={
            "file_path": staged_audio,
            "mode": "invalid_mode",
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 422, r.text
