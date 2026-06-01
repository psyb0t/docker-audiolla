# syntax=docker/dockerfile:1.7
#
# CPU image — python:3.12-slim + ffmpeg + sox + Demucs CPU + matchering +
# pedalboard + pyloudnorm + librosa + pysox.
#
# Note on GPL: matchering and pedalboard are GPL v3. This image is for
# self-hosted / internal use. If you distribute the image as a product,
# GPL compliance review is required.
#
# Supply chain:
#   - Lightweight runtime deps installed via `uv sync --frozen --no-dev`
#     against uv.lock — uv verifies sdist/wheel hashes from the lockfile.
#   - Heavy ML/DSP deps installed via `uv pip install --require-hashes -r
#     requirements-heavy-cpu.txt` — hashes pinned via
#     scripts/compile_heavy_deps.sh.

FROM python:3.12-slim-bookworm@sha256:d193c6f51a7dbd10395d6328de3a7edb0516fb0608ca138036576f574c3e07d2 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.15@sha256:e590846f4776907b254ac0f44b5b380347af5d90d668138ca7938d1b0c2f98d3 /uv /usr/local/bin/uv

WORKDIR /app

# 1) Lightweight runtime deps from the lockfile. Frozen install fails if
#    uv.lock is out of date relative to pyproject.toml.
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# 2) Heavy ML / DSP deps — CPU torch for demucs, hash-locked requirements.
#    See scripts/heavy-deps-cpu.in for the human spec. Pins/licenses:
#    demucs 4.0.1 (MIT), matchering 2.0.6 (GPL v3), pedalboard 0.9.20 (GPL v3),
#    pyloudnorm 0.1.1 (MIT), librosa 0.10.2 (ISC), sox 1.4.1 (BSD-3),
#    torch 2.5.1+cpu, torchaudio 2.5.1+cpu, numpy 1.26.4,
#    soundfile 0.12.1, huggingface-hub 0.30.2.
COPY requirements-heavy-cpu.txt ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --no-config \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        --index-strategy unsafe-best-match \
        --require-hashes \
        -r requirements-heavy-cpu.txt

# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:d193c6f51a7dbd10395d6328de3a7edb0516fb0608ca138036576f574c3e07d2 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    TZ=UTC \
    AUDIOLLA_DEVICE=cpu \
    AUDIOLLA_ENGINES_FILE=/app/engines.json \
    AUDIOLLA_DATA_DIR=/data \
    AUDIOLLA_SOUNDFONT=/usr/share/sounds/sf2/FluidR3_GM.sf2 \
    HF_HUB_OFFLINE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        sox \
        libsndfile1 \
        libgomp1 \
        libatomic1 \
        fluidsynth \
        fluid-soundfont-gm \
        libchromaprint-tools \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 1000 --create-home --shell /bin/bash audiolla \
    && mkdir -p /data \
    && chown audiolla:audiolla /data

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=audiolla:audiolla src ./src
COPY --chown=audiolla:audiolla pyproject.toml ./
COPY --chown=audiolla:audiolla engines-cpu.json /app/engines.json
COPY --chown=audiolla:audiolla entrypoint.sh /usr/local/bin/audiolla-entrypoint
RUN chmod +x /usr/local/bin/audiolla-entrypoint

USER audiolla

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)" || exit 1

ENTRYPOINT ["/usr/local/bin/audiolla-entrypoint"]
