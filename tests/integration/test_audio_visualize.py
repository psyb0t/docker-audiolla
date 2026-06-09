"""End-to-end tests for ``/v1/audio/visualize/{image,video}/...``.

Spectrogram + waveform PNG renders; spectrum / waves / cqt video renders
via ffmpeg's avectorscope / showspectrum / showcqt filters.
"""

from __future__ import annotations

import secrets

import httpx
import pytest

from .helpers import assert_mp4, assert_png, assert_webm

pytestmark = pytest.mark.engine("ffmpeg-render")


# ── PNG renders ────────────────────────────────────────────────────────────


def test_spectrogram_png(client: httpx.Client, staged_audio: str) -> None:
    """spectrogram PNG render."""
    dest = f"viz/spec-{secrets.token_hex(4)}.png"
    r = client.post(
        "/v1/audio/visualize/image/spectrogram",
        json={
            "file_path": staged_audio,
            "width": 640,
            "height": 240,
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == dest

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_png(fetched.content, min_bytes=500)


def test_waveform_png(client: httpx.Client, staged_audio: str) -> None:
    """waveform PNG render."""
    dest = f"viz/wave-{secrets.token_hex(4)}.png"
    r = client.post(
        "/v1/audio/visualize/image/waveform",
        json={
            "file_path": staged_audio,
            "width": 640,
            "height": 160,
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_png(fetched.content)


def test_spectrogram_color_scale(
    client: httpx.Client, staged_audio: str,
) -> None:
    """color=fire scale=lin produces a valid PNG."""
    dest = f"viz/spec-color-{secrets.token_hex(4)}.png"
    r = client.post(
        "/v1/audio/visualize/image/spectrogram",
        json={
            "file_path": staged_audio,
            "width": 320,
            "height": 160,
            "color": "fire",
            "scale": "lin",
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{dest}")
    assert_png(fetched.content)


def test_waveform_color(client: httpx.Client, staged_audio: str) -> None:
    """color=cyan accepted."""
    dest = f"viz/wave-color-{secrets.token_hex(4)}.png"
    r = client.post(
        "/v1/audio/visualize/image/waveform",
        json={
            "file_path": staged_audio,
            "width": 320,
            "height": 160,
            "color": "cyan",
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{dest}")
    assert_png(fetched.content)


# ── video renders ──────────────────────────────────────────────────────────


def test_visualize_spectrum_mp4(
    client: httpx.Client, staged_audio: str,
) -> None:
    """video/spectrum → MP4 container."""
    dest = f"viz/spec-{secrets.token_hex(4)}.mp4"
    r = client.post(
        "/v1/audio/visualize/video/spectrum",
        json={
            "file_path": staged_audio,
            "width": 320,
            "height": 180,
            "fps": 15,
            "container": "mp4",
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_mp4(fetched.content, min_bytes=5000)


def test_visualize_waves_webm(
    client: httpx.Client, staged_audio: str,
) -> None:
    """video/waves with container=webm → WebM container."""
    dest = f"viz/waves-{secrets.token_hex(4)}.webm"
    r = client.post(
        "/v1/audio/visualize/video/waves",
        json={
            "file_path": staged_audio,
            "width": 320,
            "height": 180,
            "fps": 15,
            "container": "webm",
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_webm(fetched.content)


def test_visualize_cqt_mp4(client: httpx.Client, staged_audio: str) -> None:
    """video/cqt exercises a different ffmpeg filter chain → MP4."""
    dest = f"viz/cqt-{secrets.token_hex(4)}.mp4"
    r = client.post(
        "/v1/audio/visualize/video/cqt",
        json={
            "file_path": staged_audio,
            "width": 320,
            "height": 180,
            "fps": 15,
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_mp4(fetched.content)


def test_visualize_unknown_mode_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Unknown video mode → 400 with `mode` mentioned in the detail."""
    r = client.post(
        "/v1/audio/visualize/video/notamode",
        json={
            "file_path": staged_audio,
            "output_path": f"viz/bad-{secrets.token_hex(4)}.mp4",
        },
    )
    assert r.status_code == 400, r.text
    assert "mode" in r.text.lower()
