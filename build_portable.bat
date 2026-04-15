@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ============================================================
echo   llama.cpp Launcher build
echo ============================================================

set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [1/4] Creating Python virtual environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv "%ROOT%.venv"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo [ERROR] Python was not found. Please install Python 3.10+ and retry.
            pause
            exit /b 1
        )
        python -m venv "%ROOT%.venv"
    )
) else (
    echo [1/4] Virtual environment already exists.
)

if not exist "%VENV_PY%" (
    echo [ERROR] Virtual environment was not created correctly: %VENV_PY%
    pause
    exit /b 1
)

echo [2/4] Installing dependencies...
"%VENV_PY%" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo [3/4] Building executable...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%core\build_portable.ps1" -PythonExe "%VENV_PY%"
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [4/4] Done.
echo.
echo Root executable:
echo   %ROOT%llama launcher exe generated. Please open the project folder and run it.
echo.
pause
