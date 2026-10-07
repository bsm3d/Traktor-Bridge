# Benoit Saint-Moulin
# Traktor Bridge : the USB drives that can be formatted, and the formatting itself

"""Windows: diskpart cleans the drive, fat32.py writes MBR + FAT32 on the raw drive (no 32 GB
limit), Windows then mounts the new volume. Linux and macOS use the same FAT32 writer on the raw
device, with their native tools only for unmounting, partition refresh and mounting.
Raw access needs administrator rights: the writing is done by this program started again
(--format-disk) through UAC, osascript or pkexec, and it checks the drive again before writing.

Only USB / SD drives are listed, never the one Windows or the system runs from, never the one
this program runs from."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field

from . import fat32, settings

log = logging.getLogger(__name__)

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
BUSES = {"USB", "SD", "MMC", "SDHC"}
PROGRESS_PREFIX = "tb_format_"
HELPER_FLAG = "--format-disk"


@dataclass
class Drive:
    id: str                     # disk number on Windows, device path elsewhere
    name: str
    size: int
    bps: int = 512
    serial: str = ""
    style: str = ""             # MBR, GPT or RAW
    mounts: list[str] = field(default_factory=list)     # E:\ or /media/x
    volumes: list[str] = field(default_factory=list)    # what is on it, for the confirmation

    @property
    def title(self) -> str:
        where = ", ".join(self.mounts)
        return f"{where + '  ' if where else ''}{self.name or 'USB drive'}  ({gigabytes(self.size)})"


def gigabytes(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n < 1e12 else f"{n / 1e12:.2f} TB"


def plain(s: str) -> str:
    """Serial numbers of cheap keys can be binary noise: keep ASCII letters and digits only."""
    return "".join(c for c in s if c.isascii() and c.isalnum())


def run(cmd: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          creationflags=NO_WINDOW, check=False)


def is_admin() -> bool:
    if sys.platform == "win32":
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    return os.geteuid() == 0


def running_from() -> str:
    return os.path.normcase(os.path.abspath(str(settings.app_dir())))


# ---- listing

WIN_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @()
foreach ($d in Get-Disk) {
  $vols = @()
  foreach ($p in @(Get-Partition -DiskNumber $d.Number)) {
    $v = $p | Get-Volume
    if ($v) { $vols += [pscustomobject]@{ Letter = [string]$v.DriveLetter; FS = [string]$v.FileSystem;
                                          Label = [string]$v.FileSystemLabel; Size = [int64]$v.Size } }
  }
  $out += [pscustomobject]@{ Number = $d.Number; Name = [string]$d.FriendlyName; Size = [int64]$d.Size;
    Bus = [string]$d.BusType; System = [bool]$d.IsSystem; Boot = [bool]$d.IsBoot; Style = [string]$d.PartitionStyle;
    Sector = [int]$d.LogicalSectorSize; Serial = ([string]$d.SerialNumber).Trim(); ReadOnly = [bool]$d.IsReadOnly;
    Vols = $vols }
}
ConvertTo-Json -InputObject @($out) -Depth 4 -Compress
"""


def describe(fs: str, label: str, size: int) -> str:
    return f"{label or 'no name'} ({fs or 'unknown file system'}, {gigabytes(size)})"


def list_windows() -> list[Drive]:
    r = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", WIN_SCRIPT], timeout=90)
    if r.returncode != 0 or not r.stdout.strip():
        raise OSError(f"Cannot list the drives: {r.stderr.strip() or r.stdout.strip() or r.returncode}")
    found = []
    for d in json.loads(r.stdout):
        if d["Bus"].upper() not in BUSES or d["System"] or d["Boot"] or d["Size"] <= 0 or d["ReadOnly"]:
            continue
        vols = d["Vols"] if isinstance(d["Vols"], list) else [d["Vols"]]
        found.append(Drive(
            str(d["Number"]), d["Name"], d["Size"], d["Sector"] or 512, plain(d["Serial"]), d["Style"],
            [v["Letter"] + ":\\" for v in vols if v["Letter"]],
            [describe(v["FS"], v["Label"], v["Size"]) for v in vols]))
    return found


