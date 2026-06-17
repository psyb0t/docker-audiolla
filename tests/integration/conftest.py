"""Pytest fixtures for audiolla integration tests.

Container lifecycle, HTTP client, fixture audio staging, prerequisite skips.

Run subsets:

    # Whole suite
    pytest tests/integration/

    # One test file
    pytest tests/integration/test_audio_enhance_deepfilter.py

    # One test inside a file
    pytest tests/integration/test_audio_enhance_deepfilter.py::test_enhance_writes_real_audio

    # By keyword across files
    pytest tests/integration/ -k generate
    pytest tests/integration/ -k "musicgen or audioldm2"

    # By marker
    pytest tests/integration/ -m "not gpu"           # skip GPU-only tests
    pytest tests/integration/ -m "gpu and not hf_gated"

Knobs (env vars):

    HARNESS_IMAGE       docker image (default: psyb0t/audiolla:local)
    HARNESS_GPU=1       pass --gpus all + AUDIOLLA_DEVICE=cuda
    HARNESS_CACHE_DIR   host dir for /data mount (default: .e2e-cache)
    HARNESS_READY_TIMEOUT  seconds to wait for /healthz (default: 600)
    HARNESS_KEEP=1      leave container running on exit (debug)
    HARNESS_REUSE_CONTAINER  name of an already-running container to reuse;
                             skips the spawn step entirely
    HARNESS_SKIP_BUILD=1  skip `make build` — use whatever's tagged

Auto-skip markers (registered by ``pytest_configure``):

    @pytest.mark.engine("slug")   declares which engine(s) a test needs
                                  (the session container's
                                  AUDIOLLA_ENABLED_ENGINES is computed from
                                  the union of these markers across the
                                  selected tests)
    @pytest.mark.gpu              requires HARNESS_GPU=1
    @pytest.mark.hf_gated         requires HF_TOKEN / HUGGINGFACE_TOKEN
    @pytest.mark.noncommercial    requires AUDIOLLA_ENABLE_NONCOMMERCIAL=1
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import time
from pathlib import Path
from typing import Iterator

import atexit
import signal

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CACHE = _REPO_ROOT / ".e2e-cache"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "integration" / ".fixtures"


# Set of container names this pytest process started — used by the
# atexit + signal-handler cleanup below. The handlers ONLY kill names
# present in this set. Nothing else on the host is touched, ever.
_SESSION_CONTAINERS: set[str] = set()


def _emergency_cleanup() -> None:
    """Last-ditch cleanup of session-owned containers.

    Fires from atexit + SIGINT/SIGTERM/SIGHUP handlers, in case pytest
    exits before the session fixture's post-yield teardown runs (e.g.
    on Ctrl+C, on test runner timeout, on a fatal exception during
    collection). Iterates a snapshot of `_SESSION_CONTAINERS` and runs
    `docker rm -f <exact-name>` on each. Never expands, never filters,
    never globs.
    """
    if not _SESSION_CONTAINERS:
        return
    if os.environ.get("HARNESS_KEEP") == "1":
        # Operator explicitly asked to keep containers. Honour even on
        # crash exits.
        return
    for name in list(_SESSION_CONTAINERS):
        try:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass
        _SESSION_CONTAINERS.discard(name)


atexit.register(_emergency_cleanup)
# Chain handlers so we don't blow away any pre-existing signal hook
# (pytest installs its own KeyboardInterrupt handling — let it run too).
for _sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    _prev = signal.getsignal(_sig)

    def _make_handler(prev_handler, sig_):
        def _handler(signum, frame):
            _emergency_cleanup()
            if callable(prev_handler):
                return prev_handler(signum, frame)
            # Default: re-raise via default handler.
            signal.signal(sig_, signal.SIG_DFL)
            os.kill(os.getpid(), sig_)
        return _handler

    try:
        signal.signal(_sig, _make_handler(_prev, _sig))
    except (ValueError, OSError):
        # ValueError if we're not in the main thread; OSError on Windows.
        pass


# Auto-load tests/.env so HF_TOKEN / HUGGINGFACE_TOKEN /
# AUDIOLLA_ENABLE_NONCOMMERCIAL / AUDIOLLA_AUTH_TOKEN / etc. are
# available to the conftest's env-forwarding logic without the operator
# having to `set -a; . tests/.env; set +a` before each run. The file is
# gitignored; secrets live there, not in tracked code. Anything already
# set in the shell takes precedence (override=False).
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
    load_dotenv(_REPO_ROOT / "tests" / ".env", override=False)
except ImportError:
    pass


# ── pytest configuration ────────────────────────────────────────────────────


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "engine(*slugs): engines the test needs; "
        "union across all collected tests determines AUDIOLLA_ENABLED_ENGINES",
    )
    config.addinivalue_line(
        "markers", "gpu: requires HARNESS_GPU=1 (CUDA + --gpus all)",
    )
    config.addinivalue_line(
        "markers",
        "hf_gated: requires HF_TOKEN / HUGGINGFACE_TOKEN with HuggingFace "
        "licence accepted for the gated repo",
    )
    config.addinivalue_line(
        "markers",
        "noncommercial: requires AUDIOLLA_ENABLE_NONCOMMERCIAL=1 "
        "(CC-BY-NC engines like MusicGen)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item],
) -> None:
    """Auto-skip tests whose marker prerequisites aren't satisfied."""
    has_gpu = os.environ.get("HARNESS_GPU", "0") == "1"
    has_hf = bool(
        os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    )
    has_nc = os.environ.get(
        "AUDIOLLA_ENABLE_NONCOMMERCIAL", "",
    ).strip().lower() in ("1", "true", "yes", "on")

    skip_gpu = pytest.mark.skip(
        reason="needs HARNESS_GPU=1 (CUDA + --gpus all)",
    )
    skip_hf = pytest.mark.skip(
        reason="needs HF_TOKEN / HUGGINGFACE_TOKEN with licence accepted",
    )
    skip_nc = pytest.mark.skip(
        reason="needs AUDIOLLA_ENABLE_NONCOMMERCIAL=1",
    )

    for item in items:
        if "gpu" in item.keywords and not has_gpu:
            item.add_marker(skip_gpu)
        if "hf_gated" in item.keywords and not has_hf:
            item.add_marker(skip_hf)
        if "noncommercial" in item.keywords and not has_nc:
            item.add_marker(skip_nc)


