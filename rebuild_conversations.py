#!/usr/bin/env python3
"""
Antigravity Conversation Recovery
=============================
Rebuilds the Antigravity conversation index so all your chat history
appears correctly — sorted by date (newest first) with proper titles.

Fixes:
  - Missing conversations in the sidebar
  - Wrong ordering (not sorted by date)
  - Missing/placeholder titles
  - Workspace assignments stripped or lost
  - Missing timestamps causing sort issues

Usage:
  1. CLOSE Antigravity completely (File > Exit, or kill from Task Manager)
  2. Run this script (or use run.bat on Windows)
  3. REBOOT your PC (full restart, not just app restart)
  4. Open Antigravity — your conversations should appear, sorted by date
 
Requirements: Python 3.7+ (no external packages needed)
License: MIT
"""

# ─── Python Version Guard ────────────────────────────────────────────────────
# If accidentally launched with Python 2 (e.g. `python` points to 2.x on
# legacy systems), automatically re-exec with python3 instead of crashing
# with syntax errors.  If python3 isn't available either, give a clear message.
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

_SYSTEM = platform.system()
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
    Strategy 2: Scan /mnt/c/Users/ for folders that have Antigravity installed.
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


def _find_brain_path(conversation_id):
    """Return the first existing brain folder for this conversation across all locations."""
    for brain_dir in _ALL_BRAIN_DIRS:
        p = os.path.join(brain_dir, conversation_id)
        if os.path.isdir(p):
            return p
    return None


def _collect_all_conversations():
    """
    Merge conversation files from all folders (new, old, backup).
    Supports both .pb (protobuf, legacy) and .db (SQLite, v2.x+) formats.
    Deduplicates by conversation ID — first seen wins (priority: new > old > backup).
    Returns dict: {conversation_id: full_file_path}
    """
    catalog = {}
    for conv_dir in _ALL_CONV_DIRS:
        if not os.path.isdir(conv_dir):
            continue
        try:
            for name in os.listdir(conv_dir):
                # Accept .pb (legacy protobuf) and .db (new SQLite) files
                # Skip SQLite journal files (.db-shm, .db-wal)
                if name.endswith(".pb"):
                    cid = name[:-3]
                elif name.endswith(".db") and not name.endswith((".db-shm", ".db-wal")):
                    cid = name[:-3]
                else:
                    continue
                if cid not in catalog:
                    catalog[cid] = os.path.join(conv_dir, name)
        except Exception:
            pass
    return catalog


# ─── Protobuf Varint Helpers ─────────────────────────────────────────────────

def encode_varint(value):
    """Encode an integer as a protobuf varint."""
    result = b""
    while value > 0x7F:
        result += bytes([(value & 0x7F) | 0x80])
        value >>= 7
    result += bytes([value & 0x7F])
    return result or b'\x00'


def decode_varint(data, pos):
    """Decode a protobuf varint at the given position. Returns (value, new_pos)."""
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result, pos + 1
        shift += 7
        pos += 1
    return result, pos


def skip_protobuf_field(data, pos, wire_type):
    """Skip over a protobuf field value at the given position. Returns new_pos."""
    if wire_type == 0:    # varint
        _, pos = decode_varint(data, pos)
    elif wire_type == 2:  # length-delimited
        length, pos = decode_varint(data, pos)
        pos += length
    elif wire_type == 1:  # 64-bit fixed
        pos += 8
    elif wire_type == 5:  # 32-bit fixed
        pos += 4
    return pos


def strip_field_from_protobuf(data, target_field_number):
    """
    Remove all instances of a specific field from raw protobuf bytes.
    Returns the remaining bytes with the target field stripped out.
    """
    remaining = b""
    pos = 0
    while pos < len(data):
        start_pos = pos
        try:
            tag, pos = decode_varint(data, pos)
        except Exception:
            remaining += data[start_pos:]
            break
        wire_type = tag & 7
        field_num = tag >> 3
        new_pos = skip_protobuf_field(data, pos, wire_type)
        if new_pos == pos and wire_type not in (0, 1, 2, 5):
            # Unknown wire type — keep everything from here
            remaining += data[start_pos:]
            break
        pos = new_pos
        if field_num != target_field_number:
            remaining += data[start_pos:pos]
    return remaining


# ─── Protobuf Write Helpers ──────────────────────────────────────────────────

def encode_length_delimited(field_number, data):
    """Encode a length-delimited protobuf field (wire type 2)."""
    tag = (field_number << 3) | 2
    return encode_varint(tag) + encode_varint(len(data)) + data


