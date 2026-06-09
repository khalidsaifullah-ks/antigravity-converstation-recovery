@echo off
chcp 65001 >nul 2>&1
echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║         Antigravity Conversation Recovery                ║
echo  ║         Fixes missing/unordered conversation history     ║
echo  ╚══════════════════════════════════════════════════════════╝
echo  
echo.
echo  IMPORTANT: Make sure Antigravity is FULLY CLOSED before continuing!
echo.
pause
echo.
python "%~dp0rebuild_conversations.py"
echo.
echo  ────────────────────────────────────────────────────────────
echo.
echo  ★ If this tool helped you, please star the GitHub repo
echo    so other users can find it too!
echo.
echo  ────────────────────────────────────────────────────────────
echo.
pause