# ── helpers ─────────────────────────────────────────────────────────────────


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _collected_engines(session: pytest.Session) -> str:
    """Union of @pytest.mark.engine(...) slugs across collected tests.

    Tests that will be auto-skipped (their prerequisites aren't satisfied
    — no GPU, no HF token, no noncommercial opt-in) are excluded from the
    union: their engines aren't needed, and including them risks asking
    the container to enable engines that aren't in this image
    (e.g. ``stable-audio-open`` on the CPU image).

    Returns a comma-separated string, or "" (== all engines) if nothing
    declared (e.g. when running ``pytest -k <substring>`` against tests
    that don't carry the marker — safer to enable everything than to
    spin up a stripped container).
    """
    has_gpu = os.environ.get("HARNESS_GPU", "0") == "1"
    has_hf = bool(
        os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    )
    has_nc = os.environ.get(
        "AUDIOLLA_ENABLE_NONCOMMERCIAL", "",
    ).strip().lower() in ("1", "true", "yes", "on")

    engines: set[str] = set()
    for item in session.items:
        if "gpu" in item.keywords and not has_gpu:
            continue
        if "hf_gated" in item.keywords and not has_hf:
            continue
        if "noncommercial" in item.keywords and not has_nc:
            continue
        for mark in item.iter_markers("engine"):
            for arg in mark.args:
                engines.add(arg)
    return ",".join(sorted(engines))


# ── session-scoped container ────────────────────────────────────────────────


