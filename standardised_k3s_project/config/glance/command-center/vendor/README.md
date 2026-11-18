# Vendored front-end libraries

`model-viewer.min.js`: Google model-viewer 4.4.0 (Apache-2.0, see `model-viewer.LICENSE`), from the npm tarball
`@google/model-viewer@4.4.0` (registry integrity checked). sha256 of the file: `18b2e711035aa4705ee281530a55dc2338ff05eed3d70ae16d54105282a75ed5`.
Used only by `../viewer.html` to show GLB/glTF job outputs. Served from this folder, never from a CDN. Draco/KTX2-compressed models
would fetch their decoders from Google's CDN by default; Blender/Unreal exports from the workers are uncompressed.
