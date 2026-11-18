#!/usr/bin/env python3
"""watoom-texture-layering: write the ue-mcp call list for a permanent nebula (or any dome) sky with a sun (host-side, stdlib only).

Verified on UE 5.8.4 with Animated_Nebulas_Starter_Pack:
  - the dome blueprint `BP_Star_Dome` carries a StaticMeshComponent `Dome` whose mesh is ~500,000 km wide; scale the ACTOR to 0.00004
    (a 20 km radius) so it sits inside the far clip and around a 4 km map,
  - the default dome material renders black: override the component with one of the `MI_Star_Nebula_01..05` instances,
  - the first capture after changing it can still be black while the 26 textures stream in: capture twice,
  - the blue `SkyAtmosphere` is drawn over the dome, so it is deleted (this is what makes the sky permanent, not a day cycle),
  - a SkyLight left Static (or Stationary with no capture) leaves every surface facing away from the sun pure black (grass blades,
    tree undersides), so it is made Movable; the DirectionalLight stays as the light source,
  - a captured-scene SkyLight (recapture or real-time capture) only sees sky meshes whose material has "Is Sky" set. The star dome
    is NOT Is-Sky, so its capture is black and gives no ambient (measured 2026-11-16: shadows pure black even at intensity 3).
    The default here is therefore --sky-source cubemap: SourceType SLS_SpecifiedCubemap, Cubemap
    /Engine/MapTemplates/Sky/DaylightAmbientCubemap, bRealTimeCapture false, intensity about 1 to 2.
    --sky-source captured keeps the old form (Movable + recaptureSky) for a level whose sky material IS Is-Sky.
  - the dome's construction script rewrites its material from the blueprint variables: setting one of them, or moving the dome
    (also the move_actor scale call below), replaces the MI_Star_Nebula override with a dynamic instance of the BLACK base material.
    The override call therefore comes after the move here; anything later that touches the dome must set it again (T-0027, 2026-11-18).
    Dim the nebula with `Power` on the MI (an exponent: higher is dimmer), see unreal_atmosphere.py.

  unreal_sky.py --center 200000 200000 --nebula 02 --out sky_calls.json
  unreal_sky.py ... --sky-source captured            (only when the sky mesh's material has Is Sky set)
  unreal_sky.py ... --sky-component-path "/Game/Maps/L_Level.L_Level:PersistentLevel.SkyLight_0.SkyLightComponent0"

The cubemap fields were verified on the rig with editor.set_property on the component object path, which is what
--sky-component-path emits. Without it the same fields are written with level.set_component_property {actorLabel,
componentName: SkyLightComponent0}; that form is NOT verified on a SkyLight, so read SourceType back
(level.get_actor_details / editor.get_property) and check a shadowed surface in a ue_viewport_shot.py capture.
"""
import argparse
import json
import sys
from os.path import abspath as _abspath, dirname as _dirname  # noqa: E402
sys.path.insert(0, _dirname(_abspath(__file__)))  # so `python3 -I script.py` finds ue_project
import ue_project  # noqa: E402

PACK = "/Game/Animated_Nebulas_Starter_Pack/Planet_System"
CUBEMAP = "/Engine/MapTemplates/Sky/DaylightAmbientCubemap.DaylightAmbientCubemap"
SKY_SOURCES = ("cubemap", "captured")


