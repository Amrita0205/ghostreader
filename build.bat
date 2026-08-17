@echo off
REM Rebuild dist\GhostRead.exe from the current source.
REM
REM   build.bat            test, then build
REM   build.bat /fast      skip the tests and just build
REM   build.bat /run       build, then start the new exe
REM
REM Everything the exe needs is set up on the first run, in the same .venv
REM that run.bat uses. Nothing is installed outside this folder.

setlocal
cd /d "%~dp0"

set PYEXE=.venv\Scripts\python.exe
set SKIPTESTS=
set LAUNCH=

:args
if "%~1"=="" goto ready
if /i "%~1"=="/fast" set SKIPTESTS=1
if /i "%~1"=="/run"  set LAUNCH=1
shift
goto args

:ready

REM PyInstaller cannot replace a file Windows is currently executing, and the
REM error it gives for that is a bare permission denied. Say the real reason.
tasklist /fi "imagename eq GhostRead.exe" 2>nul | find /i "GhostRead.exe" >nul
if not errorlevel 1 goto running

if not exist "%PYEXE%" (
    echo.
    echo   No environment yet, creating one. This takes about a minute.
    echo.

    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )

    if not exist "%PYEXE%" goto nopython

    "%PYEXE%" -m pip install --upgrade pip --quiet
    "%PYEXE%" -m pip install -r requirements.txt --quiet
    if errorlevel 1 goto nodeps
)

REM Only the build needs PyInstaller, so run.bat does not install it and a
REM plain checkout will not have it. Add it the first time we build.
"%PYEXE%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo   Installing PyInstaller, one time only.
    "%PYEXE%" -m pip install pyinstaller --quiet
    if errorlevel 1 goto nodeps
)

if defined SKIPTESTS goto build

echo.
echo   Checking the source before freezing it.
echo.
"%PYEXE%" -m tests.test_core
if errorlevel 1 goto failedtests
"%PYEXE%" -m tests.test_gui
if errorlevel 1 goto failedtests

:build
echo.
echo   Building. This takes a minute or so.
echo.

REM --clean throws away the previous analysis. Slower, but without it a
REM stale cache can quietly freeze the old code and the exe looks unchanged.
"%PYEXE%" -m PyInstaller packaging\ghostread.spec --noconfirm --clean
if errorlevel 1 goto failedbuild

if not exist "dist\GhostRead.exe" goto failedbuild

echo.
for %%F in ("dist\GhostRead.exe") do (
    echo   Built dist\GhostRead.exe   %%~zF bytes   %%~tF
)
echo.

if defined LAUNCH start "" "dist\GhostRead.exe"
goto :eof

:running
echo.
echo   GhostRead is open right now, and Windows will not let the running
echo   exe be overwritten. Close it, then run this file again.
echo.
pause
goto :eof

:failedtests
echo.
echo   Tests failed, so nothing was built. The old exe is untouched.
echo.
pause
goto :eof

:failedbuild
echo.
echo   The build failed. The message above should say why.
echo.
pause
goto :eof

:nopython
echo.
echo   Could not find Python. Install it from https://www.python.org/downloads/
echo   and tick "Add python.exe to PATH" plus "tcl/tk and IDLE" during setup.
echo.
pause
goto :eof

:nodeps
echo.
echo   Could not install the build dependencies. Check your internet
echo   connection, then delete the .venv folder and run this file again.
echo.
pause
goto :eof
