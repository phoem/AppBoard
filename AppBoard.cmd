@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Set up AppBoard's Python environment using the Windows setup in README.md.
    pause
    popd
    exit /b 1
)
start "AppBoard" ".venv\Scripts\pythonw.exe" -B -m appboard %*
popd
