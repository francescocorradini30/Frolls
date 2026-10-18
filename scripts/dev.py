"""Start the Frolls dev servers (API on 8000, web on 5173) as one process.

Run it with the backend venv (`npm run dev` or the PyCharm "Frolls" config). Stopping
this process stops everything: on Windows the servers live in a Job Object that the
OS tears down as soon as this launcher exits, even when it is killed outright, so no
orphan uvicorn or Vite is left holding the ports.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
API_PORT = 8000
WEB_PORT = 5173

# Command-line fragments that identify a leftover Frolls dev server.
OWN_MARKERS = ("uvicorn", "vite", "concurrently", "dev.py")


def kill_on_exit() -> None:
    """Put this process (and so every child it starts) in a kill-on-close Job Object."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("r", "w", "o", "rb", "wb", "ob")]

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job_object_extended_limit_information = 9
    job_object_limit_kill_on_job_close = 0x2000

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = job_object_limit_kill_on_job_close
    ok = kernel32.SetInformationJobObject(
        job, job_object_extended_limit_information, ctypes.byref(limits), ctypes.sizeof(limits)
    )
    ok = ok and kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
    if not ok:
        print(f"[dev] warning: could not create the job object (error {ctypes.get_last_error()})")
    # The handle is deliberately never closed: the OS closes it when this process dies,
    # which kills every server started below.


def is_ours(proc: psutil.Process) -> bool:
    """A dev server (or its launcher) started from this checkout."""
    try:
        cmd = " ".join(proc.cmdline())
        cwd = proc.cwd()
    except psutil.Error:
        return False
    root = str(ROOT).lower()
    return any(m in cmd for m in OWN_MARKERS) and (
        root in cmd.lower() or cwd.lower().startswith(root)
    )


def free_port(port: int) -> None:
    """Stop a leftover Frolls server on `port`; refuse to touch anything else."""
    owners = {
        c.pid
        for c in psutil.net_connections("tcp")
        if c.laddr and c.laddr.port == port and c.status == "LISTEN"
    }
    for pid in owners:
        try:
            proc = psutil.Process(pid)
        except psutil.Error:
            continue
        if not is_ours(proc):
            sys.exit(
                f"[dev] port {port} is used by another program ({proc.name()}, pid {pid}): stop it"
            )
        # Climb to the outermost Frolls launcher (npm, concurrently, uvicorn reloader...).
        top = proc
        for parent in proc.parents():
            if not is_ours(parent):
                break
            top = parent
        print(f"[dev] stopping leftover server on port {port} (pid {top.pid})")
        victims = [top, *top.children(recursive=True)]
        for p in victims:
            try:
                p.kill()
            except psutil.Error:
                pass
        psutil.wait_procs(victims, timeout=5)


def pump(name: str, proc: subprocess.Popen[bytes]) -> None:
    assert proc.stdout
    for line in iter(proc.stdout.readline, b""):
        sys.stdout.write(f"[{name}] {line.decode(errors='replace').rstrip()}\n")
        sys.stdout.flush()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Vite prints non-ASCII symbols
    kill_on_exit()
    for port in (API_PORT, WEB_PORT):
        free_port(port)

    python = BACKEND / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    node = "node.exe" if sys.platform == "win32" else "node"
    # Output goes through a pipe: force colours back on for the PyCharm console.
    env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"} | {
        "PYTHONUNBUFFERED": "1",
        "FORCE_COLOR": "1",
    }
    servers = {
        "api": subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                "app.main:app",
                "--reload",
                "--port",
                str(API_PORT),
                "--timeout-graceful-shutdown",
                "1",
            ],
            cwd=BACKEND,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ),
        "web": subprocess.Popen(
            [node, "node_modules/vite/bin/vite.js", "--port", str(WEB_PORT), "--strictPort"],
            cwd=FRONTEND,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ),
    }
    for name, proc in servers.items():
        threading.Thread(target=pump, args=(name, proc), daemon=True).start()

    try:
        # If either server dies, take the other one down too: half a dev setup only confuses.
        while all(p.poll() is None for p in servers.values()):
            time.sleep(0.5)
        dead = next(n for n, p in servers.items() if p.poll() is not None)
        print(f"[dev] {dead} exited with code {servers[dead].returncode}, stopping")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for proc in servers.values():
            if proc.poll() is None:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
