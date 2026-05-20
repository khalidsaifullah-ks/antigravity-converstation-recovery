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

def main():
    _enable_ansi_and_colors()
    print(f"{CLR_BOLD}Initializing Antigravity Conversation Recovery Utility...{CLR_RESET}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
