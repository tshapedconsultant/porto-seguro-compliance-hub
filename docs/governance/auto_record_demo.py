"""
One-shot governed demo:
  open Edge fullscreen → minimize Cursor → ffmpeg gdigrab desktop →
  continuous VO + clock-synced steps → mux same VO into MP4.

Game Bar is NOT used (it kept capturing Cursor). ffmpeg captures the screen
after Cursor is minimized and Edge covers the monitor.

Usage:
  python docs/governance/auto_record_demo.py
  python docs/governance/auto_record_demo.py --lang es
"""

from __future__ import annotations

import argparse
import atexit
import os
import shutil
import subprocess
import threading
import time
import uuid
import wave
from pathlib import Path

BROWSER_EXES = (
    "msedge.exe",
    "chrome.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
)
CURSOR_MARKERS = ("cursor.exe", "cursor agents", "cursor -", " - cursor")

ROOT = Path(__file__).resolve().parents[2]
AUDIO_EN = ROOT / "_demo_audio" / "en_220"
AUDIO_ES = ROOT / "_demo_audio" / "es_220"
AUDIO_AEPD_EN = ROOT / "_demo_audio" / "en_aepd90"
AUDIO_AEPD_ES = ROOT / "_demo_audio" / "es_aepd90"
CAPTURES = Path.home() / "Videos" / "Captures"
OUT_EN = CAPTURES / "governed-ai-en.mp4"
OUT_ES = CAPTURES / "governed-ai-es.mp4"
OUT_AEPD_EN = CAPTURES / "aepd-eipd-en.mp4"
OUT_AEPD_ES = CAPTURES / "aepd-eipd-es.mp4"
DEMO_URL = "http://localhost:8501/Governed_Decision_Demo"
DEMO_URL_AEPD = "http://localhost:8501/AEPD_EIPD_Demo"
TMP = ROOT / "docs" / "governance" / "_demo_record_tmp"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CUES_EN = [
    ("architecture", "01_intro.mp3"),
    ("architecture", "02_layers.mp3"),
    ("architecture", "03_controls.mp3"),
    ("policy", "04_art5.mp3"),
    ("policy", "05_deny.mp3"),
    ("approval", "06_approval.mp3"),
    ("antireplay", "07_antireplay.mp3"),
    ("redact", "08_redact.mp3"),
    ("audit", "09_audit.mp3"),
    ("tamper", "10_tamper.mp3"),
    ("close", "11_close.mp3"),
    ("close", "12_disclaimer.mp3"),
]
CUES_ES = list(CUES_EN)
CUES_AEPD = [
    ("scope", "01_scope.mp3"),
    ("eipd", "02_eipd.mp3"),
    ("controls", "03_controls.mp3"),
    ("evidence", "04_evidence.mp3"),
    ("register", "05_register.mp3"),
    ("close", "06_close.mp3"),
]


def _log(msg: str) -> None:
    print(f"[auto-demo] {msg}", flush=True)


def _ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    hits = sorted(root.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))
    return str(hits[-1]) if hits else None


def _ffprobe() -> str | None:
    found = shutil.which("ffprobe")
    if found:
        return found
    ff = _ffmpeg()
    if ff:
        cand = Path(ff).with_name("ffprobe.exe")
        if cand.exists():
            return str(cand)
    return None


def _media_duration(path: Path) -> float:
    probe = _ffprobe()
    if probe and path.exists():
        raw = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        try:
            return max(0.1, float((raw.stdout or "").strip() or 0.0))
        except ValueError:
            pass
    if not path.exists():
        return 1.0
    return max(1.0, path.stat().st_size / 16000.0)


def _mci_send(cmd: str) -> int:
    import ctypes

    winmm = ctypes.WinDLL("winmm")
    winmm.mciSendStringW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_void_p,
    ]
    winmm.mciSendStringW.restype = ctypes.c_uint
    return int(winmm.mciSendStringW(cmd, None, 0, None))


_ACTIVE_MCI: list[str] = []


def stop_all_audio() -> None:
    """Silence any leftover MCI / previous take (close all aliases)."""
    _mci_send("stop all")
    _mci_send("close all")
    for alias in list(_ACTIVE_MCI):
        _mci_send(f"stop {alias}")
        _mci_send(f"close {alias}")
    _ACTIVE_MCI.clear()


