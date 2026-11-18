"""Operator-defined capture scenes and exact expected outputs; no caller paths."""
PROFILES={
 'p85':{'deadline_sec':600,'memory_gib':4,'scene': '.opencode/validation/p85-vfx-capture/p85_vfx_capture.tscn', 'directory': '.opencode/captures/p8-vfx', 'names': ['01-pre-drop.png', '02-mid-flight.png', '03-impact.png', '04-splash.png', '05-drip-puddle.png', '06-settle.png', '07-closeup-impact.png', '08-closeup-splash.png', '09-closeup-drip.png', '10-ability3-impact.png', '11-ability3-post.png', '12-ability7-impact.png', '13-ability7-post.png']},
 'p6':{'scene':'.opencode/validation/p6-env-capture/p6_env_capture.tscn','directory':'.opencode/captures/p6-asset-review','names':['terrain-wild.png','meadow-tree.png','tree-closeup.png']},
 'p7':{'scene':'.opencode/validation/p7-poo-capture/p7_poo_capture.tscn','directory':'.opencode/captures/p7-poo','names':['ability-'+str(i)+'-'+name+'.png' for i,name in enumerate(['normal','explosive','rapid_fire','mega','sticky','scatter','precision','stink_bomb'])]},
}

def exit_evidence(returncode, log, elapsed, deadline_sec, errors):
    """Explain a non-zero Godot exit. systemd stops the unit at RuntimeMaxSec with a bare
    non-zero exit; naming it keeps agents from chasing a script error that never happened."""
    timed_out = returncode is None or (returncode != 0 and (
        "runtime time limit" in log or "result 'timeout'" in log or elapsed >= deadline_sec - 2))
    if timed_out:
        script_errors = [e for e in errors if str(e).startswith(("SCRIPT ERROR", "ERROR: Failed to load script", "Parse Error"))]
        if script_errors:
            # after a parse/load error the scene never ran and Godot just idled until the limit: the script error is the cause, not scene cost
            return True, ["WORKER_DEADLINE_EXCEEDED_AFTER_SCRIPT_ERROR: Godot was stopped at the %ds limit after %ds, but a script error was reported first "
                          "(listed next). The scene most likely never ran and Godot idled until the limit. Fix that script error first; this is not a scene-cost "
                          "problem." % (deadline_sec, round(elapsed))]
        return True, ["WORKER_DEADLINE_EXCEEDED: Godot was stopped at the %ds limit after %ds. "
                      "This is not a script or compile error; the scene did not finish in time. Reduce frames, "
                      "views or scene cost; resubmitting the same scene will time out again." % (deadline_sec, round(elapsed))]
    if returncode != 0 and not errors:
        tail = " | ".join([x for x in log.splitlines() if x.strip()][-3:])[:400]
        return False, ["GODOT_EXIT_%s: no ERROR line; last output: %s" % (returncode, tail)]
    return False, []

def frame_evidence_errors(profile, images):
 """A fixed ability showcase must not pass eight byte-identical frames."""
 if profile == 'p7' and len(images) == len(PROFILES['p7']['names']) and len({x['sha256'] for x in images}) == 1:
  return ['P7_FRAME_EVIDENCE_IDENTICAL: all eight ability PNGs are byte-identical; distinct ability visuals are not demonstrated']
 return []
