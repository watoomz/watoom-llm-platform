#!/usr/bin/env python3
"""Build a C++ code plugin for the rig project and (optionally) install it: the whole cycle of README "Building a C++ code plugin".

  rig_build_plugin.py PLUGINDIR                  stage the source in <project>/Saved/<P>, RunUAT BuildPlugin to Saved/<P>Pkg
  rig_build_plugin.py PLUGINDIR --install        ... then stop the project's editor, mirror the package (no Intermediate/) into
                                                 <project>/Plugins/<P>, start the editor, wait for the bridge, check a class
  rig_build_plugin.py <unpacked ue-mcp>/plugin/UE_MCP_Bridge --install --ue-mcp-version 1.4.14 [--reuse-build]
                                                 upgrade ue-mcp: the bridge plugin and the uemcp launcher pin change together
                                                 while the editor is stopped (npm pack ue-mcp@V; copy plugin/ue_mcp_bridge to a
                                                 folder named UE_MCP_Bridge; post on T-0049 first)
  rig_build_plugin.py PLUGINDIR --install --check-class /Script/WatooMCombat.Default__WatooMCombatAnimInstance --check-prop DefaultStance

Why (T-0063, 2026-11-18): the rig project is Blueprint-only with a binary-only ue-mcp bridge, so project.build always fails and
a plugin must be built standalone and installed as binaries. Doing it by hand cost several rounds: a copy attempted while the
quitting editor still held the DLL, a start racing the stop. This tool waits for the editor process of THIS project to be gone
(by its command line, never another project's editor) before copying, and refuses to copy while it runs.
Build errors are printed (compiler `error C..`, UHT `Error:` lines) and exit 1; nothing is installed after a failed build.
Uses the `migrate` maintenance account (admin; key only, never read) through rig_copy_pack.plugin_scp_args for the copy and an
-EncodedCommand PowerShell for the rig-side steps. Post on the coordination ticket before --install: it restarts the editor.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rig_copy_pack  # noqa: E402
import ue_route  # noqa: E402

PROJECT = "F:/Documents/Unreal Projects/WatooM_UEMCP_Test"
ENGINE = "F:/AI/Unreal5.8/UE_5.8"
SSH = ["ssh", "-i", rig_copy_pack.KEY, "-o", "UserKnownHostsFile=/data/ai/ue-mcp-ssh/known_hosts", "-p", str(rig_copy_pack.PORT),
       "-o", "BatchMode=yes", "%s@%s" % (rig_copy_pack.USER, rig_copy_pack.HOST)]
ERROR_LINE = re.compile(r"(error C\d+|error LNK\d+|\): error|Error: |Could not find|Unable to instantiate)")


def win(path):
    return path.replace("/", "\\")


def encoded(ps):
    """PowerShell script -> the ssh remote command (cmd is the account's shell, so quote nothing: -EncodedCommand)."""
    ps = "$ProgressPreference = 'SilentlyContinue'\n" + ps  # else CLIXML progress records swamp the output
    return "powershell -NoProfile -EncodedCommand " + base64.b64encode(ps.encode("utf-16-le")).decode()


def build_ps(name, project=PROJECT, engine=ENGINE):
    saved = win(project + "/Saved")
    return ('$pkg = "%s\\%sPkg"; if (Test-Path $pkg) { Remove-Item -Recurse -Force $pkg }\n'
            '& "%s\\Engine\\Build\\BatchFiles\\RunUAT.bat" BuildPlugin -Plugin="%s\\%s\\%s.uplugin" -Package="$pkg" '
            '-TargetPlatforms=Win64 -Rocket\nexit $LASTEXITCODE' % (saved, name, win(engine), saved, name, name))


def editor_running_ps(project=PROJECT):
    base = os.path.basename(project.rstrip("/"))
    return ("$e = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'UnrealEditor*' -and ([string]$_.CommandLine) -like '*%s*' }\n"
            "if ($e) { 'RUNNING ' + ($e.ProcessId -join ',') } else { 'STOPPED' }" % base)


def install_ps(name, project=PROJECT):
    return (editor_running_ps(project).replace("else { 'STOPPED' }", "else { '' }") + "\n"
            "if ($e) { exit 3 }\n"
            '$src = "%s\\Saved\\%sPkg"; $dst = "%s\\Plugins\\%s"\n'
            "robocopy $src $dst /MIR /XD Intermediate /NFL /NDL /NJH /NP | Out-Null\n"
            "if ($LASTEXITCODE -ge 8) { 'ROBOCOPY FAILED ' + $LASTEXITCODE; exit 4 }\n"
            "'INSTALLED ' + (Get-Item \"$dst\\Binaries\\Win64\\UnrealEditor-%s.dll\").LastWriteTime" % (win(project), name, win(project), name, name))


def package_ps(name, project=PROJECT):
    """PACKAGE <dll time> when a built package of <name> sits in Saved/<name>Pkg (checked BEFORE the editor is stopped)."""
    return ('$d = "%s\\Saved\\%sPkg\\Binaries\\Win64\\UnrealEditor-%s.dll"\n'
            "if (Test-Path $d) { 'PACKAGE ' + (Get-Item $d).LastWriteTime } else { 'NO PACKAGE'; exit 6 }" % (win(project), name, name))


LAUNCHER = "C:/watoom/rig-ue-mcp/run-ue-mcp.cmd"
VERSION = re.compile(r"^\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$")


def pin_ps(version, launcher=LAUNCHER):
    """Re-pin the uemcp launcher (written by Add-RigAuthorizedKey.ps1) to an exact ue-mcp version; prints PINNED <old> -> <new>."""
    if not VERSION.match(version):
        raise ValueError("ue-mcp version must be exact (e.g. 1.4.14), not a range or tag: %r" % version)
    return ('$l = "%s"; $t = [IO.File]::ReadAllText($l)\n'
            "$m = [regex]::Match($t, 'ue-mcp@([0-9A-Za-z.-]+)'); if (-not $m.Success) { 'PIN FAILED: no ue-mcp@ in launcher'; exit 5 }\n"
            "[IO.File]::WriteAllText($l, $t.Replace($m.Value, 'ue-mcp@%s'), [Text.Encoding]::ASCII)\n"
            "'PINNED ' + $m.Groups[1].Value + ' -> %s'" % (win(launcher), version, version))


def build_errors(output):
    return sorted({l.strip() for l in output.splitlines() if ERROR_LINE.search(l) and "Marketplace" not in l})


def rig(ps, timeout, run=subprocess.run):
    r = run(SSH + [encoded(ps)], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def wait_stopped(run, project, tries=30, sleep=time.sleep):
    for _ in range(tries):
        _, out = rig(editor_running_ps(project), 120, run)
        if "STOPPED" in out:
            return True
        sleep(10)
    return False


def dirty_content(reply):
    """/Game/ (and plugin) package names from an editor.list_dirty_packages reply; /Temp and /Engine are not the project's."""
    import re
    names = set(re.findall(r'"(/(?!Temp/|Engine/|Script/)[A-Za-z0-9_]+/[^"]+)"', reply or ""))
    return sorted(n for n in names if not n.startswith(("/Temp", "/Engine", "/Script")))


def main(argv=None, run=subprocess.run, sleep=time.sleep, route_call=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plugin")
    ap.add_argument("--project-dir", default=PROJECT, help="rig project folder (forward slashes)")
    ap.add_argument("--install", action="store_true", help="stop the editor, install the package into Plugins/, start it again")
    ap.add_argument("--check-class", help="CDO path to read after the start, e.g. /Script/<Module>.Default__<Class>")
    ap.add_argument("--check-prop", default=None)
    ap.add_argument("--reuse-build", action="store_true", help="with --install: install the package the last successful "
                    "build left in <project>/Saved/<P>Pkg instead of building again (the ue-mcp bridge takes ~45 min)")
    ap.add_argument("--project-plugins", action="store_true", help="with --install: also apply project_plugins.json "
                    "(rig_project_plugins.py --apply) while the editor is stopped, so one restart covers both")
    ap.add_argument("--ue-mcp-version", help="with --install of the UE_MCP_Bridge plugin: re-pin the uemcp launcher to this exact "
                    "ue-mcp version while the editor is stopped, so the new server and the new bridge start together")
    a = ap.parse_args(argv)
    if a.ue_mcp_version and not a.install:
        ap.error("--ue-mcp-version needs --install")
    pin = pin_ps(a.ue_mcp_version) if a.ue_mcp_version else None
    name = os.path.basename(a.plugin.rstrip("/"))
    if a.reuse_build:
        if not a.install:
            ap.error("--reuse-build needs --install")
        code, out = rig(package_ps(name, a.project_dir), 120, run)
        if code or "PACKAGE " not in out:
            raise SystemExit("no built package to reuse (run without --reuse-build): " + out.strip()[-300:])
        print(out.strip(), flush=True)
    else:
        for cmd in rig_copy_pack.plugin_scp_args(a.plugin, dest=a.project_dir + "/Saved/"):
            if run(cmd).returncode:
                raise SystemExit("staging copy failed: " + " ".join(cmd[-2:]))
        print("staged %s in %s/Saved/%s" % (name, a.project_dir, name), flush=True)
        code, out = rig(build_ps(name, a.project_dir), 3600, run)
        errs = build_errors(out)
        if code or "BUILD SUCCESSFUL" not in out and "ExitCode=0" not in out:
            print("\n".join(errs) or out[-3000:])
            raise SystemExit("BuildPlugin failed (exit %s); nothing installed" % code)
        print("built %s (BuildPlugin exit 0)" % name, flush=True)
    if not a.install:
        return 0
    call = route_call or (lambda cat, meth, args, t=600: ue_route.SshTransport(ue_route.ssh_command(
        "10.99.1.44", 2224, "uemcp", ue_route.DEFAULT_KEY_DIR)).call(cat, meth, args, t))
    call("editor", "play_in_editor", {"pieAction": "stop"})
    # refuse BEFORE stopping when project content is unsaved: the stop opens a modal Save Content dialog that blocks every
    # bridge call, dialog mode "defer" means only a person can answer it, and ending the editor then loses the work
    # (2026-11-19: six imported clips + a statue, all re-imported afterwards; the import tool now saves them)
    unsaved = dirty_content(call("editor", "list_dirty_packages", {}))
    if unsaved:
        raise SystemExit("unsaved project content; save it (asset.save {assetPaths}) and run again; plugin NOT installed:\n  "
                         + "\n  ".join(unsaved))
    r = call("editor", "stop_editor", {"discardTransient": True})
    # only a FAILED stop counts (a successful reply can carry log lines that mention "dirty"; that misfired once)
    # a reply whose log already says the editor is exiting (and no dialog blocks) is a stop in progress, not a refusal:
    # 2026-11-19 the ue-mcp 1.4.14 install aborted here on such a reply while the editor went on to quit cleanly
    exiting = '"exiting": true' in r and '"dialogBlocking": true' not in r
    if not exiting and ('"dialogBlocking": true' in r or ('"success": false' in r and ("unsaved" in r.lower() or "dirty" in r.lower()))):
        # The editor refuses to quit on unsaved work (or sits in its Save Content prompt). Never kill it to get past that:
        # save the named packages (asset.save {assetPaths}) or let the owner answer, then run again (T-0063, 2026-11-18).
        raise SystemExit("the editor will not quit: unsaved work or an open dialog; plugin NOT installed.\n" + r[:1500])
    if not wait_stopped(run, a.project_dir, sleep=sleep):
        raise SystemExit("the project's editor is still running after 5 minutes; plugin NOT installed")
    if a.project_plugins:
        import rig_project_plugins  # late: it imports this module
        if rig_project_plugins.main(["--apply"], run=run):
            raise SystemExit("project_plugins.json not applied; plugin NOT installed, editor left stopped")
    if pin:
        code, out = rig(pin, 120, run)
        print(out.strip()[-300:], flush=True)
        if code or "PINNED" not in out:
            raise SystemExit("launcher re-pin failed (%s); plugin NOT installed, editor left stopped" % code)
    code, out = rig(install_ps(name, a.project_dir), 600, run)
    print("\n".join(l for l in out.splitlines() if l.startswith(("INSTALLED", "ROBOCOPY", "RUNNING"))) or out[-500:])
    if code:
        raise SystemExit("install failed (%d)" % code)
    call("editor", "start_editor", {}, 900)  # may report a false "exited during startup"; the poll below decides
    for _ in range(40):
        r = call("project", "get_status", {}, 120)
        if '"editorConnected": true' in r:
            break
        sleep(20)
    else:
        raise SystemExit("editor did not reconnect after the install")
    print("editor back up", flush=True)
    if a.check_class:
        r = call("editor", "get_property", {"objectPath": a.check_class, "propertyName": a.check_prop or "Class"}, 120)
        ok = '"success": true' in r
        print("check %s.%s: %s" % (a.check_class, a.check_prop, "ok" if ok else r[:300]))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
