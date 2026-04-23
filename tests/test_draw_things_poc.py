"""Tests for Draw Things gRPC PoC (no live server)."""

from __future__ import annotations

import json
import struct
import sys
import types

import numpy as np
import pytest

pytest.importorskip("grpc")
pytest.importorskip("flatbuffers")

from genimg.contrib.draw_things_poc import (
    DrawThingsClient,
    DrawThingsPoCProvider,
    decode_metadata_override,
)
from genimg.contrib.draw_things_poc.catalog import empty_zoo_catalog
from genimg.contrib.draw_things_poc.config_builder import (
    build_txt2img_configuration_bytes,
    pixels_to_start_blocks,
    resolve_seed,
    round_dimension_to_multiple_of_64,
)
from genimg.contrib.draw_things_poc.constants import (
    CLI_LIST_SECTION_MODELS,
    DRAW_THINGS_TENSOR_COMPRESSED_MAGIC,
    MSG_FPZIP_DECOMPRESS_FAILED,
)
from genimg.contrib.draw_things_poc.generated import imageService_pb2 as pb2
from genimg.contrib.draw_things_poc.generated.GenerationConfiguration import GenerationConfiguration
from genimg.contrib.draw_things_poc.tensor_image import dt_tensor_bytes_to_pil
from genimg.core.config import Config
from genimg.utils.exceptions import APIError


def _synthetic_tensor_1x1_rgb() -> bytes:
    """Minimal uncompressed Draw Things tensor (1x1 RGB float16, header per imageHelpers.ts)."""
    hdr = [0] * 17
    hdr[6] = 1  # height
    hdr[7] = 1  # width
    hdr[8] = 3  # channels
    header = struct.pack("<" + "I" * 17, *hdr)
    f16 = np.array([1.0, 1.0, 1.0], dtype="<f2").tobytes()
    return header + f16


def test_round_dimension_to_multiple_of_64() -> None:
    assert round_dimension_to_multiple_of_64(100) == 128
    assert round_dimension_to_multiple_of_64(64) == 64
    assert pixels_to_start_blocks(100) == 2


def test_resolve_seed_random_when_negative() -> None:
    a = resolve_seed(-1)
    b = resolve_seed(-1)
    assert 0 <= a < 2**32 and 0 <= b < 2**32


def test_build_txt2img_configuration_roundtrip() -> None:
    raw = build_txt2img_configuration_bytes(
        model="test.ckpt",
        width_px=512,
        height_px=512,
        steps=10,
        guidance_scale=5.5,
        seed=42,
        request_id=7,
    )
    cfg = GenerationConfiguration.GetRootAs(raw, 0)
    model = cfg.Model()
    assert (model.decode("utf-8") if isinstance(model, (bytes, bytearray)) else model) == "test.ckpt"
    assert cfg.Steps() == 10
    assert cfg.GuidanceScale() == pytest.approx(5.5)
    assert cfg.StartWidth() == 8  # 512 / 64
    assert cfg.StartHeight() == 8


def test_decode_metadata_override_models() -> None:
    o = pb2.MetadataOverride()
    o.models = json.dumps([{"file": "a.ckpt", "name": "A", "extra": 1}]).encode("utf-8")
    cat = decode_metadata_override(o)
    assert len(cat.models) == 1
    assert cat.models[0].file == "a.ckpt"
    assert cat.models[0].name == "A"
    assert cat.models[0].extras == {"extra": 1}


def test_empty_zoo_catalog() -> None:
    cat = empty_zoo_catalog()
    assert cat.models == () and cat.loras == ()


def test_dt_tensor_decode_1x1() -> None:
    img = dt_tensor_bytes_to_pil(_synthetic_tensor_1x1_rgb())
    assert img.size == (1, 1)
    assert img.getpixel((0, 0)) == (254, 254, 254)


