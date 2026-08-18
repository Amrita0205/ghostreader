@echo off
REM Rebuild GhostRead.exe from the current source, and update the copy the
REM desktop shortcut actually runs.
REM
REM   build.bat            test, build, update the installed copy
REM   build.bat /fast      skip the tests
REM   build.bat /install   also create the install if there is not one yet
REM   build.bat /noinstall build only, leave the installed copy alone
REM   build.bat /run       start the app when it is done
REM
REM Everything the build needs is set up on the first run, in the same .venv
REM that run.bat uses. Nothing is installed outside this folder and %INSTALLDIR%.

setlocal
cd /d "%~dp0"

set PYEXE=.venv\Scripts\python.exe
set INSTALLDIR=%LOCALAPPDATA%\GhostRead
set SKIPTESTS=
set DOINSTALL=
set NOINSTALL=
set LAUNCH=

:args
if "%~1"=="" goto ready
if /i "%~1"=="/fast"      set SKIPTESTS=1
if /i "%~1"=="/install"   set DOINSTALL=1
if /i "%~1"=="/noinstall" set NOINSTALL=1
if /i "%~1"=="/run"       set LAUNCH=1
shift
goto args

:ready

REM Windows will not overwrite a file it is currently executing, and the error
REM for that is a bare permission denied. This blocks both the build and the
REM install, so check once here rather than failing halfway through.
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

REM The exe people actually run is the installed copy, not this one. The
REM desktop shortcut points there, so a build that stops at dist\ leaves the
REM app behaving exactly as it did before and looking like the change failed.
REM Update an install that already exists, every time. Only create one when
REM asked, so a plain build on someone else's machine stays inside this folder.
set TARGET=dist\GhostRead.exe
if defined NOINSTALL goto done
if exist "%INSTALLDIR%\GhostRead.exe" goto install
if defined DOINSTALL goto install
goto done

:install
if not exist "%INSTALLDIR%" mkdir "%INSTALLDIR%"
copy /y "dist\GhostRead.exe" "%INSTALLDIR%\GhostRead.exe" >nul
if errorlevel 1 goto failedinstall
set TARGET=%INSTALLDIR%\GhostRead.exe
echo   Installed  %INSTALLDIR%\GhostRead.exe

if exist "%USERPROFILE%\Desktop\GhostRead.lnk" goto done
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:USERPROFILE + '\Desktop\GhostRead.lnk'); $s.TargetPath = $env:LOCALAPPDATA + '\GhostRead\GhostRead.exe'; $s.Save()"
if not errorlevel 1 echo   Shortcut   %USERPROFILE%\Desktop\GhostRead.lnk

:done
echo.
if defined LAUNCH start "" "%TARGET%"
goto :eof

:running
echo.
echo   GhostRead is open right now, and Windows will not let a running exe be
echo   overwritten. Close it, then run this file again.
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

:failedinstall
echo.
echo   Built, but could not copy it to %INSTALLDIR%. If GhostRead was opened
echo   while this ran, close it and try again. dist\GhostRead.exe is fine.
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
