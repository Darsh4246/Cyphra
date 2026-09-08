@echo off
setlocal
cd /d "%~dp0"
where pythonw >nul 2>nul
if %ERRORLEVEL% equ 0 (
    start "" pythonw -m cyphra_gui.main %*
) else (
    start "" python -m cyphra_gui.main %*
)
endlocal