def encode_string_field(field_number, string_value):
    """Encode a string as a protobuf field."""
    return encode_length_delimited(field_number, string_value.encode('utf-8'))


# ─── Workspace Helpers ───────────────────────────────────────────────────────

def _is_remote_uri(path_or_uri):
    """Check if a string is already a remote/absolute URI (not a local path)."""
    return path_or_uri.startswith("vscode-remote://") or path_or_uri.startswith("file:///")


def path_to_workspace_uri(folder_path):
    """
    Convert a local folder path to a file:/// URI matching Antigravity's format.
    Passes through remote URIs (vscode-remote://, file:///) unchanged.
    Uses raw paths (no URL-encoding) for clean display in Antigravity's sidebar.
    Example: D:\\Repos\\My Project  →  file:///d:/Repos/My Project
    WSL:     /mnt/c/Users/name/Project → file:///c:/Users/name/Project
    """
    # Pass through URIs that are already in the correct format
    if _is_remote_uri(folder_path):
        return folder_path

    # WSL: convert /mnt/<drive>/... to file:///<drive>:/...
    if _IS_WSL and folder_path.startswith("/mnt/"):
        parts = folder_path.split("/")
        if len(parts) >= 3 and len(parts[2]) == 1:
            drive = parts[2].lower()
            rest = "/".join(parts[3:])
            return f"file:///{drive}:/{rest}"

    p = folder_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:]
    else:
        drive = None
        rest = p

    if drive:
        return f"file:///{drive}:{rest}"
    else:
        return f"file:///{rest.lstrip('/')}"


def build_workspace_field(folder_path):
    """
    Build protobuf field 9 (workspace sub-message) from a filesystem path.
    Sub-message structure:
      sub-field 1 (string) = workspace URI
      sub-field 2 (string) = workspace URI (duplicate)
    Returns raw bytes for one field-9 entry.
    """
    uri = path_to_workspace_uri(folder_path)
    sub_msg = (
        encode_string_field(1, uri)
        + encode_string_field(2, uri)
    )
    return encode_length_delimited(9, sub_msg)


def extract_workspace_hint(inner_blob):
    """
    Try to extract a workspace URI from the protobuf inner blob.
    Scans length-delimited fields for strings matching file:/// or
    vscode-remote:// patterns. Returns the URI string if found, or None.
    """
    if not inner_blob:
        return None
    try:
        pos = 0
        while pos < len(inner_blob):
            tag, pos = decode_varint(inner_blob, pos)
            wire_type = tag & 7
            field_num = tag >> 3
            if wire_type == 2:
                l, pos = decode_varint(inner_blob, pos)
                content = inner_blob[pos:pos + l]
                pos += l
                if field_num > 1:
                    try:
                        text = content.decode("utf-8", errors="strict")
                        if "file:///" in text or "vscode-remote://" in text:
                            return text
                    except Exception:
                        pass
            elif wire_type == 0:
                _, pos = decode_varint(inner_blob, pos)
            elif wire_type == 1:
                pos += 8
            elif wire_type == 5:
                pos += 4
            else:
                break
    except Exception:
        pass
    return None


