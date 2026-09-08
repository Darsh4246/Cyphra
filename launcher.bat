@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0python\pythonw.exe" (
    start "" "%~dp0python\pythonw.exe" "%~dp0main.py" %*
    goto :eof
)

if exist "%~dp0python-3.14.7-embed-amd64\pythonw.exe" (
    start "" "%~dp0python-3.14.7-embed-amd64\pythonw.exe" "%~dp0main.py" %*
    goto :eof
)

where pythonw >nul 2>nul
if %ERRORLEVEL% equ 0 (
    start "" pythonw "%~dp0main.py" %*
) else (
    start "" python "%~dp0main.py" %*
)
endlocal

