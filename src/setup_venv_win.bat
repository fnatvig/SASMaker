@echo off
setlocal

:: Check if python is available
where python >nul 2>&1
if errorlevel 1 (
    echo Python is not found in PATH. Please install Python 3.10.11 and ensure it's available in the system PATH.
    pause
    exit /b
)

:: Get the version string (e.g., 3.10.11)
for /f "tokens=2 delims= " %%v in ('python --version') do set PYVER=%%v

:: Extract major and minor (3.10) or full version if desired
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set MAJOR=%%a
    set MINOR=%%b
)

if not "%MAJOR%"=="3" (
    echo Python 3.10 is required. Found: %PYVER%
    pause
    exit /b
)

if not "%MINOR%"=="10" (
    echo Python 3.10 is required. Found: %PYVER%
    pause
    exit /b
)

echo Creating virtual environment in "venv"...
python -m venv venv

if exist venv\Scripts\activate.bat (
    echo Virtual environment created successfully.
    echo Activating environment...
    call venv\Scripts\activate.bat

    echo Upgrading pip...
    python -m pip install --upgrade pip

    if exist requirements.txt (
        echo Installing dependencies from requirements.txt...
        pip install -r requirements.txt
    ) else (
        pip install pandapower[all]
    )
) else (
    echo Failed to create virtual environment.
)

pause
