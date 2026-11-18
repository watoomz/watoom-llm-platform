#!/usr/bin/env bash
# Install the pinned headless asset-pipeline tools under /data/ai/toolchains/pipeline-tools.
# Idempotent: an existing version directory is left alone. No npm install scripts run.
#   gltfpack 1.3          meshoptimizer LOD/simplify/compress (MIT), release digest verified
#   gltf-transform 4.5.1  GLB inspect/validate (Khronos validator)/optimize (MIT), npm lockfile
#   blender-asset-tracer  .blend dependency list/pack (GPL), Blender 5.2 Python 3.13, locked
#   gdtoolkit 4.5.0       GDScript gdlint/gdformat (MIT), locked
set -Eeuo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
T=/data/ai/toolchains/pipeline-tools
BLENDER=/data/ai/toolchains/blender/5.2.3/blender-5.2.3-linux-x64
mkdir -p "$T/bin"

if [[ ! -x $T/gltfpack/1.3/gltfpack ]]; then
  mkdir -p "$T/gltfpack/1.3"; cd "$T/gltfpack/1.3"
  curl -sfL -o gltfpack-ubuntu.zip https://github.com/zeux/meshoptimizer/releases/download/v1.3/gltfpack-ubuntu.zip
  echo "0666d9dc40d60fe5b9a45f3fc24f8e6ca87112974bd5de9ca57152aa13d06017  gltfpack-ubuntu.zip" | sha256sum -c -
  python3 -c "import zipfile;zipfile.ZipFile('gltfpack-ubuntu.zip').extractall('.')"; chmod 755 gltfpack
fi

if [[ ! -x $T/gltf-transform/4.5.1/node_modules/.bin/gltf-transform ]]; then
  mkdir -p "$T/gltf-transform/4.5.1"
  cp "$HERE/gltf-transform.package.json" "$T/gltf-transform/4.5.1/package.json"
  cp "$HERE/gltf-transform.package-lock.json" "$T/gltf-transform/4.5.1/package-lock.json"
  npm ci --silent --prefix "$T/gltf-transform/4.5.1" --ignore-scripts --no-fund --no-audit
fi

if [[ ! -x $T/blender-asset-tracer/2.2.1/bin/bat ]]; then
  "$BLENDER/5.2/python/bin/python3.13" -m venv "$T/blender-asset-tracer/2.2.1"
  "$T/blender-asset-tracer/2.2.1/bin/pip" install -q -r "$HERE/blender-asset-tracer.lock"
fi

if [[ ! -x $T/gdtoolkit/4.5.0/bin/gdlint ]]; then
  python3 -m venv "$T/gdtoolkit/4.5.0"
  "$T/gdtoolkit/4.5.0/bin/pip" install -q -r "$HERE/gdtoolkit.lock"
fi

wrap(){ printf '#!/bin/sh\n# Pinned pipeline tool wrapper; see %s/MANIFEST.json\n%s\n' "$T" "$2" > "$T/bin/$1"; chmod 755 "$T/bin/$1"; }
wrap bat "BAT_BLENDER=$BLENDER/blender exec $T/blender-asset-tracer/2.2.1/bin/bat \"\$@\""
wrap gltfpack "exec $T/gltfpack/1.3/gltfpack \"\$@\""
wrap gltf-transform "exec $T/gltf-transform/4.5.1/node_modules/.bin/gltf-transform \"\$@\""
wrap gdlint "exec $T/gdtoolkit/4.5.0/bin/gdlint \"\$@\""
wrap gdformat "exec $T/gdtoolkit/4.5.0/bin/gdformat \"\$@\""
cp "$HERE/MANIFEST.json" "$T/MANIFEST.json"
# Check the usage text: gltfpack has no --version and exits 1 for -h.
for t in bat gltfpack gltf-transform gdlint gdformat; do
  usage=$("$T/bin/$t" -h 2>&1 || true)
  grep -qi usage <<<"$usage" || { echo "FAIL $t"; exit 1; }
done
echo "PASS pipeline tools in $T/bin"