def load_known_workspace_uris():
    """
    Load all known workspace URIs from Antigravity's workspaceStorage.
    Each subfolder contains a workspace.json with a 'folder' or 'workspace' URI.
    Returns a list of URI strings sorted longest-first for prefix matching.
    """
    uris = []
    if not os.path.isdir(WORKSPACE_STORAGE_DIR):
        return uris
    try:
        for name in os.listdir(WORKSPACE_STORAGE_DIR):
            ws_json = os.path.join(WORKSPACE_STORAGE_DIR, name, "workspace.json")
            if os.path.exists(ws_json):
                try:
                    with open(ws_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    uri = data.get("folder") or data.get("workspace")
                    if uri:
                        uris.append(uri)
                except Exception:
                    pass
    except Exception:
        pass
    # Sort longest first so more-specific paths match before parent paths
    uris.sort(key=len, reverse=True)
    return uris


def _uri_to_local_path(file_uri):
    """
    Convert a file:/// URI to a local filesystem path.
    Handles URL-encoding (e.g. %20 -> space, %3A -> colon).
    On WSL, converts file:///C:/... to /mnt/c/...
    Returns None for non-file URIs.
    """
    if not file_uri.startswith("file:///"):
        return None
    raw = unquote(file_uri[len("file://"):])
    # On Windows, file:///C:/... -> C:/...
    if _SYSTEM == "Windows" and len(raw) >= 3 and raw[0] == '/' and raw[2] == ':':
        raw = raw[1:]  # strip leading /
    # On WSL, file:///C:/... -> /mnt/c/...
    elif _IS_WSL and len(raw) >= 3 and raw[0] == '/' and raw[2] == ':':
        drive = raw[1].lower()
        raw = f"/mnt/{drive}{raw[3:]}"
    return raw


def infer_workspace_from_brain(conversation_id, known_ws_uris=None):
    """
    Scan brain .md files for file:/// and vscode-remote:// paths and infer
    the workspace by matching against known workspace URIs.
    Falls back to a heuristic depth-based approach if no known URIs match.
    Returns a filesystem path string, a remote URI string, or None.
    """
    brain_path = _find_brain_path(conversation_id)
    if not brain_path:
        return None

    # Two separate patterns: local file:/// and remote vscode-remote://
    if _SYSTEM == "Windows":
        local_pattern = re.compile(r"file:///([A-Za-z](?:%3A|:)/[^)\s\"'\]>]+)")
    else:
        local_pattern = re.compile(r"file:///([^)\s\"'\]>]+)")
    remote_pattern = re.compile(r"(vscode-remote://[^)\s\"'\]>]+)")

    # Collect all file URIs found in brain .md files
    found_uris = []     # full file:/// URIs
    found_remote = []   # full vscode-remote:// URIs

    try:
        for name in os.listdir(brain_path):
            if not name.endswith(".md") or name.startswith("."):
                continue
            filepath = os.path.join(brain_path, name)
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(16384)

                for match in remote_pattern.finditer(content):
                    found_remote.append(match.group(1))

                for match in local_pattern.finditer(content):
                    found_uris.append("file:///" + match.group(1))
            except Exception:
                pass
    except Exception:
        return None

    if not found_uris and not found_remote:
        return None

    # ── Strategy 1: Match against known workspace URIs (preferred) ────────
    if known_ws_uris:
        ws_counts = {}
        for file_uri in found_uris:
            normalized = file_uri.replace("%3A", ":").replace("%3a", ":")
            normalized = normalized.replace("%20", " ")
            for ws_uri in known_ws_uris:
                ws_norm = ws_uri.replace("%3A", ":").replace("%3a", ":")
                ws_norm = ws_norm.replace("%20", " ")
                if normalized.startswith(ws_norm + "/") or normalized == ws_norm:
                    ws_counts[ws_uri] = ws_counts.get(ws_uri, 0) + 1
                    break  # matched most-specific (sorted longest-first)

        for remote_uri in found_remote:
            for ws_uri in known_ws_uris:
                if remote_uri.startswith(ws_uri + "/") or remote_uri == ws_uri:
                    ws_counts[ws_uri] = ws_counts.get(ws_uri, 0) + 1
                    break

        if ws_counts:
            best_ws_uri = max(ws_counts, key=ws_counts.get)
            local = _uri_to_local_path(best_ws_uri)
            if local:
                return local
            return best_ws_uri

    # ── Strategy 2: Fallback — heuristic depth-based approach ─────────────
    path_counts = {}
    for file_uri in found_uris:
        raw = file_uri[len("file:///"):]
        raw = raw.replace("%3A", ":").replace("%3a", ":")
        raw = raw.replace("%20", " ")

        # WSL: normalize Windows drive letters in URIs to /mnt/ paths
        if _IS_WSL and len(raw) >= 2 and raw[1] == ':':
            drive = raw[0].lower()
            raw = f"mnt/{drive}/{raw[3:]}"

        parts = raw.replace("\\", "/").split("/")
        # On Windows paths like C:/Users/name/Desktop/Project → 5 segments.
        # On WSL paths like mnt/c/Users/name/Project → 5 segments.
        # On Linux/Mac like home/user/projects/Project → 4 segments + re-add /.
        if _SYSTEM == "Windows":
            depth = 5
        elif _IS_WSL and raw.startswith("mnt/"):
            depth = 5
        else:
            depth = 4
        if len(parts) >= depth:
            ws = "/".join(parts[:depth])
            if _SYSTEM != "Windows" and not ws.startswith("/"):
                ws = "/" + ws
            path_counts[ws] = path_counts.get(ws, 0) + 1

    for remote_uri in found_remote:
        path_counts[remote_uri] = path_counts.get(remote_uri, 0) + 1

    if not path_counts:
        return None

    best = max(path_counts, key=path_counts.get)
    # Remote URIs are returned as-is; local paths get OS-native separators
    if best.startswith("vscode-remote://"):
        return best
    return best.replace("/", os.sep)


# ─── Timestamp Helpers ───────────────────────────────────────────────────────

def build_timestamp_fields(epoch_seconds):
    """
    Build protobuf timestamp fields 3, 7, and 10 from an epoch timestamp.
    Each is a sub-message with: sub-field 1 (varint) = seconds since epoch.
    Returns raw protobuf bytes containing all three fields.
    """
    seconds = int(epoch_seconds)
    ts_inner = encode_varint((1 << 3) | 0) + encode_varint(seconds)
    return (
        encode_length_delimited(3, ts_inner)
        + encode_length_delimited(7, ts_inner)
        + encode_length_delimited(10, ts_inner)
    )


def has_timestamp_fields(inner_blob):
    """Check if the inner blob already contains timestamp fields (3, 7, or 10)."""
    if not inner_blob:
        return False
    try:
        pos = 0
        while pos < len(inner_blob):
            tag, pos = decode_varint(inner_blob, pos)
            fn = tag >> 3
            wt = tag & 7
            if fn in (3, 7, 10):
                return True
            pos = skip_protobuf_field(inner_blob, pos, wt)
    except Exception:
        pass
    return False


# ─── Interactive Workspace Assignment ────────────────────────────────────────

def _prompt_valid_folder(prompt_text):
    """Keep asking for a folder until user gives a valid one or presses Enter."""
    while True:
        raw = input(prompt_text).strip()
        if raw == "":
            return None
        folder = raw.strip('"').strip("'").rstrip("\\/")
        # Accept remote URIs without filesystem validation
        if _is_remote_uri(folder):
            print(f"    + Mapped remote URI: {folder}")
            return folder
        if os.path.isdir(folder):
            print(f"    + Mapped to {folder}")
            return folder
        else:
            print(f"    x Path not found: {folder}")
            print(f"      (Make sure the folder exists. Try again or press Enter to skip)")


def interactive_workspace_assignment(unmapped_entries):
    """
    Show unmapped conversations and let user assign workspace paths.
    unmapped_entries: list of (index, conversation_id, title)
    Returns dict: {conversation_id: folder_path}
    """
    if not unmapped_entries:
        return {}

    print()
    print("  " + f"{CLR_CYAN}=" * 58 + CLR_RESET)
    print(f"  {CLR_BOLD}{CLR_WHITE}WORKSPACE ASSIGNMENT (optional){CLR_RESET}")
    print("  " + f"{CLR_CYAN}=" * 58 + CLR_RESET)
    print(f"  {CLR_BOLD}{CLR_YELLOW}{len(unmapped_entries)}{CLR_RESET} conversation(s) have no workspace.")
    print("  You can assign each to a workspace folder now,")
    print("  or press Enter to skip and leave them unassigned.")
    print()

    assignments = {}
    batch_path = None

    for idx, cid, title in unmapped_entries:
        if batch_path:
            assignments[cid] = batch_path
            print(f"    [{CLR_CYAN}{idx:3d}{CLR_RESET}] {title[:45]}  -> {os.path.basename(batch_path)}")
            continue

        print(f"  [{CLR_CYAN}{idx:3d}{CLR_RESET}] {CLR_BOLD}{title[:55]}{CLR_RESET}")
        while True:
            raw = input(f"    {CLR_BOLD}Workspace path (Enter=skip, 'all'=batch, 'q'=stop): {CLR_RESET}").strip()
            if raw == "":
                print(f"    {CLR_DIM}Skipped.{CLR_RESET}")
                break
            if raw.lower() == "q":
                print(f"    {CLR_YELLOW}Stopped — remaining conversations left unmapped.{CLR_RESET}")
                return assignments
            if raw.lower() == "all":
                folder = _prompt_valid_folder(f"    {CLR_BOLD}Path for ALL remaining (Enter=cancel): {CLR_RESET}")
                if folder is None:
                    continue
                batch_path = folder
                assignments[cid] = folder
                break
            # Normal path entry
            folder = raw.strip('"').strip("'").rstrip("\\/")
            # Accept remote URIs without filesystem validation
            if _is_remote_uri(folder):
                print(f"    + Mapped remote URI: {folder}")
                assignments[cid] = folder
                break
            if os.path.isdir(folder):
                print(f"    + Mapped to {folder}")
                assignments[cid] = folder
                break
            else:
                print(f"    x Path not found: {folder}")
                print(f"      (Try again or press Enter to skip)")

    if assignments:
        print()
        print(f"  + Assigned workspace to {len(assignments)} conversation(s)")
    print()
    return assignments


# ─── Metadata Extraction ─────────────────────────────────────────────────────

def extract_existing_metadata(db_path):
    """
    Read metadata already stored in the database's trajectory data.
    Returns two dicts:
      - titles:      {conversation_id: title}  (real, non-fallback titles)
      - inner_blobs: {conversation_id: raw_inner_protobuf_bytes}
    The inner_blobs contain workspace URIs, timestamps, tool state, etc.
    These are preserved so re-running the script doesn't lose data.
    """
    titles = {}
    inner_blobs = {}
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT value FROM ItemTable "
            "WHERE key='antigravityUnifiedStateSync.trajectorySummaries'"
        )
        row = cur.fetchone()
        conn.close()

        if not row or not row[0]:
            return titles, inner_blobs

        decoded = base64.b64decode(row[0])
        pos = 0

        while pos < len(decoded):
            tag, pos = decode_varint(decoded, pos)
            wire_type = tag & 7

            if wire_type != 2:
                break

            length, pos = decode_varint(decoded, pos)
            entry = decoded[pos:pos + length]
            pos += length

            # Parse each entry for UUID (field 1) and info blob (field 2)
            ep, uid, info_b64 = 0, None, None
            while ep < len(entry):
                t, ep = decode_varint(entry, ep)
                fn, wt = t >> 3, t & 7
                if wt == 2:
                    l, ep = decode_varint(entry, ep)
                    content = entry[ep:ep + l]
                    ep += l
                    if fn == 1:
                        uid = content.decode('utf-8', errors='replace')
                    elif fn == 2:
                        sp = 0
                        _, sp = decode_varint(content, sp)
                        sl, sp = decode_varint(content, sp)
                        info_b64 = content[sp:sp + sl].decode('utf-8', errors='replace')
                elif wt == 0:
                    _, ep = decode_varint(entry, ep)
                else:
                    break

            if uid and info_b64:
                try:
                    raw_inner = base64.b64decode(info_b64)
                    inner_blobs[uid] = raw_inner

                    ip = 0
                    _, ip = decode_varint(raw_inner, ip)
                    il, ip = decode_varint(raw_inner, ip)
                    title = raw_inner[ip:ip + il].decode('utf-8', errors='replace')
                    if not title.startswith("Conversation (") and not title.startswith("Conversation "):
                        titles[uid] = title
                except Exception:
                    pass

    except Exception:
        pass

    return titles, inner_blobs


