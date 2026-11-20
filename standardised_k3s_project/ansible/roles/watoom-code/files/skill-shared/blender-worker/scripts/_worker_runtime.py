"""Windows Job Object boundary. Start suspended, assign limits, then resume."""

import ctypes, ctypes.wintypes as w, subprocess, time


class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", w.DWORD),
        ("lpReserved", w.LPWSTR),
        ("lpDesktop", w.LPWSTR),
        ("lpTitle", w.LPWSTR),
        ("dwX", w.DWORD),
        ("dwY", w.DWORD),
        ("dwXSize", w.DWORD),
        ("dwYSize", w.DWORD),
        ("dwXCountChars", w.DWORD),
        ("dwYCountChars", w.DWORD),
        ("dwFillAttribute", w.DWORD),
        ("dwFlags", w.DWORD),
        ("wShowWindow", w.WORD),
        ("cbReserved2", w.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", w.HANDLE),
        ("hStdOutput", w.HANDLE),
        ("hStdError", w.HANDLE),
    ]


class PROCESSINFO(ctypes.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]


class BASIC(ctypes.Structure):
    _fields_ = [
        ("processTime", ctypes.c_longlong),
        ("jobTime", ctypes.c_longlong),
        ("flags", w.DWORD),
        ("minimum", ctypes.c_size_t),
        ("maximum", ctypes.c_size_t),
        ("active", w.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", w.DWORD),
        ("scheduling", w.DWORD),
    ]


class IO(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in ("readOps", "writeOps", "otherOps", "readBytes", "writeBytes", "otherBytes")
    ]


class EXTENDED(ctypes.Structure):
    _fields_ = [
        ("basic", BASIC),
        ("io", IO),
        ("processMemory", ctypes.c_size_t),
        ("jobMemory", ctypes.c_size_t),
        ("peakProcess", ctypes.c_size_t),
        ("peakJob", ctypes.c_size_t),
    ]


def api():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    k.CreateJobObjectW.restype = w.HANDLE
    k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    k.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
    k.GetCurrentProcess.restype = w.HANDLE
    k.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)]
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.CreateProcessW.argtypes = [
        w.LPCWSTR,
        w.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        w.BOOL,
        w.DWORD,
        ctypes.c_void_p,
        w.LPCWSTR,
        ctypes.POINTER(STARTUPINFO),
        ctypes.POINTER(PROCESSINFO),
    ]
    k.ResumeThread.argtypes = [w.HANDLE]
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    k.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
    k.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    k.CloseHandle.argtypes = [w.HANDLE]
    return k


def checked(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def current_limit():
    k = api()
    inside = w.BOOL()
    checked(k.IsProcessInJob(k.GetCurrentProcess(), None, ctypes.byref(inside)))
    if not inside.value:
        raise RuntimeError("Blender not inside a Windows Job Object")
    info = EXTENDED()
    checked(k.QueryInformationJobObject(None, 9, ctypes.byref(info), ctypes.sizeof(info), None))
    if not info.basic.flags & 0x200 or info.jobMemory != 8 * 1024**3:
        raise RuntimeError("Incorrect Job Object memory limit")
    return {
        "memory_limit_verified": True,
        "memory_limit_bytes": info.jobMemory,
        "memory_peak_bytes": info.peakJob,
        "boundary": "Windows Job Object",
    }


def run(command, cwd, timeout=900, heartbeat=None):
    k = api()
    job = checked(k.CreateJobObjectW(None, None))
    info = EXTENDED()
    info.basic.flags = 0x2000 | 0x200 | 0x8
    info.basic.active = 8
    info.jobMemory = 8 * 1024**3
    checked(k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)))
    start = STARTUPINFO()
    start.cb = ctypes.sizeof(start)
    proc = PROCESSINFO()
    try:
        checked(
            k.CreateProcessW(
                None,
                ctypes.create_unicode_buffer(subprocess.list2cmdline(command)),
                None,
                None,
                False,
                0x4 | 0x08000000,
                None,
                str(cwd),
                ctypes.byref(start),
                ctypes.byref(proc),
            )
        )
        checked(k.AssignProcessToJobObject(job, proc.process))
        if k.ResumeThread(proc.thread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + timeout
        while k.WaitForSingleObject(proc.process, 500) == 258:
            if heartbeat:
                heartbeat()
            if time.monotonic() > deadline:
                checked(k.TerminateJobObject(job, 124))
                raise TimeoutError("Render deadline exceeded")
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