def list_linux() -> list[Drive]:
    cols = "NAME,PATH,SIZE,TYPE,TRAN,RM,HOTPLUG,MODEL,VENDOR,SERIAL,FSTYPE,LABEL,MOUNTPOINT,PTTYPE,LOG-SEC"
    r = run(["lsblk", "-J", "-b", "-o", cols])
    if r.returncode != 0:
        raise OSError(f"Cannot list the drives: {r.stderr.strip()}")
    found = []
    for d in json.loads(r.stdout)["blockdevices"]:
        if d.get("type") != "disk" or not (d.get("tran") in ("usb", "mmc") or d.get("rm") in (True, "1", 1)
                                           or d.get("hotplug") in (True, "1", 1)):
            continue
        kids = d.get("children") or []
        mounts = [k["mountpoint"] for k in [d, *kids] if k.get("mountpoint")]
        if int(d.get("size") or 0) <= 0 or any(m in ("/", "/boot", "/boot/efi", "/home", "/usr", "/var") for m in mounts):
            continue
        name = " ".join(x.strip() for x in (d.get("vendor"), d.get("model")) if x and x.strip())
        found.append(Drive(
            d["path"], name, int(d["size"]), int(d.get("log-sec") or 512), plain(d.get("serial") or ""),
            (d.get("pttype") or "RAW").upper(), mounts,
            [describe(k.get("fstype") or "", k.get("label") or "", int(k.get("size") or 0)) for k in kids]))
    return found


def list_mac() -> list[Drive]:
    r = subprocess.run(["diskutil", "list", "-plist", "external", "physical"],
                       capture_output=True, check=False, timeout=60)
    if r.returncode != 0:
        raise OSError(f"Cannot list the drives: {r.stderr.decode(errors='replace').strip()}")
    found = []
    for d in plistlib.loads(r.stdout).get("AllDisksAndPartitions", []):
        dev = d["DeviceIdentifier"]
        i = subprocess.run(["diskutil", "info", "-plist", dev], capture_output=True, check=False, timeout=60)
        info = plistlib.loads(i.stdout) if i.returncode == 0 else {}
        if info.get("Internal") or info.get("SystemImage") or info.get("VirtualOrPhysical") == "Virtual":
            continue
        parts = d.get("Partitions", [])
        found.append(Drive(
            f"/dev/{dev}", info.get("MediaName", ""), int(d.get("Size", 0)), int(info.get("DeviceBlockSize", 512)),
            "", info.get("Content", ""), [p["MountPoint"] for p in parts if p.get("MountPoint")],
            [describe(p.get("Content", ""), p.get("VolumeName", ""), int(p.get("Size", 0))) for p in parts]))
    return found


def list_drives(progress=None, cancel=None) -> list[Drive]:
    """The drives that can be formatted. Also the Job entry point of the dialog."""
    found = {"win32": list_windows, "darwin": list_mac}.get(sys.platform, list_linux)()
    here = running_from()
    return [d for d in found if not any(here.startswith(os.path.normcase(m)) for m in d.mounts if m)]


def drive_for(path: str, progress=None, cancel=None) -> Drive | None:
    """The listed drive that holds path, None for a folder on an internal disk or a network share."""
    here = os.path.normcase(os.path.abspath(path))
    for d in {"win32": list_windows, "darwin": list_mac}.get(sys.platform, list_linux)():
        for m in d.mounts:
            m = os.path.normcase(os.path.abspath(m))
            if here == m or here.startswith(m.rstrip("\\/") + os.sep):
                return d
    return None


# ---- ejecting

