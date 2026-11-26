---
title: "Separation and restoration"
description: "Split stems with Demucs or UVR, remix them, split harmonic from percussive, and remove reverb, echo, noise, clipping and mains hum."
nav_order: 6
---

# Separation and restoration

Use separation to isolate parts of a mix. Use restoration to clean up the recording itself. See [Engines](engines.md) for model availability and [Async jobs](jobs.md) for long requests.

## Split stems

Ask for one stem to get an audio file. Asking for several stems or leaving the selection empty produces a ZIP. Demucs uses lowercase stem names such as `vocals`. The UVR vocal and karaoke models use `Vocals` and `Instrumental`. These names are case-sensitive. Demucs weights for enabled variants download at startup.

API reference: [Separate stems](/reference/separate/).

## Remix stems

Separate and mix again in one request. In `stem_mix`, zero mutes, values above zero through one are linear gain, and negative values or values above one are dB. Omitted stems keep their original level.

API reference: [Remix stems](/reference/remix/).

## Harmonic/percussive split

Separate tonal sound from transients without downloading a model. The result is a ZIP with both stems.

API reference: [Split harmonic and percussive audio](/reference/hpss/).

## De-reverb, de-echo, de-noise

Pick the UVR restoration engine for the problem you hear. The aggressive model option applies to `uvr-deecho`.

API reference: [Restore a recording](/reference/restore/).

## Noise reduction

Use stationary reduction for a steady noise floor. Use adaptive reduction or a UVR model when the noise changes over time.

API reference: [Reduce noise](/reference/noise-reduce/).

## Repair

Use declipping for distorted peaks and dehum for a steady mains tone. Match the hum setting to the source, typically 50 Hz or 60 Hz.

API reference: [Repair audio](/reference/repair/).