@pytest.fixture(scope="session")
def audiolla_url(request: pytest.FixtureRequest) -> Iterator[str]:
    """Spawn one audiolla container per pytest session; yield its base URL.

    Behaviour:

    - If ``HARNESS_REUSE_CONTAINER`` is set and the named container is
      running, bind to it. No new container is spawned. No teardown.
      This is the path used when a parent process (CI script, multi-suite
      runner) pre-warmed a container.
    - Otherwise: spawn a fresh container with the engines required by the
      collected tests (or all engines if no marker was declared), wait
      for /healthz, yield, tear down on session end (unless ``HARNESS_KEEP=1``).
    """
    reuse_name = os.environ.get("HARNESS_REUSE_CONTAINER")
    reuse_port = os.environ.get("HARNESS_REUSE_PORT")
    if reuse_name and reuse_port:
        if _container_running(reuse_name):
            url = f"http://127.0.0.1:{reuse_port}"
            _wait_healthz(url, timeout=int(os.environ.get(
                "HARNESS_READY_TIMEOUT", "600",
            )))
            yield url
            return
        print(
            f"[harness] HARNESS_REUSE_CONTAINER={reuse_name} not running; "
            "falling through to fresh spawn",
        )

    image = os.environ.get("HARNESS_IMAGE", "psyb0t/audiolla:local")
    use_gpu = os.environ.get("HARNESS_GPU", "0") == "1"
    cache_dir = Path(os.environ.get("HARNESS_CACHE_DIR", str(_DEFAULT_CACHE)))
    cache_dir.mkdir(parents=True, exist_ok=True)
    timeout = int(os.environ.get("HARNESS_READY_TIMEOUT", "600"))

    engines_csv = _collected_engines(request.session)
    port = _free_port()
    # Fixed container name so concurrent pytest runs share the same
    # slot — first one wins, the rest see the existing container and
    # would collide on the `docker run --name`. Kill any leftover by
    # exact name before starting (only this exact name; the global rule
    # forbids filter+xargs patterns). CUDA vs CPU runs use a different
    # name so an in-flight CPU container doesn't conflict with a CUDA
    # invocation.
    name = "audiolla-pytest-cuda" if use_gpu else "audiolla-pytest"
    subprocess.run(
        ["docker", "rm", "-f", name],
        capture_output=True, timeout=30,
    )

    _ensure_fixtures(image)

    # No `--rm` here — if the entrypoint fails fast we still need to read
    # the container's logs to diagnose. Cleanup happens explicitly at the
    # end of the session (or never, if HARNESS_KEEP=1).
    cmd: list[str] = [
        "docker", "run", "-d",
        "--name", name,
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{cache_dir.resolve()}:/data",
        "-p", f"{port}:8000",
        "-e", f"AUDIOLLA_ENABLED_ENGINES={engines_csv}",
        "-e", f"AUDIOLLA_DEVICE={'cuda' if use_gpu else 'cpu'}",
    ]
    if use_gpu:
        cmd.extend(["--gpus", "all"])

    # Forward AUDIOLLA_* / HF_* / HUGGINGFACE_* / LOG_LEVEL from the
    # caller's environment so tests can override config without touching
    # the harness signature.
    #
    # AUDIOLLA_ENGINES_FILE is force-skipped because the parent
    # `tests/conftest.py` sets it to a HOST path (so unit-test imports of
    # audiolla.server can resolve the file). Forwarding that host path
    # into the container would break the entrypoint — the container has
    # its own default `/app/engines.json` baked in.
    # AUDIOLLA_DATA_DIR is similarly skipped; the container's own /data
    # is mounted, and overriding to a host path inside the container
    # would point at a missing dir.
    skip_names = {
        "AUDIOLLA_DEVICE",
        "AUDIOLLA_ENABLED_ENGINES",
        "AUDIOLLA_ENGINES_FILE",
        "AUDIOLLA_DATA_DIR",
    }
    for var, val in os.environ.items():
        if var in skip_names:
            continue
        if (
            var.startswith(("AUDIOLLA_", "HF_", "HUGGINGFACE_"))
            or var == "LOG_LEVEL"
        ):
            cmd.extend(["-e", f"{var}={val}"])

    cmd.append(image)

    print(
        f"\n[harness] starting {name}\n"
        f"          image:   {image}\n"
        f"          port:    {port}\n"
        f"          cache:   {cache_dir}\n"
        f"          engines: {engines_csv or '(all)'}\n"
        f"          device:  {'cuda' if use_gpu else 'cpu'}",
    )
    subprocess.run(cmd, check=True, capture_output=True)
    # Register this exact name for atexit / signal-handler cleanup so a
    # Ctrl+C / kill mid-session doesn't leave an orphan running. The
    # cleanup ONLY ever kills names we put in this set; nothing else on
    # the host is touched.
    _SESSION_CONTAINERS.add(name)

    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_healthz(base_url, timeout=timeout, container=name)
    except Exception:
        _dump_logs(name)
        _kill(name)
        raise

    yield base_url

    if os.environ.get("HARNESS_KEEP") == "1":
        print(
            f"\n[harness] HARNESS_KEEP=1 — leaving {name} on port {port}\n"
            f"          logs: docker logs -f {name}\n"
            f"          rm:   docker rm -f {name}",
        )
        # Don't auto-kill on graceful exit, but DO drop it from the
        # session set so an unrelated signal-handler invocation later
        # doesn't sweep it. The operator now owns the lifecycle.
        _SESSION_CONTAINERS.discard(name)
        return
    _kill(name)
    _SESSION_CONTAINERS.discard(name)


