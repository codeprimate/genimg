"""Wire defaults and labels for the Draw Things gRPC PoC (no scattered literals)."""

from __future__ import annotations

import importlib.resources as pkg_resources
from pathlib import Path

# --- Network ---
DEFAULT_DRAW_THINGS_HOST: str = "127.0.0.1"
DEFAULT_DRAW_THINGS_PORT: int = 7859

# gRPCio max message sizes (TS uses unbounded; use explicit large cap)
GRPC_MAX_SEND_MESSAGE_LENGTH: int = 256 * 1024 * 1024
GRPC_MAX_RECEIVE_MESSAGE_LENGTH: int = 256 * 1024 * 1024

# --- TLS ---
VENDOR_ROOT_CA_FILENAME: str = "draw_things_root_ca.pem"


def default_root_ca_pem_path() -> Path:
    """Path to the vendored Draw Things root CA (dt-grpc-ts)."""
    root = pkg_resources.files("genimg.contrib.draw_things_poc.vendor")
    return Path(str(root.joinpath(VENDOR_ROOT_CA_FILENAME)))


# --- FlatBuffers / txt2img defaults ---
LAYOUT_BLOCK_PX: int = 64
MIN_DIMENSION_PX: int = 64
SCALE_FACTOR_DEFAULT: int = 1
# dt-grpc-ts ``generateImage`` omits this field (false): chunked mode needs reassembly we do not implement.
DEFAULT_CHUNKED: bool = False
DEFAULT_STRENGTH: float = 1.0
DEFAULT_NEGATIVE_PROMPT: str = ""

# --- Draw Things response tensor header (imageHelpers.ts) ---
TENSOR_HEADER_BYTE_LEN: int = 68
TENSOR_HEADER_UINT32_COUNT: int = TENSOR_HEADER_BYTE_LEN // 4
# First uint32 marks fpzip-compressed payload when equal to this magic.
DRAW_THINGS_TENSOR_COMPRESSED_MAGIC: int = 1012247
# Uncompressed **request** tensors: dt-grpc-ts ``convertImageForRequest`` sets these six
# ``uint32`` values before height/width/channels (``imageHelpers.ts``).
TENSOR_REQUEST_HEADER_LE6: tuple[int, int, int, int, int, int] = (0, 1, 2, 131072, 0, 1)
# First five ``uint32`` values of ``convertImageToMask`` before H/W (``imageHelpers.ts``).
MASK_REQUEST_HEADER_U32_LE5: tuple[int, int, int, int, int] = (0, 1, 1, 4096, 0)
# Per ``convertImageToMask`` comments in ``imageHelpers.ts`` (mask byte per pixel after header).
DRAW_THINGS_MASK_RETAIN: int = 0
DRAW_THINGS_MASK_FULL_DENOISE: int = 1  # 100% strength
DRAW_THINGS_MASK_CFG_DENOISE: int = 2  # use ``GenerationConfiguration.strength``

# --- Debug ---
DEBUG_SAVE_RAW_TENSOR_BYTES: bool = False

# --- Errors (stable prefixes for tests) ---
ERR_PREFIX_API: str = "[draw_things]"
MSG_FPZIP_IMPORT: str = (
    f"{ERR_PREFIX_API} Compressed tensor requires the ``fpzip`` package. "
    "Install with: pip install 'genimg[draw-things]' (includes fpzip) or pip install fpzip."
)
MSG_FPZIP_DECOMPRESS_FAILED: str = (
    f"{ERR_PREFIX_API} fpzip decompression failed for compressed Draw Things tensor."
)
MSG_DECODE_FAILED: str = f"{ERR_PREFIX_API} Failed to decode Draw Things tensor to image."
MSG_PROVIDER_DECODE_NOT_IMPLEMENTED: str = (
    f"{ERR_PREFIX_API} Tensor decode not available; install draw-things extra and numpy."
)

# --- CLI ---
CLI_COMMAND_LIST_ASSETS: str = "list-assets"
CLI_COMMAND_LIST_SAMPLERS: str = "list-samplers"
CLI_COMMAND_GENERATE: str = "generate"

# Human-oriented ``list-assets`` section titles (what to pass where).
CLI_LIST_RULE: str = "=" * 64
CLI_LIST_BANNER: str = "Draw Things server catalog  ({host}:{port})"
CLI_LIST_FOOTER: str = "Use a checkpoint line verbatim as:  genimg-draw-things generate --model \"…\""
CLI_LIST_SECTION_MODELS: str = "CHECKPOINTS  (--model uses the file name below)"
CLI_LIST_SECTION_LORAS: str = "LORAS  (GenerationConfiguration.loras[].file in Draw Things)"
CLI_LIST_SECTION_CONTROL_NETS: str = "CONTROLNETS  (controls[].file)"
CLI_LIST_SECTION_TEXTUAL_INVERSIONS: str = "TEXTUAL INVERSIONS  (file on disk; keyword in prompts)"
CLI_LIST_SECTION_UPSCALERS: str = "UPSCALERS  (GenerationConfiguration.upscaler string)"
CLI_LIST_SECTION_SAMPLERS: str = (
    "SAMPLERS  (--sampler: FlatBuffers ``SamplerType`` name or integer wire value)"
)
CLI_LIST_SAMPLERS_FOOTER: str = 'Example:  genimg-draw-things generate ... --sampler EulerA'
CLI_LIST_EMPTY: str = "(none)"
