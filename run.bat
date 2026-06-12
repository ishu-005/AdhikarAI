@echo off
REM AdhikarAI — Windows launcher
REM Usage:
REM   run.bat              - Start backend only
REM   run.bat download     - Download acts + ingest + start backend
REM   run.bat frontend     - Start backend + frontend dev server
REM   run.bat full         - Everything

setlocal enabledelayedexpansion

REM Detect Python executable
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo AdhikarAI Launcher
echo.

REM Check if running in the right directory
if not exist "backend\app.py" (
    echo Error: Please run this from the AdhikarAI project root directory
    exit /b 1
)

REM Pass arguments to the Python script
if "%1"=="" (
    %PYTHON% run.py
) else if "%1"=="download" (
    %PYTHON% run.py --download
) else if "%1"=="frontend" (
    %PYTHON% run.py --frontend
) else if "%1"=="full" (
    %PYTHON% run.py --full
) else (
    echo Usage: run.bat [download^|frontend^|full]
    echo.
    echo   download  - Download acts from India Code, ingest, start backend
    echo   frontend  - Start backend and frontend dev server
    echo   full      - Download, ingest, start backend and frontend
    exit /b 1
)