def _container_running(name: str) -> bool:
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and r.stdout.strip() == "true"


def _wait_healthz(url: str, *, timeout: int, container: str | None = None) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/healthz", timeout=5)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if container and not _container_running(container):
            raise RuntimeError(
                f"container {container} exited during boot — see docker logs",
            )
        time.sleep(2)
    raise RuntimeError(f"/healthz never came up at {url} within {timeout}s")


def _dump_logs(name: str) -> None:
    print(f"\n[harness] last 80 lines of {name}:")
    subprocess.run(["docker", "logs", "--tail", "80", name])


def _kill(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _ensure_fixtures(image: str) -> None:
    """Generate the synthetic audio fixtures via the audiolla image's
    ffmpeg if they're missing. Avoids depending on the host having ffmpeg.
    """
    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    required = {
        "audio.wav": [
            "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
            "-af", "pan=stereo|c0=c0|c1=c0",
            "-ar", "44100",
        ],
        "audio_ref.wav": None,  # derived from audio.wav below
        "beat_120.wav": [
            "-f", "lavfi",
            "-i", "aevalsrc=sin(2*PI*880*t)*if(lt(mod(t\\,0.5)\\,0.05)\\,1\\,0):s=44100:d=8",
            "-ar", "44100",
        ],
        # 16-second stereo for engines that reject <10s input — UVR
        # separator family (deverb / deecho / denoise / vocal-bsr /
        # karaoke) drops everything below the 10-second threshold with
        # "model produced no output files".
        "audio_long.wav": [
            "-f", "lavfi", "-i", "sine=frequency=440:duration=16",
            "-af", "pan=stereo|c0=c0|c1=c0",
            "-ar", "44100",
        ],
    }
    if all((_FIXTURES_DIR / name).exists() for name in required):
        return

    for name, args in required.items():
        target = _FIXTURES_DIR / name
        if target.exists():
            continue
        if name == "audio_ref.wav":
            # derived: -6dB version of audio.wav
            src = _FIXTURES_DIR / "audio.wav"
            if not src.exists():
                continue
            subprocess.run(
                [
                    "docker", "run", "--rm",
                    "-u", f"{os.getuid()}:{os.getgid()}",
                    "-v", f"{_FIXTURES_DIR}:/fx",
                    "--entrypoint", "ffmpeg", image,
                    "-hide_banner", "-loglevel", "error",
                    "-y", "-i", "/fx/audio.wav", "-af", "volume=-6dB",
                    "/fx/audio_ref.wav",
                ],
                check=True, capture_output=True,
            )
            continue
        assert args is not None
        subprocess.run(
            [
                "docker", "run", "--rm",
                "-u", f"{os.getuid()}:{os.getgid()}",
                "-v", f"{_FIXTURES_DIR}:/fx",
                "--entrypoint", "ffmpeg", image,
                "-hide_banner", "-loglevel", "error",
                *args,
                "-y", f"/fx/{name}",
            ],
            check=True, capture_output=True,
        )


# ── per-test fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def client(audiolla_url: str) -> Iterator[httpx.Client]:
    """An ``httpx.Client`` bound to the running audiolla container, with
    any configured auth header pre-set and a generous default timeout
    (some endpoints — text-to-audio generation, mastering on a 10-minute
    track — legitimately take minutes)."""
    token = os.environ.get("AUDIOLLA_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(
        base_url=audiolla_url,
        headers=headers,
        timeout=httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0),
    ) as c:
        yield c


