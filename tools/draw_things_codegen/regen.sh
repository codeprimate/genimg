#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENDOR="$ROOT/src/genimg/contrib/draw_things_poc/vendor"
OUT="$ROOT/src/genimg/contrib/draw_things_poc/generated"
mkdir -p "$OUT"
rm -f "$OUT"/*.py 2>/dev/null || true

FLATC="${FLATC:-flatc}"
if ! command -v "$FLATC" >/dev/null 2>&1; then
  echo "error: flatc not found; set FLATC=/path/to/flatc or install FlatBuffers compiler" >&2
  exit 1
fi

"$FLATC" --python -o "$OUT" "$VENDOR/config.fbs"

"$ROOT/.venv/bin/python" -m grpc_tools.protoc \
  -I"$VENDOR" \
  --python_out="$OUT" \
  --grpc_python_out="$OUT" \
  "$VENDOR/imageService.proto"

# grpc_tools emits a non-package import; fix for package-relative layout.
if [[ "$(uname -s)" == "Darwin" ]]; then
  sed -i '' 's/^import imageService_pb2/from . import imageService_pb2/' "$OUT/imageService_pb2_grpc.py"
else
  sed -i 's/^import imageService_pb2/from . import imageService_pb2/' "$OUT/imageService_pb2_grpc.py"
fi

touch "$OUT/__init__.py"

echo "Generated into $OUT"
