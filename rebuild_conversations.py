#!/usr/bin/env python3
"""
Antigravity Conversation Recovery
=============================
Rebuilds the Antigravity conversation index so all your chat history
appears correctly — sorted by date (newest first) with proper titles.
"""

import sys
import os

if sys.version_info[0] < 3:
    try:
        sys.stdout.flush()
        os.execvp("python3", ["python3"] + sys.argv)
    except OSError:
        sys.stderr.write(
            "ERROR: This script requires Python 3.7+.\n"
            "       'python' on this system is Python {}.{}, and 'python3' was not found.\n"
            "       Please install Python 3: https://www.python.org/downloads/\n"
            .format(sys.version_info[0], sys.version_info[1])
        )
        sys.exit(1)

if sys.version_info < (3, 7):
    sys.stderr.write(
        "ERROR: This script requires Python 3.7+, but you are running Python {}.{}.\n"
        "       Please upgrade: https://www.python.org/downloads/\n"
        .format(sys.version_info[0], sys.version_info[1])
    )
    sys.exit(1)

import sqlite3
import base64
import json
import re
import time
import subprocess
import platform
import webbrowser
from urllib.parse import quote, unquote
from urllib.request import urlopen, Request

_CURRENT_VERSION = "1.0"
_GITHUB_REPO = "khalidsaifullah-ks/antigravity-converstation-recovery"
_RELEASES_URL = f"https://github.com/{_GITHUB_REPO}/releases/latest"

# ─── Terminal Styling ────────────────────────────────────────────────────────
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_DIM = "\033[2m"
CLR_RED = "\033[31m"
CLR_GREEN = "\033[32m"
CLR_YELLOW = "\033[33m"
CLR_BLUE = "\033[34m"
CLR_MAGENTA = "\033[35m"
CLR_CYAN = "\033[36m"
CLR_WHITE = "\033[37m"

_SYSTEM = platform.system()

def _enable_ansi_and_colors():
    global CLR_RESET, CLR_BOLD, CLR_DIM, CLR_RED, CLR_GREEN, CLR_YELLOW, CLR_BLUE, CLR_MAGENTA, CLR_CYAN, CLR_WHITE
    
    use_color = sys.stdout.isatty()
    if _SYSTEM == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hOut = kernel32.GetStdHandle(-11)
            if hOut != -1:
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(hOut, ctypes.byref(mode)):
                    if kernel32.SetConsoleMode(hOut, mode.value | 0x0004):
                        use_color = True
                    else:
                        use_color = False
                else:
                    use_color = False
            else:
                use_color = False
        except Exception:
            use_color = False
            
    if not use_color:
        CLR_RESET = ""
        CLR_BOLD = ""
        CLR_DIM = ""
        CLR_RED = ""
        CLR_GREEN = ""
        CLR_YELLOW = ""
        CLR_BLUE = ""
        CLR_MAGENTA = ""
        CLR_CYAN = ""
        CLR_WHITE = ""

# ─── Path Detection ──────────────────────────────────────────────────────────
# Antigravity was renamed to "Antigravity IDE" in a recent update.
# We check the new name first, then fall back to the old name so the tool
# works on both old and new installations.

_ANTIGRAVITY_NAMES = ("Antigravity IDE", "antigravity", "Antigravity")

def _is_wsl():
    """Detect if running inside Windows Subsystem for Linux."""
    if _SYSTEM != "Linux":
        return False
    if "microsoft" in platform.release().lower():
        return True
    try:
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                return True
    except Exception:
        pass
    return False

_IS_WSL = _is_wsl()

def _get_wsl_windows_appdata():
    """
    Resolve the Windows %APPDATA% path from inside WSL.
    Strategy 1: Ask Windows directly via cmd.exe and convert with wslpath.
    Strategy 2: Scan /mnt/c/Users/ for user folders that have Antigravity installed.
    Returns a WSL-accessible path string, or None if resolution fails.
    """
    # Strategy 1: cmd.exe %APPDATA% → wslpath
    try:
        proc = subprocess.run(
            ['cmd.exe', '/c', 'echo %APPDATA%'],
            capture_output=True, text=True, check=True
        )
        win_path = proc.stdout.strip()
        if win_path and win_path != "%APPDATA%":
            proc_wsl = subprocess.run(
                ['wslpath', win_path],
                capture_output=True, text=True, check=True
            )
            wsl_path = proc_wsl.stdout.strip()
            if os.path.exists(wsl_path):
                return wsl_path
    except Exception:
        pass

    # Strategy 2: Scan /mnt/c/Users/ for user folders that have Antigravity
    if os.path.exists("/mnt/c/Users"):
        _skip = {"Default", "Default User", "All Users", "desktop.ini", "Public"}
        try:
            for user in os.listdir("/mnt/c/Users"):
                if user in _skip:
                    continue
                appdata = os.path.join("/mnt/c/Users", user, "AppData", "Roaming")
                if not os.path.exists(appdata):
                    continue
                for name in _ANTIGRAVITY_NAMES:
                    if os.path.exists(os.path.join(appdata, name)):
                        return appdata
        except Exception:
            pass

    return None

