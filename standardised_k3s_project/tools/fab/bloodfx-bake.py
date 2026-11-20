"""Bake bounded native RGBA cache frames into a namespaced Godot sprite library."""

import argparse, pathlib, json, hashlib, math, re, shutil
from PIL import Image, ImageChops


def rgba_from_inverse_opacity(image):
    image = image.convert("RGBA")
    out = []
    for red, green, blue, inverse in image.get_flattened_data():
        alpha = 255 - inverse
        out.append(
            (
                min(255, round(red * 255 / alpha)) if alpha else 0,
                min(255, round(green * 255 / alpha)) if alpha else 0,
                min(255, round(blue * 255 / alpha)) if alpha else 0,
                alpha,
            )
        )
    image.putdata(out)
    return image


def bake(source, destination):
    source = pathlib.Path(source).resolve()
    destination = pathlib.Path(destination)
    if destination.exists():
        raise ValueError("New destination required; existing bakes preserved")
    receipt = json.loads((source / "software-render-receipt.json").read_text())
    if (
        receipt["status"] != "PASS_NATIVE_SAMPLED_RENDER"
        or not receipt.get("actual_software_device")
        or receipt["exit_code"]
    ):
        raise ValueError("Actual native render acceptance required")
    if not 1 <= len(receipt["assets"]) <= 16:
        raise ValueError("Effect count budget")
    destination.mkdir(parents=True)
    assets = []
    for asset in receipt["assets"]:
        name = asset["asset"].split("/")[-1]
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise ValueError("Unsafe effect name")
        frames = asset["frames"]
        assert 2 <= len(frames) <= 96
        folder = destination / "bloodfx/frames" / name
        folder.mkdir(parents=True)
        paths = []
        hashes = []
        opaque = []
        times = []
        for i, frame in enumerate(frames):
            relative = pathlib.PurePosixPath(frame["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Frame escapes project")
            path = (source / relative).resolve()
            assert path.is_relative_to(source) and not path.is_symlink()
            with Image.open(path) as image:
                assert image.size == (256, 256)
                converted = rgba_from_inverse_opacity(image)
                alpha = converted.getchannel("A")
                opaque.append(sum(n for value, n in enumerate(alpha.histogram()) if value > 16))
                hashes.append(hashlib.sha256(converted.tobytes()).hexdigest())
                target = folder / f"frame_{i:03d}.png"
                converted.save(target)
                paths.append(target.relative_to(destination).as_posix())
            t = float(frame["time"])
            assert math.isfinite(t) and (not times or t > times[-1])
            times.append(t)
        if len(set(hashes)) < 2 or sum(x > 4 for x in opaque) < 2:
            raise ValueError("No actual visible temporal effect: " + name)
        fps = (len(times) - 1) / (times[-1] - times[0])
        resource = destination / "bloodfx/resources" / (name + ".tres")
        resource.parent.mkdir(parents=True, exist_ok=True)
        lines = [f'[gd_resource type="SpriteFrames" load_steps={len(paths)+1} format=3]']
        lines += [f'[ext_resource type="Texture2D" path="res://{path}" id="{i+1}"]' for i, path in enumerate(paths)]
        values = ", ".join('{"duration":1.0,"texture":ExtResource("' + str(i + 1) + '")}' for i in range(len(paths)))
        lines += [
            "[resource]",
            'animations = [{"frames": [' + values + '], "loop": false, "name": &"default", "speed": ' + str(fps) + "}]",
        ]
        resource.write_text("\n".join(lines) + "\n")
        assets.append(
            {
                "name": name,
                "source": asset["asset"],
                "resource": resource.relative_to(destination).as_posix(),
                "duration": asset["duration"],
                "sample_times": times,
                "fps": fps,
                "frames": len(frames),
                "pixel_size": asset["ortho_width"] / 100 / 256,
                "visible_pixels": opaque,
                "pixel_hashes": hashes,
            }
        )
    manifest = {
        "schema": 1,
        "kind": "fixed-view-sprite-effect-library",
        "source_renderer": "Unreal GeometryCache original material / software Vulkan",
        "native_3d_preserved": False,
        "resolution": [256, 256],
        "frame_budget": 96,
        "nominal_fps": 12,
        "alpha": "native inverse opacity inverted; RGB unpremultiplied",
        "assets": assets,
        "license": "Derived from owned BloodFX Alembic pack; internal authorized use. Review original license before distribution.",
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (destination / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="BloodFX portable validation"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\ntextures/default_filters/use_nearest_mipmap_filter=false\n'
    )
    (destination / "SOURCE_AND_LICENSE.md").write_text(
        manifest["license"]
        + "\nFixed-view sprite bake, not a 3D geometry cache or shader translation. Copy the bloodfx directory into a Godot project; load a SpriteFrames resource on AnimatedSprite3D and use the manifest pixel_size.\n"
    )
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--destination", required=True)
    a = p.parse_args()
    print(json.dumps({"status": "PASS", "effects": len(bake(a.source, a.destination)["assets"])}))