def build(center=(200000.0, 200000.0), z=0.0, nebula="02", scale=0.00004, sky_light="SkyLight", sky_intensity=1.2,
          atmosphere="SkyAtmosphere", sun="DirectionalLight", sun_intensity=None, pack=PACK, label="StarDome",
          sky_source="cubemap", cubemap=CUBEMAP, sky_component_path=None):
    """sky_source "cubemap" (default; right for the star dome, which is not Is-Sky) or "captured" (Movable + recaptureSky; only
    lights the scene when the sky mesh's material has Is Sky set). sky_component_path: object path of the SkyLightComponent, to
    write the cubemap fields with editor.set_property (the verified form) instead of level.set_component_property."""
    if sky_source not in SKY_SOURCES:
        raise ValueError("sky_source is one of %s" % ", ".join(SKY_SOURCES))
    nebula = "%02d" % int(nebula)
    if not 1 <= int(nebula) <= 5:
        raise ValueError("the pack has MI_Star_Nebula_01..05")
    mi = "%s/Materials/Star_Dome/MI_Star_Nebula_%s" % (pack, nebula)
    calls = []
    if atmosphere:
        calls.append(["level.delete_actor", {"actorLabel": atmosphere}])
    calls.append(["level.place_actor", {"actorClass": "%s/Blueprints/BP_Star_Dome.BP_Star_Dome_C" % pack, "label": label,
                                        "location": {"x": float(center[0]), "y": float(center[1]), "z": float(z)}, "onConflict": "skip"}])
    calls.append(["level.move_actor", {"actorLabel": label, "scale": {"x": scale, "y": scale, "z": scale}}])
    calls.append(["level.bulk_set_component_property", {"labelPrefix": label, "componentName": "Dome", "propertyName": "OverrideMaterials",
                                                        "value": ["%s.MI_Star_Nebula_%s" % (mi, nebula)]}])
    if sky_source == "captured":
        calls.append(["level.set_light_properties", {"actorLabel": sky_light, "intensity": float(sky_intensity), "mobility": "Movable", "recaptureSky": True}])
    else:
        calls.append(["level.set_light_properties", {"actorLabel": sky_light, "intensity": float(sky_intensity), "mobility": "Movable"}])
        for prop, value in (("SourceType", "SLS_SpecifiedCubemap"), ("Cubemap", cubemap), ("bRealTimeCapture", False)):
            if sky_component_path:
                calls.append(["editor.set_property", {"objectPath": sky_component_path, "propertyName": prop, "value": value}])
            else:
                calls.append(["level.set_component_property", {"actorLabel": sky_light, "componentName": "SkyLightComponent0", "propertyName": prop, "value": value}])
        calls.append(["editor.redraw_viewport", {"allViewports": True}])
    if sun and sun_intensity is not None:
        calls.append(["level.set_light_properties", {"actorLabel": sun, "intensity": float(sun_intensity)}])
    calls.append(["level.save", {}])
    return calls


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--center", nargs=2, type=float, default=[200000.0, 200000.0], metavar=("X", "Y"))
    ap.add_argument("--z", type=float, default=0.0)
    ap.add_argument("--nebula", default="02")
    ap.add_argument("--scale", type=float, default=0.00004)
    ap.add_argument("--sky-intensity", type=float, default=1.2, help="about 1 to 2 with the cubemap source")
    ap.add_argument("--sky-source", choices=SKY_SOURCES, default="cubemap",
                    help="cubemap (default): specified cubemap, works with a dome that is not Is-Sky; captured: Movable + recaptureSky, only for an Is-Sky sky material")
    ap.add_argument("--sky-cubemap", default=CUBEMAP, help="cubemap asset for --sky-source cubemap")
    ap.add_argument("--sky-light", default="SkyLight", help="SkyLight actor label")
    ap.add_argument("--sky-component-path", default=None, help="SkyLightComponent object path: write the cubemap fields with editor.set_property (verified form)")
    ap.add_argument("--keep-atmosphere", action="store_true", help="do not delete the SkyAtmosphere actor")
    ap.add_argument("--atmosphere", default="SkyAtmosphere", help="SkyAtmosphere actor label to delete")
    ap.add_argument("--out", required=True)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    calls = build(tuple(a.center), a.z, a.nebula, a.scale, sky_light=a.sky_light, sky_intensity=a.sky_intensity, atmosphere=None if a.keep_atmosphere else a.atmosphere,
                  sky_source=a.sky_source, cubemap=a.sky_cubemap, sky_component_path=a.sky_component_path)
    json.dump({"phases": [{"name": "sky", "calls": calls}]}, open(a.out, "w"))
    print("wrote %s: %d calls" % (a.out, len(calls)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
