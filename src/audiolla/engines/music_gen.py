"""Text-to-music / text-to-SFX generation engines.

Five engines covering different licence / quality / VRAM tradeoffs. All
share the same ``generate(prompt, ...)`` contract so the
``/v1/audio/generate/{engine}`` REST endpoint can dispatch uniformly.

  stable-audio-open     Stability Stable Audio Open 1.0 (Stability AI
                        Community Licence — commercial use OK below the
                        revenue threshold). 1.21B params, 47-second hard
                        cap, instrumental only — loops / riffs / SFX /
                        textures. ~12 GB VRAM at fp16. Loads via
                        ``StableAudioPipeline``.
  musicgen-small        Meta MusicGen 300M (CC-BY-NC weights). Instrumental
                        only, ~30 s output cap, ~3 GB VRAM at fp16. Gated
                        behind ``AUDIOLLA_ENABLE_NONCOMMERCIAL=1``.
  musicgen-medium       Meta MusicGen 1.5B (CC-BY-NC). Same gate. ~6 GB
                        VRAM at fp16. Higher quality than small.
  riffusion             Riffusion-model-v1 (CreativeML OpenRAIL-M licence —
                        commercial use OK with the usage restrictions in
                        the licence). Stable Diffusion variant that
                        generates spectrograms, converted to audio via
                        Griffin-Lim. ~3 GB VRAM at fp16. Unique character —
                        lo-fi, loop-friendly. 22.05 kHz mono.
  audioldm2             AudioLDM2 (CC-BY 4.0 — commercial use OK, NO
                        opt-in gate). 1.1B params, dual CLAP + Flan-T5
                        encoders. 16 kHz mono. General-purpose SFX:
                        ambience, foley, animal sounds, mechanical SFX.
                        ~8-10 GB VRAM at fp16; CPU offload trims peak.
                        Slow (200-step DDIM default). Loads via
                        ``AudioLDM2Pipeline``.

Generators considered for v1.0.0 and deferred:

  ace-step              Needs ``AceStepPipeline`` from diffusers >= 0.38.0,
                        which itself requires a pre-release ``safetensors``.
                        Doesn't pass the project's hash-locked supply-chain
                        gate. Revisit when safetensors 0.8.x ships stable
                        or we vendor ACE-Step's pipeline directly.
  diffrhythm            ASLP-lab research repo, not packaged (no setup.py
                        / PyPI release). Revisit on upstream package
                        release or vendored ``thirdparty/`` integration.
  stable-audio-open-small  Requires the ``stable-audio-tools`` library
                        (no diffusers pipeline as of mid-2026), which is
                        pinned to ``python >=3.10, <3.11`` — hard
                        incompatibility with audiolla's Python 3.12.
                        Revisit when stable-audio-tools widens the Python
                        constraint or diffusers grows a pipeline for it.

Model weights download on first call to HF_HOME (default /data/hf inside
the container — already wired by the image's HF cache mount). First call
takes several minutes; subsequent calls are inference-only.

Returns raw WAV bytes at the model's native sample rate; the endpoint
re-encodes to the caller's ``output_format`` via the existing
``encode_audio()`` helper from audio.py.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from ..audio import AudioConversionError, encode_audio
from .base import EngineBase


class MusicGenError(AudioConversionError):
    """Text-to-music inference failed."""


# ── shared helpers ──────────────────────────────────────────────────────────


def _validate_duration(duration_sec: float, *, max_sec: float, engine: str) -> None:
    if duration_sec <= 0:
        raise MusicGenError(f"{engine}: duration_sec must be > 0, got {duration_sec}")
    if duration_sec > max_sec:
        raise MusicGenError(
            f"{engine}: duration_sec {duration_sec} exceeds engine cap {max_sec}"
        )


def _write_wav_temp(samples, sample_rate: int) -> str:
    """Persist a numpy float32 array to a temporary WAV file and return its path."""
    import soundfile as sf  # noqa: PLC0415

    fd, path = tempfile.mkstemp(prefix="audiolla-musicgen-", suffix=".wav")
    os.close(fd)
    sf.write(path, samples, sample_rate, subtype="FLOAT")
    return path


def _encode(samples, sample_rate: int, output_format: str) -> bytes:
    wav_path = _write_wav_temp(samples, sample_rate)
    try:
        audio_bytes, _ct = encode_audio(wav_path, output_format)
        return audio_bytes
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def _resolve_device() -> str:
    """Return ``cuda`` if a GPU is visible, otherwise ``cpu``. Music gen on
    CPU is slow but functional for small models / short clips."""
    try:
        import torch  # noqa: PLC0415
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


# ── Stable Audio Open 1.0 ───────────────────────────────────────────────────


class StableAudioOpenEngine(EngineBase):
    """Stability AI Stable Audio Open 1.0 (Community License). 47-second
    hard cap. Best for loops, riffs, ambient textures, SFX, drum beats.
    No vocals — trained on Freesound + FMA instrumentals."""

    SAMPLE_RATE = 44100
    MAX_DURATION_SEC = 47.0
    MODEL_ID = "stabilityai/stable-audio-open-1.0"

    def _load_sync(self) -> object:
        import torch  # noqa: PLC0415
        from diffusers import StableAudioPipeline  # noqa: PLC0415

        device = _resolve_device()
        dtype = torch.float16 if device == "cuda" else torch.float32
        self._log.info("loading Stable Audio Open 1.0 (device=%s dtype=%s)", device, dtype)
        pipe = StableAudioPipeline.from_pretrained(
            self.MODEL_ID, torch_dtype=dtype,
        )
        pipe.to(device)
        self._device = device
        self._log.info("Stable Audio Open ready")
        return pipe

    async def generate(
        self,
        prompt: str,
        *,
        duration_sec: float = 10.0,
        seed: int | None = None,
        num_inference_steps: int = 100,
        output_format: str = "wav",
        lyrics: str | None = None,  # accepted for API uniformity; ignored (no vocals)
    ) -> bytes:
        _validate_duration(duration_sec, max_sec=self.MAX_DURATION_SEC, engine="stable-audio-open")
        if not prompt or not isinstance(prompt, str):
            raise MusicGenError("stable-audio-open: prompt must be a non-empty string")
        del lyrics  # this engine doesn't support vocals
        await self.get_model()
        async with self._lock:
            audio_bytes = await asyncio.to_thread(
                self._generate_sync, prompt, duration_sec, seed,
                num_inference_steps, output_format,
            )
            self._touch()
            return audio_bytes

    def _generate_sync(
        self,
        prompt: str,
        duration_sec: float,
        seed: int | None,
        num_inference_steps: int,
        output_format: str,
    ) -> bytes:
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        gen = torch.Generator(device=self._device)
        if seed is not None:
            gen = gen.manual_seed(int(seed))
        try:
            result = self._model(
                prompt,
                negative_prompt="low quality, average quality",
                num_inference_steps=num_inference_steps,
                audio_end_in_s=float(duration_sec),
                num_waveforms_per_prompt=1,
                generator=gen,
            )
        except Exception as exc:  # noqa: BLE001
            raise MusicGenError(f"stable-audio-open inference failed: {exc}") from exc
        audio = result.audios[0] if hasattr(result, "audios") else result["audios"][0]
        if hasattr(audio, "cpu"):
            audio = audio.cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32)
        # StableAudioPipeline returns shape (channels, samples) at 44.1kHz
        if audio.ndim == 2 and audio.shape[0] in (1, 2):
            audio = audio.T
        return _encode(audio, self.SAMPLE_RATE, output_format)

    def _release_model(self, model: Any) -> None:
        try:
            model.to("cpu")
        except Exception:  # noqa: BLE001
            pass
        del model


# ── licence gate ────────────────────────────────────────────────────────────


def _require_noncommercial_optin(engine_slug: str) -> None:
    """Raise MusicGenError if AUDIOLLA_ENABLE_NONCOMMERCIAL is not opted in.

    MusicGen weights are CC-BY-NC. The project ships the engine code but
    refuses to load the model unless the operator explicitly opts in by
    setting AUDIOLLA_ENABLE_NONCOMMERCIAL=1 (any of 1/true/yes/on). Same
    pattern matchering (GPL v3) follows — license-encumbered code in the
    image, conscious opt-in to actually use it."""
    raw = os.environ.get("AUDIOLLA_ENABLE_NONCOMMERCIAL", "").strip().lower()
    if raw not in ("1", "true", "yes", "on"):
        raise MusicGenError(
            f"{engine_slug}: weights are CC-BY-NC-licensed. Set "
            "AUDIOLLA_ENABLE_NONCOMMERCIAL=1 in the server's environment "
            "to opt in. Read the licence at "
            "https://github.com/facebookresearch/audiocraft/blob/main/LICENSE_weights "
            "before doing so."
        )


# ── MusicGen (small / medium) ───────────────────────────────────────────────


class _MusicGenBase(EngineBase):
    """Shared body for MusicGen small + medium. Subclasses just bind
    ``MODEL_ID`` + ``MAX_DURATION_SEC``. Uses transformers' native
    ``MusicgenForConditionalGeneration`` — no audiocraft dependency."""

    SAMPLE_RATE = 32000
    MODEL_ID: str
    MAX_DURATION_SEC: float

    def _load_sync(self) -> object:
        import torch  # noqa: PLC0415
        from transformers import (  # noqa: PLC0415
            MusicgenForConditionalGeneration,
            MusicgenProcessor,
        )

        _require_noncommercial_optin(self.slug)

        device = _resolve_device()
        dtype = torch.float16 if device == "cuda" else torch.float32
        self._log.info(
            "loading MusicGen %s (device=%s dtype=%s)", self.MODEL_ID, device, dtype,
        )
        processor = MusicgenProcessor.from_pretrained(self.MODEL_ID)
        model = MusicgenForConditionalGeneration.from_pretrained(
            self.MODEL_ID, torch_dtype=dtype,
        )
        model.to(device)
        self._processor = processor
        self._device = device
        self._log.info("MusicGen %s ready", self.MODEL_ID)
        return model

    async def generate(
        self,
        prompt: str,
        *,
        duration_sec: float = 15.0,
        lyrics: str | None = None,  # accepted for API uniformity; ignored
        seed: int | None = None,
        output_format: str = "wav",
    ) -> bytes:
        _validate_duration(duration_sec, max_sec=self.MAX_DURATION_SEC, engine=self.slug)
        if not prompt or not isinstance(prompt, str):
            raise MusicGenError(f"{self.slug}: prompt must be a non-empty string")
        del lyrics  # MusicGen is instrumental-only, no vocal stack
        await self.get_model()
        async with self._lock:
            audio_bytes = await asyncio.to_thread(
                self._generate_sync, prompt, duration_sec, seed, output_format,
            )
            self._touch()
            return audio_bytes

    def _generate_sync(
        self,
        prompt: str,
        duration_sec: float,
        seed: int | None,
        output_format: str,
    ) -> bytes:
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        if seed is not None:
            torch.manual_seed(int(seed))
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(int(seed))

        # MusicGen tokens-per-second is roughly 50 at 32kHz; +20% headroom
        max_new_tokens = int(round(duration_sec * 50 * 1.05))

        inputs = self._processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        ).to(self._device)

        try:
            with torch.no_grad():
                tokens = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=True,
                    guidance_scale=3.0,
                )
        except Exception as exc:  # noqa: BLE001
            raise MusicGenError(f"{self.slug} inference failed: {exc}") from exc

        audio = tokens[0, 0].float().cpu().numpy()
        # Truncate to requested duration (MusicGen emits in token-block multiples)
        max_samples = int(self.SAMPLE_RATE * duration_sec)
        audio = audio[:max_samples]
        return _encode(np.asarray(audio, dtype=np.float32), self.SAMPLE_RATE, output_format)

    def _release_model(self, model: Any) -> None:
        try:
            model.to("cpu")
        except Exception:  # noqa: BLE001
            pass
        del model


class MusicGenSmallEngine(_MusicGenBase):
    """Meta MusicGen 300M (small). CC-BY-NC, ~3 GB VRAM, instrumental only,
    ~30 s output cap."""

    MODEL_ID = "facebook/musicgen-small"
    MAX_DURATION_SEC = 30.0


class MusicGenMediumEngine(_MusicGenBase):
    """Meta MusicGen 1.5B (medium). CC-BY-NC, ~6-8 GB VRAM, instrumental
    only, ~30 s output cap. Higher quality than -small."""

    MODEL_ID = "facebook/musicgen-medium"
    MAX_DURATION_SEC = 30.0


# ── Riffusion ───────────────────────────────────────────────────────────────


class RiffusionEngine(EngineBase):
    """Riffusion-model-v1 (CreativeML OpenRAIL-M). Stable Diffusion variant
    fine-tuned to generate spectrograms from a text prompt; spectrograms are
    converted to audio via Griffin-Lim phase reconstruction.

    Quality is lo-fi / loop-y compared to native audio models — a unique
    character vs Stable Audio Open's clean output. 22.05 kHz mono, ~5 s
    clips per pass (the model is trained on fixed-size 512x512 spectrograms).
    For longer outputs, multiple passes can be stitched but this engine
    keeps it to one pass per call.
    """

    SAMPLE_RATE = 22050
    MAX_DURATION_SEC = 30.0  # ceiling; actual output capped by the spec size
    MODEL_ID = "riffusion/riffusion-model-v1"
    # Riffusion's reference image size is 512x512; one image ≈ 5 seconds of audio.
    IMAGE_HEIGHT = 512
    IMAGE_WIDTH = 512
    HOP_LENGTH = 256
    N_FFT = 1024

    def _load_sync(self) -> object:
        import torch  # noqa: PLC0415
        from diffusers import StableDiffusionPipeline  # noqa: PLC0415

        device = _resolve_device()
        dtype = torch.float16 if device == "cuda" else torch.float32
        self._log.info("loading Riffusion (device=%s dtype=%s)", device, dtype)
        pipe = StableDiffusionPipeline.from_pretrained(
            self.MODEL_ID, torch_dtype=dtype, safety_checker=None,
        )
        pipe.to(device)
        pipe.set_progress_bar_config(disable=True)
        self._device = device
        self._log.info("Riffusion ready")
        return pipe

    async def generate(
        self,
        prompt: str,
        *,
        duration_sec: float = 5.0,
        lyrics: str | None = None,  # accepted for API uniformity; ignored
        seed: int | None = None,
        output_format: str = "wav",
    ) -> bytes:
        _validate_duration(duration_sec, max_sec=self.MAX_DURATION_SEC, engine="riffusion")
        if not prompt or not isinstance(prompt, str):
            raise MusicGenError("riffusion: prompt must be a non-empty string")
        del lyrics  # no vocals
        await self.get_model()
        async with self._lock:
            audio_bytes = await asyncio.to_thread(
                self._generate_sync, prompt, duration_sec, seed, output_format,
            )
            self._touch()
            return audio_bytes

    def _generate_sync(
        self,
        prompt: str,
        duration_sec: float,
        seed: int | None,
        output_format: str,
    ) -> bytes:
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        gen = torch.Generator(device=self._device)
        if seed is not None:
            gen = gen.manual_seed(int(seed))

        try:
            result = self._model(
                prompt=prompt,
                height=self.IMAGE_HEIGHT,
                width=self.IMAGE_WIDTH,
                num_inference_steps=50,
                guidance_scale=7.0,
                generator=gen,
            )
        except Exception as exc:  # noqa: BLE001
            raise MusicGenError(f"riffusion inference failed: {exc}") from exc

        # result.images[0] is a PIL.Image (RGB spectrogram). Convert to mono
        # magnitude spectrogram then Griffin-Lim to audio.
        img = result.images[0]
        audio = self._spectrogram_image_to_audio(img)
        # Truncate to requested duration (the model emits ~5s; if the caller
        # asked for less, trim; if more, we still emit what the model gave).
        max_samples = int(self.SAMPLE_RATE * duration_sec)
        audio = audio[:max_samples]
        return _encode(np.asarray(audio, dtype=np.float32), self.SAMPLE_RATE, output_format)

    def _spectrogram_image_to_audio(self, img) -> "Any":
        """Convert a Riffusion RGB spectrogram image to a mono audio array.

        The Riffusion image encodes spectrogram magnitude in the red channel.
        We invert the trained mapping (db → linear amplitude) then Griffin-Lim
        for phase reconstruction."""
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415
        import torchaudio  # noqa: PLC0415

        arr = np.array(img).astype(np.float32)
        # Use the red channel; flip vertically (image origin is top, spectrogram
        # bins go bottom-up by convention).
        mag = arr[:, :, 0]
        mag = np.flip(mag, axis=0)
        # Riffusion's training mapping: image pixel 0-255 ↔ dB scale.
        # Reference scale: db_max=10 → loudest pixel = 0 dB, then attenuated.
        max_volume = 50.0
        power_for_image = 0.25
        data = mag / 255.0
        data = np.power(data, 1.0 / power_for_image)
        data = data * 10.0 ** (max_volume / 20.0)
        # Griffin-Lim for phase reconstruction. The image is 512 px tall, so
        # the spectrogram has 512 frequency bins. torch.istft (called inside
        # GriffinLim) requires n_fft//2 + 1 bins, so for n_fft=1024 we need
        # 513 bins — pad one row of zeros at the top (Nyquist bin = 0).
        mag_t = torch.tensor(data.copy())
        pad_rows = (self.N_FFT // 2 + 1) - mag_t.shape[0]
        if pad_rows > 0:
            mag_t = torch.nn.functional.pad(mag_t, (0, 0, 0, pad_rows))
        gl = torchaudio.transforms.GriffinLim(
            n_fft=self.N_FFT,
            hop_length=self.HOP_LENGTH,
            n_iter=32,
            power=1.0,
        )
        audio = gl(mag_t).numpy()
        return audio.astype(np.float32)

    def _release_model(self, model: Any) -> None:
        try:
            model.to("cpu")
        except Exception:  # noqa: BLE001
            pass
        del model


# ── AudioLDM 2 ──────────────────────────────────────────────────────────────


class AudioLDM2Engine(EngineBase):
    """AudioLDM 2 (cvssp/audioldm2). CC-BY 4.0 — commercial use OK, no opt-in
    gate. General-purpose text-to-audio: environmental ambience, animal
    sounds, mechanical SFX, foley, impacts. 16 kHz mono output. Slow
    inference (200-step DDIM by default) but solid prompt adherence via dual
    CLAP + Flan-T5 encoders.

    VRAM ~8-10 GB at fp16; CPU offload keeps it under 10 GB on a 12 GB GPU.
    Use ``num_waveforms_per_prompt > 1`` to auto-rank candidates by CLAP
    similarity at the cost of linear time/VRAM scaling."""

    SAMPLE_RATE = 16000
    MAX_DURATION_SEC = 30.0
    MODEL_ID = "cvssp/audioldm2"
    DEFAULT_NEGATIVE_PROMPT = "Low quality."

    def _load_sync(self) -> object:
        import torch  # noqa: PLC0415
        from diffusers import AudioLDM2Pipeline  # noqa: PLC0415

        device = _resolve_device()
        dtype = torch.float16 if device == "cuda" else torch.float32
        self._log.info("loading AudioLDM2 (device=%s dtype=%s)", device, dtype)
        pipe = AudioLDM2Pipeline.from_pretrained(self.MODEL_ID, torch_dtype=dtype)
        # CPU offload trims peak VRAM on 12 GB cards. On CPU-only this is a
        # no-op (and would error on .to("cuda") in the helper), so guard.
        if device == "cuda":
            try:
                pipe.enable_model_cpu_offload()
            except Exception:  # noqa: BLE001
                pipe.to(device)
        self._device = device
        self._log.info("AudioLDM2 ready")
        return pipe

    async def generate(
        self,
        prompt: str,
        *,
        duration_sec: float = 10.0,
        lyrics: str | None = None,  # accepted for API uniformity; ignored
        seed: int | None = None,
        num_inference_steps: int = 200,
        output_format: str = "wav",
    ) -> bytes:
        _validate_duration(duration_sec, max_sec=self.MAX_DURATION_SEC, engine="audioldm2")
        if not prompt or not isinstance(prompt, str):
            raise MusicGenError("audioldm2: prompt must be a non-empty string")
        del lyrics  # AudioLDM2 has no vocal stack
        await self.get_model()
        async with self._lock:
            audio_bytes = await asyncio.to_thread(
                self._generate_sync, prompt, duration_sec, seed,
                num_inference_steps, output_format,
            )
            self._touch()
            return audio_bytes

    def _generate_sync(
        self,
        prompt: str,
        duration_sec: float,
        seed: int | None,
        num_inference_steps: int,
        output_format: str,
    ) -> bytes:
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415

        # CPU offload moves submodules to CPU between calls; using a CUDA
        # generator can mismatch the active module's device. CPU generator is
        # safe in both offload + non-offload paths.
        gen = torch.Generator(device="cpu")
        if seed is not None:
            gen = gen.manual_seed(int(seed))
        try:
            result = self._model(
                prompt,
                negative_prompt=self.DEFAULT_NEGATIVE_PROMPT,
                num_inference_steps=num_inference_steps,
                audio_length_in_s=float(duration_sec),
                num_waveforms_per_prompt=1,
                generator=gen,
            )
        except Exception as exc:  # noqa: BLE001
            raise MusicGenError(f"audioldm2 inference failed: {exc}") from exc
        audio = result.audios[0] if hasattr(result, "audios") else result["audios"][0]
        if hasattr(audio, "cpu"):
            audio = audio.cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32)
        # AudioLDM2 returns shape (samples,) mono at 16kHz
        return _encode(audio, self.SAMPLE_RATE, output_format)

    def _release_model(self, model: Any) -> None:
        try:
            model.to("cpu")
        except Exception:  # noqa: BLE001
            pass
        del model
