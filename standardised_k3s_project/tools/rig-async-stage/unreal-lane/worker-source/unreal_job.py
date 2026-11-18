"""Windows Job Object with a CONFIGURABLE memory limit for the Unreal lane (windows_job.run is fixed at 8 GiB for Blender/Godot).
Start suspended, assign limits, resume; the whole process tree dies with the job (kill-on-close)."""
import ctypes, ctypes.wintypes as w, subprocess, time, os
from windows_job import api, checked, STARTUPINFO, PROCESSINFO, EXTENDED


def run_limited(command, cwd, timeout, memory_bytes, cpus=None, heartbeat=None):
    k = api()
    job = checked(k.CreateJobObjectW(None, None))
    info = EXTENDED()
    # 0x2000 kill-on-close, 0x200 job memory, 0x8 active-process limit, 0x10 affinity
    info.basic.flags = 0x2000 | 0x200 | 0x8 | 0x10
    count = max(1, min(cpus or max(1, (os.cpu_count() or 2) - 2), os.cpu_count() or 1))
    info.basic.affinity = (1 << count) - 1
    info.basic.active = 64
    info.jobMemory = int(memory_bytes)
    checked(k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)))
    start = STARTUPINFO(); start.cb = ctypes.sizeof(start); start.dwFlags = 1; start.wShowWindow = 0
    proc = PROCESSINFO()
    try:
        checked(k.CreateProcessW(None, ctypes.create_unicode_buffer(subprocess.list2cmdline(command)), None, None, False, 0x4 | 0x08000000, None, str(cwd), ctypes.byref(start), ctypes.byref(proc)))
        checked(k.AssignProcessToJobObject(job, proc.process))
        if k.ResumeThread(proc.thread) == 0xffffffff:
            raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + timeout
        while k.WaitForSingleObject(proc.process, 500) == 258:
            if heartbeat:
                heartbeat()
            if time.monotonic() > deadline:
                checked(k.TerminateJobObject(job, 124))
                raise TimeoutError('Unreal deadline exceeded')
        result = w.DWORD()
        checked(k.GetExitCodeProcess(proc.process, ctypes.byref(result)))
        return result.value
    finally:
        if proc.process:
            k.TerminateProcess(proc.process, 125)
        k.CloseHandle(job)
        if proc.thread:
            k.CloseHandle(proc.thread)
        if proc.process:
            k.CloseHandle(proc.process)