@pytest.fixture
def staged_audio(client: httpx.Client) -> str:
    """PUT the synthetic ``audio.wav`` fixture into a unique
    ``/v1/files/uploads/...`` slot and return the relative path. Each
    test gets a fresh path so parallel runs don't collide."""
    src = _FIXTURES_DIR / "audio.wav"
    assert src.exists(), (
        f"fixture {src} missing — conftest's _ensure_fixtures() should have "
        "generated it"
    )
    rel = f"uploads/test-{secrets.token_hex(8)}.wav"
    with src.open("rb") as fh:
        r = client.put(
            f"/v1/files/{rel}",
            content=fh.read(),
            headers={"Content-Type": "application/octet-stream"},
        )
    assert r.status_code in (200, 201), (
        f"failed to stage {rel}: {r.status_code} {r.text}"
    )
    return rel


@pytest.fixture
def staged_beat(client: httpx.Client) -> str:
    """Like ``staged_audio`` but for the 120 BPM click track. Used by
    beat-detection / loop-point / DJ-prep tests."""
    src = _FIXTURES_DIR / "beat_120.wav"
    assert src.exists()
    rel = f"uploads/beat-{secrets.token_hex(8)}.wav"
    with src.open("rb") as fh:
        r = client.put(
            f"/v1/files/{rel}",
            content=fh.read(),
            headers={"Content-Type": "application/octet-stream"},
        )
    assert r.status_code in (200, 201)
    return rel


@pytest.fixture
def staged_long_audio(client: httpx.Client) -> str:
    """16-second stereo sine staged under ``uploads/``. Used by engines
    that reject short clips (UVR separator family won't run on <10s
    audio — they refuse with `model produced no output files`)."""
    src = _FIXTURES_DIR / "audio_long.wav"
    assert src.exists()
    rel = f"uploads/long-{secrets.token_hex(8)}.wav"
    with src.open("rb") as fh:
        r = client.put(
            f"/v1/files/{rel}",
            content=fh.read(),
            headers={"Content-Type": "application/octet-stream"},
        )
    assert r.status_code in (200, 201)
    return rel


@pytest.fixture
def staged_reference(client: httpx.Client) -> str:
    """The ``audio_ref.wav`` (-6 dB version of ``audio.wav``) used as a
    mastering reference. Distinct from ``staged_audio`` so reference-mode
    tests have a target ≠ reference."""
    src = _FIXTURES_DIR / "audio_ref.wav"
    assert src.exists()
    rel = f"uploads/ref-{secrets.token_hex(8)}.wav"
    with src.open("rb") as fh:
        r = client.put(
            f"/v1/files/{rel}",
            content=fh.read(),
            headers={"Content-Type": "application/octet-stream"},
        )
    assert r.status_code in (200, 201)
    return rel
