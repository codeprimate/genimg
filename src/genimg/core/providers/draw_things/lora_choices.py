"""LoRA parsing, display labels, and Draw Things catalog fetch helpers."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

from genimg.core.config import Config
from genimg.core.providers.draw_things.client import DrawThingsClient
from genimg.core.providers.draw_things.constants import ECHO_RPC_TIMEOUT_SECONDS
from genimg.core.providers.draw_things.types import LoraInfo, ModelInfo
from genimg.logging_config import get_logger
from genimg.utils.exceptions import NetworkError

logger = get_logger(__name__)

DEFAULT_LORA_WEIGHT: float = 0.8
# Draw Things may answer Echo before MetadataOverride is populated; retry briefly on one channel.
_LORA_FETCH_ATTEMPTS: int = 4
_LORA_FETCH_RETRY_DELAY_S: float = 0.15
_LORA_CHANNEL_READY_TIMEOUT_S: float = 3.0


@dataclass(frozen=True)
class DrawThingsCatalogResult:
    """Outcome of a Draw Things ``Echo`` catalog probe (checkpoints + LoRAs)."""

    models: tuple[ModelInfo, ...]
    loras: tuple[LoraInfo, ...]
    reachable: bool
    catalog_published: bool


@dataclass(frozen=True)
class LoraCatalogResult:
    """Outcome of a Draw Things ``Echo`` catalog probe."""

    loras: tuple[LoraInfo, ...]
    reachable: bool
    catalog_published: bool


def model_display_label(model: ModelInfo) -> str:
    """Human label for a catalog checkpoint (``file — name`` when name differs)."""
    f = model.file.strip()
    if not f:
        return ""
    n = model.name.strip()
    if n and n != f:
        return f"{f}  —  {n}"
    return f


def model_dropdown_choices(models: tuple[ModelInfo, ...]) -> list[tuple[str, str]]:
    """Return ``(checkpoint_filename, display_label)`` sorted case-insensitively."""
    pairs: list[tuple[str, str]] = []
    for model in models:
        f = model.file.strip()
        if not f:
            continue
        label = model_display_label(model)
        pairs.append((f, label or f))
    pairs.sort(key=lambda p: p[1].lower())
    return pairs


def merge_checkpoint_filenames(
    *sources: Sequence[str],
) -> list[str]:
    """Dedupe checkpoint filenames; preserve first-seen order across sources."""
    out: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for item in source:
            f = (item or "").strip()
            if not f or f in seen:
                continue
            seen.add(f)
            out.append(f)
    return out


def model_catalog_hint(result: DrawThingsCatalogResult, *, host: str, port: int) -> str:
    """User-facing hint when the checkpoint dropdown would be empty."""
    if result.models:
        return ""
    if not result.reachable:
        return (
            f"Could not reach Draw Things gRPC at {host}:{port}. "
            "Start Draw Things with API Server enabled, or type a checkpoint filename."
        )
    if not result.catalog_published:
        return (
            "Draw Things is reachable but did not publish a model catalog "
            "(Echo returned no MetadataOverride). In Draw Things → Advanced Settings, "
            "enable **Enable Model Browser**, restart the gRPC API server, then switch provider again."
        )
    return (
        "Draw Things published a catalog but listed no checkpoints. "
        "Import models in the app, or type a .ckpt filename."
    )


def lora_catalog_hint(result: LoraCatalogResult, *, host: str, port: int) -> str:
    """User-facing hint when the LoRA dropdown would be empty."""
    if result.loras:
        return ""
    if not result.reachable:
        return (
            f"Could not reach Draw Things gRPC at {host}:{port}. "
            "Start Draw Things with API Server enabled, or type a checkpoint filename below."
        )
    if not result.catalog_published:
        return (
            "Draw Things is reachable but did not publish a model catalog "
            "(Echo returned no MetadataOverride). In Draw Things → Advanced Settings, "
            "enable **Enable Model Browser**, restart the gRPC API server, then reload."
        )
    return (
        "Draw Things published a catalog but listed no LoRAs. "
        "Import LoRAs in the app (Settings → Model → Manage), or type a filename below."
    )


def parse_lora_spec(spec: str) -> tuple[str, float]:
    """Parse ``file.ckpt`` or ``file.ckpt:0.75`` (weight defaults to 0.8)."""
    s = spec.strip()
    if not s:
        raise ValueError("empty LoRA spec")
    if ":" in s:
        path, w = s.rsplit(":", 1)
        path = path.strip()
        if not path:
            raise ValueError(f"invalid LoRA spec: {spec!r}")
        return path, float(w.strip())
    return s, DEFAULT_LORA_WEIGHT


def parse_lora_stack(specs: Sequence[str]) -> tuple[tuple[str, float], ...]:
    """Parse repeatable CLI inputs; preserve order, skip empty, dedupe by file (first wins)."""
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    for spec in specs:
        if not (spec or "").strip():
            continue
        file_name, weight = parse_lora_spec(spec)
        if file_name in seen:
            continue
        seen.add(file_name)
        out.append((file_name, weight))
    return tuple(out)


def lora_display_label(lora: LoraInfo) -> str:
    """Human label for a catalog LoRA (``file — name`` when name differs)."""
    f = lora.file.strip()
    if not f:
        return ""
    n = lora.name.strip()
    if n and n != f:
        return f"{f}  —  {n}"
    return f


def lora_dropdown_choices(loras: tuple[LoraInfo, ...]) -> list[tuple[str, str]]:
    """Return ``(checkpoint_filename, display_label)`` sorted case-insensitively."""
    pairs: list[tuple[str, str]] = []
    for lora in loras:
        f = lora.file.strip()
        if not f:
            continue
        label = lora_display_label(lora)
        pairs.append((f, label or f))
    pairs.sort(key=lambda p: p[1].lower())
    return pairs


def _draw_things_client_from_config(config: Config) -> DrawThingsClient:
    return DrawThingsClient(
        host=config.draw_things_host,
        port=config.draw_things_port,
        root_ca_pem_path=config.draw_things_root_ca_pem_path,
        use_tls=config.draw_things_use_tls,
        insecure=config.draw_things_insecure,
        shared_secret=config.draw_things_shared_secret,
    )


def fetch_draw_things_catalog(config: Config) -> DrawThingsCatalogResult:
    """Fetch checkpoints and LoRAs from Draw Things ``Echo`` in one probe."""
    target = f"{config.draw_things_host}:{config.draw_things_port}"
    logger.debug("Draw Things catalog fetch start target=%s attempts=%d", target, _LORA_FETCH_ATTEMPTS)
    t0 = time.monotonic()
    catalog_published = False
    try:
        with _draw_things_client_from_config(config) as client:
            logger.debug("Draw Things catalog fetch opening channel to %s", target)
            client.wait_for_ready(timeout_seconds=_LORA_CHANNEL_READY_TIMEOUT_S)
            logger.debug(
                "Draw Things catalog channel ready (%.0fms)", (time.monotonic() - t0) * 1000
            )
            for attempt in range(_LORA_FETCH_ATTEMPTS):
                if attempt > 0:
                    time.sleep(_LORA_FETCH_RETRY_DELAY_S)
                attempt_t0 = time.monotonic()
                logger.debug(
                    "Draw Things catalog Echo attempt %d/%d", attempt + 1, _LORA_FETCH_ATTEMPTS
                )
                loras, had_override = client.echo_catalog_loras(
                    timeout_seconds=ECHO_RPC_TIMEOUT_SECONDS
                )
                cached = getattr(client, "_catalog_cache", None)
                models = cached.models if cached is not None else ()
                if had_override:
                    catalog_published = True
                logger.debug(
                    "Draw Things catalog attempt %d done in %.0fms: models=%d loras=%d had_override=%s",
                    attempt + 1,
                    (time.monotonic() - attempt_t0) * 1000,
                    len(models),
                    len(loras),
                    had_override,
                )
                if models or loras:
                    logger.debug(
                        "Draw Things catalog fetch complete in %.0fms",
                        (time.monotonic() - t0) * 1000,
                    )
                    return DrawThingsCatalogResult(
                        models=models,
                        loras=loras,
                        reachable=True,
                        catalog_published=True,
                    )
                if had_override:
                    logger.debug(
                        "Draw Things catalog fetch complete in %.0fms (empty catalog)",
                        (time.monotonic() - t0) * 1000,
                    )
                    return DrawThingsCatalogResult(
                        models=(),
                        loras=(),
                        reachable=True,
                        catalog_published=True,
                    )
    except (NetworkError, OSError) as e:
        logger.warning("Could not fetch Draw Things catalog: %s", e)
        return DrawThingsCatalogResult(
            models=(), loras=(), reachable=False, catalog_published=False
        )
    except Exception as e:
        logger.warning("Could not fetch Draw Things catalog: %s", e)
        return DrawThingsCatalogResult(
            models=(), loras=(), reachable=False, catalog_published=False
        )

    logger.debug(
        "Draw Things catalog fetch gave up after %d attempts (%.0fms total); catalog_published=%s",
        _LORA_FETCH_ATTEMPTS,
        (time.monotonic() - t0) * 1000,
        catalog_published,
    )
    return DrawThingsCatalogResult(
        models=(),
        loras=(),
        reachable=True,
        catalog_published=catalog_published,
    )


def fetch_lora_catalog(config: Config) -> LoraCatalogResult:
    """Fetch LoRAs from Draw Things ``Echo``; distinguish unreachable vs unpublished catalog."""
    full = fetch_draw_things_catalog(config)
    return LoraCatalogResult(
        loras=full.loras,
        reachable=full.reachable,
        catalog_published=full.catalog_published,
    )


def fetch_loras(config: Config) -> tuple[LoraInfo, ...]:
    """Fetch LoRAs from Draw Things ``Echo`` on a single channel with brief retries."""
    return fetch_lora_catalog(config).loras


def fetch_lora_choices(config: Config) -> list[tuple[str, str]]:
    """Fetch LoRA dropdown choices; on failure log warning and return ``[]``."""
    logger.debug("fetch_lora_choices called")
    return lora_dropdown_choices(fetch_lora_catalog(config).loras)
