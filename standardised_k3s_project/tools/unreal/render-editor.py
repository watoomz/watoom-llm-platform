#!/usr/bin/env python3
"""Allocate an owned X display, then run the Vulkan editor inside the resource namespace."""

import pathlib, os, subprocess, time, sys, signal, select


def interrupted(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, interrupted)
read_fd, write_fd = os.pipe()
x = None
engine = None
try:
    x = subprocess.Popen(
        ["Xvfb", "-displayfd", str(write_fd), "-screen", "0", "1280x900x24", "-nolisten", "tcp"],
        pass_fds=(write_fd,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.close(write_fd)
    write_fd = None
    ready, _, _ = select.select([read_fd], [], [], 10)
    if not ready:
        raise RuntimeError("Xvfb display allocation timed out")
    display_number = os.read(read_fd, 64).decode().strip()
    if not display_number.isdigit() or x.poll() is not None:
        raise RuntimeError("Xvfb did not allocate a working display")
    display = ":" + display_number
    if sys.argv[1:] == ["--probe-display"]:
        print("PROBE_DISPLAY_PASS")
    else:
        root = pathlib.Path(sys.argv[1])
        binary = pathlib.Path(sys.argv[2])
        probe = pathlib.Path(sys.argv[3])
        env = dict(os.environ, DISPLAY=display, WATOOM_ACCEPTANCE_ROOT=str(root))
        command = [
            str(binary / "Engine/Binaries/Linux/UnrealEditor"),
            str(root / "RenderProbe.uproject"),
            "-vulkan",
            "-unattended",
            "-nosound",
            "-nosplash",
            "-nop4",
            "-stdout",
            "-FullStdOutLogOutput",
            "-ddc=NoZenLocalFallback",
            "-LocalDataCachePath=" + str(root / "DerivedDataCache"),
            "-ExecutePythonScript=" + str(probe),
        ]
        if os.environ.get("WATOOM_RENDER_DEBUG") == "1":
            command = [
                "/usr/sbin/gdb",
                "-nx",
                "-batch",
                "--return-child-result",
                "-ex",
                "set auto-load off",
                "-ex",
                "set pagination off",
                "-ex",
                "handle SIGABRT stop print nopass",
                "-ex",
                "run",
                "-ex",
                "bt 100",
                "--args",
                *command,
            ]
        engine = subprocess.Popen(command, env=env)
        raise SystemExit(engine.wait())
finally:
    os.close(read_fd)
    if write_fd is not None:
        os.close(write_fd)
    if engine is not None and engine.poll() is None:
        engine.terminate()
        try:
            engine.wait(timeout=10)
        except subprocess.TimeoutExpired:
            engine.kill()
            engine.wait()
    if x is not None and x.poll() is None:
        x.terminate()
        try:
            x.wait(timeout=5)
        except subprocess.TimeoutExpired:
            x.kill()
            x.wait()
