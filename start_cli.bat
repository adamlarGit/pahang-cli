@echo off
setlocal enabledelayedexpansion

echo Verifying prerequisites...
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Git is not installed or not in PATH.
    echo Please install Git from https://git-scm.com/
    pause
    exit /b 1
)

where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] uv is not installed or not in PATH.
    echo Please install uv.
    pause
    exit /b 1
)

echo Checking for updates...
git fetch origin main >nul 2>&1

set BEHIND=0

:: Parse local version
for /f "tokens=2 delims==" %%a in ('findstr "__version__" "src\__init__.py"') do (
    set LOCAL_VER=%%a
)
set LOCAL_VER=!LOCAL_VER: =!
set LOCAL_VER=!LOCAL_VER:"=!

:: Parse remote version
for /f "tokens=2 delims==" %%a in ('git show origin/main:src/__init__.py ^| findstr "__version__"') do (
    set REMOTE_VER=%%a
)
set REMOTE_VER=!REMOTE_VER: =!
set REMOTE_VER=!REMOTE_VER:"=!

for /f %%i in ('git rev-list --count HEAD..origin/main') do set BEHIND=%%i

if !BEHIND! GTR 0 (
    echo.
    echo ===================================================
    echo   An update is available ^(!BEHIND! new commits^).
    echo   Current Version : v!LOCAL_VER!
    echo   Latest Version  : v!REMOTE_VER!
    echo ===================================================
    set /p UPDATE_CHOICE="Do you want to update now? (Y/N): "
    if /I "!UPDATE_CHOICE!"=="Y" (
        echo.
        echo Pulling latest changes...
        git pull origin main
        echo.
        echo Syncing Project Environment Dependencies...
        uv sync --frozen
        echo.
    ) else (
        echo.
        echo Skipping update...
        echo.
    )
) else (
    echo You are on the latest version ^(v!LOCAL_VER!^).
    echo.
)

echo ===================================================
echo   Starting Pahang CLI...
echo ===================================================
uv run --frozen pahang-cli

pause