def eject_windows(mount: str) -> None:
    """Flush, lock and dismount the volume, then ask the drive to eject: what Safely Remove does."""
    import ctypes
    import time
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                              ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    k.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                  ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
    k.FlushFileBuffers.argtypes = [ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k.CreateFileW("\\\\.\\" + mount.rstrip("\\/"), 0xC0000000, 3, None, 3, 0, None)
    if h in (None, ctypes.c_void_p(-1).value):
        raise OSError(f"Cannot open {mount}: error {ctypes.get_last_error()}")
    try:
        got = ctypes.c_ulong(0)

        def ioctl(code: int, buf=None, size: int = 0) -> bool:
            return bool(k.DeviceIoControl(h, code, buf, size, None, 0, ctypes.byref(got), None))

        k.FlushFileBuffers(h)
        for _ in range(10):
            if ioctl(0x90018):          # FSCTL_LOCK_VOLUME
                break
            time.sleep(0.5)
        else:
            raise OSError(f"{mount} is still in use: close what is reading it (a player, a window) and try again")
        ioctl(0x90020)                  # FSCTL_DISMOUNT_VOLUME
        allow = ctypes.c_ubyte(0)       # PREVENT_MEDIA_REMOVAL.PreventMediaRemoval = FALSE
        ioctl(0x2D4804, ctypes.byref(allow), 1)
        ioctl(0x2D4808)                 # IOCTL_STORAGE_EJECT_MEDIA, a key that cannot eject is still safe to pull
    finally:
        k.CloseHandle(h)


def eject(d: Drive, progress=None, cancel=None) -> str:
    """Safely removes the drive (Job entry point), returns its title."""
    if progress:
        progress(0, "Ejecting")
    if sys.platform == "win32":
        for m in d.mounts:
            eject_windows(m)
    elif sys.platform == "darwin":
        r = run(["diskutil", "eject", d.id])
        if r.returncode != 0:
            raise OSError(r.stdout.strip() or r.stderr.strip() or "diskutil could not eject the drive")
    else:
        for m in d.mounts:
            src = run(["findmnt", "-n", "-o", "SOURCE", m]).stdout.strip()
            r = run(["udisksctl", "unmount", "-b", src]) if src else run(["umount", m])
            if r.returncode != 0:
                raise OSError(r.stderr.strip() or r.stdout.strip() or f"Cannot unmount {m}, it is in use")
        run(["udisksctl", "power-off", "-b", d.id])
    log.info("ejected %s (%s)", d.id, d.name)
    return d.title


# ---- formatting

def rescan_windows(dev, n: str):
    """Tells Windows the partition table changed, it mounts the new volume by itself."""
    import ctypes
    import msvcrt
    handle = msvcrt.get_osfhandle(dev.f.fileno())
    got = ctypes.c_ulong(0)
    ctypes.windll.kernel32.DeviceIoControl(ctypes.c_void_p(handle), 0x70140, None, 0, None, 0, ctypes.byref(got), None)


def drive_letter(n: str) -> str:
    """The letter of the new volume, assigned when Windows did not."""
    script = (f"$p = Get-Partition -DiskNumber {int(n)} | Select-Object -First 1; "
              "if ($p -and -not $p.DriveLetter) { $p | Add-PartitionAccessPath -AssignDriveLetter }; "
              f"(Get-Partition -DiskNumber {int(n)} | Select-Object -First 1).DriveLetter")
    for _ in range(10):
        r = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=60)
        letter = r.stdout.strip()[-1:]
        if letter.isalpha():
            return letter.upper() + ":\\"
        threading.Event().wait(1)
    return ""


