@echo off
REM NeuroSync launcher (Windows): venv -> dependencies -> models -> app
REM Tip: keep the project in a short path (e.g. C:\Projects\NeuroSync); deep paths can break pip installs.
setlocal
cd /d "%~dp0"
if "%VENV_DIR%"=="" set VENV_DIR=.venv

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [setup] creating virtual environment in %VENV_DIR%
    py -3.12 -m venv "%VENV_DIR%" || python -m venv "%VENV_DIR%" || goto :error
)

"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul
"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
"%VENV_DIR%\Scripts\python.exe" scripts\download_models.py || goto :error

echo [run] NeuroSync on http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/docs)
"%VENV_DIR%\Scripts\python.exe" -m src.api
goto :eof

:error
echo [error] setup failed - see the messages above.
pause
exit /b 1