def _first_existing(*candidates):
    """Return the first path that exists on disk, or the first candidate if none exist."""
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]

def _existing_paths(*candidates):
    """Return all candidate paths that exist on disk, preserving order."""
    return [p for p in candidates if p and os.path.exists(p)]

if _SYSTEM == "Windows":
    _appdata = os.path.expandvars(r"%APPDATA%")
    _profile = os.path.expandvars(r"%USERPROFILE%")
    _gemini = os.path.join(_profile, ".gemini")

    _DB_CANDIDATES = (
        os.path.join(_appdata, "Antigravity IDE", "User", "globalStorage", "state.vscdb"),
        os.path.join(_appdata, "antigravity", "User", "globalStorage", "state.vscdb"),
        os.path.join(_appdata, "Antigravity", "User", "globalStorage", "state.vscdb"),
    )
    DB_PATH = _first_existing(*_DB_CANDIDATES)
    CONVERSATIONS_DIR = _first_existing(
        os.path.join(_gemini, "antigravity-ide", "conversations"),
        os.path.join(_gemini, "antigravity", "conversations"),
    )
    BRAIN_DIR = _first_existing(
        os.path.join(_gemini, "antigravity-ide", "brain"),
        os.path.join(_gemini, "antigravity", "brain"),
    )
    WORKSPACE_STORAGE_DIR = _first_existing(
        os.path.join(_appdata, "Antigravity IDE", "User", "workspaceStorage"),
        os.path.join(_appdata, "antigravity", "User", "workspaceStorage"),
    )
    _ALL_CONV_DIRS = [
        os.path.join(_gemini, "antigravity-ide", "conversations"),
        os.path.join(_gemini, "antigravity", "conversations"),
        os.path.join(_gemini, "antigravity-backup", "conversations"),
    ]
    _ALL_BRAIN_DIRS = [
        os.path.join(_gemini, "antigravity-ide", "brain"),
        os.path.join(_gemini, "antigravity", "brain"),
        os.path.join(_gemini, "antigravity-backup", "brain"),
    ]
elif _IS_WSL:
    _wsl_appdata = _get_wsl_windows_appdata()
    _home = os.path.expanduser("~")

    if _wsl_appdata:
        _DB_CANDIDATES = (
            os.path.join(_wsl_appdata, "Antigravity IDE", "User", "globalStorage", "state.vscdb"),
            os.path.join(_wsl_appdata, "antigravity", "User", "globalStorage", "state.vscdb"),
            os.path.join(_wsl_appdata, "Antigravity", "User", "globalStorage", "state.vscdb"),
        )
        DB_PATH = _first_existing(*_DB_CANDIDATES)
        WORKSPACE_STORAGE_DIR = _first_existing(
            os.path.join(_wsl_appdata, "Antigravity IDE", "User", "workspaceStorage"),
            os.path.join(_wsl_appdata, "antigravity", "User", "workspaceStorage"),
            os.path.join(_wsl_appdata, "Antigravity", "User", "workspaceStorage"),
        )
    else:
        _DB_CANDIDATES = ()
        DB_PATH = ""
        WORKSPACE_STORAGE_DIR = ""

    CONVERSATIONS_DIR = _first_existing(
        os.path.join(_home, ".gemini", "antigravity-ide", "conversations"),
        os.path.join(_home, ".gemini", "antigravity", "conversations"),
    )
    BRAIN_DIR = _first_existing(
        os.path.join(_home, ".gemini", "antigravity-ide", "brain"),
        os.path.join(_home, ".gemini", "antigravity", "brain"),
    )
    _gemini_wsl = os.path.join(_home, ".gemini")
    _ALL_CONV_DIRS = [
        os.path.join(_gemini_wsl, "antigravity-ide", "conversations"),
        os.path.join(_gemini_wsl, "antigravity", "conversations"),
        os.path.join(_gemini_wsl, "antigravity-backup", "conversations"),
    ]
    _ALL_BRAIN_DIRS = [
        os.path.join(_gemini_wsl, "antigravity-ide", "brain"),
        os.path.join(_gemini_wsl, "antigravity", "brain"),
        os.path.join(_gemini_wsl, "antigravity-backup", "brain"),
    ]
