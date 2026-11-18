#!/usr/bin/env python3
"""watoom-texture-layering: write the ue-mcp call list for a game's sky look: locked exposure, a sky atmosphere, volumetric clouds and
light height fog, plus (only when the game uses the nebula star dome) a dimmer nebula (host-side, stdlib only). Apply with ue_run_phases.py.

  unreal_atmosphere.py --out atmo.json --project game.json [--dome ''] [--exposure E] [--no-clouds] [--no-fog] ...
  ue_run_phases.py atmo.json
  tools/rig-ue-mcp/ue_look_check.py --from-calls atmo.json      verifies every value this file set (exits 1 on drift)
  tools/rig-ue-mcp/ue_look_probe.py --sweep-exposure 0.3 0.45 0.6 --post-process LABEL   pick E for a new game first

Any game: actor labels come from the profile -- `label_prefix` + PostProcess / Sun / Atmosphere / Clouds / HeightFog, or the
explicit keys post_process_label, sun_label, sky_dome_label; the cloud material goes to <content_root>/Sky; the fog sits at sea_cm.
The profile key `exposure` (or --exposure) is per game: measure it with ue_look_probe.py, do not copy 0.45. A game without the nebula
star dome passes --dome '' (or sky_dome_label ""): no nebula or dome calls, and the atmosphere keeps its full distance haze (1.0)
because there is no dome behind it to keep visible. The PostProcessVolume must exist and be unbound (unreal_sky.py / level setup).

Why each step (measured on the test game, T-0027, 2026-11-18; numbers are the ground's mean sRGB luminance over 5 horizon views):
  - exposure: the PostProcessVolume's auto exposure (range 0.3..2.5) sat at its brightest end, 0.3, in EVERY view, so "too bright"
    was that floor, not pumping. Min = Max locks it: 0.3 -> 135, 0.45 -> ~105, 0.6 -> 86, 1.0 -> 59 (higher = darker). Locked 0.45.
    The views facing the sun stay darker (~65) because they look at the shaded side of everything; that is real backlight.
  - nebula: MI_Star_Nebula_* `Power` is an exponent: LOWER is BRIGHTER (0.4 blew out 71% of the sun-side sky, 0.7 -> 38%, 1.4 -> 18%).
    The dome blueprint's own `Brightness` variables must NOT be used: changing an actor variable (or moving the dome) reruns its
    construction script, which replaces the MI_Star_Nebula override with a dynamic instance of the black base M_Star_Nebula -- the
    cause of the black sky and washed-out leaves. Set `Power` on the MI asset instead, and set the dome override LAST.
  - atmosphere: without a SkyAtmosphere the volumetric clouds render flat and grey and the dark parts of the nebula stay pure black
    (which drives auto exposure up). A SkyAtmosphere with AerialPespectiveViewDistanceScale 0.35 lights the clouds and fills the black
    with blue while the bright nebula still shows; at the default 1.0 the nebula almost disappears behind a plain blue sky.
  - clouds: the VolumetricCloud defaults (layer 5..15 km) sit behind the 20 km star dome near the horizon; layer 1..3 km shows them.
    Coverage lives in a project MI (`Cloud_GlobalCoverage`, engine default -0.2 is nearly clear) -- never edit the engine instance.
    The sun gets bCastCloudShadows, but ground cloud shadows were NOT visible on this level (on/off A/B from above: no change); open item.
  - fog: ExponentialHeightFog at sea level, FogDensity 0.01 (default 0.02 is heavier), StartDistance 3000 cm keeps the foreground clear.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_project  # noqa: E402

PACK = "/Game/Animated_Nebulas_Starter_Pack/Planet_System"
CLOUD_PARENT = "/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst"


def comp(label, component, prop, value):
    return ["level.set_component_property", {"actorLabel": label, "componentName": component, "propertyName": prop, "value": value}]


def build(post_process="ZAS_PostProcess", exposure=0.45, nebula="02", nebula_power=1.4, dome="ZAS_StarDome", sun="ZAS_Sun",
          atmosphere="ZAS_Atmosphere", aerial_scale=None, clouds="ZAS_Clouds", cloud_mi="/Game/ZAS/Sky/MI_ZAS_Clouds", cloud_coverage=0.35,
          cloud_bottom_km=1.0, cloud_height_km=2.0, fog="ZAS_HeightFog", fog_density=0.01, fog_start_cm=3000.0, fog_z=4900.0,
          center=(200000.0, 200000.0)):
    """-> {"phases": [...]}; pass atmosphere/clouds/fog=None to leave that part out, dome=None for a game without the nebula dome.
    aerial_scale None: 0.35 under a dome (keeps the nebula visible), 1.0 (engine default) without one."""
    cx, cy = float(center[0]), float(center[1])
    if aerial_scale is None:
        aerial_scale = 0.35 if dome else 1.0
    phases = []
    # post-process settings live on the volume actor, not a component: set_component_property cannot reach them;
    # set_post_process_settings with enableOverrides also turns on each bOverride_ flag (a value without its flag is ignored)
    phases.append({"name": "exposure", "calls": [
        ["level.set_post_process_settings", {"actorLabel": post_process, "enableOverrides": True,
                                             "settings": {"AutoExposureMinBrightness": float(exposure),
                                                          "AutoExposureMaxBrightness": float(exposure)}}]]})
    n = "%02d" % int(nebula)
    mi = "%s/Materials/Star_Dome/MI_Star_Nebula_%s" % (PACK, n)
    if dome:
        phases.append({"name": "nebula", "calls": [
            ["material.set_parameter", {"assetPath": mi, "parameterName": "Power", "value": float(nebula_power)}],
            ["material.set_parameter", {"assetPath": mi, "parameterName": "Power_Extra_Cubemap", "value": float(nebula_power)}]]})
    if atmosphere:
        phases.append({"name": "atmosphere", "calls": [
            ["level.place_actor", {"actorClass": "/Script/Engine.SkyAtmosphere", "label": atmosphere, "location": {"x": cx, "y": cy, "z": 0.0},
                                   "onConflict": "skip"}],
            comp(atmosphere, "SkyAtmosphereComponent", "AerialPespectiveViewDistanceScale", float(aerial_scale))]})
    if clouds:
        pkg, name = cloud_mi.rsplit("/", 1)
        phases.append({"name": "clouds", "calls": [
            ["material.create_instance", {"name": name, "parentPath": CLOUD_PARENT, "packagePath": pkg, "onConflict": "skip"}],
            ["material.set_parameter", {"assetPath": cloud_mi, "parameterName": "Cloud_GlobalCoverage", "value": float(cloud_coverage)}],
            ["level.place_actor", {"actorClass": "/Script/Engine.VolumetricCloud", "label": clouds, "location": {"x": cx, "y": cy, "z": 0.0},
                                   "onConflict": "skip"}],
            comp(clouds, "VolumetricCloudComponent", "Material", "%s.%s" % (cloud_mi, name)),
            comp(clouds, "VolumetricCloudComponent", "LayerBottomAltitude", float(cloud_bottom_km)),
            comp(clouds, "VolumetricCloudComponent", "LayerHeight", float(cloud_height_km)),
            comp(sun, "LightComponent0", "bCastCloudShadows", True)]})
    if fog:
        phases.append({"name": "fog", "calls": [
            ["level.place_actor", {"actorClass": "/Script/Engine.ExponentialHeightFog", "label": fog,
                                   "location": {"x": cx, "y": cy, "z": float(fog_z)}, "onConflict": "skip"}],
            comp(fog, "HeightFogComponent0", "FogDensity", float(fog_density)),
            comp(fog, "HeightFogComponent0", "StartDistance", float(fog_start_cm))]})
    # LAST: anything above that touched the dome would have reverted its material; put the nebula override back, then save
    last = []
    if dome:
        last.append(["level.bulk_set_component_property", {"labelPrefix": dome, "componentName": "Dome", "propertyName": "OverrideMaterials",
                                                           "value": ["%s.MI_Star_Nebula_%s" % (mi, n)]}])
    last += [["editor.redraw_viewport", {"allViewports": True}], ["level.save", {}]]
    phases.append({"name": "dome_and_save" if dome else "save", "calls": last})
    return {"phases": phases}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--post-process", help="PostProcessVolume label (default: profile post_process_label, else <label_prefix>PostProcess)")
    ap.add_argument("--exposure", type=float, default=0.45,
                    help="locked auto-exposure value (Min = Max); higher = darker; per game, measure with ue_look_probe.py")
    ap.add_argument("--dome", help="nebula star-dome label; '' for a game without one (default: profile sky_dome_label, else <prefix>StarDome)")
    ap.add_argument("--nebula", default="02")
    ap.add_argument("--nebula-power", type=float, default=1.4, help="MI_Star_Nebula Power; an exponent, higher = DIMMER")
    ap.add_argument("--sun", help="sun (DirectionalLight) label (default: profile sun_label, else <prefix>Sun)")
    ap.add_argument("--no-atmosphere", action="store_true")
    ap.add_argument("--aerial-scale", type=float, default=None,
                    help="SkyAtmosphere AerialPespectiveViewDistanceScale (default 0.35 under a dome, 1.0 without)")
    ap.add_argument("--no-clouds", action="store_true")
    ap.add_argument("--cloud-coverage", type=float, default=0.35, help="Cloud_GlobalCoverage on the project cloud MI (engine default -0.2)")
    ap.add_argument("--cloud-bottom-km", type=float, default=1.0, help="keep the layer inside a sky dome's radius; engine default 5")
    ap.add_argument("--cloud-height-km", type=float, default=2.0)
    ap.add_argument("--no-fog", action="store_true")
    ap.add_argument("--fog-density", type=float, default=0.01)
    ap.add_argument("--fog-start-cm", type=float, default=3000.0)
    ap.add_argument("--fog-z", type=float, default=None, help="fog actor height in cm (default: the profile's sea_cm, else 0)")
    ap.add_argument("--center", nargs=2, type=float, default=None, metavar=("X", "Y"),
                    help="where new actors go (default: the map centre from size_m, else 0 0)")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    pre = ue_project.get("label_prefix", "ZAS_")
    root = ue_project.get("content_root", "/Game/ZAS")

    def pick(flag, key, default):
        return flag if flag is not None else ue_project.get(key, default)
    dome = pick(a.dome, "sky_dome_label", pre + "StarDome") or None
    size_m = ue_project.get("size_m")
    center = tuple(a.center) if a.center else ((size_m * 50.0, size_m * 50.0) if size_m else (0.0, 0.0))
    fog_z = a.fog_z if a.fog_z is not None else float(ue_project.get("sea_cm", 0.0))
    calls = build(post_process=pick(a.post_process, "post_process_label", pre + "PostProcess"), exposure=a.exposure, nebula=a.nebula,
                  nebula_power=a.nebula_power, dome=dome, sun=pick(a.sun, "sun_label", pre + "Sun"),
                  atmosphere=None if a.no_atmosphere else pre + "Atmosphere", aerial_scale=a.aerial_scale,
                  clouds=None if a.no_clouds else pre + "Clouds", cloud_mi="%s/Sky/MI_%sClouds" % (root, pre),
                  cloud_coverage=a.cloud_coverage, cloud_bottom_km=a.cloud_bottom_km, cloud_height_km=a.cloud_height_km,
                  fog=None if a.no_fog else pre + "HeightFog", fog_density=a.fog_density, fog_start_cm=a.fog_start_cm, fog_z=fog_z,
                  center=center)
    json.dump(calls, open(a.out, "w"), indent=1)
    print("wrote %s: %s" % (a.out, ", ".join("%s %d" % (p["name"], len(p["calls"])) for p in calls["phases"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