def play_mp3(path: Path, wait: bool = True) -> float:
    """Play through speakers (so loopback can hear it). Returns duration used."""
    dur = _media_duration(path)
    if not path.exists():
        _log(f"missing audio: {path}")
        return 0.0
    # Never stack clips from a previous crashed run
    stop_all_audio()
    alias = f"porto_vo_{abs(hash(str(path))) & 0xFFFFFFFF:08x}"
    err = _mci_send(f'open "{path}" type mpegvideo alias {alias}')
    if err != 0:
        _log(f"MCI open failed err={err} — startfile fallback")
        os.startfile(str(path))  # noqa: S606
        if wait:
            time.sleep(dur + 0.35)
        return dur
    _ACTIVE_MCI.append(alias)
    _mci_send(f"play {alias}")
    if wait:
        time.sleep(dur + 0.35)
        _mci_send(f"stop {alias}")
        _mci_send(f"close {alias}")
        if alias in _ACTIVE_MCI:
            _ACTIVE_MCI.remove(alias)
    return dur


def _send_vk(vk: int, up: bool) -> None:
    import ctypes
    from ctypes import wintypes

    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _I(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", _I)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.union.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def toggle_game_bar_record() -> None:
    VK_LWIN, VK_LMENU, VK_R = 0x5B, 0xA4, 0x52
    _send_vk(VK_LWIN, False)
    _send_vk(VK_LMENU, False)
    _send_vk(VK_R, False)
    time.sleep(0.05)
    _send_vk(VK_R, True)
    _send_vk(VK_LMENU, True)
    _send_vk(VK_LWIN, True)
    for vk in (0x52, 0xA4, 0x12, 0xA5, 0x5B, 0x5C):
        _send_vk(vk, True)


def ensure_game_dvr() -> None:
    import winreg

    def _dword(path: str, name: str, value: int) -> None:
        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
        finally:
            winreg.CloseKey(key)

    _dword(r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 1)
    _dword(r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameDVR", "AudioCaptureEnabled", 1)
    _dword(r"SYSTEM\GameConfigStore", "GameDVR_Enabled", 1)


def wait_streamlit(timeout: float = 60.0) -> bool:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://localhost:8501", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(1.0)
    return False


def _window_title(hwnd: int) -> str:
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _exe_for_hwnd(hwnd: int) -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value
    finally:
        kernel32.CloseHandle(handle)


def _foreground_title() -> str:
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    return _window_title(int(user32.GetForegroundWindow() or 0))


def _is_cursor_title(title: str) -> bool:
    t = (title or "").strip().lower()
    return any(m in t for m in CURSOR_MARKERS) or t == "cursor" or t.startswith("cursor ")


def _is_browser_exe(exe: str) -> bool:
    name = Path(exe or "").name.lower()
    return name in BROWSER_EXES


def _root_hwnd(hwnd: int) -> int:
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    root = int(user32.GetAncestor(hwnd, 2) or 0)  # GA_ROOT
    return root or hwnd


def _fill_monitor(hwnd: int) -> None:
    """Force the window to cover the primary monitor (ShowWindow maximize often fails on Edge)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = _root_hwnd(hwnd)
    user32.ShowWindow(hwnd, 9)  # restore first
    time.sleep(0.15)
    sw = int(user32.GetSystemMetrics(0))
    sh = int(user32.GetSystemMetrics(1))
    # even sizes help some encoders
    sw -= sw % 2
    sh -= sh % 2
    user32.MoveWindow(hwnd, 0, 0, sw, sh, True)
    user32.ShowWindow(hwnd, 3)  # maximize
    time.sleep(0.2)
    # if still not covering, force MoveWindow again
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        w = int(rect.right) - int(rect.left)
        h = int(rect.bottom) - int(rect.top)
        if w < sw * 0.85 or h < sh * 0.85:
            user32.MoveWindow(hwnd, 0, 0, sw, sh, True)


def _press_key(vk: int) -> None:
    _send_vk(vk, False)
    time.sleep(0.04)
    _send_vk(vk, True)


def _browser_fullscreen(hwnd: int) -> None:
    """F11 after focus — true browser fullscreen for Game Bar."""
    _force_foreground(hwnd)
    _click_titlebar(hwnd)
    time.sleep(0.25)
    _press_key(0x7A)  # VK_F11
    time.sleep(0.6)


def _force_foreground(hwnd: int) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    SWP_NOSIZE, SWP_NOMOVE, SWP_SHOWWINDOW = 0x0001, 0x0002, 0x0040
    HWND_TOPMOST, HWND_NOTOPMOST = -1, -2

    hwnd = _root_hwnd(hwnd)
    user32.ShowWindow(hwnd, 9)  # restore
    user32.ShowWindow(hwnd, 5)  # show
    fg = int(user32.GetForegroundWindow() or 0)

    pid = wintypes.DWORD()
    fg_tid = user32.GetWindowThreadProcessId(fg, ctypes.byref(pid)) if fg else 0
    target_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    cur_tid = kernel32.GetCurrentThreadId()
    if fg_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, True)
    if target_tid and target_tid != fg_tid:
        user32.AttachThreadInput(cur_tid, target_tid, True)
    user32.BringWindowToTop(hwnd)
    user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    )
    user32.SetWindowPos(
        hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    )
    user32.SetForegroundWindow(hwnd)
    _fill_monitor(hwnd)
    if fg_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, False)
    if target_tid and target_tid != fg_tid:
        user32.AttachThreadInput(cur_tid, target_tid, False)


def _click_titlebar(hwnd: int) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = _root_hwnd(hwnd)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return
    x = (int(rect.left) + int(rect.right)) // 2
    y = int(rect.top) + 12
    user32.SetCursorPos(x, y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def _find_browser_hwnd() -> tuple[int, str, str] | None:
    """Return (hwnd, title, exe) for a browser tab showing the demo — never Cursor."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    scored: list[tuple[int, int, str, str]] = []

    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if not title or _is_cursor_title(title):
            return True
        exe = _exe_for_hwnd(hwnd)
        if not _is_browser_exe(exe):
            return True
        tl = title.lower()
        score = 0
        if "localhost:8501" in tl or "governed" in tl or "eipd" in tl or "aepd" in tl:
            score += 100
        if "streamlit" in tl or "laboratorio" in tl:
            score += 40
        if "8501" in tl:
            score += 30
        if score <= 0:
            # browser window without demo title — weak fallback only
            score = 1
        scored.append((score, int(hwnd), title, exe))
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    if best[0] < 30:
        _log(f"weak browser match score={best[0]} title={best[2]!r}")
    return best[1], best[2], best[3]


def _browser_candidates() -> list[Path]:
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    return [
        Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(pf) / "Mozilla Firefox" / "firefox.exe",
    ]


_BROWSER_LAUNCHED = False


def open_step(step: str, lang: str = "en", *, new_window: bool | None = None) -> None:
    global _BROWSER_LAUNCHED
    url = f"{DEMO_URL}?lang={lang}&auto=1&step={step}"
    use_new = _BROWSER_LAUNCHED is False if new_window is None else new_window
    launched = False
    for exe in _browser_candidates():
        if not exe.exists():
            continue
        cmd = [str(exe)]
        if use_new:
            # dedicated window, maximized — Game Bar targets this process
            cmd.extend(
                [
                    "--new-window",
                    "--start-maximized",
                    "--window-position=0,0",
                ]
            )
        cmd.append(url)
        subprocess.Popen(  # noqa: S603
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        launched = True
        _BROWSER_LAUNCHED = True
        break
    if not launched:
        os.startfile(url)  # noqa: S606
        _BROWSER_LAUNCHED = True
    time.sleep(2.4 if use_new else 1.4)
    focus_browser(required=False)


def focus_browser(required: bool = False) -> bool:
    """Bring demo browser to front (never Cursor). Returns True if browser is foreground."""
    try:
        for _ in range(10):
            found = _find_browser_hwnd()
            if not found:
                time.sleep(0.25)
                continue
            hwnd, title, exe = found
            _force_foreground(hwnd)
            _click_titlebar(hwnd)
            time.sleep(0.35)
            fg = _foreground_title()
            if _is_cursor_title(fg):
                _log(f"foreground still Cursor ({fg!r}); retry")
                time.sleep(0.2)
                continue
            if _is_browser_exe(_exe_for_hwnd(int(__import__("ctypes").windll.user32.GetForegroundWindow()))):
                _log(f"browser foreground: {fg!r} ({Path(exe).name})")
                return True
            # title may not update; accept if our hwnd is foreground
            import ctypes

            if int(ctypes.windll.user32.GetForegroundWindow() or 0) == hwnd:
                _log(f"browser hwnd foreground: {title!r}")
                return True
            time.sleep(0.2)
        msg = f"could not put browser in foreground (now: {_foreground_title()!r})"
        _log(msg)
        if required:
            raise RuntimeError(msg)
        return False
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        _log(f"focus_browser skipped: {exc}")
        if required:
            raise
        return False


def minimize_cursor_windows() -> int:
    """Minimize every Cursor IDE window so desktop capture cannot show it."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    n = 0

    def _cb(hwnd, _lp):
        nonlocal n
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        exe = _exe_for_hwnd(hwnd)
        name = Path(exe).name.lower() if exe else ""
        if "cursor" in name or _is_cursor_title(title):
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            n += 1
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    _log(f"minimized Cursor windows: {n}")
    return n


def start_ffmpeg_capture(out_mp4: Path, hwnd: int | None = None) -> subprocess.Popen:
    """Capture the browser window by HWND (preferred) or full desktop fallback.

    Never uses Xbox Game Bar — that kept latching onto Cursor.
    """
    ff = _ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    if out_mp4.exists():
        try:
            out_mp4.unlink()
        except OSError:
            pass

    # Desktop grab after Cursor minimize + Edge fullscreen (hwnd= is flaky on Win11)
    grab_i = "desktop"
    cmd = [
        ff,
        "-y",
        "-f",
        "gdigrab",
        "-framerate",
        "30",
        "-draw_mouse",
        "0",
        "-i",
        grab_i,
        "-vf",
        "scale=1920:-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(out_mp4),
    ]
    err_log = TMP / "ffmpeg_capture.err"
    TMP.mkdir(parents=True, exist_ok=True)
    err_f = open(err_log, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=err_f,
        creationflags=CREATE_NO_WINDOW,
    )
    time.sleep(1.0)
    proc._porto_err = err_f  # type: ignore[attr-defined]
    _log(f"ffmpeg gdigrab START i={grab_i} -> {out_mp4.name} (pid={proc.pid})")
    return proc


def stop_ffmpeg(proc: subprocess.Popen, timeout: float = 20.0) -> None:
    if proc.poll() is not None:
        err_f = getattr(proc, "_porto_err", None)
        if err_f:
            try:
                err_f.close()
            except Exception:
                pass
        return
    try:
        if proc.stdin:
            proc.stdin.write(b"q")
            proc.stdin.flush()
    except Exception:
        pass
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    err_f = getattr(proc, "_porto_err", None)
    if err_f:
        try:
            err_f.close()
        except Exception:
            pass
    _log(f"ffmpeg STOP rc={proc.returncode}")


def allow_gamebar_for_exe(exe_path: str) -> None:
    """Register browser exe so Win+Alt+R targets it (Agent Fail pattern)."""
    if not exe_path:
        return
    import winreg

    children = r"System\GameConfigStore\Children"
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, children)
    except OSError:
        root = winreg.CreateKey(winreg.HKEY_CURRENT_USER, children)
    try:
        count = winreg.QueryInfoKey(root)[0]
        for i in range(count):
            name = winreg.EnumKey(root, i)
            with winreg.OpenKey(root, name) as child:
                try:
                    existing, _ = winreg.QueryValueEx(child, "MatchedExeFullPath")
                except OSError:
                    continue
                if str(existing).lower() == exe_path.lower():
                    return
    finally:
        winreg.CloseKey(root)

    key_path = children + "\\" + str(uuid.uuid4())
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
    try:
        winreg.SetValueEx(key, "Type", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "Revision", 0, winreg.REG_DWORD, 2691)
        winreg.SetValueEx(key, "Flags", 0, winreg.REG_DWORD, 17)
        winreg.SetValueEx(key, "MatchedExeFullPath", 0, winreg.REG_SZ, exe_path)
        winreg.SetValueEx(key, "GameDVR_GameGUID", 0, winreg.REG_SZ, str(uuid.uuid4()))
    finally:
        winreg.CloseKey(key)
    _log(f"Game Bar allowed for {exe_path}")


def arm_game_bar(before: set[str] | None = None) -> bool:
    """Focus + fill screen + F11, register Edge/Chrome, Win+Alt+R, verify capture starts."""
    before = before if before is not None else {p.name for p in CAPTURES.glob("*.mp4")}
    if not focus_browser(required=False):
        _log("ABORT: browser not foreground — refuse to record Cursor")
        return False
    found = _find_browser_hwnd()
    if not found:
        _log("ABORT: no browser hwnd")
        return False
    hwnd, title, exe = found
    hwnd = _root_hwnd(hwnd)
    if _is_cursor_title(_foreground_title()):
        _log(f"ABORT: Cursor still foreground ({_foreground_title()!r})")
        return False

    allow_gamebar_for_exe(exe)
    # also allow ApplicationFrameHost / GameBar helpers sometimes used by Edge
    system = os.environ.get("SystemRoot", r"C:\Windows")
    for extra in (
        str(Path(system) / "System32" / "ApplicationFrameHost.exe"),
        exe,
    ):
        allow_gamebar_for_exe(extra)

    _force_foreground(hwnd)
    _fill_monitor(hwnd)
    _click_titlebar(hwnd)
    time.sleep(0.35)
    try:
        _browser_fullscreen(hwnd)
    except Exception as exc:  # noqa: BLE001
        _log(f"F11 skipped: {exc}")

    fg = _foreground_title()
    if _is_cursor_title(fg):
        _log(f"ABORT: would record Cursor ({fg!r})")
        return False

    def _fresh_ok(path: Path | None) -> bool:
        if path is None or not path.exists():
            return False
        name = path.name.lower()
        # Ignore Cursor IDE dumps — means we toggled STOP on a prior Cursor take
        if "cursor" in name:
            return False
        return True

    def _wait_growing(prior: set[str], timeout: float = 8.0) -> Path | None:
        deadline = time.monotonic() + timeout
        candidate: Path | None = None
        last_size = -1
        while time.monotonic() < deadline:
            fresh = [
                p
                for p in CAPTURES.glob("*.mp4")
                if p.name not in prior and _fresh_ok(p)
            ]
            if fresh:
                candidate = max(fresh, key=lambda p: p.stat().st_mtime)
                try:
                    size = candidate.stat().st_size
                except OSError:
                    time.sleep(0.3)
                    continue
                if size > last_size + 8_000:
                    last_size = size
                    time.sleep(0.6)
                    try:
                        if candidate.stat().st_size >= last_size:
                            return candidate
                    except OSError:
                        pass
                elif size > 30_000 and size == last_size:
                    return candidate
                last_size = size
            time.sleep(0.35)
        return candidate if _fresh_ok(candidate) else None

    _log(f"Game Bar START on browser: {fg!r}")
    CAPTURES.mkdir(parents=True, exist_ok=True)

    # If a Cursor capture appears right after toggle, we likely STOPPED an old take — start again
    toggle_game_bar_record()
    time.sleep(1.0)
    early = [p for p in CAPTURES.glob("*.mp4") if p.name not in before]
    if early and any("cursor" in p.name.lower() for p in early):
        _log("detected Cursor capture file — prior recording was stopped; starting fresh on browser")
        before = {p.name for p in CAPTURES.glob("*.mp4")}
        focus_browser(required=False)
        found2 = _find_browser_hwnd()
        if found2:
            _force_foreground(found2[0])
            _fill_monitor(found2[0])
            _click_titlebar(found2[0])
            time.sleep(0.5)
        if _is_cursor_title(_foreground_title()):
            _log(f"ABORT: Cursor still foreground ({_foreground_title()!r})")
            return False
        toggle_game_bar_record()

    clip = _wait_growing(before, timeout=9.0)
    if clip is None:
        _log("Game Bar no growing browser capture — retry once")
        focus_browser(required=False)
        found2 = _find_browser_hwnd()
        if found2:
            _force_foreground(found2[0])
            _fill_monitor(found2[0])
            _click_titlebar(found2[0])
            time.sleep(0.5)
        if _is_cursor_title(_foreground_title()):
            _log(f"ABORT on retry: Cursor foreground ({_foreground_title()!r})")
            return False
        before = {p.name for p in CAPTURES.glob("*.mp4")}
        toggle_game_bar_record()
        clip = _wait_growing(before, timeout=8.0)

    if clip is None:
        _log(
            "ABORT: Game Bar did not start on the browser. "
            "Focus Edge, press Win+G once, enable capture, then retry."
        )
        return False

    _log(f"Game Bar file started: {clip.name} ({clip.stat().st_size} bytes)")
    return True


def newest_mp4(before: set[str]) -> Path | None:
    found = [
        p
        for p in CAPTURES.glob("*.mp4")
        if p.name not in before
        and p.stat().st_size > 50_000
        and "cursor" not in p.name.lower()
    ]
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


def _loopback_device() -> tuple[int, int, int] | None:
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        _log("pyaudiowpatch missing — will mux VO file instead of loopback")
        return None
    audio = pyaudio.PyAudio()
    try:
        wasapi = audio.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = audio.get_device_info_by_index(wasapi["defaultOutputDevice"])
        loop = speakers if speakers.get("isLoopbackDevice") else None
        if loop is None:
            for dev in audio.get_loopback_device_info_generator():
                if speakers["name"] in dev["name"]:
                    loop = dev
                    break
        if loop is None:
            return None
        index = int(loop["index"])
        rate = int(loop["defaultSampleRate"])
        reported = int(loop["maxInputChannels"] or 0)
        for ch in (2, 1, reported):
            if ch <= 0:
                continue
            stream = None
            try:
                stream = audio.open(
                    format=pyaudio.paInt16,
                    channels=ch,
                    rate=rate,
                    input=True,
                    input_device_index=index,
                    frames_per_buffer=2048,
                )
                stream.close()
                return (index, rate, ch)
            except Exception:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
        return None
    finally:
        audio.terminate()


def _record_loopback(path: Path, stop: threading.Event, device: tuple[int, int, int]) -> None:
    import pyaudiowpatch as pyaudio

    index, rate, channels = device
    audio = pyaudio.PyAudio()
    stream = None
    try:
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=index,
            frames_per_buffer=2048,
        )
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            for _ in range(12):
                stream.read(2048, exception_on_overflow=False)
            while not stop.is_set():
                wav.writeframes(stream.read(2048, exception_on_overflow=False))
        _log(f"loopback wav ready ({path.name})")
    except Exception as exc:  # noqa: BLE001
        _log(f"loopback failed: {exc}")
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        audio.terminate()


def build_vo_track(
    cues: list[tuple[str, str]],
    audio_dir: Path,
    dest: Path,
    lead_s: float = 0.0,
) -> Path:
    """Continuous concat of cue MP3s (no gaps). Optional lead silence for Game Bar head."""
    ff = _ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    TMP.mkdir(parents=True, exist_ok=True)
    list_path = TMP / "concat.txt"
    parts: list[Path] = []
    if lead_s > 0.05:
        lead = TMP / f"silence_lead_{lead_s:.2f}.mp3"
        subprocess.run(
            [
                ff,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                f"{lead_s:.2f}",
                "-q:a",
                "9",
                str(lead),
            ],
            check=False,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )
        if lead.exists():
            parts.append(lead)
    for _step, fname in cues:
        clip = audio_dir / fname
        if clip.exists():
            parts.append(clip)
    if not parts:
        raise RuntimeError("no clips to concat")
    lines = [
        "file '" + p.resolve().as_posix().replace("'", "'\\''") + "'" for p in parts
    ]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rc = subprocess.run(
        [
            ff,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(dest),
        ],
        check=False,
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )
    if rc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"concat VO failed: {(rc.stderr or b'')[:400]!r}")
    return dest


def cue_timeline(
    cues: list[tuple[str, str]], audio_dir: Path
) -> tuple[list[tuple[float, str]], float]:
    """(t_start, step) for each step change + total VO duration."""
    events: list[tuple[float, str]] = []
    t = 0.0
    last: str | None = None
    for step, fname in cues:
        if step != last:
            events.append((t, step))
            last = step
        t += _media_duration(audio_dir / fname)
    return events, t


def set_demo_step(step: str) -> None:
    """Tell page 09 which step to show (polled every ~0.6s when ?auto=1)."""
    TMP.mkdir(parents=True, exist_ok=True)
    step_path = TMP / "current_step.txt"
    # write tmp then replace so readers never see a half write
    tmp = step_path.with_suffix(".tmp")
    tmp.write_text(step.strip().lower() + "\n", encoding="utf-8")
    tmp.replace(step_path)
    _log(f"step file -> {step}")


def navigate_step_fast(step: str, lang: str = "en") -> None:
    """Advance Streamlit step via file poll — no Ctrl+L / tabs."""
    del lang
    set_demo_step(step)
    # Wait long enough for fragment run_every + rerun + auto action
    time.sleep(1.4)
    minimize_cursor_windows()
    focus_browser(required=False)


def mux_audio(video: Path, audio: Path, dest: Path) -> Path:
    ff = _ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg not found")
    tmp = dest.with_name(dest.stem + ".mux.tmp.mp4")
    cmd = [
        ff,
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    rc = subprocess.run(cmd, check=False, capture_output=True, creationflags=CREATE_NO_WINDOW)
    if rc.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 50_000:
        err = (rc.stderr or b"").decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"mux failed: {err}")
    tmp.replace(dest)
    _log(f"muxed audio into {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def copy_capture(src: Path, dest: Path) -> Path:
    CAPTURES.mkdir(parents=True, exist_ok=True)
    stamp = dest.with_name(dest.stem + time.strftime("-%Y%m%d-%H%M%S") + dest.suffix)
    shutil.copy2(src, dest)
    shutil.copy2(src, stamp)
    _log(f"saved {dest}")
    _log(f"saved {stamp}")
    return dest


def run(lang: str, record: bool, voice: bool, profile: str = "governed") -> int:
    """One clock: ffmpeg desktop → continuous VO + step file → mux same VO."""
    global DEMO_URL
    atexit.register(stop_all_audio)
    stop_all_audio()
    if profile == "aepd":
        DEMO_URL = DEMO_URL_AEPD
        audio_dir = AUDIO_AEPD_ES if lang == "es" else AUDIO_AEPD_EN
        cues = list(CUES_AEPD)
        out = OUT_AEPD_ES if lang == "es" else OUT_AEPD_EN
    else:
        DEMO_URL = "http://localhost:8501/Governed_Decision_Demo"
        audio_dir = AUDIO_ES if lang == "es" else AUDIO_EN
        cues = list(CUES_ES if lang == "es" else CUES_EN)
        out = OUT_ES if lang == "es" else OUT_EN
    lead_s = 1.0

    if voice:
        missing = [c for _, c in cues if not (audio_dir / c).exists()]
        if missing:
            full = audio_dir / (
                "narration_en_full.mp3" if lang == "en" else "narration_es_full.mp3"
            )
            if not full.exists():
                _log(f"missing clips: {missing[:3]}...")
                return 2
            # single file: use playbook wall-clock step table
            cues = [("architecture", full.name)]
            _log(f"using single narration {full.name}")

    if not wait_streamlit(45):
        _log("Streamlit not reachable on :8501")
        return 3
    if _ffmpeg() is None:
        _log("WARNING: ffmpeg not found — cannot mux VO into MP4")

    # Continuous VO for speakers + mux (identical timeline)
    vo_play: Path | None = None
    vo_mux: Path | None = None
    events: list[tuple[float, str]] = []
    total_vo = 0.0

    if voice and len(cues) > 1:
        events, total_vo = cue_timeline(cues, audio_dir)
        try:
            vo_play = build_vo_track(cues, audio_dir, TMP / f"vo_{lang}_play.mp3", lead_s=0.0)
            vo_mux = build_vo_track(
                cues, audio_dir, TMP / f"vo_{lang}_mux.mp3", lead_s=lead_s
            )
            _log(
                f"synced timeline: {len(events)} steps, VO={total_vo:.1f}s, lead={lead_s:.1f}s"
            )
            for t_rel, step in events:
                _log(f"  t={t_rel:6.1f}s  -> {step}")
        except Exception as exc:  # noqa: BLE001
            _log(f"VO build failed: {exc}")
            return 2
    elif voice and len(cues) == 1:
        vo_play = audio_dir / cues[0][1]
        total_vo = _media_duration(vo_play)
        # Playbook absolute offsets (seconds from VO start)
        events = [
            (0.0, "architecture"),
            (20.0, "policy"),
            (45.0, "approval"),
            (75.0, "antireplay"),
            (95.0, "redact"),
            (115.0, "audit"),
            (135.0, "tamper"),
            (145.0, "close"),
        ]
        events = [(t, s) for t, s in events if t < total_vo]
        try:
            vo_mux = build_vo_track(
                cues, audio_dir, TMP / f"vo_{lang}_mux.mp3", lead_s=lead_s
            )
        except Exception:
            vo_mux = vo_play

    global _BROWSER_LAUNCHED
    _BROWSER_LAUNCHED = False

    first_step = events[0][1] if events else "architecture"
    set_demo_step(first_step)
    open_step(first_step, lang, new_window=True)
    if not focus_browser(required=False):
        open_step(first_step, lang, new_window=True)
        focus_browser(required=False)

    found = _find_browser_hwnd()
    if found:
        hwnd, _title, _exe = found
        _force_foreground(hwnd)
        _fill_monitor(hwnd)
        try:
            _browser_fullscreen(hwnd)
        except Exception as exc:  # noqa: BLE001
            _log(f"F11 skipped: {exc}")
    minimize_cursor_windows()
    focus_browser(required=False)
    time.sleep(0.6)

    ff_proc: subprocess.Popen | None = None
    raw_mp4 = TMP / f"desktop_{lang}_{time.strftime('%H%M%S')}.mp4"
    if record:
        TMP.mkdir(parents=True, exist_ok=True)
        if _is_cursor_title(_foreground_title()):
            _log("Cursor stole focus — minimizing again and re-focusing Edge")
            minimize_cursor_windows()
            focus_browser(required=False)
            time.sleep(0.4)
        if _is_cursor_title(_foreground_title()):
            _log(f"ABORT: cannot keep Edge in front ({_foreground_title()!r})")
            return 5
        hwnd_cap = _root_hwnd(found[0]) if found else None
        try:
            ff_proc = start_ffmpeg_capture(raw_mp4, hwnd=hwnd_cap)
        except Exception as exc:  # noqa: BLE001
            _log(f"ffmpeg start failed: {exc}")
            return 5
        if ff_proc.poll() is not None:
            _log("ABORT: ffmpeg exited immediately — check _demo_record_tmp/ffmpeg_capture.err")
            return 5
        _log(f"lead-in {lead_s:.1f}s (matches mux pad)")
        time.sleep(lead_s)

    # --- single clock for VO + UI ---
    try:
        if voice and vo_play and vo_play.exists():
            _log(f"VO START ({vo_play.name})")
            play_mp3(vo_play, wait=False)
            t0 = time.monotonic()
            for t_rel, step in events:
                if t_rel <= 0.05:
                    continue
                wait_for = t0 + t_rel - time.monotonic()
                if wait_for > 0:
                    time.sleep(wait_for)
                if _is_cursor_title(_foreground_title()):
                    minimize_cursor_windows()
                _log(f"[{time.monotonic() - t0:5.1f}s] step -> {step}")
                navigate_step_fast(step, lang)
            left = (t0 + total_vo) - time.monotonic()
            if left > 0:
                time.sleep(left + 0.4)
            stop_all_audio()
        else:
            silent_steps = [s for s, _ in cues] if cues else ["scope"]
            seen: set[str] = set()
            for step in silent_steps:
                if step in seen:
                    continue
                seen.add(step)
                navigate_step_fast(step, lang)
                time.sleep(4.0)
        time.sleep(0.5)
    finally:
        stop_all_audio()
        if ff_proc is not None:
            stop_ffmpeg(ff_proc)

    if record:
        if not raw_mp4.exists() or raw_mp4.stat().st_size < 100_000:
            _log("ABORT: ffmpeg produced no usable video")
            return 4

        audio_src = vo_mux if vo_mux and vo_mux.exists() else vo_play
        final = raw_mp4
        if audio_src is not None and _ffmpeg():
            _log(f"mux VO timeline -> {audio_src.name}")
            muxed = TMP / f"{profile}-{lang}-muxed.mp4"
            try:
                mux_audio(raw_mp4, audio_src, muxed)
                final = muxed
            except Exception as exc:  # noqa: BLE001
                _log(f"mux failed, keeping silent desktop capture: {exc}")
        else:
            _log("WARNING: no VO to mux")

        copy_capture(final, out)
        _log(f"DONE -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    else:
        _log("DONE (no record)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=("en", "es"), default="en")
    ap.add_argument("--profile", choices=("governed", "aepd"), default="governed")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--no-voice", action="store_true")
    args = ap.parse_args()
    return run(
        args.lang,
        record=not args.no_record,
        voice=not args.no_voice,
        profile=args.profile,
    )


if __name__ == "__main__":
    raise SystemExit(main())
