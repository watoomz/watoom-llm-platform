#!/usr/bin/env python3
"""watoom-terrain-map: lat/long -> real-world Godot terrain.

Fetches open elevation (AWS terrarium tiles, SRTM/Copernicus-based factual DEM),
builds a float-EXR heightmap for a square region, and emits a ready-to-use Godot
terrain (heightmap.exr + meta.json + terrain.gd + terrain_material.gdshader +
<name>.tscn) into a project directory. No Google / proprietary map data is used,
and no roads/buildings are added -- only the landform.

Example:
  build_terrain.py --lat -27.3981546 --lon 152.9481812 \
      --size 4000 --out /data/ai/projects/games/<proj>/World/terrain

Deps (host-side): numpy, pillow. Run on the homelab host, not inside the app
container; the output is plain files a Godot project loads.
"""
import argparse, json, math, os, shutil, sys, urllib.request

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q="


def geocode(place):
    """Resolve a place name to (lat, lon) via OpenStreetMap Nominatim (open)."""
    import json as _json
    import urllib.parse
    url = GEOCODE_URL + urllib.parse.quote(place)
    req = urllib.request.Request(url, headers={"User-Agent": "watoom-terrain-map/1.0 (homelab)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        hits = _json.loads(r.read())
    if not hits:
        raise SystemExit(f"[terrain] no geocoding match for place: {place!r}")
    h = hits[0]
    print(f"[terrain] '{place}' -> {h.get('display_name', '')[:70]}  "
          f"({float(h['lat']):.5f}, {float(h['lon']):.5f})")
    return float(h["lat"]), float(h["lon"])


def merc_global_px(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n * 256.0
    lr = math.radians(lat)
    y = (1 - math.asinh(math.tan(lr)) / math.pi) / 2 * n * 256.0
    return x, y


def fetch_tile(z, tx, ty, cache):
    fp = os.path.join(cache, f"{z}_{tx}_{ty}.png")
    if not os.path.exists(fp):
        url = TILE_URL.format(z=z, x=tx, y=ty)
        req = urllib.request.Request(url, headers={"User-Agent": "watoom-terrain/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            open(fp, "wb").write(r.read())
    return fp


def save_exr_r_float(path, arr):
    """Write a single-channel ('R') 32-bit-float, uncompressed, scanline EXR.

    arr: 2D float32 (H, W), row 0 = top. Godot's Image.load() reads this as
    FORMAT_RF at full precision (unlike a 16-bit PNG, which it quantizes to 8-bit
    and terraces gentle slopes). Self-contained -- no OpenEXR/Pillow-EXR dependency.
    """
    import struct
    import numpy as _np
    arr = _np.ascontiguousarray(arr.astype('<f4'))
    H, W = arr.shape

    def attr(name, typ, payload):
        return name.encode() + b'\x00' + typ.encode() + b'\x00' + struct.pack('<I', len(payload)) + payload

    chan = b'R\x00' + struct.pack('<i', 2) + struct.pack('<B', 0) + b'\x00\x00\x00' \
        + struct.pack('<i', 1) + struct.pack('<i', 1)          # name, FLOAT, pLinear+pad, xSamp, ySamp
    header = b''
    header += attr('channels', 'chlist', chan + b'\x00')
    header += attr('compression', 'compression', struct.pack('<B', 0))     # NO_COMPRESSION
    header += attr('dataWindow', 'box2i', struct.pack('<4i', 0, 0, W - 1, H - 1))
    header += attr('displayWindow', 'box2i', struct.pack('<4i', 0, 0, W - 1, H - 1))
    header += attr('lineOrder', 'lineOrder', struct.pack('<B', 0))         # INCREASING_Y
    header += attr('pixelAspectRatio', 'float', struct.pack('<f', 1.0))
    header += attr('screenWindowCenter', 'v2f', struct.pack('<2f', 0.0, 0.0))
    header += attr('screenWindowWidth', 'float', struct.pack('<f', 1.0))
    header += b'\x00'
    magic = struct.pack('<I', 20000630) + struct.pack('<I', 2)             # magic, version 2
    row_bytes = W * 4
    block_size = 4 + 4 + row_bytes
    off_table = len(magic) + len(header) + 8 * H
    offsets = b''.join(struct.pack('<Q', off_table + i * block_size) for i in range(H))
    blocks = b''.join(struct.pack('<i', y) + struct.pack('<I', row_bytes) + arr[y].tobytes() for y in range(H))
    with open(path, 'wb') as f:
        f.write(magic)
        f.write(header)
        f.write(offsets)
        f.write(blocks)


def res_path_for(abs_dir):
    """Return (res://<rel>, project_root) if abs_dir is inside a Godot project."""
    p = os.path.abspath(abs_dir)
    cur = p
    while True:
        if os.path.exists(os.path.join(cur, "project.godot")):
            rel = os.path.relpath(p, cur).replace(os.sep, "/")
            return "res://" + rel, cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None, None
        cur = parent


def build(args):
    import numpy as np
    from PIL import Image

    # Keep the tile cache OUT of the project tree (Godot would try to import the
    # cached PNG tiles otherwise).
    cache = args.cache or os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
        "watoom-terrain-tiles")
    os.makedirs(cache, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    half = args.size / 2.0
    dlat = half / 111320.0
    dlon = half / (111320.0 * math.cos(math.radians(args.lat)))
    lat_n, lat_s = args.lat + dlat, args.lat - dlat
    lon_w, lon_e = args.lon - dlon, args.lon + dlon

    xw, yn = merc_global_px(lat_n, lon_w, args.zoom)
    xe, ys = merc_global_px(lat_s, lon_e, args.zoom)
    px0, px1 = int(math.floor(min(xw, xe))), int(math.ceil(max(xw, xe)))
    py0, py1 = int(math.floor(min(yn, ys))), int(math.ceil(max(yn, ys)))
    tx0, tx1 = px0 // 256, px1 // 256
    ty0, ty1 = py0 // 256, py1 // 256
    ntiles = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    print(f"[terrain] region lat[{lat_s:.5f},{lat_n:.5f}] lon[{lon_w:.5f},{lon_e:.5f}]  "
          f"z{args.zoom} tiles {tx0}-{tx1} x {ty0}-{ty1} ({ntiles})")
    if ntiles > args.max_tiles:
        sys.exit(f"[terrain] {ntiles} tiles exceeds --max-tiles {args.max_tiles}; "
                 f"lower --size or --zoom.")

    W = (tx1 - tx0 + 1) * 256
    H = (ty1 - ty0 + 1) * 256
    elev = np.zeros((H, W), dtype=np.float64)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            fp = fetch_tile(args.zoom, tx, ty, cache)
            t = np.asarray(Image.open(fp).convert("RGB"), dtype=np.float64)
            dec = t[:, :, 0] * 256.0 + t[:, :, 1] + t[:, :, 2] / 256.0 - 32768.0
            elev[(ty - ty0) * 256:(ty - ty0 + 1) * 256,
                 (tx - tx0) * 256:(tx - tx0 + 1) * 256] = dec
    ox, oy = tx0 * 256, ty0 * 256

    g = args.grid
    lats = np.linspace(lat_n, lat_s, g)
    lons = np.linspace(lon_w, lon_e, g)
    npix = 2 ** args.zoom * 256.0
    gx_all = (lons + 180.0) / 360.0 * npix - ox
    grid = np.zeros((g, g), dtype=np.float64)
    for i, la in enumerate(lats):
        gy = (1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * npix - oy
        x0 = np.clip(gx_all.astype(int), 0, W - 2)
        y0 = int(np.clip(gy, 0, H - 2))
        dx = np.clip(gx_all - x0, 0, 1)
        dy = float(np.clip(gy - y0, 0, 1))
        top = elev[y0, x0] * (1 - dx) + elev[y0, x0 + 1] * dx
        bot = elev[y0 + 1, x0] * (1 - dx) + elev[y0 + 1, x0 + 1] * dx
        grid[i] = top * (1 - dy) + bot * dy

    hmin, hmax = float(grid.min()), float(grid.max())
    print(f"[terrain] elevation {hmin:.1f}..{hmax:.1f} m  relief {hmax - hmin:.1f} m  "
          f"spacing {args.size / (g - 1):.1f} m/sample")
    norm = (grid - hmin) / max(1e-6, (hmax - hmin))
    # Authoritative heightmap: single-channel float EXR. Godot's Image.load() reads
    # it as FORMAT_RF at full precision; a 16-bit PNG would be quantized to 8-bit on
    # load (~256 steps) and terrace gentle slopes. PNG stays as a human preview only.
    save_exr_r_float(os.path.join(args.out, "heightmap.exr"), norm.astype(np.float32))
    Image.fromarray((norm * 255.0).astype(np.uint8)).save(os.path.join(args.out, "heightmap_preview.png"))

    # copy generic Godot assets
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
    for f in ("terrain.gd", "terrain_material.gdshader"):
        shutil.copyfile(os.path.join(tpl, f), os.path.join(args.out, f))

    meta = {
        "source": "AWS open terrain tiles (terrarium; SRTM/Copernicus-based open DEM)",
        "note": "Factual open elevation only -- no Google/proprietary map data, no roads/buildings.",
        "center_lat": args.lat, "center_lon": args.lon, "zoom": args.zoom,
        "size_m": args.size, "grid": g,
        "min_elev_m": round(hmin, 2), "max_elev_m": round(hmax, 2),
        "relief_m": round(hmax - hmin, 2),
        "meters_per_sample": round(args.size / (g - 1), 3),
        "height_scale": args.vscale,
    }
    json.dump(meta, open(os.path.join(args.out, "meta.json"), "w"), indent=2)

    res_dir, proj = res_path_for(args.out)
    if res_dir is None:
        res_dir = "res://" + args.name
        print("[terrain] WARNING: output is not inside a Godot project; using placeholder "
              "res:// paths in the .tscn -- move the folder into a project or fix paths.")
    tscn = os.path.join(args.out, f"{args.name}.tscn")
    res = int(min(args.mesh_resolution, g - 1))
    with open(tscn, "w") as fh:
        fh.write(
            "[gd_scene load_steps=2 format=3]\n\n"
            f'[ext_resource type="Script" path="{res_dir}/terrain.gd" id="1"]\n\n'
            '[node name="Terrain" type="Node3D"]\n'
            'script = ExtResource("1")\n'
            f'heightmap_path = "{res_dir}/heightmap.exr"\n'
            f"world_size = {float(args.size)}\n"
            f"height_min = {round(hmin, 2)}\n"
            f"height_max = {round(hmax, 2)}\n"
            f"height_scale = {float(args.vscale)}\n"
            f"mesh_resolution = {res}\n"
            "add_collision = true\n"
        )
    print(f"[terrain] wrote {args.out}:  {args.name}.tscn, terrain.gd, "
          f"terrain_material.gdshader, heightmap.exr, meta.json")
    if proj:
        print(f"[terrain] drop into the game: instance {res_dir}/{args.name}.tscn (project {proj})")


def main():
    ap = argparse.ArgumentParser(description="Build a Godot terrain from real-world lat/long elevation.")
    ap.add_argument("--place", default=None, help="place name to geocode (alternative to --lat/--lon)")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--size", type=float, default=4000.0, help="square map edge in metres (default 4000)")
    ap.add_argument("--zoom", type=int, default=14, help="DEM tile zoom (12-15; higher=finer, default 14)")
    ap.add_argument("--grid", type=int, default=513, help="heightmap resolution per side (default 513)")
    ap.add_argument("--mesh-resolution", type=int, default=256, help="mesh quads per side (default 256)")
    ap.add_argument("--vscale", type=float, default=1.0, help="vertical exaggeration (default 1.0 = true)")
    ap.add_argument("--out", required=True, help="output directory (ideally inside a Godot project)")
    ap.add_argument("--name", default="terrain", help="scene base name (default 'terrain')")
    ap.add_argument("--cache", default=None, help="tile cache dir (default ~/.cache/watoom-terrain-tiles)")
    ap.add_argument("--max-tiles", type=int, default=64, help="safety cap on tiles fetched")
    args = ap.parse_args()
    if args.lat is None or args.lon is None:
        if not args.place:
            ap.error("provide --place <name> or both --lat and --lon")
        args.lat, args.lon = geocode(args.place)
    build(args)


if __name__ == "__main__":
    main()
