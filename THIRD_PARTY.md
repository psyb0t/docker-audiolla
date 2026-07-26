# Third-party components

audiolla's own source is [WTFPL](LICENSE). The **published Docker image**
additionally installs the third-party components below, some of which are
copyleft. This file exists so anyone consuming the image (not just the
source repo) can see what's bundled and under what terms.

| Component | Kind | License | Source | Where it lives | Note |
|---|---|---|---|---|---|
| [matchering](https://github.com/sergree/matchering) | Python package | GPL-3.0 | https://github.com/sergree/matchering | installed into the published Docker image | corresponding source at the URL |
| [pedalboard](https://github.com/spotify/pedalboard) | Python package | GPL-3.0 | https://github.com/spotify/pedalboard | installed into the published Docker image | corresponding source at the URL |
| [mutagen](https://github.com/quodlibet/mutagen) | Python package | GPL-2.0-or-later | https://github.com/quodlibet/mutagen | installed into the published Docker image | corresponding source at the URL |
| sox | apt package | GPL-2.0+ | https://sox.sourceforge.net | installed into the published Docker image | corresponding source at the URL |
| ffmpeg | apt package | GPL/LGPL | https://ffmpeg.org | installed into the published Docker image | corresponding source at the URL |
| fluidsynth | apt package | LGPL-2.1+ | https://www.fluidsynth.org | installed into the published Docker image | corresponding source at the URL |

Local copies of the GPL license texts referenced above are in
[`LICENSES/GPL-3.0.txt`](LICENSES/GPL-3.0.txt) and
[`LICENSES/GPL-2.0.txt`](LICENSES/GPL-2.0.txt).

Runtime AI models (MusicGen, etc.) are **optional downloads** pulled at
runtime under their own terms (some are CC-BY-NC) and are **not
distributed by this repo** — see the [README License section](README.md#license)
and the model table for per-model licensing.