elif _SYSTEM == "Darwin":  # macOS
    _home = os.path.expanduser("~")
    _support = os.path.join(_home, "Library", "Application Support")

    _DB_CANDIDATES = (
        os.path.join(_support, "Antigravity IDE", "User", "globalStorage", "state.vscdb"),
        os.path.join(_support, "antigravity", "User", "globalStorage", "state.vscdb"),
    )
    DB_PATH = _first_existing(*_DB_CANDIDATES)
    CONVERSATIONS_DIR = _first_existing(
        os.path.join(_home, ".gemini", "antigravity-ide", "conversations"),
        os.path.join(_home, ".gemini", "antigravity", "conversations"),
    )
    BRAIN_DIR = _first_existing(
        os.path.join(_home, ".gemini", "antigravity-ide", "brain"),
        os.path.join(_home, ".gemini", "antigravity", "brain"),
    )
    WORKSPACE_STORAGE_DIR = _first_existing(
        os.path.join(_support, "Antigravity IDE", "User", "workspaceStorage"),
        os.path.join(_support, "antigravity", "User", "workspaceStorage"),
    )
    _gemini_mac = os.path.join(_home, ".gemini")
    _ALL_CONV_DIRS = [
        os.path.join(_gemini_mac, "antigravity-ide", "conversations"),
        os.path.join(_gemini_mac, "antigravity", "conversations"),
        os.path.join(_gemini_mac, "antigravity-backup", "conversations"),
    ]
    _ALL_BRAIN_DIRS = [
        os.path.join(_gemini_mac, "antigravity-ide", "brain"),
        os.path.join(_gemini_mac, "antigravity", "brain"),
        os.path.join(_gemini_mac, "antigravity-backup", "brain"),
    ]
else:  # Linux and other POSIX systems
    _home = os.path.expanduser("~")
    _config = os.path.join(_home, ".config")

    _DB_CANDIDATES = (
        os.path.join(_config, "Antigravity IDE", "User", "globalStorage", "state.vscdb"),
        os.path.join(_config, "Antigravity", "User", "globalStorage", "state.vscdb"),
    )
    DB_PATH = _first_existing(*_DB_CANDIDATES)
    CONVERSATIONS_DIR = _first_existing(
        os.path.join(_home, ".gemini", "antigravity-ide", "conversations"),
        os.path.join(_home, ".gemini", "antigravity", "conversations"),
    )
    BRAIN_DIR = _first_existing(
        os.path.join(_home, ".gemini", "antigravity-ide", "brain"),
        os.path.join(_home, ".gemini", "antigravity", "brain"),
    )
    WORKSPACE_STORAGE_DIR = _first_existing(
        os.path.join(_config, "Antigravity IDE", "User", "workspaceStorage"),
        os.path.join(_config, "Antigravity", "User", "workspaceStorage"),
    )
    _gemini_linux = os.path.join(_home, ".gemini")
    _ALL_CONV_DIRS = [
        os.path.join(_gemini_linux, "antigravity-ide", "conversations"),
        os.path.join(_gemini_linux, "antigravity", "conversations"),
        os.path.join(_gemini_linux, "antigravity-backup", "conversations"),
    ]
    _ALL_BRAIN_DIRS = [
        os.path.join(_gemini_linux, "antigravity-ide", "brain"),
        os.path.join(_gemini_linux, "antigravity", "brain"),
        os.path.join(_gemini_linux, "antigravity-backup", "brain"),
    ]

DB_PATHS = _existing_paths(*_DB_CANDIDATES)
BACKUP_FILENAME = "trajectorySummaries_backup.txt"

def main():
    _enable_ansi_and_colors()
    print(f"{CLR_BOLD}Initializing Antigravity Conversation Recovery Utility...{CLR_RESET}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
