"""Exercise the production image with real tensors, audio processing and cleanup."""

from __future__ import annotations

import asyncio
import io
import math
import os
import struct
import time
import wave

import httpx
import torch
import torchaudio

from audiolla import __version__, config, server


async def main() -> None:
    assert __version__ == os.environ["RELEASE_VERSION"], __version__
    assert server.app.version == __version__, server.app.version
    device = os.environ["AUDIOLLA_DEVICE"]
    expected = "2.5.1+cu124" if device == "cuda" else "2.5.1+cpu"
    assert torch.__version__ == expected, torch.__version__
    assert torchaudio.__version__ == expected, torchaudio.__version__
    samples = torch.arange(16000, device=device, dtype=torch.float32)
    signal = torch.sin(samples * (2 * math.pi * 440 / 16000))
    resampled = torchaudio.functional.resample(signal, 16000, 8000)
    assert resampled.shape == (8000,)
    assert torch.isfinite(resampled).all().item()
    assert resampled.device.type == device
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(
            b"".join(
                struct.pack("<h", int(10000 * math.sin(2 * math.pi * 440 * i / 16000)))
                for i in range(16000)
            )
        )
    async with server.app.router.lifespan_context(server.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app), base_url="http://test"
        ) as client:
            uploaded = await client.put(
                "/v1/files/input.wav",
                content=buffer.getvalue(),
                headers={"Content-Type": "audio/wav"},
            )
            assert uploaded.status_code == 201, uploaded.text
            transformed = await client.post(
                "/v1/audio/transform",
                json={
                    "file_path": "input.wav",
                    "operations": [{"op": "gain", "params": {"db": -3}}],
                    "output_format": "wav",
                    "output_path": "output.wav",
                },
            )
            assert transformed.status_code == 200, transformed.text
            downloaded = await client.get("/v1/files/output.wav")
            assert downloaded.status_code == 200, downloaded.text
            with wave.open(io.BytesIO(downloaded.content), "rb") as wav:
                assert abs(wav.getnframes() / wav.getframerate() - 1.0) < 0.01
                assert wav.getsampwidth() == 2
                pcm = wav.readframes(wav.getnframes())
                peak = max(abs(sample[0]) for sample in struct.iter_unpack("<h", pcm))
            queued = await client.post(
                "/v1/audio/transform",
                json={
                    "file_path": "input.wav",
                    "operations": [],
                    "output_format": "wav",
                    "output_path": "async.wav",
                    "async_job": True,
                },
            )
            assert queued.status_code == 202, queued.text
            job_id = queued.json()["job_id"]
            for _ in range(100):
                job = await client.get(f"/v1/jobs/{job_id}")
                assert job.status_code == 200, job.text
                if job.json()["status"] in ("completed", "failed", "cancelled"):
                    break
                await asyncio.sleep(0.05)
            assert job.json()["status"] == "completed", job.text
            identity = await client.get("/v1/files/async.wav")
            assert identity.status_code == 200, identity.text
            with wave.open(io.BytesIO(identity.content), "rb") as wav:
                assert wav.getsampwidth() == 2
                pcm = wav.readframes(wav.getnframes())
                identity_peak = max(
                    abs(sample[0]) for sample in struct.iter_unpack("<h", pcm)
                )
            # PySoX gain normalizes to the requested dB below full scale.
            assert abs(peak / 32768 - 10 ** (-3 / 20)) < 0.01, peak
            assert identity_peak > 0 and identity_peak != peak
            staged = config.FILES_DIR / "output.wav"
            old = time.time() - config.FILES_TTL_SECONDS - 10
            os.utime(staged, (old, old))
            for _ in range(100):
                if not staged.exists():
                    break
                await asyncio.sleep(0.05)
            assert not staged.exists(), "lifespan sweeper did not expire output"
            assert (await client.get("/v1/files/output.wav")).status_code == 404
            assert (await client.get("/healthz")).status_code == 200
    print(
        f"PASS: {device}, matching Torch/Torchaudio, real resampling, upload, "
        "SoX gain, download, background job, automatic expiration and healthy API"
    )


if __name__ == "__main__":
    asyncio.run(main())
