#!/bin/sh
# audiolla entrypoint — prefetches model weights for enabled engines, then
# execs the server. Demucs models are not on the HF hub; they're hosted at
# dl.fbaipublicfiles.com and demucs handles its own download. We invoke
# demucs.pretrained.get_model() per variant during prefetch so the first
# /v1/audio/separate request doesn't pay the cold-download cost.
#
# Engines without weights (pysox, librosa, pedalboard, matchering) are
# skipped silently.
set -eu

: "${AUDIOLLA_DEVICE:=auto}"
: "${AUDIOLLA_ENGINES_FILE:=/app/engines.json}"
: "${AUDIOLLA_DATA_DIR:=/data}"
: "${AUDIOLLA_ENABLED_ENGINES:=}"

# Demucs writes downloaded checkpoints under TORCH_HOME/hub/checkpoints/.
# Point that at the persistent data volume so weights survive container
# restarts.
: "${TORCH_HOME:=${AUDIOLLA_DATA_DIR}/torch_cache}"

export AUDIOLLA_DEVICE
export AUDIOLLA_ENGINES_FILE AUDIOLLA_DATA_DIR
export AUDIOLLA_ENABLED_ENGINES
export TORCH_HOME

# HuggingFace token aliasing. huggingface_hub (used by diffusers,
# transformers, etc. for gated-model auth) reads HF_TOKEN as the
# canonical name. Audiolla's own pyannote engine + older docs use
# HUGGINGFACE_TOKEN. Mirror in both directions so operators only need
# to set ONE name and gated downloads (stable-audio-open, musicgen-*,
# pyannote, etc.) work regardless of which name they picked.
if [ -n "${HUGGINGFACE_TOKEN:-}" ] && [ -z "${HF_TOKEN:-}" ]; then
    HF_TOKEN="${HUGGINGFACE_TOKEN}"
    export HF_TOKEN
fi
if [ -n "${HF_TOKEN:-}" ] && [ -z "${HUGGINGFACE_TOKEN:-}" ]; then
    HUGGINGFACE_TOKEN="${HF_TOKEN}"
    export HUGGINGFACE_TOKEN
fi

mkdir -p "${AUDIOLLA_DATA_DIR}/models"
mkdir -p "${AUDIOLLA_DATA_DIR}/files"
mkdir -p "${TORCH_HOME}/hub/checkpoints"

echo "[entrypoint] resolving enabled engines (AUDIOLLA_ENABLED_ENGINES=${AUDIOLLA_ENABLED_ENGINES:-<all>})"
echo "[entrypoint] TORCH_HOME=${TORCH_HOME}"

python3 -c "
import json, os, sys
from pathlib import Path

with open(os.environ['AUDIOLLA_ENGINES_FILE']) as fh:
    reg = json.load(fh)['engines']

raw = os.environ.get('AUDIOLLA_ENABLED_ENGINES', '').strip()
if raw:
    enabled = [s.strip() for s in raw.split(',') if s.strip()]
    missing = [s for s in enabled if s not in reg]
    if missing:
        print(
            f'[entrypoint] AUDIOLLA_ENABLED_ENGINES contains unknown slug(s) '
            f'{missing}; known: {sorted(reg)}',
            file=sys.stderr,
        )
        sys.exit(1)
else:
    enabled = list(reg)

demucs_variants = [
    reg[s].get('variant', s) for s in enabled
    if reg[s].get('prefetch') == 'demucs'
]
print(f'[entrypoint] demucs variants to prefetch: {demucs_variants}', flush=True)

if demucs_variants:
    from demucs.pretrained import get_model
    for variant in demucs_variants:
        print(f'[entrypoint] loading demucs variant={variant} (will download if missing) ...', flush=True)
        try:
            get_model(name=variant)
            print(f'[entrypoint] ok: demucs {variant}', flush=True)
        except Exception as exc:
            print(f'[entrypoint] WARN: demucs {variant} prefetch failed: {exc}', file=sys.stderr, flush=True)

print('[entrypoint] prefetch done', flush=True)
"

exec python3 -m audiolla