def format_windows(d: Drive, label: str, progress) -> str:
    progress(2, "Cleaning the drive")
    script = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)  # noqa: SIM115
    with script:
        script.write(f"select disk {int(d.id)}\nattributes disk clear readonly noerr\nonline disk noerr\nclean\n")
    try:
        r = run(["diskpart", "/s", script.name], timeout=180)
    finally:
        os.unlink(script.name)
    if r.returncode != 0:
        raise OSError(f"diskpart could not clean the drive:\n{r.stdout.strip()}")
    dev = fat32.RawDevice(rf"\\.\PhysicalDrive{int(d.id)}")
    try:
        fat32.format_disk(dev, d.size, d.bps, label, progress=lambda p, m: progress(5 + p * 85 // 100, m))
        rescan_windows(dev, d.id)
    finally:
        dev.close()
    progress(92, "Mounting the new volume")
    return drive_letter(d.id)


def partition_node(dev: str) -> str:
    return dev + ("p1" if dev[-1].isdigit() else "1")


def format_linux(d: Drive, label: str, progress) -> str:
    progress(2, "Unmounting")
    r = run(["lsblk", "-ln", "-o", "PATH,MOUNTPOINT", d.id])
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and run(["umount", parts[0]]).returncode != 0:
            raise OSError(f"Cannot unmount {parts[0]}: close what uses {parts[1]}")
    dev = fat32.RawDevice(d.id)
    try:
        fat32.format_disk(dev, d.size, d.bps, label, progress=lambda p, m: progress(5 + p * 85 // 100, m))
    finally:
        dev.close()
    progress(92, "Reading the new partition table")
    run(["blockdev", "--rereadpt", d.id])
    run(["udevadm", "settle"], timeout=30)
    return partition_node(d.id)


def mac_raw_device(d: Drive) -> str:
    """Translate a listed whole disk to its unbuffered macOS device node."""
    if not re.fullmatch(r"/dev/disk\d+", d.id):
        raise OSError(f"Not a whole macOS disk: {d.id}")
    return d.id.replace("/dev/disk", "/dev/rdisk", 1)


def mac_mountpoint(d: Drive) -> str:
    """Return the first mounted volume on a refreshed disk, when macOS mounted it."""
    refreshed = next((disk for disk in list_mac() if disk.id == d.id), None)
    return refreshed.mounts[0] if refreshed and refreshed.mounts else ""


def format_mac(d: Drive, label: str, progress) -> str:
    """Use the shared FAT32 writer; diskutil only handles macOS volume lifecycle."""
    progress(2, "Unmounting the drive")
    r = run(["diskutil", "unmountDisk", d.id], timeout=180)
    if r.returncode != 0:
        raise OSError(f"diskutil could not unmount the drive:\n{r.stdout.strip()}\n{r.stderr.strip()}")
    dev = fat32.RawDevice(mac_raw_device(d))
    try:
        fat32.format_disk(
            dev, d.size, d.bps, label,
            progress=lambda pct, msg: progress(5 + pct * 85 // 100, msg),
        )
    finally:
        dev.close()
    progress(92, "Mounting the new volume")
    r = run(["diskutil", "mountDisk", d.id], timeout=180)
    if r.returncode != 0:
        raise OSError(
            "The drive was formatted, but macOS could not mount it:\n"
            f"{r.stdout.strip()}\n{r.stderr.strip()}"
        )
    return mac_mountpoint(d)


def do_format(d: Drive, label: str, progress) -> str:
    if sys.platform == "win32":
        return format_windows(d, label, progress)
    if sys.platform == "darwin":
        return format_mac(d, label, progress)
    return format_linux(d, label, progress)


def check(d: Drive) -> Drive:
    """The drive as it is now: it must still be listed, with the same size and serial."""
    for now in list_drives():
        if now.id == d.id:
            if now.size != d.size or now.serial != d.serial:
                raise OSError("The drive changed since it was listed, list the drives again")
            return now
    raise OSError("The drive is no longer there, or it is not one that can be formatted")


# ---- the privileged helper

def open_progress(path: str, owner: str = ""):
    """The file the caller made for the progress lines: it must exist, be a plain file, be named
    for us and belong to the caller when the helper is elevated."""
    if not os.path.basename(path).startswith(PROGRESS_PREFIX):
        raise OSError("Bad progress file")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
    st = os.fstat(fd)
    uid = owner or os.environ.get("PKEXEC_UID")
    if not os.path.isfile(path) or (uid and st.st_uid != int(uid)):
        os.close(fd)
        raise OSError("Bad progress file")
    return os.fdopen(fd, "w", encoding="utf-8")


def helper_main(argv: list[str]) -> int:
    """TraktorBridge --format-disk ID --size N --serial S --label L --progress FILE [--owner UID]"""
    def opt(name: str) -> str:
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else ""

    with open_progress(opt("--progress"), opt("--owner")) as out:
        def say(kind: str, msg: str):
            out.write(f"{kind}|{msg.replace(chr(10), ' ')}\n")
            out.flush()

        try:
            d = check(Drive(opt("--format-disk"), "", int(opt("--size")), serial=opt("--serial")))
            say("pct:2", "Starting")
            res = do_format(d, opt("--label"), lambda p, m: say(f"pct:{p}", m))
        except Exception as e:
            log.exception("format failed")
            say("fail", f"{e}")
            return 1
        say("done", res)
        return 0


def relay(path: str, pos: int, progress) -> tuple[int, str, str]:
    """New lines of the helper's file: returns the position, the result kind and its text."""
    kind = text = ""
    with open(path, encoding="utf-8", errors="replace") as f:
        f.seek(pos)
        data = f.read()
        pos = f.tell()
    for line in data.splitlines():
        k, _, msg = line.partition("|")
        if k.startswith("pct:"):
            progress(int(k[4:]), msg)
        else:
            kind, text = k, msg
    return pos, kind, text


def helper_args(d: Drive, label: str, path: str) -> list[str]:
    owner = str(os.getuid()) if hasattr(os, "getuid") else ""
    return [HELPER_FLAG, d.id, "--size", str(d.size), "--serial", d.serial, "--label", label,
            "--progress", path, "--owner", owner]


def applescript_string(value: str) -> str:
    """Quote a value as an AppleScript string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def launch_elevated(args: list[str]):
    """Starts this program again with administrator rights, returns what waits for its end."""
    frozen = getattr(sys, "frozen", False)
    exe = sys.executable
    full = args if frozen else ["-m", "traktor_bridge", *args]
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Info(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                        ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                        ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                        ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                        ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

        info = Info()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = 0x40                       # SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = "runas"
        info.lpFile = exe
        info.lpParameters = subprocess.list2cmdline(full)
        info.lpDirectory = str(settings.app_dir())
        info.nShow = 0
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)) or not info.hProcess:
            raise PermissionError("Administrator rights are needed to format a drive, and were refused")
        return info.hProcess
    if sys.platform == "darwin":
        import shlex

        command = f"PYTHONPATH={shlex.quote(str(settings.app_dir()))} exec {shlex.join([exe, *full])}"
        script = f"do shell script {applescript_string(command)} with administrator privileges"
        return subprocess.Popen(["osascript", "-e", script])
    cmd = ["pkexec", "env", f"PYTHONPATH={settings.app_dir()}", exe, *full] if not frozen else ["pkexec", exe, *full]
    return subprocess.Popen(cmd)


def wait_elevated(handle, step) -> int:
    """Waits for the process, calling step() every 300 ms, returns its exit code."""
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        try:
            while k.WaitForSingleObject(handle, 300) == 0x102:      # WAIT_TIMEOUT
                step()
            code = ctypes.c_ulong(1)
            k.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value
        finally:
            k.CloseHandle(handle)
    try:
        while handle.poll() is None:
            step()
            threading.Event().wait(0.3)
    except BaseException:
        handle.wait()
        raise
    return handle.returncode


def format_drive(d: Drive, label: str, progress=None, cancel=None) -> str:
    """Formats the drive FAT32 / MBR and returns where it is mounted ('' when that is not known).
    A Job entry point: progress(pct, text)."""
    cb = progress or (lambda pct, msg: None)
    d = check(d)
    label = fat32.clean_label(label)
    log.info("format %s (%s, %s) as FAT32 '%s'", d.id, d.name, gigabytes(d.size), label)
    if is_admin():
        res = do_format(d, label, cb)
    else:
        fd, path = tempfile.mkstemp(prefix=PROGRESS_PREFIX, suffix=".log")
        os.close(fd)
        state = {"pos": 0, "kind": "", "text": ""}

        def step():
            state["pos"], k, t = relay(path, state["pos"], cb)
            if k:
                state["kind"], state["text"] = k, t

        try:
            code = wait_elevated(launch_elevated(helper_args(d, label, path)), step)
            step()
        finally:
            with contextlib.suppress(OSError):
                os.unlink(path)
        if state["kind"] != "done":
            raise OSError(state["text"] or f"The formatting stopped (code {code})")
        res = state["text"]
    if sys.platform.startswith("linux"):
        res = mount_linux(res) or res
    cb(100, "Done")
    return res


def mount_linux(part: str) -> str:
    """Mounts the new partition for the user (udisks), '' when that is not possible."""
    r = run(["udisksctl", "mount", "-b", part], timeout=30)
    m = re.search(r" at (.+?)\.?\s*$", r.stdout)
    return m.group(1) if r.returncode == 0 and m else ""