def test_dt_tensor_compressed_fpzip_fails_on_garbage() -> None:
    pytest.importorskip("fpzip")
    hdr = [DRAW_THINGS_TENSOR_COMPRESSED_MAGIC] + [0] * 5 + [2, 2, 3] + [0] * 8
    bad = struct.pack("<" + "I" * 17, *hdr) + b"not-valid-fpzip-payload"
    with pytest.raises(APIError) as excinfo:
        dt_tensor_bytes_to_pil(bad)
    assert MSG_FPZIP_DECOMPRESS_FAILED in str(excinfo.value)


def test_dt_tensor_compressed_with_mock_fpzip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.SimpleNamespace(
        decompress=lambda _b: np.zeros((1, 2, 2, 3), dtype=np.float32),
    )
    monkeypatch.setitem(sys.modules, "fpzip", fake)
    hdr = [DRAW_THINGS_TENSOR_COMPRESSED_MAGIC] + [0] * 5 + [2, 2, 3] + [0] * 8
    blob = struct.pack("<" + "I" * 17, *hdr) + b"ignored"
    img = dt_tensor_bytes_to_pil(blob)
    assert img.size == (2, 2)


class _FakeStub:
    def Echo(self, request: pb2.EchoRequest, timeout: float | None = None) -> pb2.EchoReply:
        o = pb2.MetadataOverride()
        o.models = json.dumps([{"file": "m.ckpt", "name": "M"}]).encode("utf-8")
        r = pb2.EchoReply()
        r.override.CopyFrom(o)
        return r

    def GenerateImage(
        self,
        request: pb2.ImageGenerationRequest,
        timeout: float | None = None,
    ):
        tensor = _synthetic_tensor_1x1_rgb()
        yield pb2.ImageGenerationResponse(generatedImages=[tensor])


def test_client_catalog_with_injected_stub() -> None:
    c = DrawThingsClient(host="127.0.0.1", port=7859, insecure=True, grpc_stub=_FakeStub())
    c.clear_catalog_cache()
    models = c.list_models()
    assert len(models) == 1 and models[0].file == "m.ckpt"


def test_client_generate_last_tensor() -> None:
    c = DrawThingsClient(host="127.0.0.1", port=7859, insecure=True, grpc_stub=_FakeStub())
    raw = c.generate_image_last_tensor(
        prompt="hi",
        model="m.ckpt",
        width_px=64,
        height_px=64,
        steps=1,
        guidance_scale=1.0,
        seed=1,
        timeout_seconds=5.0,
    )
    assert len(raw) > 68


def test_provider_generate() -> None:
    cfg = Config()
    prov = DrawThingsPoCProvider(
        insecure=True,
        width_px=64,
        height_px=64,
        steps=1,
        guidance_scale=1.0,
        grpc_stub=_FakeStub(),
    )
    res = prov.generate("p", "m.ckpt", None, 30, cfg, None)
    assert res.image.size == (1, 1)


def test_cli_list_assets_human_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    import genimg.contrib.draw_things_poc.cli as cli_mod

    class _C(DrawThingsClient):
        def __init__(self, **kwargs: object) -> None:
            kwargs = dict(kwargs)
            kwargs["grpc_stub"] = _FakeStub()
            super().__init__(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cli_mod, "DrawThingsClient", _C)
    from genimg.contrib.draw_things_poc.cli import list_assets

    runner = CliRunner()
    result = runner.invoke(list_assets, ["--insecure", "--kind", "models"])
    assert result.exit_code == 0
    out = result.output
    assert CLI_LIST_SECTION_MODELS in out
    assert "m.ckpt" in out
    assert "M" in out


def test_cli_list_assets_json_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    import genimg.contrib.draw_things_poc.cli as cli_mod

    class _C(DrawThingsClient):
        def __init__(self, **kwargs: object) -> None:
            kwargs = dict(kwargs)
            kwargs["grpc_stub"] = _FakeStub()
            super().__init__(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cli_mod, "DrawThingsClient", _C)
    from genimg.contrib.draw_things_poc.cli import list_assets

    runner = CliRunner()
    result = runner.invoke(list_assets, ["--insecure", "--kind", "models", "--json"])
    assert result.exit_code == 0
    line = result.output.strip().splitlines()[0]
    data = json.loads(line)
    assert data["kind"] == "models"
    assert data["items"][0]["file"] == "m.ckpt"
