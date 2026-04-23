# Draw Things PoC — code generation

Regenerates Python gRPC stubs and FlatBuffers bindings from vendored sources:

- `src/genimg/contrib/draw_things_poc/vendor/imageService.proto`
- `src/genimg/contrib/draw_things_poc/vendor/config.fbs`

## Prerequisites

```bash
.venv/bin/pip install 'grpcio-tools>=1.80' 'protobuf>=6.31' flatbuffers
```

Checked-in `*_pb2*.py` targets **protobuf 6.31+** (`google.protobuf.runtime_version`) and **grpcio 1.80+**. If you `pip install genimg[draw-things]`, those pins are applied automatically.

## Regenerate

From repo root:

```bash
./tools/draw_things_codegen/regen.sh
```

Requires `protoc` on `PATH` **or** only `grpc_tools.protoc` (script uses Python grpc_tools for proto; FlatBuffers needs the `flatc` binary).
