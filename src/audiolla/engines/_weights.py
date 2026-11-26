from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .. import config


def load_pretrained(loader: Callable[..., Any], model: str, **kwargs: Any) -> Any:
    if config.MODEL_DOWNLOAD:
        from huggingface_hub.errors import LocalEntryNotFoundError

        try:
            return loader(model, local_files_only=True, **kwargs)
        except (OSError, LocalEntryNotFoundError):
            pass  # The Hugging Face loader can fetch missing files on a cache miss.
    return loader(model, **kwargs)
