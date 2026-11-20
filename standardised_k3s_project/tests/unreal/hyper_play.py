"""Run inside a licensed isolated Hyper Unreal editor; acceptance test, not a build dependency."""

import unreal, pathlib, json, time, os, traceback

root = pathlib.Path(os.environ["WATOOM_ACCEPTANCE_ROOT"])
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
receipt = {
    "scope": "Isolated offline gameplay; Engine.GameInstance fixture; online integration NOT TESTED",
    "engine": unreal.SystemLibrary.get_engine_version(),
    "phase": "LOADING_MAP",
}


def save():
    (root / "play.json").write_text(json.dumps(receipt, indent=2))


save()
assert levels.load_level("/Game/Hyper/CombatSystem/Map/Map_Example_Combat")
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
started = time.monotonic()
phase = 0
pawn = None
origin = None
began = None


def tick(dt):
    global phase, pawn, origin, began
    try:
        elapsed = time.monotonic() - started
        if phase == 0 and elapsed > 10:
            levels.editor_request_begin_play()
            phase = 1
            receipt["phase"] = "STARTING_PLAY"
            save()
        elif phase == 1 and levels.is_in_play_in_editor():
            world = editor.get_game_world()
            if not world:
                return
            pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
            if not pawn:
                return
            receipt["pawn"] = pawn.get_class().get_path_name()
            receipt["components"] = [
                {
                    "name": c.get_name(),
                    "class": c.get_class().get_path_name(),
                    "api": [
                        n
                        for n in dir(c)
                        if any(k in n.lower() for k in ["health", "damage", "attribute", "value", "current"])
                    ],
                }
                for c in pawn.get_components_by_class(unreal.ActorComponent)
            ]
            import subprocess

            windows = subprocess.check_output(
                ["/usr/sbin/xdotool", "search", "--onlyvisible", "--name", "RenderProbe"], text=True
            ).split()
            assert windows
            subprocess.run(["/usr/sbin/xdotool", "windowfocus", "--sync", windows[0]], check=True, timeout=10)
            subprocess.run(["/usr/sbin/xdotool", "keydown", "w"], check=True, timeout=10)
            receipt["input_route"] = "X11 keyboard W -> actual PIE PlayerController"
            origin = pawn.get_actor_location()
            began = elapsed
            phase = 2
            receipt["phase"] = "PLAY_RUNNING"
            receipt["initial_game_time"] = unreal.GameplayStatics.get_time_seconds(world)
            save()
        elif phase == 2:
            # Movement now comes from the actual keyboard route, not direct pawn injection.
            if unreal.GameplayStatics.get_time_seconds(editor.get_game_world()) - receipt["initial_game_time"] > 5:
                pos = pawn.get_actor_location()
                receipt["movement_distance_cm"] = (pos - origin).length()
                key = unreal.Key()
                assert key.import_text("W")
                receipt["keyboard_key"] = key.export_text()
                assert receipt["keyboard_key"] == "W"
                receipt["keyboard_held_seconds"] = unreal.GameplayStatics.get_player_controller(
                    editor.get_game_world(), 0
                ).get_input_key_time_down(key)
                import subprocess

                subprocess.run(["/usr/sbin/xdotool", "keyup", "w"], check=True, timeout=10)
                controller = unreal.GameplayStatics.get_player_controller(editor.get_game_world(), 0)
                movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
                receipt["movement_diagnostics"] = {
                    "world_time": unreal.GameplayStatics.get_time_seconds(editor.get_game_world()),
                    "ignore_move": controller.is_move_input_ignored(),
                    "movement_mode": str(movement.get_editor_property("movement_mode")),
                    "max_walk_speed": movement.get_editor_property("max_walk_speed"),
                    "pending_input": str(pawn.get_pending_movement_input_vector()),
                    "last_input": str(pawn.get_last_movement_input_vector()),
                    "controller_api": [n for n in dir(controller) if "input" in n],
                }
                receipt["attribute_properties"] = {}
                attr = next(
                    c
                    for c in pawn.get_components_by_class(unreal.ActorComponent)
                    if c.get_name() == "AC_CH_Attribute_Manager_Base"
                )
                for name in [
                    "Health",
                    "Current Health",
                    "Non-Persistent Attributes",
                    "Non Persistent Attributes",
                    "Assigned Attributes",
                ]:
                    try:
                        receipt["attribute_properties"][name] = str(attr.get_editor_property(name))
                    except Exception as exc:
                        receipt["attribute_properties"][name] = str(exc)
                receipt["gameplay_tag_api"] = [n for n in dir(unreal.GameplayTag()) if "text" in n or "tag" in n]
                receipt["health_before"] = attr.get_editor_property("Current Health")
                receipt["damage_return"] = unreal.GameplayStatics.apply_damage(
                    pawn,
                    10.0,
                    unreal.GameplayStatics.get_player_controller(editor.get_game_world(), 0),
                    None,
                    unreal.DamageType,
                )
                receipt["phase"] = "DAMAGE_SENT"
                receipt["damage_game_time"] = unreal.GameplayStatics.get_time_seconds(editor.get_game_world())
                save()
                phase = 4
        elif (
            phase == 4
            and unreal.GameplayStatics.get_time_seconds(editor.get_game_world()) - receipt["damage_game_time"] > 1
        ):
            attr = next(
                c
                for c in pawn.get_components_by_class(unreal.ActorComponent)
                if c.get_name() == "AC_CH_Attribute_Manager_Base"
            )
            receipt["health_after"] = attr.get_editor_property("Current Health")
            phase = 5  # Flush pumps Slate: prevent callback re-entry before waiting.
            receipt["phase"] = "FINISHING_RENDER_ASSETS"
            save()
            unreal.AutomationLibrary.finish_loading_before_screenshot()
            receipt["phase"] = "WAITING_RENDER_REPAINT"
            receipt["flush_finished_wall"] = time.monotonic()
            save()
            phase = 6
        elif phase == 6 and time.monotonic() - receipt["flush_finished_wall"] > 10:
            import subprocess

            subprocess.run(
                ["/usr/sbin/import", "-window", "root", str(root / "play-viewport.png")], timeout=20, check=True
            )
            receipt["phase"] = "PLAY_TEST_COMPLETE"
            save()
            levels.editor_request_end_play()
            phase = 3
        elif phase == 3 and not levels.is_in_play_in_editor():
            receipt["play_stopped_cleanly"] = True
            save()
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        if elapsed > 1800 and phase in (0, 1, 2):
            raise RuntimeError("Play timeout")
    except Exception:
        receipt["error"] = traceback.format_exc()
        receipt["phase"] = "FAILED"
        save()
        levels.editor_request_end_play()
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)


handle = unreal.register_slate_post_tick_callback(tick)
