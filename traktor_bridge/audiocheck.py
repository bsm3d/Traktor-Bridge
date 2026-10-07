"""Read-only header and full-stream checks; decoder acceptance is not a checksum."""

from __future__ import annotations

import multiprocessing
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

import soundfile as sf
from mutagen import File, MutagenError

from .export.files import Cancelled
from .tagwrite import EXTENSIONS


@dataclass
class Result:
    path: str
    status: str
    detail: str


def find_clamav() -> str:
    executable = shutil.which("clamscan")
    if executable:
        return executable
    if sys.platform == "win32":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(variable)
            if root:
                path = os.path.join(root, "ClamAV", "clamscan.exe")
                if os.path.isfile(path):
                    return path
    return ""


def _memory_bytes(pid: int) -> int:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in
                          ("peak_working", "working", "peak_paged", "paged", "peak_nonpaged",
                           "nonpaged", "pagefile", "peak_pagefile", "private")]]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        handle = kernel.OpenProcess(0x1000 | 0x10, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                raise ctypes.WinError(ctypes.get_last_error())
            return max(counters.working, counters.private)
        finally:
            kernel.CloseHandle(handle)
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True,
                            text=True, timeout=2, check=True)
    return int(result.stdout.strip()) * 1024


def _child_check(connection, path, full):
    try:
        connection.send(check_file(path, full))
    finally:
        connection.close()


def isolated_check(path: str, full: bool, cancel=None, timeout=120, memory_mb=1024) -> Result:
    _cancel(cancel)
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child_check, args=(sender, path, full), daemon=True)
    start = time.monotonic()
    next_memory_check = start
    try:
        process.start()
        sender.close()
        while process.is_alive():
            _cancel(cancel)
            now = time.monotonic()
            if now - start > timeout:
                return Result(path, "Not checked", f"Time limit exceeded ({timeout} seconds)")
            if now >= next_memory_check:
                try:
                    used = _memory_bytes(process.pid)
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    if not process.is_alive():
                        break
                    return Result(path, "Not checked", f"Cannot enforce memory monitoring: {error}")
                if used > memory_mb * 1024 * 1024:
                    return Result(path, "Not checked", f"Memory limit exceeded ({memory_mb} MB)")
                next_memory_check = now + .25
            try:
                available = receiver.poll(.05)
            except BrokenPipeError:
                break
            if available:
                break
        try:
            if receiver.poll(.2):
                return receiver.recv()
        except (EOFError, BrokenPipeError):
            pass
        return Result(path, "Not checked", f"Analysis process stopped without a result (exit {process.exitcode})")
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join()
        sender.close()
        receiver.close()
        process.close()


def _cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def check_file(path: str, full: bool, cancel=None) -> Result:
    _cancel(cancel)
    if not os.path.isfile(path):
        return Result(path, "Missing", "File not found")
    try:
        if os.path.getsize(path) == 0:
            return Result(path, "Suspect", "Empty file")
        metadata = File(path)
        if metadata is None or not getattr(metadata, "info", None):
            return Result(path, "Not checked", "Unrecognized audio format")
        if getattr(metadata.info, "length", 0) <= 0:
            return Result(path, "Suspect", "No audio duration in the header")
        # RIFF/AIFF readers may accept a container whose declared end is past EOF.
        with open(path, "rb") as source:
            header = source.read(12)
        if header[:4] in (b"RIFF", b"FORM"):
            byteorder = "little" if header[:4] == b"RIFF" else "big"
            declared = int.from_bytes(header[4:8], byteorder) + 8
            if declared > os.path.getsize(path):
                return Result(path, "Suspect", "Truncated container: declared size exceeds file size")
        if not full:
            return Result(path, "Headers readable", "Audio data has not been decoded")
        with sf.SoundFile(path) as audio:
            if not 1 <= audio.channels <= 32 or not 1 <= audio.samplerate <= 768000:
                return Result(path, "Not checked", "Audio parameters exceed safety limits (32 channels / 768 kHz)")
            expected = audio.frames
            if expected > audio.samplerate * 86400:
                return Result(path, "Not checked", "Declared audio duration exceeds the 24-hour safety limit")
            read = 0
            while True:
                _cancel(cancel)
                block = audio.read(65536, dtype="float32", always_2d=True)
                if not len(block):
                    break
                read += len(block)
                if read > audio.samplerate * 86400:
                    return Result(path, "Not checked", "Decoded audio exceeds the 24-hour safety limit")
            if read == 0 or (read != expected and audio.format != "MP3"):
                return Result(path, "Suspect", f"Incomplete decode: {read} of {expected} frames")
            if read != expected:
                return Result(path, "Decoded",
                              f"Entire stream decoded; MP3 sample count differs from the header estimate "
                              f"({read} read, {expected} estimated). This alone does not establish corruption.")
        return Result(path, "Decoded", "Entire stream read without a reported decoder error")
    except sf.LibsndfileError as error:
        if error.code == 1:
            return Result(path, "Not checked", f"Decoder does not recognize this format: {error}")
        return Result(path, "Suspect", f"Decoder error: {error}")
    except MutagenError as error:
        return Result(path, "Suspect", f"Header error: {error}")
    except OSError as error:
        return Result(path, "Unreadable", str(error))
    except ValueError as error:
        return Result(path, "Suspect", str(error))


def scan(paths: list[str], folder: str, full: bool, progress=None, cancel=None,
         timeout=120, memory_mb=1024) -> list[Result]:
    files = list(paths)
    if folder:
        if not os.path.isdir(folder):
            raise OSError(f"Audio folder does not exist: {folder}")
        files = []

        def walk_error(error):
            raise error

        for root, _dirs, names in os.walk(folder, onerror=walk_error):
            _cancel(cancel)
            files.extend(os.path.join(root, name) for name in sorted(names)
                         if os.path.splitext(name)[1].lower() in EXTENSIONS)
    files = list(dict.fromkeys(os.path.normcase(os.path.abspath(path)) for path in files))
    results = []
    for index, path in enumerate(files):
        _cancel(cancel)
        result = isolated_check(path, full, cancel, timeout, memory_mb)
        results.append(result)
        if progress:
            progress(int((index + 1) * 100 / len(files)), f"{index + 1}/{len(files)}: {path}")
    return results