def extract_existing_metadata_from_paths(db_paths):
    """
    Read metadata from ALL existing Antigravity databases.
    First DB wins for each conversation ID, so metadata is not overwritten
    by a later DB that might have stale data.
    """
    merged_titles = {}
    merged_inner_blobs = {}
    for db_path in db_paths:
        titles, inner_blobs = extract_existing_metadata(db_path)
        for cid, title in titles.items():
            if cid not in merged_titles:
                merged_titles[cid] = title
        for cid, blob in inner_blobs.items():
            if cid not in merged_inner_blobs:
                merged_inner_blobs[cid] = blob
    return merged_titles, merged_inner_blobs


def write_index_to_database(db_path, encoded_value, backup_suffix):
    """Back up and write the rebuilt trajectory index into one state.vscdb."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT value FROM ItemTable "
        "WHERE key='antigravityUnifiedStateSync.trajectorySummaries'"
    )
    row = cur.fetchone()

    backup_name = f"trajectorySummaries_backup_{backup_suffix}.txt" if backup_suffix else BACKUP_FILENAME
    backup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), backup_name)
    if row and row[0]:
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(row[0])

    if row:
        cur.execute(
            "UPDATE ItemTable SET value=? "
            "WHERE key='antigravityUnifiedStateSync.trajectorySummaries'",
            (encoded_value,)
        )
    else:
        cur.execute(
            "INSERT INTO ItemTable (key, value) "
            "VALUES ('antigravityUnifiedStateSync.trajectorySummaries', ?)",
            (encoded_value,)
        )

    conn.commit()
    conn.close()
    return backup_name if row and row[0] else None


def main():
    if "_enable_ansi_and_colors" in globals():
        _enable_ansi_and_colors()
    print("Initializing Antigravity Conversation Recovery Utility...")
    return 0

if __name__ == "__main__":
    sys.exit(main())
