@echo off
REM GhostRead launcher for Windows.
REM
REM   run.bat                     opens a file picker
REM   run.bat "C:\path\book.pdf"  opens that file
REM   drag a PDF onto this file   opens that file
REM
REM On the first run it builds a small virtual environment inside this folder
REM and installs the two dependencies. After that it starts straight away.

setlocal
cd /d "%~dp0"

set PYEXE=.venv\Scripts\python.exe

if not exist "%PYEXE%" (
    echo.
    echo   First run, setting up GhostRead. This takes about a minute.
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

    echo   Setup done.
    echo.
)

"%PYEXE%" -m ghostread %*
if errorlevel 1 (
    echo.
    echo   GhostRead exited with an error. The message above should say why.
    pause
)
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
echo   Could not install PyMuPDF and Pillow. Check your internet connection,
echo   then delete the .venv folder and run this file again.
echo.
pause
goto :eof
